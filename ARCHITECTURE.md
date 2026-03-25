# Crucible — Architecture

> Interface designs for the four core engine modules.
> These define the contracts that all scenarios and extensions must satisfy.

---

## Implementation Status

| Module | File | Status | Tests |
|--------|------|--------|-------|
| SimSpec | `core/spec.py` | ✅ Implemented | 57 passing |
| BDI Agents | `core/agents/base.py` | ✅ Implemented | 131 passing |
| Theory base + registry | `core/theories/base.py`, `__init__.py` | ✅ Implemented | 32 passing |
| Richardson Arms Race | `core/theories/richardson_arms_race.py` | ✅ Implemented | 30 passing |
| SimRunner | `core/sim_runner.py` | 🔲 Next | — |
| Remaining theories | Fearon, Wittman-Zartman, Keynesian, Porter | 🔲 Pending | — |

---

## Overview

```
SimSpec (data contract)
    ↓
SimRunner.setup()
    ├── builds BDIAgent instances from ActorSpec
    └── initializes TheoryBase instances from TheoryRef list
            ↓
SimRunner.run() — tick loop
    ├── apply external shocks
    ├── agents observe environment
    ├── agents update beliefs
    ├── agents decide → list[Action]
    ├── resolve actions → environment mutations
    ├── theory updates → environment mutations
    ├── record metrics
    └── trigger snapshots
```

---

## 1. `core/spec.py` — SimSpec

The central data contract. Output of the Scoping Agent, input to SimRunner.
JSON-serializable, fully reproducible, Pydantic v2.

```python
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Belief distribution types ──────────────────────────────────────────────

class BeliefDistType(str, Enum):
    BETA = "beta"          # probability beliefs (0–1), e.g. "P(actor cooperates)"
    GAUSSIAN = "gaussian"  # continuous beliefs, e.g. "estimated GDP growth"
    POINT = "point"        # known value, no uncertainty


class BeliefSpec(BaseModel):
    belief_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    dist_type: BeliefDistType = BeliefDistType.BETA
    # BETA: initial alpha and beta (both > 0)
    alpha: float = 1.0
    beta: float = 1.0
    # GAUSSIAN: initial mean and variance
    mean: float = 0.0
    variance: float = 1.0
    # POINT: fixed value
    value: float = 0.0
    # which env key this belief tracks (if different from belief name)
    maps_to_env_key: str | None = None
    # runtime dynamics — propagated to BetaBelief.decay_rate / GaussianBelief.process_noise
    decay_rate: float = 1.0    # BETA: pull toward uniform per tick (1.0 = no decay)
    process_noise: float = 0.0  # GAUSSIAN: variance added per tick (0.0 = no diffusion)


# ── Desires / objectives ───────────────────────────────────────────────────

class DesireSpec(BaseModel):
    desire_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    # environment key this desire targets
    target_env_key: str
    # direction: +1 = maximize, -1 = minimize
    direction: float = 1.0
    # salience weight (0–1) — how much this desire drives behavior
    weight: float = 1.0


# ── Capabilities ───────────────────────────────────────────────────────────

class CapabilitySpec(BaseModel):
    capability_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    # max capacity units
    capacity: float = 1.0
    # units consumed per use
    cost: float = 0.1
    # recovery rate per tick
    recovery_rate: float = 0.05
    # cooldown ticks after use
    cooldown_ticks: int = 0


# ── Actors ─────────────────────────────────────────────────────────────────

class ActorSpec(BaseModel):
    actor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    # fully-qualified agent class, e.g. "scenarios.hormuz.agents.IranAgent"
    agent_class: str = "core.agents.base.BDIAgent"
    beliefs: list[BeliefSpec] = Field(default_factory=list)
    desires: list[DesireSpec] = Field(default_factory=list)
    capabilities: list[CapabilitySpec] = Field(default_factory=list)
    # initial environment keys this actor owns
    # e.g. {"iran__military_readiness": 0.7, "iran__oil_revenue": 0.4}
    initial_env_contributions: dict[str, float] = Field(default_factory=dict)
    # per-actor observation noise — overrides UncertaintySpec.observation_noise_sigma
    observation_noise_sigma: float = 0.02
    # arbitrary scenario-specific metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Timeframe ──────────────────────────────────────────────────────────────

class TimeframeSpec(BaseModel):
    total_ticks: int = 365
    tick_unit: str = "day"   # "hour", "day", "week", "month", "quarter", "year"
    # real-world anchor date (ISO 8601), optional
    start_date: str | None = None


# ── Uncertainty ────────────────────────────────────────────────────────────

class UncertaintySpec(BaseModel):
    # global observation noise applied to all env readings by agents
    observation_noise_sigma: float = 0.02
    # probability of an external shock per tick (0–1)
    shock_probability: float = 0.01
    # max magnitude of a random shock to any single env key
    shock_magnitude: float = 0.1
    # optional named shocks: {tick: {env_key: delta}}
    scheduled_shocks: dict[int, dict[str, float]] = Field(default_factory=dict)


# ── Outcome metrics ────────────────────────────────────────────────────────

class OutcomeMetricSpec(BaseModel):
    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    # environment key to track
    env_key: str
    # optional threshold that triggers a named snapshot when crossed
    snapshot_threshold: float | None = None
    snapshot_direction: float = 1.0  # +1 = above threshold, -1 = below


# ── Research sources ───────────────────────────────────────────────────────

class ResearchSourceSpec(BaseModel):
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str  # "arxiv", "ssrn", "fred", "world_bank", "news"
    query: str
    # calibration target: which env key this source informs
    calibrates: str | None = None
    # raw data snapshot (filled by research pipeline)
    data_snapshot: dict[str, Any] = Field(default_factory=dict)


# ── Theory references ──────────────────────────────────────────────────────

class TheoryRef(BaseModel):
    theory_id: str   # matches registry key, e.g. "richardson_arms_race"
    priority: int = 0  # lower = runs first in tick loop
    parameters: dict[str, float] = Field(default_factory=dict)


# ── SimSpec (root) ─────────────────────────────────────────────────────────

class SimSpec(BaseModel):
    spec_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    domain: str = ""  # "geopolitics", "market", "macro", etc.

    actors: list[ActorSpec] = Field(default_factory=list)
    theories: list[TheoryRef] = Field(default_factory=list)
    timeframe: TimeframeSpec = Field(default_factory=TimeframeSpec)
    uncertainty: UncertaintySpec = Field(default_factory=UncertaintySpec)
    metrics: list[OutcomeMetricSpec] = Field(default_factory=list)
    research_sources: list[ResearchSourceSpec] = Field(default_factory=list)

    # global environment seed values (all floats — no nested objects)
    # key convention: "{theory_id}__{var}", "{actor_id}__{var}", "global__{var}"
    initial_environment: dict[str, float] = Field(default_factory=dict)

    # arbitrary metadata for the scoping agent to attach
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def actor_ids_unique(self) -> "SimSpec":
        ids = [a.actor_id for a in self.actors]
        if len(ids) != len(set(ids)):
            raise ValueError("actor_ids must be unique")
        return self

    @model_validator(mode="after")
    def metric_env_keys_exist(self) -> "SimSpec":
        env_keys = set(self.initial_environment.keys())
        for metric in self.metrics:
            if metric.env_key not in env_keys:
                raise ValueError(
                    f"OutcomeMetric '{metric.name}' references env_key "
                    f"'{metric.env_key}' which is not in initial_environment"
                )
        return self

    def display_env(self, normalized: dict[str, float]) -> dict[str, Any]:
        """Convert normalized env to display values. Called at API/report layer only."""
        index = {s.key: s for s in self.env_key_specs}
        out: dict[str, Any] = {}
        for k, v in normalized.items():
            spec = index.get(k)
            if spec:
                out[k] = {"normalized": v, "display": v * spec.scale,
                          "unit": spec.unit, "display_name": spec.display_name or k}
            else:
                out[k] = {"normalized": v, "display": v, "unit": "", "display_name": k}
        return out


# ── Display annotations for env keys ───────────────────────────────────────

class EnvKeySpec(BaseModel):
    """Display metadata for a normalized env key. Engine stays in [0, 1]."""
    key:          str
    scale:        float = 1.0    # multiply normalized to get display value
    unit:         str   = ""     # "USD", "billion USD", "% of GDP", "index"
    display_name: str   = ""     # human-readable label
    log_scale:    bool  = False


# ── Versioning helpers ──────────────────────────────────────────────────────

@dataclass
class SpecDiff:
    """One changed field between two SimSpec versions."""
    field_path: str
    old_value:  Any
    new_value:  Any


def diff_simspecs(v1: SimSpec, v2: SimSpec) -> list[SpecDiff]: ...
    # Diffs: initial_environment (per-key), theories (added/removed/params),
    # timeframe (field-level), actors (added/removed by actor_id)

def branch_simspec(base: SimSpec, branch_name: str, change_reason: str = "") -> SimSpec: ...
    # Returns new SimSpec with new spec_id, updated name/description.
    # Parent relationship stored in DB (sim_specs.parent_spec_id), not on SimSpec.
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| `dict[str, float]` environment (no nested objects) | Theories and agents read/write floats by key. Simple, fast, serializable. |
| UUIDs as strings | JSON-serializable without custom encoders. |
| `agent_class` as dotted path string | SimRunner imports dynamically — no coupling between spec and implementation. |
| `initial_env_contributions` on ActorSpec | Actor-owned keys are set at spec time; SimRunner merges them into the global env at setup. |
| `TheoryRef.priority` | Theories with lower priority run first within a tick. Prevents order-dependence surprises. |
| `maps_to_env_key` on BeliefSpec | Decouples belief name from env key — actor can name a belief "adversary strength" while tracking `iran__military_readiness`. |
| `decay_rate` / `process_noise` on BeliefSpec | Spec fully describes belief dynamics. Without these, `from_spec()` would silently drop all runtime configuration. |
| `observation_noise_sigma` on ActorSpec | Per-actor noise models intelligence differences: a well-resourced actor sees more clearly. Overrides UncertaintySpec global. |
| `EnvKeySpec` + `display_env()` | Engine always operates in [0, 1]. Display translation (scale, unit, label) is API/report layer only. |
| `SpecDiff` + `branch_simspec()` | Version DAG support: branch a spec for scenario variants, diff for changelogs. Parent stored in DB, not on the spec. |

---

## 2. `core/agents/base.py` — BDIAgent

BDI = Belief-Desire-Intention. Beliefs are probabilistic. Decisions derive from expected utility over desires.

### Key types

```python
class AgentHydrationError(Exception):
    """Raised when from_spec() cannot build a valid BDIAgent from an ActorSpec.
    Specific causes: duplicate belief names in the spec."""


@dataclass
class BetaBelief:
    """Conjugate prior for probability beliefs (0–1)."""
    name: str
    alpha: float = 1.0           # pseudo-count of "successes" (> 0, validated)
    beta: float = 1.0            # pseudo-count of "failures"  (> 0, validated)
    decay_rate: float = 1.0      # < 1.0 pulls toward uniform prior each tick
    maps_to_env_key: str | None = None  # env key to read; falls back to name

    # __post_init__ validates alpha > 0 and beta > 0 (raises ValueError)
    # .mean  → alpha / (alpha + beta)
    # .decay()  → pulls (alpha-1) and (beta-1) toward 0 by decay_rate
    # .update(observed, precision, bias) → Bayesian update
    # .sample(rng)  → rng.betavariate(alpha, beta)  ← thread-safe RNG


@dataclass
class GaussianBelief:
    """Kalman-filter belief for continuous quantities."""
    name: str
    mean: float = 0.0
    variance: float = 1.0
    process_noise: float = 0.0   # variance added per tick (diffusion)
    maps_to_env_key: str | None = None

    # .update(observed, obs_variance) → Kalman gain step
    #   Guard: if variance + obs_variance == 0.0, return early (no crash)
    # .diffuse() → variance += process_noise
    # .sample(rng) → rng.gauss(mean, sqrt(variance))


@dataclass
class Action:
    action_id: str
    target: str                          # actor_id, env key, or "environment"
    capability_id: str | None = None
    parameters: dict[str, float] = ...  # {env_key: delta} applied by SimRunner
    duration: int = 1
```

### BDIAgent lifecycle

```
Tick lifecycle (enforced by tick() coordinator):
    1. decay_beliefs()           — pull Beta beliefs toward uniform; diffuse Gaussian variance
    2. observe_environment(env)  — Gaussian noise read of all env keys
    3. update_beliefs(obs)       — Bayesian / Kalman update; uses maps_to_env_key
    4. decide(env, tick)         — abstract: return list[Action]
    NOTE: recharge_capabilities() is NOT called here — SimRunner's job
```

```python
class BDIAgent(ABC):
    def __init__(self, actor_id, name, beliefs, desires, capabilities,
                 observation_noise_sigma, rng: random.Random): ...
        # rng is a local random.Random instance — never uses global random state

    def tick(self, env, tick_num) -> list[Action]:
        """Coordinator: enforces lifecycle steps 1–4 in order."""
        self.decay_beliefs()
        obs = self.observe_environment(env)
        self.update_beliefs(obs)
        return self.decide(env, tick_num)

    @classmethod
    def from_spec(cls, spec: ActorSpec, rng: random.Random) -> "BDIAgent":
        """
        Canonical hydration path from ActorSpec.
        Propagates: decay_rate, process_noise, maps_to_env_key, observation_noise_sigma.
        Raises AgentHydrationError on duplicate belief names in the spec.
        """

    @abstractmethod
    def decide(self, env, tick) -> list[Action]: ...

    def expected_utility(self, env) -> float:
        """Weighted sum of (direction × env_value) across all DesireSpec desires."""

    # Capability management: can_act(), expend_capacity(), recharge_capabilities()
    # Snapshot: get_state_snapshot() → serializable dict


class DefaultBDIAgent(BDIAgent):
    """
    Utility-maximizing concrete agent. Covers ~80% of standard scenarios.

    decide(): for each owned env key, if desired direction is unsatisfied,
    use first available capability to push it. Returns one Action per key.

    from_spec(): calls super().from_spec() then sets
        agent.owned_env_keys = list(spec.initial_env_contributions.keys())
    """
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| `BetaBelief` for probabilities | Conjugate prior for "P(actor cooperates)" type beliefs — cheap Bayesian update. |
| `GaussianBelief` for continuous | Kalman gain handles uncertainty correctly; process_noise enables diffusion. |
| `rng: random.Random` on agent | Thread-safe — each agent has its own RNG, global `random` state untouched. |
| `tick()` coordinator | Enforces decay→observe→update→decide order; SimRunner calls one method, not five. |
| `from_spec()` factory | Canonical hydration path; propagates all dynamics config from BeliefSpec to runtime objects. |
| `AgentHydrationError` | Named exception for spec validation failures — not swallowed silently. |
| `maps_to_env_key` on beliefs | Belief name can differ from env key — allows human-readable names tracking any env key. |
| `decide()` returns `list[Action]` | SimRunner resolves all actions after all agents decide — no action ordering bias. |
| `DefaultBDIAgent` | Concrete utility-maximizer ships out of the box; scenario agents only need to subclass when default logic is insufficient. |

---

## 3. `core/theories/base.py` — TheoryBase

A theory module is a pure function over the environment: `update(env, agents, tick) → env_delta`.
Composable, order-controlled via priority.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from core.agents.base import BDIAgent


# ── State variable contract ────────────────────────────────────────────────

@dataclass
class TheoryStateVariables:
    """
    Declares which environment keys this theory reads, writes, and initializes.
    Used by SimRunner to validate key conflicts and set up initial environment.
    """
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    # keys this theory creates at setup (with default values)
    initializes: list[str] = field(default_factory=list)


# ── Theory base ────────────────────────────────────────────────────────────

class TheoryBase(ABC):
    """
    Abstract base for all theory modules.

    Subclass, declare state_variables, implement update().

    Convention for env keys owned by this theory:
        "{theory_id}__{variable_name}"
    e.g. "richardson_arms_race__escalation_rate"
    """

    theory_id: str = "base"  # override in subclass

    class Parameters(BaseModel):
        """Override in subclass to define theory parameters."""
        pass

    def __init__(self, parameters: dict[str, float] | None = None) -> None:
        self.params = self.Parameters(**(parameters or {}))
        self._tick_history: list[dict[str, float]] = []

    @property
    def state_variables(self) -> TheoryStateVariables:
        """
        Override to declare reads/writes/initializes.
        SimRunner calls this during setup() to validate and seed the environment.
        """
        return TheoryStateVariables()

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Called once before the tick loop starts.
        Initialize any env keys this theory owns that aren't already set.
        Returns the env keys to set (SimRunner merges them).
        """
        inits: dict[str, float] = {}
        for key in self.state_variables.initializes:
            if key not in env:
                inits[key] = 0.0
        return inits

    @abstractmethod
    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Core theory update. Called once per tick by SimRunner.

        Args:
            env: current environment (read-only by convention — do not mutate directly)
            agents: all active agents (read beliefs, do not mutate)
            tick: current tick number

        Returns:
            dict of {env_key: new_value} — SimRunner applies these after all theories run.
            Return only keys you own (listed in state_variables.writes).
        """
        ...

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return current theory state for snapshot."""
        return {
            "theory_id": self.theory_id,
            "parameters": self.params.model_dump(),
        }
```

### Registry (`core/theories/__init__.py`)

```python
_THEORY_REGISTRY: dict[str, Type[TheoryBase]] = {}

def register_theory(theory_id: str) -> Callable:
    """
    Class decorator. Sets cls.theory_id = theory_id and registers in _THEORY_REGISTRY.
    Raises ValueError if theory_id is already registered (prevents silent overwrites).
    Auto-discovery: importing the module registers it. No manual registry list needed.
    """

def get_theory(theory_id: str) -> Type[TheoryBase]:
    """Raises KeyError if not registered (includes hint to import the module)."""

def list_theories() -> list[str]:
    """Returns sorted list of all registered theory IDs."""
```

### Richardson Arms Race (`core/theories/richardson_arms_race.py`)

Full implementation — not a stub. See `ARCHITECTURE-THEORIES.md` §2 for math.

```
Equations:
    dx/dt = k·y - a·x + g      (actor A rate of arms change)
    dy/dt = l·x - b·y + h      (actor B rate of arms change)

Stability:  a·b > k·l  →  equilibrium exists
            a·b ≤ k·l  →  runaway escalation (warning logged at construction)

Parameters (Pydantic Field with ge/le bounds):
    k, l  defense coefficients  [0, 1]  default 0.30
    a, b  fatigue coefficients  [0, 1]  default 0.15
    g, h  grievance terms      [-0.5, 0.5]  default 0.05
    tick_unit  "month" | "quarter" | "year"  default "year"
    actor_a_id, actor_b_id  env key prefix  default "actor_a", "actor_b"

dt scaling:  month=1/12, quarter=0.25, year=1.0

Env keys written:
    {actor_a_id}__military_readiness   actor-namespaced (shared with Fearon, Zartman)
    {actor_b_id}__military_readiness
    richardson__escalation_index       (x + y) / 2
    richardson__stable                 1.0 if a·b > k·l, else 0.0

setup() overrides: military_readiness keys default to 0.5 (not 0.0) if absent

equilibrium() → (x*, y*) | None  — returns None if unstable
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| `update()` returns delta dict, not mutates env | SimRunner accumulates all deltas and applies once per tick — no ordering race conditions. |
| `state_variables.writes` declaration | SimRunner validates at setup() that no two theories write the same key. |
| `@register_theory` raises on duplicate | Silent overwrite would mask import order bugs; better to fail loudly. |
| Parameters as inner Pydantic `BaseModel` | Validated from `TheoryRef.parameters` dict at construction; `model_validator` can warn on unstable regimes. |
| Actor-namespaced military_readiness keys | Fearon/Zartman can read arms levels without coupling to Richardson's namespace. |
| `equilibrium()` method on Richardson | Useful for scenario calibration — compute where the system is headed before running 100 ticks. |

---

## 4. `core/sim_runner.py` — SimRunner

The tick engine. Owns the environment dict and orchestrates all agents and theories.

```python
from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.agents.base import Action, BDIAgent
from core.spec import ActorSpec, SimSpec, TheoryRef
from core.theories import get_theory
from core.theories.base import TheoryBase


# ── Snapshot types ─────────────────────────────────────────────────────────

@dataclass
class SimSnapshot:
    tick: int
    label: str
    env: dict[str, float]
    agent_states: list[dict[str, Any]]
    theory_states: list[dict[str, Any]]
    timestamp: float = field(default_factory=time.time)


@dataclass
class MetricRecord:
    tick: int
    metric_id: str
    env_key: str
    value: float


# ── Snapshot triggers ──────────────────────────────────────────────────────

@dataclass
class ScheduledSnapshotTrigger:
    """Snapshot every N ticks."""
    interval: int
    label_prefix: str = "auto"

    def should_trigger(self, tick: int, env: dict[str, float]) -> bool:
        return tick > 0 and tick % self.interval == 0

    def label(self, tick: int) -> str:
        return f"{self.label_prefix}_tick_{tick}"


@dataclass
class ThresholdSnapshotTrigger:
    """Snapshot when an env key crosses a threshold."""
    env_key: str
    threshold: float
    direction: float = 1.0  # +1 = above, -1 = below
    label: str = "threshold"
    _triggered: bool = field(default=False, init=False)

    def should_trigger(self, tick: int, env: dict[str, float]) -> bool:
        if self._triggered:
            return False
        value = env.get(self.env_key, 0.0)
        crossed = (self.direction > 0 and value >= self.threshold) or \
                  (self.direction < 0 and value <= self.threshold)
        if crossed:
            self._triggered = True
        return crossed


# ── SimRunner ──────────────────────────────────────────────────────────────

class SimRunner:
    """
    Domain-agnostic simulation engine.

    Usage:
        runner = SimRunner(spec)
        runner.setup()
        runner.run()                    # blocking, runs in thread via asyncio.to_thread
        snapshots = runner.snapshots
        history = runner.metric_history
    """

    def __init__(self, spec: SimSpec) -> None:
        self.spec = spec
        self.env: dict[str, float] = {}
        self.agents: list[BDIAgent] = []
        self.theories: list[TheoryBase] = []
        self.snapshots: list[SimSnapshot] = []
        self.metric_history: list[MetricRecord] = []
        self._lock = threading.Lock()
        self._snapshot_triggers: list[ScheduledSnapshotTrigger | ThresholdSnapshotTrigger] = []
        self._running = False

    # ── Setup ──────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Initialize environment, build agents, instantiate theories.
        Must be called before run().
        """
        # 1. Seed global env from spec
        self.env = dict(self.spec.initial_environment)

        # 2. Merge actor-owned env contributions
        for actor_spec in self.spec.actors:
            for key, value in actor_spec.initial_env_contributions.items():
                self.env[key] = value

        # 3. Build agents
        self.agents = [self._build_agent(actor_spec) for actor_spec in self.spec.actors]

        # 4. Instantiate theories in priority order
        sorted_theory_refs = sorted(self.spec.theories, key=lambda t: t.priority)
        self.theories = [self._build_theory(ref) for ref in sorted_theory_refs]

        # 5. Validate no theory write conflicts
        self._validate_theory_conflicts()

        # 6. Run theory setup() — let theories seed their own keys
        for theory in self.theories:
            env_additions = theory.setup(self.env)
            self.env.update(env_additions)

        # 7. Set up snapshot triggers from metrics
        for metric in self.spec.metrics:
            if metric.snapshot_threshold is not None:
                self._snapshot_triggers.append(
                    ThresholdSnapshotTrigger(
                        env_key=metric.env_key,
                        threshold=metric.snapshot_threshold,
                        direction=metric.snapshot_direction,
                        label=f"threshold_{metric.name}",
                    )
                )
        # Default: snapshot every 10% of total ticks
        interval = max(1, self.spec.timeframe.total_ticks // 10)
        self._snapshot_triggers.append(ScheduledSnapshotTrigger(interval=interval))

    def _build_agent(self, actor_spec: ActorSpec) -> BDIAgent:
        """Dynamically import and instantiate the agent class from actor_spec.agent_class."""
        module_path, class_name = actor_spec.agent_class.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        AgentClass = getattr(module, class_name)

        # Build beliefs dict
        from core.agents.base import BetaBelief, GaussianBelief, BeliefDistType  # local import avoids circular
        beliefs = {}
        for b_spec in actor_spec.beliefs:
            if b_spec.dist_type == BeliefDistType.BETA:
                beliefs[b_spec.belief_id] = BetaBelief(
                    name=b_spec.name, alpha=b_spec.alpha, beta=b_spec.beta
                )
            elif b_spec.dist_type == BeliefDistType.GAUSSIAN:
                beliefs[b_spec.belief_id] = GaussianBelief(
                    name=b_spec.name, mean=b_spec.mean, variance=b_spec.variance
                )
            # POINT beliefs: stored as GaussianBelief with zero variance
            else:
                beliefs[b_spec.belief_id] = GaussianBelief(
                    name=b_spec.name, mean=b_spec.value, variance=0.0
                )

        # Build capabilities dict
        capabilities = {}
        for cap_spec in actor_spec.capabilities:
            capabilities[cap_spec.capability_id] = {
                "capacity": cap_spec.capacity,
                "cost": cap_spec.cost,
                "recovery_rate": cap_spec.recovery_rate,
                "cooldown_ticks": cap_spec.cooldown_ticks,
                "current": cap_spec.capacity,  # start full
                "cooldown_remaining": 0,
            }

        return AgentClass(
            actor_id=actor_spec.actor_id,
            name=actor_spec.name,
            beliefs=beliefs,
            desires=[d.model_dump() for d in actor_spec.desires],
            capabilities=capabilities,
            observation_noise_sigma=self.spec.uncertainty.observation_noise_sigma,
        )

    def _build_theory(self, ref: TheoryRef) -> TheoryBase:
        TheoryClass = get_theory(ref.theory_id)
        return TheoryClass(parameters=ref.parameters)

    def _validate_theory_conflicts(self) -> None:
        """Raise if two theories declare they write the same env key."""
        seen: dict[str, str] = {}  # key → theory_id
        for theory in self.theories:
            for key in theory.state_variables.writes:
                if key in seen:
                    raise ValueError(
                        f"Theory write conflict: '{key}' claimed by both "
                        f"'{seen[key]}' and '{theory.theory_id}'"
                    )
                seen[key] = theory.theory_id

    # ── Tick loop ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Blocking tick loop. Call via asyncio.to_thread() from async contexts.
        """
        self._running = True
        total_ticks = self.spec.timeframe.total_ticks
        shock_prob = self.spec.uncertainty.shock_probability
        shock_mag = self.spec.uncertainty.shock_magnitude
        scheduled_shocks = self.spec.uncertainty.scheduled_shocks

        for tick in range(total_ticks):
            with self._lock:
                # 1. Apply scheduled shocks
                if tick in scheduled_shocks:
                    for key, delta in scheduled_shocks[tick].items():
                        if key in self.env:
                            self.env[key] = max(0.0, min(1.0, self.env[key] + delta))

                # 2. Apply random shocks
                if random.random() < shock_prob and self.env:
                    shock_key = random.choice(list(self.env.keys()))
                    shock_delta = random.uniform(-shock_mag, shock_mag)
                    self.env[shock_key] = max(0.0, min(1.0, self.env[shock_key] + shock_delta))

                # 3. Agents observe (noisy read)
                observations = {
                    agent.actor_id: agent.observe_environment(self.env)
                    for agent in self.agents
                }

                # 4. Agents update beliefs
                for agent in self.agents:
                    agent.update_beliefs(observations[agent.actor_id])

                # 5. Agents decide → collect all actions
                all_actions: list[tuple[BDIAgent, Action]] = []
                for agent in self.agents:
                    actions = agent.decide(self.env, tick)
                    for action in actions:
                        if action.capability_id is None or agent.can_act(action.capability_id):
                            all_actions.append((agent, action))

                # 6. Resolve actions → env mutations
                env_delta: dict[str, float] = {}
                for agent, action in all_actions:
                    if action.capability_id:
                        agent.expend_capacity(action.capability_id)
                    for key, delta in action.parameters.items():
                        if key in self.env:
                            env_delta[key] = env_delta.get(key, 0.0) + delta

                for key, delta in env_delta.items():
                    self.env[key] = max(0.0, min(1.0, self.env[key] + delta))

                # 7. Theory updates (in priority order)
                theory_deltas: dict[str, float] = {}
                for theory in self.theories:
                    delta = theory.update(self.env, self.agents, tick)
                    theory_deltas.update(delta)

                self.env.update(theory_deltas)

                # 8. Record metrics
                for metric in self.spec.metrics:
                    if metric.env_key in self.env:
                        self.metric_history.append(MetricRecord(
                            tick=tick,
                            metric_id=metric.metric_id,
                            env_key=metric.env_key,
                            value=self.env[metric.env_key],
                        ))

                # 9. Recharge capabilities
                for agent in self.agents:
                    agent.recharge_capabilities()

                # 10. Snapshot triggers
                for trigger in self._snapshot_triggers:
                    if trigger.should_trigger(tick, self.env):
                        label = (
                            trigger.label(tick)
                            if isinstance(trigger, ScheduledSnapshotTrigger)
                            else trigger.label
                        )
                        self._take_snapshot(tick, label)

        self._running = False

    async def run_async(self) -> None:
        """Run the tick loop in a thread pool to avoid blocking the async event loop."""
        await asyncio.to_thread(self.run)

    # ── Snapshot ───────────────────────────────────────────────────────────

    def _take_snapshot(self, tick: int, label: str) -> SimSnapshot:
        snapshot = SimSnapshot(
            tick=tick,
            label=label,
            env=dict(self.env),
            agent_states=[a.get_state_snapshot() for a in self.agents],
            theory_states=[t.get_state_snapshot() for t in self.theories],
        )
        self.snapshots.append(snapshot)
        return snapshot

    def take_named_snapshot(self, label: str) -> SimSnapshot:
        """Manually trigger a named snapshot (e.g. from API endpoint)."""
        with self._lock:
            return self._take_snapshot(
                tick=len(self.metric_history),
                label=label,
            )

    # ── State ──────────────────────────────────────────────────────────────

    def get_current_env(self) -> dict[str, float]:
        with self._lock:
            return dict(self.env)

    def is_running(self) -> bool:
        return self._running
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| `asyncio.to_thread(self.run)` | Tick loop is CPU-bound synchronous. Blocking the async event loop would freeze the FastAPI server. |
| `threading.Lock` per SimRunner | Multiple API requests can read state (snapshots, current env) while the loop runs. |
| All action deltas accumulated before applying | Prevents agent ordering from affecting outcomes. All agents see the same pre-tick env. |
| Theory deltas applied after all agent actions | Theories model background dynamics. Agents react to a stable environment. |
| Env clamped to `[0.0, 1.0]` | All env values are normalized. Theories and agents work in consistent value range. |
| `_validate_theory_conflicts()` at setup | Fail fast — a write conflict would cause silent bugs at runtime. |

---

## Environment Key Conventions

All environment keys follow a namespacing convention to prevent collisions:

| Prefix | Owner | Example |
|--------|-------|---------|
| `{theory_id}__` | Theory module | `richardson_arms_race__escalation_index` |
| `{actor_id}__` | Actor (agent) | `iran__military_readiness` |
| `global__` | Shared / cross-cutting | `global__trade_disruption_index` |

Theories **declare** their keys in `state_variables.writes`. SimRunner validates at setup time.

---

## Module Dependency Graph

```
core/spec.py          (no internal deps — pure Pydantic)
    ↑
core/agents/base.py   (no internal deps — pure dataclass + ABC)
    ↑
core/theories/base.py (imports BDIAgent for type hint only)
    ↑
core/theories/__init__.py  (registry — imports TheoryBase)
    ↑
core/sim_runner.py    (imports spec, agents.base, theories registry)
```

No circular imports. Each layer only depends on the layer below it.

---

## Next: Theory Stubs (Week 1, Day 4–5)

Five theory stubs to implement (bodies can return `{}` initially, flesh out in Week 2):

| Theory ID | File | Domain |
|-----------|------|--------|
| `richardson_arms_race` | `core/theories/richardson_arms_race.py` | Conflict escalation |
| `wittman_zartman` | `core/theories/wittman_zartman.py` | Negotiation / war termination |
| `fearon_bargaining` | `core/theories/fearon_bargaining.py` | Bargaining model of war |
| `keynesian_multiplier` | `core/theories/keynesian_multiplier.py` | Macro / fiscal policy |
| `porter_five_forces` | `core/theories/porter_five_forces.py` | Market competitive dynamics |
