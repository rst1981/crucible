from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Belief types ─────────────────────────────────────────────────────────────

@dataclass
class BetaBelief:
    """
    Conjugate prior for probability beliefs (0–1).
    alpha = pseudo-count of "successes", beta = pseudo-count of "failures".
    mean = alpha / (alpha + beta).
    """
    name:  str
    alpha: float = 1.0
    beta:  float = 1.0

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

    def sample(self, rng: random.Random) -> float:
        """Draw a sample from the Beta distribution."""
        return rng.betavariate(self.alpha, self.beta)


@dataclass
class GaussianBelief:
    """
    Kalman-style belief for continuous quantities.
    mean: current estimate. variance: uncertainty.
    """
    name:     str
    mean:     float = 0.0
    variance: float = 1.0

    def update(self, observed: float, obs_variance: float = 0.1) -> None:
        """
        Kalman filter update step.
        obs_variance: noise in the observation.
        """
        kalman_gain = self.variance / (self.variance + obs_variance)
        self.mean     = self.mean + kalman_gain * (observed - self.mean)
        self.variance = (1 - kalman_gain) * self.variance

    def sample(self, rng: random.Random) -> float:
        return rng.gauss(self.mean, math.sqrt(max(0.0, self.variance)))


# ── Actions ───────────────────────────────────────────────────────────────────

@dataclass
class Action:
    action_id: str
    # target actor_id, env key, or "environment"
    target:    str
    # signed intensity in [-1, 1]: how strongly to push the target
    intensity: float
    # capability_id required to execute this action (None = no capability required)
    capability_id: str | None = None
    # env key mutations: {key: delta} — applied by SimRunner after all decide() calls
    parameters:  dict[str, float] = field(default_factory=dict)
    description: str              = ""


# ── BDIAgent base ─────────────────────────────────────────────────────────────

class BDIAgent(ABC):
    """
    Abstract BDI agent. Subclass and implement decide().

    Lifecycle per tick (called by SimRunner):
        1. observe_environment(env)     — noisy read of env keys
        2. update_beliefs(observations) — Bayesian / Kalman update
        3. decide(env, tick)            — abstract: return list[Action]
        4. (SimRunner resolves actions and mutates env)
        5. recharge_capabilities()      — partial capacity recovery

    Thread safety: all randomness must go through self.rng (a local
    random.Random instance). Never call random.random() or random.gauss()
    directly — those touch global state and break EnsembleRunner.
    """

    def __init__(
        self,
        actor_id: str,
        name:     str,
        beliefs:      dict[str, BetaBelief | GaussianBelief] | None = None,
        desires:      list[dict[str, Any]]                   | None = None,
        capabilities: dict[str, dict[str, float]]            | None = None,
        observation_noise_sigma: float         = 0.02,
        rng: random.Random | None              = None,
    ) -> None:
        self.actor_id = actor_id
        self.name     = name
        self.beliefs:      dict[str, BetaBelief | GaussianBelief] = beliefs or {}
        self.desires:      list[dict[str, Any]]                   = desires or []
        # capabilities: {capability_id: {capacity, cost, recovery_rate,
        #                                cooldown_ticks, current, cooldown_remaining}}
        self.capabilities: dict[str, dict[str, float]] = capabilities or {}
        self.observation_noise_sigma = observation_noise_sigma
        # Injected RNG — local instance, thread-safe for EnsembleRunner
        self.rng: random.Random = rng or random.Random()
        # Last tick's observations (raw, noisy)
        self._observations: dict[str, float] = {}

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
        Update beliefs from observations. Override for custom update logic.
        Default: update any belief whose name matches an observation key.
        """
        obs = observations or self._observations
        for belief_name, belief in self.beliefs.items():
            if belief_name in obs:
                if isinstance(belief, BetaBelief):
                    belief.update(obs[belief_name])
                elif isinstance(belief, GaussianBelief):
                    belief.update(
                        obs[belief_name],
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
            key       = desire.get("target_env_key", "")
            direction = desire.get("direction", 1.0)
            weight    = desire.get("weight", 1.0)
            value     = env.get(key, 0.0)
            total    += weight * direction * value
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
