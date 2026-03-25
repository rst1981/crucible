"""
Tests for core/sim_runner.py — SimRunner tick engine.
"""
from __future__ import annotations

import pytest

from core.sim_runner import (
    MetricRecord,
    ScheduledSnapshotTrigger,
    SimRunner,
    SimSnapshot,
    ThresholdSnapshotTrigger,
)
from core.spec import (
    ActorSpec,
    OutcomeMetricSpec,
    SimSpec,
    TheoryRef,
    TimeframeSpec,
    UncertaintySpec,
)
from core.spec import BeliefDistType
from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables


# ── Helpers ────────────────────────────────────────────────────────────────


def _minimal_spec(
    ticks: int = 5,
    initial_env: dict | None = None,
    actors: list | None = None,
    theories: list | None = None,
    metrics: list | None = None,
    uncertainty: UncertaintySpec | None = None,
) -> SimSpec:
    return SimSpec(
        name="Test",
        timeframe=TimeframeSpec(total_ticks=ticks),
        initial_environment=initial_env or {"x": 0.5},
        actors=actors or [],
        theories=theories or [],
        metrics=metrics or [],
        uncertainty=uncertainty or UncertaintySpec(shock_probability=0.0),
    )


def _make_noop_theory(theory_id: str, writes: list[str] | None = None) -> type[TheoryBase]:
    """Return a no-op theory class that's already registered (or re-uses existing)."""
    from core.theories import _THEORY_REGISTRY  # type: ignore[attr-defined]

    if theory_id in _THEORY_REGISTRY:
        return _THEORY_REGISTRY[theory_id]

    @register_theory(theory_id)
    class _Noop(TheoryBase):
        @property
        def state_variables(self) -> TheoryStateVariables:
            return TheoryStateVariables(writes=writes or [])

        def update(self, env, agents, tick):
            return {}

    return _Noop


# ── ScheduledSnapshotTrigger ───────────────────────────────────────────────


class TestScheduledSnapshotTrigger:
    def test_fires_at_interval(self):
        t = ScheduledSnapshotTrigger(interval=5)
        assert not t.should_trigger(0, {})
        assert not t.should_trigger(4, {})
        assert t.should_trigger(5, {})
        assert t.should_trigger(10, {})

    def test_does_not_fire_at_zero(self):
        t = ScheduledSnapshotTrigger(interval=1)
        assert not t.should_trigger(0, {})
        assert t.should_trigger(1, {})

    def test_label_includes_tick(self):
        t = ScheduledSnapshotTrigger(interval=5, label_prefix="chk")
        assert t.label(10) == "chk_tick_10"


# ── ThresholdSnapshotTrigger ───────────────────────────────────────────────


class TestThresholdSnapshotTrigger:
    def test_fires_when_above_threshold(self):
        t = ThresholdSnapshotTrigger(env_key="x", threshold=0.8, direction=1.0)
        assert not t.should_trigger(0, {"x": 0.5})
        assert t.should_trigger(1, {"x": 0.9})

    def test_fires_only_once(self):
        t = ThresholdSnapshotTrigger(env_key="x", threshold=0.8, direction=1.0)
        assert t.should_trigger(0, {"x": 0.9})
        assert not t.should_trigger(1, {"x": 0.9})

    def test_fires_when_below_threshold(self):
        t = ThresholdSnapshotTrigger(env_key="x", threshold=0.2, direction=-1.0)
        assert not t.should_trigger(0, {"x": 0.5})
        assert t.should_trigger(1, {"x": 0.1})

    def test_missing_key_treated_as_zero(self):
        t = ThresholdSnapshotTrigger(env_key="missing", threshold=0.0, direction=-1.0)
        # 0.0 <= 0.0 => fires
        assert t.should_trigger(0, {})


# ── SimSnapshot and MetricRecord ───────────────────────────────────────────


class TestDataclasses:
    def test_sim_snapshot_stores_env_copy(self):
        env = {"a": 0.5}
        snap = SimSnapshot(tick=1, label="t", env=env, agent_states=[], theory_states=[])
        env["a"] = 0.9  # mutate original
        assert snap.env["a"] == 0.9  # shallow copy — matches original

    def test_metric_record_fields(self):
        mr = MetricRecord(tick=3, metric_id="m1", env_key="x", value=0.7)
        assert mr.tick == 3
        assert mr.value == 0.7


# ── SimRunner setup ────────────────────────────────────────────────────────


class TestSimRunnerSetup:
    def test_env_seeded_from_spec(self):
        spec = _minimal_spec(initial_env={"alpha": 0.3, "beta": 0.7})
        runner = SimRunner(spec)
        runner.setup()
        assert runner.env["alpha"] == pytest.approx(0.3)
        assert runner.env["beta"] == pytest.approx(0.7)

    def test_actor_env_contributions_merge(self):
        actor = ActorSpec(
            name="TestActor",
            agent_class="core.agents.base.DefaultBDIAgent",
            initial_env_contributions={"actor__val": 0.6},
        )
        spec = _minimal_spec(initial_env={"x": 0.5}, actors=[actor])
        runner = SimRunner(spec)
        runner.setup()
        assert runner.env["actor__val"] == pytest.approx(0.6)

    def test_theory_seeds_env_keys(self):
        """A theory's setup() can add keys to env."""
        _make_noop_theory("_test_seeder_theory")

        @register_theory("_seeder_actual") if "_seeder_actual" not in __import__(
            "core.theories", fromlist=["_THEORY_REGISTRY"]
        )._THEORY_REGISTRY else lambda c: c
        class _Seeder(TheoryBase):
            @property
            def state_variables(self):
                return TheoryStateVariables(initializes=["seeded_key"])

            def setup(self, env):
                return {"seeded_key": 0.42}

            def update(self, env, agents, tick):
                return {}

        from core.theories import _THEORY_REGISTRY
        _THEORY_REGISTRY["_seeder_actual"] = _Seeder
        spec = _minimal_spec(
            theories=[TheoryRef(theory_id="_seeder_actual")],
        )
        runner = SimRunner(spec)
        runner.setup()
        assert runner.env.get("seeded_key") == pytest.approx(0.42)

    def test_write_conflict_raises(self):
        _make_noop_theory("_conflict_a", writes=["shared_key"])
        _make_noop_theory("_conflict_b", writes=["shared_key"])
        spec = _minimal_spec(
            theories=[
                TheoryRef(theory_id="_conflict_a"),
                TheoryRef(theory_id="_conflict_b"),
            ],
        )
        runner = SimRunner(spec)
        with pytest.raises(ValueError, match="write conflict"):
            runner.setup()

    def test_default_scheduled_trigger_registered(self):
        spec = _minimal_spec(ticks=100)
        runner = SimRunner(spec)
        runner.setup()
        scheduled = [t for t in runner._snapshot_triggers if isinstance(t, ScheduledSnapshotTrigger)]
        assert len(scheduled) == 1
        assert scheduled[0].interval == 10  # 100 // 10

    def test_threshold_trigger_from_metric(self):
        metric = OutcomeMetricSpec(
            name="x_high",
            env_key="x",
            snapshot_threshold=0.9,
            snapshot_direction=1.0,
        )
        spec = _minimal_spec(metrics=[metric])
        runner = SimRunner(spec)
        runner.setup()
        threshold_triggers = [t for t in runner._snapshot_triggers if isinstance(t, ThresholdSnapshotTrigger)]
        assert len(threshold_triggers) == 1
        assert threshold_triggers[0].threshold == 0.9


# ── SimRunner.run() ────────────────────────────────────────────────────────


class TestSimRunnerRun:
    def test_runs_without_error(self):
        spec = _minimal_spec(ticks=3)
        runner = SimRunner(spec, rng_seed=42)
        runner.setup()
        runner.run()
        assert not runner.is_running()

    def test_produces_metric_history(self):
        metric = OutcomeMetricSpec(name="x", env_key="x")
        spec = _minimal_spec(ticks=4, metrics=[metric])
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        assert len(runner.metric_history) == 4
        assert all(isinstance(r, MetricRecord) for r in runner.metric_history)
        assert all(r.env_key == "x" for r in runner.metric_history)

    def test_no_shocks_when_shock_prob_zero(self):
        """With shock_probability=0 env should stay at initial value (no theory changes)."""
        spec = _minimal_spec(
            ticks=10,
            initial_env={"stable": 0.5},
            uncertainty=UncertaintySpec(shock_probability=0.0),
            metrics=[OutcomeMetricSpec(name="stable", env_key="stable")],
        )
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        values = [r.value for r in runner.metric_history]
        assert all(v == pytest.approx(0.5) for v in values)

    def test_scheduled_shocks_applied(self):
        spec = _minimal_spec(
            ticks=5,
            initial_env={"x": 0.5},
            uncertainty=UncertaintySpec(
                shock_probability=0.0,
                scheduled_shocks={2: {"x": 0.2}},
            ),
            metrics=[OutcomeMetricSpec(name="x", env_key="x")],
        )
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        # tick 2 record should show 0.7
        tick2 = [r for r in runner.metric_history if r.tick == 2]
        assert tick2[0].value == pytest.approx(0.7)

    def test_snapshots_taken_on_schedule(self):
        spec = _minimal_spec(ticks=20)
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        # interval = 20 // 10 = 2; snapshots at ticks 2,4,6,8,10,12,14,16,18
        assert len(runner.snapshots) == 9

    def test_env_values_remain_clamped(self):
        """Scheduled shocks beyond [0,1] must be clamped."""
        spec = _minimal_spec(
            ticks=3,
            initial_env={"x": 0.95},
            uncertainty=UncertaintySpec(
                shock_probability=0.0,
                scheduled_shocks={0: {"x": 0.5}},  # would push to 1.45
            ),
            metrics=[OutcomeMetricSpec(name="x", env_key="x")],
        )
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        assert all(r.value <= 1.0 for r in runner.metric_history)

    def test_theory_updates_applied(self):
        """A theory that increments a key by 0.1 each tick should be reflected."""
        from core.theories import _THEORY_REGISTRY

        if "_incrementer" not in _THEORY_REGISTRY:
            @register_theory("_incrementer")
            class _Inc(TheoryBase):
                @property
                def state_variables(self):
                    return TheoryStateVariables(writes=["counter"])

                def setup(self, env):
                    if "counter" not in env:
                        return {"counter": 0.0}
                    return {}

                def update(self, env, agents, tick):
                    return {"counter": min(1.0, env.get("counter", 0.0) + 0.1)}

        spec = _minimal_spec(
            ticks=3,
            initial_env={"counter": 0.0},
            theories=[TheoryRef(theory_id="_incrementer")],
            uncertainty=UncertaintySpec(shock_probability=0.0),
            metrics=[OutcomeMetricSpec(name="counter", env_key="counter")],
        )
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        values = [r.value for r in runner.metric_history]
        assert values[0] == pytest.approx(0.1)
        assert values[1] == pytest.approx(0.2)
        assert values[2] == pytest.approx(0.3)

    def test_get_current_env_returns_copy(self):
        spec = _minimal_spec(ticks=2, initial_env={"x": 0.5})
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        env_snapshot = runner.get_current_env()
        env_snapshot["x"] = 0.99
        assert runner.env["x"] != 0.99  # mutation didn't leak in

    def test_is_running_false_after_complete(self):
        spec = _minimal_spec(ticks=2)
        runner = SimRunner(spec)
        runner.setup()
        runner.run()
        assert runner.is_running() is False

    def test_take_named_snapshot(self):
        spec = _minimal_spec(ticks=2, initial_env={"x": 0.5})
        runner = SimRunner(spec, rng_seed=0)
        runner.setup()
        runner.run()
        snap = runner.take_named_snapshot("manual_check")
        assert snap.label == "manual_check"
        assert "x" in snap.env

    def test_rng_seed_produces_deterministic_results(self):
        """Same seed -> same random shocks -> same results."""
        spec1 = _minimal_spec(
            ticks=20,
            initial_env={"x": 0.5},
            uncertainty=UncertaintySpec(shock_probability=0.5, shock_magnitude=0.2),
            metrics=[OutcomeMetricSpec(name="x", env_key="x")],
        )
        spec2 = _minimal_spec(
            ticks=20,
            initial_env={"x": 0.5},
            uncertainty=UncertaintySpec(shock_probability=0.5, shock_magnitude=0.2),
            metrics=[OutcomeMetricSpec(name="x", env_key="x")],
        )
        r1 = SimRunner(spec1, rng_seed=7)
        r1.setup()
        r1.run()
        r2 = SimRunner(spec2, rng_seed=7)
        r2.setup()
        r2.run()
        v1 = [r.value for r in r1.metric_history]
        v2 = [r.value for r in r2.metric_history]
        assert v1 == v2
