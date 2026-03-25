"""
Tests for core/spec.py

Covers:
- SimSpec construction and validation
- BeliefSpec, DesireSpec, CapabilitySpec, ActorSpec defaults
- TimeframeSpec, UncertaintySpec defaults
- OutcomeMetricSpec + metric_env_keys_exist validator
- EnvKeySpec + display_env()
- SpecDiff dataclass
- diff_simspecs()
- branch_simspec()
"""

import uuid

import pytest
from pydantic import ValidationError

from core.spec import (
    ActorSpec,
    BeliefDistType,
    BeliefSpec,
    CapabilitySpec,
    DesireSpec,
    EnvKeySpec,
    OutcomeMetricSpec,
    ResearchSourceSpec,
    SimSpec,
    SpecDiff,
    TheoryRef,
    TimeframeSpec,
    UncertaintySpec,
    branch_simspec,
    diff_simspecs,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def minimal_spec(**overrides) -> SimSpec:
    """Simplest valid SimSpec — no actors, no metrics."""
    kwargs = dict(name="Test Spec", domain="test")
    kwargs.update(overrides)
    return SimSpec(**kwargs)


def spec_with_env(**overrides) -> SimSpec:
    """SimSpec with two env keys for testing display and metrics."""
    kwargs = dict(
        name="Env Spec",
        initial_environment={
            "iran__military_readiness": 0.7,
            "strait__tension": 0.4,
        },
    )
    kwargs.update(overrides)
    return SimSpec(**kwargs)


# ── BeliefSpec ───────────────────────────────────────────────────────────────

class TestBeliefSpec:
    def test_defaults(self):
        b = BeliefSpec(name="P(cooperate)")
        assert b.dist_type == BeliefDistType.BETA
        assert b.alpha == 1.0
        assert b.beta == 1.0
        assert b.belief_id  # auto-generated

    def test_gaussian(self):
        b = BeliefSpec(name="GDP estimate", dist_type=BeliefDistType.GAUSSIAN, mean=2.5, variance=0.3)
        assert b.dist_type == BeliefDistType.GAUSSIAN
        assert b.mean == 2.5

    def test_point(self):
        b = BeliefSpec(name="Fixed", dist_type=BeliefDistType.POINT, value=0.9)
        assert b.value == 0.9

    def test_unique_ids(self):
        ids = {BeliefSpec(name="x").belief_id for _ in range(10)}
        assert len(ids) == 10


# ── DesireSpec ───────────────────────────────────────────────────────────────

class TestDesireSpec:
    def test_defaults(self):
        d = DesireSpec(name="Maximize revenue", target_env_key="iran__oil_revenue")
        assert d.direction == 1.0
        assert d.weight == 1.0

    def test_minimize(self):
        d = DesireSpec(name="Reduce tension", target_env_key="strait__tension", direction=-1.0)
        assert d.direction == -1.0


# ── CapabilitySpec ───────────────────────────────────────────────────────────

class TestCapabilitySpec:
    def test_defaults(self):
        c = CapabilitySpec(name="Naval deployment")
        assert c.capacity == 1.0
        assert c.cost == 0.1
        assert c.recovery_rate == 0.05
        assert c.cooldown_ticks == 0


# ── ActorSpec ────────────────────────────────────────────────────────────────

class TestActorSpec:
    def test_defaults(self):
        a = ActorSpec(name="Iran")
        assert a.agent_class == "core.agents.base.BDIAgent"
        assert a.beliefs == []
        assert a.desires == []
        assert a.capabilities == []
        assert a.initial_env_contributions == {}

    def test_with_components(self):
        a = ActorSpec(
            name="Iran",
            beliefs=[BeliefSpec(name="P(US strikes)")],
            desires=[DesireSpec(name="Sovereignty", target_env_key="iran__sovereignty")],
            capabilities=[CapabilitySpec(name="Naval")],
            initial_env_contributions={"iran__military_readiness": 0.7},
        )
        assert len(a.beliefs) == 1
        assert a.initial_env_contributions["iran__military_readiness"] == 0.7

    def test_custom_agent_class(self):
        a = ActorSpec(name="Iran", agent_class="scenarios.hormuz.agents.IranAgent")
        assert a.agent_class == "scenarios.hormuz.agents.IranAgent"


# ── TimeframeSpec ────────────────────────────────────────────────────────────

class TestTimeframeSpec:
    def test_defaults(self):
        t = TimeframeSpec()
        assert t.total_ticks == 365
        assert t.tick_unit == "day"
        assert t.start_date is None

    def test_custom(self):
        t = TimeframeSpec(total_ticks=52, tick_unit="week", start_date="2025-01-01")
        assert t.total_ticks == 52
        assert t.start_date == "2025-01-01"


# ── UncertaintySpec ──────────────────────────────────────────────────────────

class TestUncertaintySpec:
    def test_defaults(self):
        u = UncertaintySpec()
        assert u.observation_noise_sigma == 0.02
        assert u.shock_probability == 0.01
        assert u.shock_magnitude == 0.1
        assert u.scheduled_shocks == {}

    def test_scheduled_shocks(self):
        u = UncertaintySpec(scheduled_shocks={10: {"strait__tension": 0.3}})
        assert u.scheduled_shocks[10]["strait__tension"] == 0.3


# ── OutcomeMetricSpec ────────────────────────────────────────────────────────

class TestOutcomeMetricSpec:
    def test_defaults(self):
        m = OutcomeMetricSpec(name="Tension", env_key="strait__tension")
        assert m.snapshot_threshold is None
        assert m.snapshot_direction == 1.0

    def test_with_threshold(self):
        m = OutcomeMetricSpec(
            name="Crisis trigger",
            env_key="strait__tension",
            snapshot_threshold=0.8,
            snapshot_direction=1.0,
        )
        assert m.snapshot_threshold == 0.8


# ── EnvKeySpec + display_env ─────────────────────────────────────────────────

class TestEnvKeySpec:
    def test_defaults(self):
        e = EnvKeySpec(key="iran__military_readiness")
        assert e.scale == 1.0
        assert e.unit == ""
        assert e.display_name == ""
        assert e.log_scale is False

    def test_display_env_with_annotation(self):
        spec = SimSpec(
            name="Display test",
            initial_environment={"iran__military_readiness": 0.7, "strait__tension": 0.4},
            env_key_specs=[
                EnvKeySpec(
                    key="iran__military_readiness",
                    scale=100.0,
                    unit="index",
                    display_name="Iranian Military Readiness",
                )
            ],
        )
        display = spec.display_env({"iran__military_readiness": 0.7, "strait__tension": 0.4})

        annotated = display["iran__military_readiness"]
        assert annotated["normalized"] == 0.7
        assert annotated["display"] == pytest.approx(70.0)
        assert annotated["unit"] == "index"
        assert annotated["display_name"] == "Iranian Military Readiness"

        unannotated = display["strait__tension"]
        assert unannotated["normalized"] == 0.4
        assert unannotated["display"] == 0.4
        assert unannotated["unit"] == ""
        assert unannotated["display_name"] == "strait__tension"

    def test_display_env_empty_env_key_specs(self):
        spec = minimal_spec()
        display = spec.display_env({"some_key": 0.5})
        assert display["some_key"]["display"] == 0.5
        assert display["some_key"]["display_name"] == "some_key"

    def test_display_env_scale_zero_edge(self):
        spec = SimSpec(
            name="Zero scale",
            initial_environment={"x": 0.0},
            env_key_specs=[EnvKeySpec(key="x", scale=1_000_000, unit="USD")],
        )
        display = spec.display_env({"x": 0.0})
        assert display["x"]["display"] == 0.0

    def test_display_env_large_scale(self):
        spec = SimSpec(
            name="Billion scale",
            initial_environment={"gdp": 0.5},
            env_key_specs=[EnvKeySpec(key="gdp", scale=2_000_000_000, unit="billion USD")],
        )
        display = spec.display_env({"gdp": 0.5})
        assert display["gdp"]["display"] == pytest.approx(1_000_000_000)


# ── SimSpec validators ────────────────────────────────────────────────────────

class TestSimSpecValidators:
    def test_actor_ids_unique_passes(self):
        a1 = ActorSpec(name="Iran")
        a2 = ActorSpec(name="US")
        spec = SimSpec(name="Test", actors=[a1, a2])
        assert len(spec.actors) == 2

    def test_actor_ids_unique_fails(self):
        fixed_id = str(uuid.uuid4())
        a1 = ActorSpec(actor_id=fixed_id, name="Iran")
        a2 = ActorSpec(actor_id=fixed_id, name="Also Iran")
        with pytest.raises(ValidationError, match="actor_ids must be unique"):
            SimSpec(name="Test", actors=[a1, a2])

    def test_metric_env_keys_exist_passes(self):
        spec = SimSpec(
            name="Valid",
            initial_environment={"strait__tension": 0.4},
            metrics=[OutcomeMetricSpec(name="Tension", env_key="strait__tension")],
        )
        assert len(spec.metrics) == 1

    def test_metric_env_keys_exist_fails(self):
        with pytest.raises(ValidationError, match="not in initial_environment"):
            SimSpec(
                name="Invalid",
                initial_environment={"other_key": 0.5},
                metrics=[OutcomeMetricSpec(name="Tension", env_key="strait__tension")],
            )

    def test_no_metrics_no_env_ok(self):
        spec = minimal_spec()
        assert spec.metrics == []

    def test_spec_id_auto_generated(self):
        ids = {minimal_spec().spec_id for _ in range(5)}
        assert len(ids) == 5


# ── TheoryRef ────────────────────────────────────────────────────────────────

class TestTheoryRef:
    def test_defaults(self):
        t = TheoryRef(theory_id="richardson_arms_race")
        assert t.priority == 0
        assert t.parameters == {}

    def test_with_parameters(self):
        t = TheoryRef(
            theory_id="richardson_arms_race",
            priority=1,
            parameters={"k": 0.1, "a": 0.2, "g": 0.05},
        )
        assert t.parameters["k"] == 0.1


# ── SpecDiff ─────────────────────────────────────────────────────────────────

class TestSpecDiff:
    def test_construction(self):
        d = SpecDiff("initial_environment.tension", 0.3, 0.5)
        assert d.field_path == "initial_environment.tension"
        assert d.old_value == 0.3
        assert d.new_value == 0.5

    def test_none_values(self):
        d = SpecDiff("theories.richardson", None, {"k": 0.1})
        assert d.old_value is None


# ── diff_simspecs ─────────────────────────────────────────────────────────────

class TestDiffSimspecs:
    def test_identical_specs_no_diffs(self):
        spec = spec_with_env()
        diffs = diff_simspecs(spec, spec)
        assert diffs == []

    def test_env_value_change(self):
        s1 = spec_with_env()
        s2 = s1.model_copy(
            update={"initial_environment": {**s1.initial_environment, "strait__tension": 0.9}}
        )
        diffs = diff_simspecs(s1, s2)
        tension_diffs = [d for d in diffs if "strait__tension" in d.field_path]
        assert len(tension_diffs) == 1
        assert tension_diffs[0].old_value == 0.4
        assert tension_diffs[0].new_value == 0.9

    def test_env_key_added(self):
        s1 = spec_with_env()
        s2 = s1.model_copy(
            update={"initial_environment": {**s1.initial_environment, "new_key": 0.1}}
        )
        diffs = diff_simspecs(s1, s2)
        new_key_diffs = [d for d in diffs if "new_key" in d.field_path]
        assert len(new_key_diffs) == 1
        assert new_key_diffs[0].old_value is None
        assert new_key_diffs[0].new_value == 0.1

    def test_env_key_removed(self):
        s1 = spec_with_env()
        s2 = s1.model_copy(
            update={"initial_environment": {"iran__military_readiness": 0.7}}
        )
        diffs = diff_simspecs(s1, s2)
        removed = [d for d in diffs if "strait__tension" in d.field_path]
        assert len(removed) == 1
        assert removed[0].old_value == 0.4
        assert removed[0].new_value is None

    def test_theory_added(self):
        s1 = SimSpec(name="T")
        s2 = s1.model_copy(
            update={"theories": [TheoryRef(theory_id="richardson_arms_race", parameters={"k": 0.1})]}
        )
        diffs = diff_simspecs(s1, s2)
        theory_diffs = [d for d in diffs if "richardson_arms_race" in d.field_path]
        assert len(theory_diffs) == 1
        assert theory_diffs[0].old_value is None

    def test_theory_parameter_changed(self):
        t1 = TheoryRef(theory_id="richardson_arms_race", parameters={"k": 0.1, "a": 0.2})
        t2 = TheoryRef(theory_id="richardson_arms_race", parameters={"k": 0.15, "a": 0.2})
        s1 = SimSpec(name="T", theories=[t1])
        s2 = SimSpec(name="T", theories=[t2])
        diffs = diff_simspecs(s1, s2)
        param_diffs = [d for d in diffs if "parameters.k" in d.field_path]
        assert len(param_diffs) == 1
        assert param_diffs[0].old_value == 0.1
        assert param_diffs[0].new_value == 0.15

    def test_timeframe_change(self):
        s1 = SimSpec(name="T", timeframe=TimeframeSpec(total_ticks=365))
        s2 = SimSpec(name="T", timeframe=TimeframeSpec(total_ticks=180))
        diffs = diff_simspecs(s1, s2)
        tf_diffs = [d for d in diffs if "total_ticks" in d.field_path]
        assert len(tf_diffs) == 1
        assert tf_diffs[0].old_value == 365
        assert tf_diffs[0].new_value == 180

    def test_actor_added(self):
        s1 = SimSpec(name="T")
        actor = ActorSpec(name="Iran")
        s2 = SimSpec(name="T", actors=[actor])
        diffs = diff_simspecs(s1, s2)
        actor_diffs = [d for d in diffs if actor.actor_id in d.field_path]
        assert len(actor_diffs) == 1
        assert actor_diffs[0].old_value is None

    def test_actor_removed(self):
        actor = ActorSpec(name="Iran")
        s1 = SimSpec(name="T", actors=[actor])
        s2 = SimSpec(name="T", actors=[])
        diffs = diff_simspecs(s1, s2)
        actor_diffs = [d for d in diffs if actor.actor_id in d.field_path]
        assert len(actor_diffs) == 1
        assert actor_diffs[0].new_value is None


# ── branch_simspec ────────────────────────────────────────────────────────────

class TestBranchSimspec:
    def test_new_spec_id(self):
        base = spec_with_env()
        branch = branch_simspec(base, "post-reform")
        assert branch.spec_id != base.spec_id

    def test_name_includes_branch(self):
        base = SimSpec(name="Hormuz")
        branch = branch_simspec(base, "post-reform")
        assert "post-reform" in branch.name

    def test_change_reason_in_description(self):
        base = SimSpec(name="Hormuz")
        branch = branch_simspec(base, "post-reform", change_reason="sanctions lifted")
        assert "sanctions lifted" in branch.description

    def test_env_preserved(self):
        base = spec_with_env()
        branch = branch_simspec(base, "scenario-b")
        assert branch.initial_environment == base.initial_environment

    def test_base_unchanged(self):
        base = spec_with_env()
        original_id = base.spec_id
        branch_simspec(base, "test")
        assert base.spec_id == original_id

    def test_branch_of_branch(self):
        base = SimSpec(name="Base")
        b1 = branch_simspec(base, "v2")
        b2 = branch_simspec(b1, "v3")
        assert b2.spec_id != b1.spec_id != base.spec_id

    def test_no_reason_ok(self):
        base = SimSpec(name="X")
        branch = branch_simspec(base, "alt")
        assert branch.name  # just doesn't blow up


# ── Serialization round-trip ──────────────────────────────────────────────────

class TestSerialization:
    def test_model_dump_json_round_trip(self):
        spec = SimSpec(
            name="Hormuz",
            domain="geopolitics",
            initial_environment={"iran__military_readiness": 0.7, "strait__tension": 0.4},
            actors=[ActorSpec(name="Iran", initial_env_contributions={"iran__military_readiness": 0.7})],
            theories=[TheoryRef(theory_id="richardson_arms_race", parameters={"k": 0.1})],
            metrics=[OutcomeMetricSpec(name="Tension", env_key="strait__tension")],
            env_key_specs=[EnvKeySpec(key="iran__military_readiness", scale=100, unit="index")],
        )
        json_str = spec.model_dump_json()
        restored = SimSpec.model_validate_json(json_str)
        assert restored.spec_id == spec.spec_id
        assert restored.initial_environment == spec.initial_environment
        assert restored.actors[0].name == "Iran"
        assert restored.theories[0].theory_id == "richardson_arms_race"
        assert restored.env_key_specs[0].scale == 100

    def test_model_dump_round_trip(self):
        spec = minimal_spec()
        d = spec.model_dump()
        restored = SimSpec.model_validate(d)
        assert restored.spec_id == spec.spec_id
