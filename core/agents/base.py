from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.spec import ActorSpec, DesireSpec


# ── Belief types ─────────────────────────────────────────────────────────────

@dataclass
class BetaBelief:
    """
    Conjugate prior for probability beliefs (0–1).
    alpha = pseudo-count of "successes", beta = pseudo-count of "failures".
    mean  = alpha / (alpha + beta).

    decay_rate: pulls alpha/beta back toward the uniform prior (1, 1) each tick.
    Set to 1.0 (default) for no decay. 0.99 = slow forgetting.
    Prevents belief calcification: without decay, after hundreds of ticks a
    new observation barely moves the mean.

    maps_to_env_key: the env dict key this belief observes.
    If None, falls back to matching by belief name.
    """
    name:            str
    alpha:           float      = 1.0
    beta:            float      = 1.0
    decay_rate:      float      = 1.0
    maps_to_env_key: str | None = None

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        a, b = self.alpha, self.beta
        n = a + b
        return (a * b) / (n * n * (n + 1))

    def update(
        self,
        observed: float,
        precision: float = 1.0,
        bias: float = 0.0,
    ) -> None:
        """
        Bayesian update given an observation in [0, 1].
        precision: strength of this observation (effective sample size).
        bias: systematic over/under-estimation (e.g. adversarial perception).
        """
        adjusted = max(0.0, min(1.0, observed + bias))
        self.alpha += precision * adjusted
        self.beta  += precision * (1.0 - adjusted)

    def decay(self) -> None:
        """
        Pull alpha and beta back toward the uniform prior (1, 1).
        Call once per tick before update_beliefs(). No-op if decay_rate == 1.0.
        """
        if self.decay_rate < 1.0:
            self.alpha = 1.0 + (self.alpha - 1.0) * self.decay_rate
            self.beta  = 1.0 + (self.beta  - 1.0) * self.decay_rate

    def sample(self, rng: random.Random) -> float:
        """Draw a sample from the Beta distribution."""
        return rng.betavariate(self.alpha, self.beta)


@dataclass
class GaussianBelief:
    """
    Kalman-style belief for continuous quantities.
    mean: current estimate. variance: uncertainty.

    process_noise: added to variance each tick before the Kalman update.
    Models confidence degrading without fresh observations. 0.0 (default) = no diffusion.

    maps_to_env_key: the env dict key this belief observes.
    If None, falls back to matching by belief name.
    """
    name:            str
    mean:            float      = 0.0
    variance:        float      = 1.0
    process_noise:   float      = 0.0
    maps_to_env_key: str | None = None

    def update(self, observed: float, obs_variance: float = 0.1) -> None:
        """
        Kalman filter update step.
        obs_variance: noise in the observation.
        """
        kalman_gain   = self.variance / (self.variance + obs_variance)
        self.mean     = self.mean + kalman_gain * (observed - self.mean)
        self.variance = (1 - kalman_gain) * self.variance

    def diffuse(self) -> None:
        """
        Add process noise to variance. Call once per tick before update_beliefs().
        Prevents variance collapsing to zero, keeping beliefs open to revision.
        No-op if process_noise == 0.0.
        """
        self.variance += self.process_noise

    def sample(self, rng: random.Random) -> float:
        return rng.gauss(self.mean, math.sqrt(max(0.0, self.variance)))


# ── Actions ───────────────────────────────────────────────────────────────────

@dataclass
class Action:
    """
    An intent to change the world, returned by decide().

    target:        actor_id, env key, or "environment"
    capability_id: which capability this consumes (None = free action)
    parameters:    concrete env key deltas: {"strait__tension": +0.05}
    duration:      ticks to hold this action active (SimRunner re-applies each tick)
    """
    action_id:     str
    target:        str
    capability_id: str | None       = None
    parameters:    dict[str, float] = field(default_factory=dict)
    duration:      int              = 1
    description:   str              = ""


# ── BDIAgent base ─────────────────────────────────────────────────────────────

class BDIAgent(ABC):
    """
    Abstract BDI agent. Subclass and implement decide().

    Lifecycle per tick (called by SimRunner):
        1. decay_beliefs()              — decay toward priors / diffuse variance
        2. observe_environment(env)     — noisy read of env keys
        3. update_beliefs(observations) — Bayesian / Kalman update
        4. decide(env, tick)            — abstract: return list[Action]
        5. (SimRunner resolves actions and mutates env)
        6. recharge_capabilities()      — partial capacity recovery

    Thread safety: all randomness must go through self.rng (a local
    random.Random instance). Never call random.random() or random.gauss()
    directly — those touch global state and break EnsembleRunner.
    """

    def __init__(
        self,
        actor_id:    str,
        name:        str,
        beliefs:      dict[str, BetaBelief | GaussianBelief] | None = None,
        desires:      list[DesireSpec]                        | None = None,
        capabilities: dict[str, dict[str, float]]             | None = None,
        observation_noise_sigma: float    = 0.02,
        rng: random.Random | None         = None,
    ) -> None:
        self.actor_id = actor_id
        self.name     = name
        self.beliefs:      dict[str, BetaBelief | GaussianBelief] = beliefs or {}
        self.desires:      list[DesireSpec]                       = desires or []
        # capabilities: {capability_id: {capacity, cost, recovery_rate,
        #                                cooldown_ticks, current, cooldown_remaining}}
        self.capabilities: dict[str, dict[str, float]] = capabilities or {}
        self.observation_noise_sigma = observation_noise_sigma
        # Injected RNG — local instance, thread-safe for EnsembleRunner
        self.rng: random.Random = rng or random.Random()
        # Last tick's observations (raw, noisy)
        self._observations: dict[str, float] = {}

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_spec(cls, spec: ActorSpec, rng: random.Random) -> BDIAgent:
        """
        Hydrate a BDIAgent (or subclass) from an ActorSpec.
        SimRunner calls cls.from_spec(actor_spec, rng) where cls is resolved
        from actor_spec.agent_class via importlib.

        POINT beliefs become GaussianBelief(mean=value, variance=0.0) —
        mathematically a Dirac delta: known value, no uncertainty.
        """
        from core.spec import BeliefDistType

        beliefs: dict[str, BetaBelief | GaussianBelief] = {}
        for bs in spec.beliefs:
            if bs.dist_type == BeliefDistType.BETA:
                beliefs[bs.name] = BetaBelief(
                    name=bs.name,
                    alpha=bs.alpha,
                    beta=bs.beta,
                    maps_to_env_key=bs.maps_to_env_key,
                )
            elif bs.dist_type == BeliefDistType.GAUSSIAN:
                beliefs[bs.name] = GaussianBelief(
                    name=bs.name,
                    mean=bs.mean,
                    variance=bs.variance,
                    maps_to_env_key=bs.maps_to_env_key,
                )
            else:  # POINT
                beliefs[bs.name] = GaussianBelief(
                    name=bs.name,
                    mean=bs.value,
                    variance=0.0,
                    maps_to_env_key=bs.maps_to_env_key,
                )

        capabilities: dict[str, dict[str, float]] = {}
        for cs in spec.capabilities:
            capabilities[cs.capability_id] = {
                "capacity":           cs.capacity,
                "cost":               cs.cost,
                "recovery_rate":      cs.recovery_rate,
                "cooldown_ticks":     float(cs.cooldown_ticks),
                "current":            cs.capacity,   # start at full capacity
                "cooldown_remaining": 0.0,
            }

        return cls(
            actor_id=spec.actor_id,
            name=spec.name,
            beliefs=beliefs,
            desires=list(spec.desires),
            capabilities=capabilities,
            rng=rng,
        )

    # ── Decay ─────────────────────────────────────────────────────────────────

    def decay_beliefs(self) -> None:
        """
        Decay all beliefs toward their priors. Called by SimRunner at the
        start of each tick, before observation.

        BetaBelief:    pulls alpha/beta back toward uniform (no-op if decay_rate=1.0).
        GaussianBelief: adds process_noise to variance (no-op if process_noise=0.0).
        """
        for belief in self.beliefs.values():
            if isinstance(belief, BetaBelief):
                belief.decay()
            elif isinstance(belief, GaussianBelief):
                belief.diffuse()

    # ── Observation ───────────────────────────────────────────────────────────

    def observe_environment(self, env: dict[str, float]) -> dict[str, float]:
        """
        Read environment with Gaussian noise.
        Stores result in self._observations and returns it.
        Clamps to [0.0, 1.0] — env values are normalized.
        """
        obs: dict[str, float] = {}
        for key, value in env.items():
            noise = self.rng.gauss(0.0, self.observation_noise_sigma)
            obs[key] = max(0.0, min(1.0, value + noise))
        self._observations = obs
        return obs

    # ── Belief update ─────────────────────────────────────────────────────────

    def update_beliefs(self, observations: dict[str, float] | None = None) -> None:
        """
        Update beliefs from observations.
        Lookup key = belief.maps_to_env_key if set, else belief name.
        Override for custom update logic.
        """
        obs = observations or self._observations
        for belief_name, belief in self.beliefs.items():
            lookup_key = belief.maps_to_env_key or belief_name
            if lookup_key in obs:
                if isinstance(belief, BetaBelief):
                    belief.update(obs[lookup_key])
                elif isinstance(belief, GaussianBelief):
                    belief.update(
                        obs[lookup_key],
                        obs_variance=self.observation_noise_sigma ** 2,
                    )

    # ── Decision ──────────────────────────────────────────────────────────────

    @abstractmethod
    def decide(self, env: dict[str, float], tick: int) -> list[Action]:
        """
        Core BDI decision loop. Return a list of Actions to attempt.
        SimRunner will filter by can_act() before applying.
        Use self.rng for any randomness — never the global random module.
        """
        ...

    # ── Utility ───────────────────────────────────────────────────────────────

    def expected_utility(self, env: dict[str, float]) -> float:
        """
        Compute expected utility across all desires.
        Weighted sum of (direction × current_value) per desire.
        """
        total = 0.0
        for desire in self.desires:
            value  = env.get(desire.target_env_key, 0.0)
            total += desire.weight * desire.direction * value
        return total

    # ── Capability management ─────────────────────────────────────────────────

    def can_act(self, capability_id: str) -> bool:
        """True if the capability exists, has enough capacity, and is off cooldown."""
        if capability_id not in self.capabilities:
            return False
        cap = self.capabilities[capability_id]
        return (
            cap.get("current", 0.0) >= cap.get("cost", 0.0)
            and cap.get("cooldown_remaining", 0) <= 0
        )

    def expend_capacity(self, capability_id: str) -> bool:
        """Consume capacity and start cooldown. Returns False if cannot act."""
        if not self.can_act(capability_id):
            return False
        cap = self.capabilities[capability_id]
        cap["current"]            = cap.get("current", 0.0) - cap.get("cost", 0.0)
        cap["cooldown_remaining"] = cap.get("cooldown_ticks", 0)
        return True

    def recharge_capabilities(self) -> None:
        """Called by SimRunner at end of each tick to recover capacity."""
        for cap in self.capabilities.values():
            max_capacity = cap.get("capacity", 1.0)
            recovery     = cap.get("recovery_rate", 0.05)
            cap["current"] = min(max_capacity, cap.get("current", 0.0) + recovery)
            if cap.get("cooldown_remaining", 0) > 0:
                cap["cooldown_remaining"] -= 1

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return serializable state for snapshot storage."""
        return {
            "actor_id": self.actor_id,
            "name":     self.name,
            "beliefs": {
                k: (
                    {"mean": b.mean, "variance": b.variance}
                    if isinstance(b, GaussianBelief)
                    else {"mean": b.mean, "alpha": b.alpha, "beta": b.beta}
                )
                for k, b in self.beliefs.items()
            },
            "capabilities": {
                k: dict(cap)
                for k, cap in self.capabilities.items()
            },
        }
