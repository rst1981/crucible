"""
SimRunner — domain-agnostic simulation tick engine.

Owns the environment dict and orchestrates all agents and theories.

Usage::

    runner = SimRunner(spec)
    runner.setup()
    runner.run()                    # blocking; use run_async() from async contexts
    snapshots = runner.snapshots
    history   = runner.metric_history

Thread safety:
    run() acquires self._lock for the entire tick.
    get_current_env() and take_named_snapshot() also acquire the lock,
    so API reads are safe while the loop is running.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.agents.base import Action, BDIAgent
from core.spec import ActorSpec, SimSpec
from core.theories import get_theory
from core.theories.base import TheoryBase

logger = logging.getLogger(__name__)


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
    name: str = ""


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
    """Snapshot once when an env key crosses a threshold."""
    env_key: str
    threshold: float
    direction: float = 1.0   # +1 = fire when value >= threshold; -1 = when value <= threshold
    label: str = "threshold"
    _triggered: bool = field(default=False, init=False)

    def should_trigger(self, tick: int, env: dict[str, float]) -> bool:
        if self._triggered:
            return False
        value = env.get(self.env_key, 0.0)
        crossed = (
            (self.direction > 0 and value >= self.threshold) or
            (self.direction < 0 and value <= self.threshold)
        )
        if crossed:
            self._triggered = True
        return crossed


# ── SimRunner ──────────────────────────────────────────────────────────────


class SimRunner:
    """
    Domain-agnostic simulation engine.

    Lifecycle:
        1. ``setup()``   — build agents + theories, seed env, register triggers
        2. ``run()``     — blocking tick loop (wrap with ``asyncio.to_thread``)
        3. read results — ``snapshots``, ``metric_history``, ``get_current_env()``
    """

    def __init__(self, spec: SimSpec, rng_seed: int | None = None) -> None:
        self.spec = spec
        self.env: dict[str, float] = {}
        self.agents: list[BDIAgent] = []
        self.theories: list[TheoryBase] = []
        self.snapshots: list[SimSnapshot] = []
        self.metric_history: list[MetricRecord] = []
        self.theory_contribution_history: list[dict] = []
        # Each entry: {"tick": int, "theory_id": str, "total_delta": float}
        self._lock = threading.Lock()
        self._snapshot_triggers: list[ScheduledSnapshotTrigger | ThresholdSnapshotTrigger] = []
        self._running = False
        self.ticks_completed: int = 0
        # Instance-level RNG — never use the global random module in this class.
        # This ensures two SimRunner instances (e.g. in EnsembleRunner) don't share
        # random state and that results are reproducible given the same seed.
        self.rng = random.Random(rng_seed)

    # ── Setup ──────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Initialise environment, build agents, instantiate theories.
        Must be called before run().
        """
        # 1. Seed global env from spec
        self.env = dict(self.spec.initial_environment)

        # 2. Merge actor-owned env contributions
        for actor_spec in self.spec.actors:
            for key, value in actor_spec.initial_env_contributions.items():
                self.env[key] = value

        # 3. Build agents via from_spec() — handles beliefs, desires, capabilities,
        #    decay_rate, process_noise, maps_to_env_key, and rng threading correctly.
        self.agents = [self._build_agent(a) for a in self.spec.actors]

        # 4. Instantiate theories in priority order
        sorted_refs = sorted(self.spec.theories, key=lambda t: t.priority)
        self.theories = [self._build_theory(ref) for ref in sorted_refs]

        # 5. Validate no theory write conflicts
        self._validate_theory_conflicts()

        # 6. Run theory setup() — let theories seed their own keys
        for theory in self.theories:
            env_additions = theory.setup(self.env)
            self.env.update(env_additions)

        # 7. Register snapshot triggers
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
        # Default: snapshot every 10 % of total ticks
        interval = max(1, self.spec.timeframe.total_ticks // 10)
        self._snapshot_triggers.append(ScheduledSnapshotTrigger(interval=interval))

        logger.info(
            "SimRunner setup: %d agents, %d theories, env_keys=%d",
            len(self.agents), len(self.theories), len(self.env),
        )

    def _build_agent(self, actor_spec: ActorSpec) -> BDIAgent:
        """Delegate to AgentClass.from_spec() — single source of truth for hydration."""
        module_path, class_name = actor_spec.agent_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        AgentClass = getattr(module, class_name)
        # Each agent gets its own Random seeded from the runner's RNG stream,
        # so all randomness is deterministic given SimRunner(rng_seed=N).
        agent_rng = random.Random(self.rng.random())
        return AgentClass.from_spec(actor_spec, rng=agent_rng)

    def _build_theory(self, ref) -> TheoryBase:
        TheoryClass = get_theory(ref.theory_id)
        return TheoryClass(parameters=ref.parameters)

    def _validate_theory_conflicts(self) -> None:
        """Raise ValueError if two theories declare they write the same env key."""
        seen: dict[str, str] = {}  # key -> theory_id
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

        logger.info("SimRunner.run(): %d ticks starting", total_ticks)

        try:
            for tick in range(total_ticks):
                with self._lock:
                    # 1. Apply scheduled shocks
                    if tick in scheduled_shocks:
                        for key, delta in scheduled_shocks[tick].items():
                            if key in self.env:
                                self.env[key] = max(0.0, min(1.0, self.env[key] + delta))

                    # 2. Apply random shocks (use self.rng — never global random)
                    if self.env and self.rng.random() < shock_prob:
                        shock_key = self.rng.choice(list(self.env.keys()))
                        shock_delta = self.rng.uniform(-shock_mag, shock_mag)
                        self.env[shock_key] = max(0.0, min(1.0, self.env[shock_key] + shock_delta))

                    # 3. Agents observe (noisy read of env)
                    observations = {
                        agent.actor_id: agent.observe_environment(self.env)
                        for agent in self.agents
                    }

                    # 4. Agents update beliefs from observations
                    for agent in self.agents:
                        agent.update_beliefs(observations[agent.actor_id])

                    # 5. Agents decide -> collect all feasible actions
                    all_actions: list[tuple[BDIAgent, Action]] = []
                    for agent in self.agents:
                        for action in agent.decide(self.env, tick):
                            if action.capability_id is None or agent.can_act(action.capability_id):
                                all_actions.append((agent, action))

                    # 6. Resolve actions -> accumulated env deltas
                    #    All agents see the same pre-tick env; accumulate then apply.
                    env_delta: dict[str, float] = {}
                    for agent, action in all_actions:
                        if action.capability_id:
                            agent.expend_capacity(action.capability_id)
                        for key, delta in action.parameters.items():
                            if key in self.env:
                                env_delta[key] = env_delta.get(key, 0.0) + delta

                    for key, delta in env_delta.items():
                        self.env[key] = max(0.0, min(1.0, self.env[key] + delta))

                    # 7. Theory updates (priority order)
                    #    Collect all deltas first, apply once -> no intra-tick ordering race.
                    theory_deltas: dict[str, float] = {}
                    for theory in self.theories:
                        t_deltas = theory.update(self.env, self.agents, tick)
                        t_total = sum(abs(v) for v in t_deltas.values()) if t_deltas else 0.0
                        self.theory_contribution_history.append({
                            "tick": tick,
                            "theory_id": theory.theory_id,
                            "total_delta": t_total,
                        })
                        theory_deltas.update(t_deltas)
                    self.env.update(theory_deltas)

                    # 8. Record metrics
                    for metric in self.spec.metrics:
                        if metric.env_key in self.env:
                            self.metric_history.append(MetricRecord(
                                tick=tick,
                                metric_id=metric.metric_id,
                                env_key=metric.env_key,
                                value=self.env[metric.env_key],
                                name=metric.name,
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

                    self.ticks_completed += 1

        finally:
            self._running = False

        logger.info(
            "SimRunner.run() complete: %d snapshots, %d metric records",
            len(self.snapshots), len(self.metric_history),
        )

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
        """Manually trigger a named snapshot (e.g. from an API endpoint)."""
        with self._lock:
            tick = self.metric_history[-1].tick if self.metric_history else 0
            return self._take_snapshot(tick=tick, label=label)

    # ── State accessors ────────────────────────────────────────────────────

    def get_current_env(self) -> dict[str, float]:
        """Thread-safe snapshot of current env."""
        with self._lock:
            return dict(self.env)

    def is_running(self) -> bool:
        return self._running
