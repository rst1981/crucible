from __future__ import annotations

import logging
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.spec import ActorSpec, DesireSpec

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class AgentHydrationError(Exception):
    """
    Raised when from_spec() cannot build a valid BDIAgent from an ActorSpec.
    Wraps the actor name and spec field that caused the failure so the caller
    can surface a meaningful error rather than a raw Python exception.
    """


# ── Belief types ─────────────────────────────────────────────────────────────

@dataclass
class BetaBelief:
    """
    Conjugate prior for probability beliefs (0–1).
    alpha = pseudo-count of "successes", beta = pseudo-count of "failures".
    mean  = alpha / (alpha + beta).

    decay_rate: pulls alpha/beta back toward the uniform prior (1, 1) each tick.
    Set to 1.0 (default) for no decay. 0.99 = slow forgetting.
    Prevents belief calcification after hundreds of ticks.

    maps_to_env_key: the env dict key this belief observes.
    If None, falls back to matching by belief name.
    """
    name:            str
    alpha:           float      = 1.0
    beta:            float      = 1.0
    decay_rate:      float      = 1.0
    maps_to_env_key: str | None = None

    def __post_init__(self) -> None:
        if self.alpha <= 0 or self.beta <= 0:
            raise ValueError(
                f"BetaBelief '{self.name}': alpha and beta must be > 0, "
                f"got alpha={self.alpha}, beta={self.beta}"
            )

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
        If both self.variance and obs_variance are 0 (POINT belief + zero noise),
        the belief is already certain — skip the update rather than divide by zero.
        """
        denom = self.variance + obs_variance
        if denom == 0.0:
            return  # already certain; observation adds nothing
        kalman_gain   = self.variance / denom
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
    For standard scenarios use DefaultBDIAgent — no subclassing required.

    Tick lifecycle — call tick() or orchestrate manually:
        1. decay_beliefs()              — decay toward priors / diffuse variance
        2. observe_environment(env)     — noisy read of env keys
        3. update_beliefs(observations) — Bayesian / Kalman update
        4. decide(env, tick)            — abstract: return list[Action]
        5. (SimRunner applies actions and mutates env)
        6. recharge_capabilities()      — partial capacity recovery  ← NOT in tick()

    Thread safety: all randomness goes through self.rng (local random.Random).
    Never call random.random() or random.gauss() directly — those touch global
    state and break EnsembleRunner's reproducibility guarantee.
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
        self.rng: random.Random = rng or random.Random()
        self._observations: dict[str, float] = {}

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_spec(cls, spec: ActorSpec, rng: random.Random) -> BDIAgent:
        """
        Hydrate a BDIAgent (or subclass) from an ActorSpec.
        SimRunner resolves actor_spec.agent_class via importlib, then calls
        resolved_cls.from_spec(actor_spec, rng).

        Propagates: decay_rate, process_noise, maps_to_env_key, observation_noise_sigma.
        Raises AgentHydrationError on duplicate belief names.

        POINT beliefs become GaussianBelief(mean=value, variance=0.0).
        """
        from core.spec import BeliefDistType

        beliefs: dict[str, BetaBelief | GaussianBelief] = {}
        for bs in spec.beliefs:
            if bs.name in beliefs:
                raise AgentHydrationError(
                    f"Actor '{spec.name}': duplicate belief name '{bs.name}'. "
                    "Each belief must have a unique name."
                )
            if bs.dist_type == BeliefDistType.BETA:
                beliefs[bs.name] = BetaBelief(
                    name=bs.name,
                    alpha=bs.alpha,
                    beta=bs.beta,
                    decay_rate=bs.decay_rate,
                    maps_to_env_key=bs.maps_to_env_key,
                )
            elif bs.dist_type == BeliefDistType.GAUSSIAN:
                beliefs[bs.name] = GaussianBelief(
                    name=bs.name,
                    mean=bs.mean,
                    variance=bs.variance,
                    process_noise=bs.process_noise,
                    maps_to_env_key=bs.maps_to_env_key,
                )
            else:  # POINT
                beliefs[bs.name] = GaussianBelief(
                    name=bs.name,
                    mean=bs.value,
                    variance=0.0,
                    process_noise=bs.process_noise,
                    maps_to_env_key=bs.maps_to_env_key,
                )

        capabilities: dict[str, dict[str, float]] = {}
        for cs in spec.capabilities:
            capabilities[cs.capability_id] = {
                "capacity":           cs.capacity,
                "cost":               cs.cost,
                "recovery_rate":      cs.recovery_rate,
                "cooldown_ticks":     float(cs.cooldown_ticks),
                "current":            cs.capacity,
                "cooldown_remaining": 0.0,
            }

        agent = cls(
            actor_id=spec.actor_id,
            name=spec.name,
            beliefs=beliefs,
            desires=list(spec.desires),
            capabilities=capabilities,
            observation_noise_sigma=spec.observation_noise_sigma,
            rng=rng,
        )
        logger.debug(
            "hydrated agent '%s' (class=%s) with %d beliefs, %d desires, %d capabilities",
            spec.name, cls.__name__, len(beliefs), len(spec.desires), len(capabilities),
        )
        return agent

    # ── Tick coordinator ──────────────────────────────────────────────────────

    def tick(self, env: dict[str, float], tick_num: int) -> list[Action]:
        """
        Run the full per-tick BDI lifecycle steps 1–4 and return intended actions.
        SimRunner calls this for each agent, then applies all actions, then calls
        agent.recharge_capabilities() for all agents.

        recharge_capabilities() is intentionally NOT called here — it must run
        after all agents have acted, not mid-tick.

        Enforced order:
            1. decay_beliefs()
            2. observe_environment(env)
            3. update_beliefs(obs)
            4. decide(env, tick_num)
        """
        self.decay_beliefs()
        obs = self.observe_environment(env)
        self.update_beliefs(obs)
        actions = self.decide(env, tick_num)
        logger.debug(
            "agent '%s' tick %d → %d actions", self.name, tick_num, len(actions)
        )
        return actions

    # ── Decay ─────────────────────────────────────────────────────────────────

    def decay_beliefs(self) -> None:
        """
        Decay all beliefs toward their priors. Called by tick() at start of
        each tick, before observation.
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


# ── DefaultBDIAgent ───────────────────────────────────────────────────────────

class DefaultBDIAgent(BDIAgent):
    """
    Ready-to-use utility-maximizing agent. Covers most standard scenarios —
    no subclassing required.

    decide(): for each available capability (in dict order), builds an action
    that pushes each owned env key in the direction that increases expected
    utility. Returns a single action from the first usable capability, or []
    if no capability is available or no desires map to owned keys.

    owned_env_keys: env keys this actor can directly influence. Set automatically
    by from_spec() from ActorSpec.initial_env_contributions.

    push_delta: magnitude of each env key change per action (default 0.05 = 5%).
    """

    def __init__(
        self,
        *args: Any,
        owned_env_keys: list[str] | None = None,
        push_delta: float = 0.05,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.owned_env_keys: list[str] = owned_env_keys or []
        self.push_delta = push_delta

    def decide(self, env: dict[str, float], tick: int) -> list[Action]:
        """
        Build one action per tick: push owned env keys toward desired state
        using the first available capability.

        Decision logic:
            1. Index desires by target_env_key ∩ owned_env_keys
            2. For each available capability, build params dict:
               {key: push_delta × sign(net_desire_direction)}
            3. Return action if params non-empty, else continue to next capability
            4. Return [] if no capability can produce a useful action
        """
        desire_index: dict[str, float] = {}
        for desire in self.desires:
            key = desire.target_env_key
            if key in self.owned_env_keys:
                desire_index[key] = (
                    desire_index.get(key, 0.0) + desire.direction * desire.weight
                )

        if not desire_index:
            return []

        for cap_id in self.capabilities:
            if not self.can_act(cap_id):
                continue
            params = {
                key: self.push_delta * (1.0 if net > 0 else -1.0)
                for key, net in desire_index.items()
                if net != 0.0
            }
            if not params:
                continue
            return [Action(
                action_id=f"{self.actor_id}__{cap_id}__t{tick}",
                target="environment",
                capability_id=cap_id,
                parameters=params,
            )]

        return []

    @classmethod
    def from_spec(cls, spec: ActorSpec, rng: random.Random) -> DefaultBDIAgent:
        """
        Hydrate from ActorSpec. Sets owned_env_keys from
        spec.initial_env_contributions automatically.
        """
        agent: DefaultBDIAgent = super().from_spec(spec, rng)  # type: ignore[assignment]
        agent.owned_env_keys = list(spec.initial_env_contributions.keys())
        return agent
