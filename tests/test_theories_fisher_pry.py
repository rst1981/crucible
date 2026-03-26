"""
Tests for core/theories/fisher_pry.py

Covers: Fisher-Pry (1971) logistic technology substitution model.
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.fisher_pry import FisherPry


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "fisher_pry" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("fisher_pry") is FisherPry

    def test_theory_id_attribute(self):
        assert FisherPry.theory_id == "fisher_pry"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = FisherPry()
        assert t.params.substitution_rate == pytest.approx(0.30)
        assert t.params.cost_sensitivity  == pytest.approx(0.50)
        assert t.params.gdp_sensitivity   == pytest.approx(0.30)
        assert t.params.tech_id   == "fisher"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = FisherPry(parameters={"substitution_rate": 0.50, "tech_id": "ev"})
        assert t.params.substitution_rate == pytest.approx(0.50)
        assert t.params.tech_id == "ev"

    def test_substitution_rate_at_zero_rejected(self):
        # ge=0.01 means 0.0 is below minimum — should raise
        with pytest.raises(Exception):
            FisherPry(parameters={"substitution_rate": 0.0})

    def test_substitution_rate_above_maximum_rejected(self):
        with pytest.raises(Exception):
            FisherPry(parameters={"substitution_rate": 2.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = FisherPry().state_variables
        assert "fisher__new_tech_share"    in sv.writes
        assert "fisher__old_tech_share"    in sv.writes
        assert "fisher__substitution_flow" in sv.writes
        assert "fisher__takeoff_index"     in sv.writes

    def test_cost_reduction_not_in_writes(self):
        # cost_reduction is owned by experience_curve or agents
        assert "fisher__cost_reduction" not in FisherPry().state_variables.writes

    def test_cost_reduction_in_initializes(self):
        assert "fisher__cost_reduction" in FisherPry().state_variables.initializes

    def test_custom_tech_id_reflected_in_keys(self):
        t = FisherPry(parameters={"tech_id": "ev"})
        sv = t.state_variables
        assert "ev__new_tech_share" in sv.writes
        assert "fisher__new_tech_share" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_new_tech_share_at_0_01(self):
        inits = FisherPry().setup({})
        assert inits["fisher__new_tech_share"] == pytest.approx(0.01)

    def test_seeds_cost_reduction_at_zero(self):
        inits = FisherPry().setup({})
        assert inits["fisher__cost_reduction"] == pytest.approx(0.0)

    def test_does_not_overwrite_existing_new_tech_share(self):
        env = {"fisher__new_tech_share": 0.40}
        inits = FisherPry().setup(env)
        assert "fisher__new_tech_share" not in inits

    def test_does_not_overwrite_existing_cost_reduction(self):
        env = {"fisher__cost_reduction": 0.25}
        inits = FisherPry().setup(env)
        assert "fisher__cost_reduction" not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, f: float = 0.01, cost_reduction: float = 0.0,
             gdp: float = 0.50, tech_id: str = "fisher") -> dict[str, float]:
        return {
            f"{tech_id}__new_tech_share": f,
            f"{tech_id}__cost_reduction": cost_reduction,
            "keynesian__gdp_normalized": gdp,
        }

    def test_returns_four_keys(self):
        delta = FisherPry().update(self._env(), [], 0)
        assert "fisher__new_tech_share"    in delta
        assert "fisher__old_tech_share"    in delta
        assert "fisher__substitution_flow" in delta
        assert "fisher__takeoff_index"     in delta

    def test_does_not_mutate_env(self):
        env = self._env(f=0.20)
        original_f = env["fisher__new_tech_share"]
        FisherPry().update(env, [], 0)
        assert env["fisher__new_tech_share"] == pytest.approx(original_f)

    def test_outputs_clamped_to_0_1(self):
        t = FisherPry(parameters={"substitution_rate": 2.0})
        for f in [0.01, 0.25, 0.50, 0.75, 0.99]:
            delta = t.update(self._env(f=f), [], 0)
            for v in delta.values():
                assert 0.0 <= v <= 1.0, f"value {v} out of range at f={f}"

    def test_new_plus_old_share_equals_one(self):
        delta = FisherPry().update(self._env(f=0.30), [], 0)
        assert delta["fisher__new_tech_share"] + delta["fisher__old_tech_share"] == pytest.approx(1.0, abs=1e-9)

    def test_new_tech_share_increases_each_tick(self):
        # Logistic growth: f should increase when f < 0.5
        t = FisherPry()
        env = self._env(f=0.20)
        for _ in range(5):
            delta = t.update(env, [], 0)
            assert delta["fisher__new_tech_share"] > env["fisher__new_tech_share"]
            env = {**env, **delta}

    def test_substitution_flow_positive_when_f_in_interior(self):
        delta = FisherPry().update(self._env(f=0.30), [], 0)
        assert delta["fisher__substitution_flow"] > 0.0

    def test_takeoff_index_peaks_near_f_half(self):
        # 4 × 0.5 × 0.5 = 1.0; near maximum at f=0.5
        t = FisherPry(parameters={"substitution_rate": 0.01})  # tiny step so f≈0.5 after update
        delta = t.update(self._env(f=0.50), [], 0)
        assert delta["fisher__takeoff_index"] > 0.99

    def test_takeoff_index_near_zero_at_f_extremes(self):
        t = FisherPry(parameters={"substitution_rate": 0.01})
        d_low  = t.update(self._env(f=0.01), [], 0)
        d_high = t.update(self._env(f=0.99), [], 0)
        assert d_low["fisher__takeoff_index"] < 0.10
        assert d_high["fisher__takeoff_index"] < 0.10

    def test_cost_reduction_accelerates_substitution(self):
        t = FisherPry()
        d_base = t.update(self._env(f=0.10, cost_reduction=0.0), [], 0)
        d_boost = t.update(self._env(f=0.10, cost_reduction=0.50), [], 0)
        assert d_boost["fisher__new_tech_share"] > d_base["fisher__new_tech_share"]

    def test_gdp_boom_accelerates_substitution(self):
        t = FisherPry()
        d_base = t.update(self._env(f=0.10, gdp=0.50), [], 0)
        d_boom = t.update(self._env(f=0.10, gdp=0.90), [], 0)
        assert d_boom["fisher__new_tech_share"] > d_base["fisher__new_tech_share"]

    def test_multi_tick_f_exceeds_half_after_enough_ticks(self):
        # substitution_rate=0.30, t_half = ln(2)/0.30 ≈ 2.3 years
        # After 30 ticks (years), f starting at 0.01 should exceed 0.5
        t = FisherPry(parameters={"substitution_rate": 0.30})
        env = self._env(f=0.01, gdp=0.50)
        for _ in range(30):
            delta = t.update(env, [], 0)
            env = {**env, **delta}
        assert env["fisher__new_tech_share"] > 0.50

    def test_custom_tech_id_in_output(self):
        t = FisherPry(parameters={"tech_id": "solar_pv"})
        delta = t.update(self._env(f=0.10, tech_id="solar_pv"), [], 0)
        assert "solar_pv__new_tech_share" in delta
        assert "fisher__new_tech_share" not in delta

    def test_missing_env_keys_default_gracefully(self):
        # No env keys provided; should use defaults and return valid outputs
        delta = FisherPry().update({}, [], 0)
        assert 0.0 <= delta["fisher__new_tech_share"] <= 1.0
        assert 0.0 <= delta["fisher__old_tech_share"] <= 1.0
        assert 0.0 <= delta["fisher__substitution_flow"] <= 1.0
        assert 0.0 <= delta["fisher__takeoff_index"] <= 1.0

    def test_reads_keynesian_gdp_normalized_from_env(self):
        # Higher GDP above 0.5 should accelerate substitution vs. GDP at 0.5
        t = FisherPry(parameters={"gdp_sensitivity": 0.50})
        d_neutral = t.update({"fisher__new_tech_share": 0.20, "fisher__cost_reduction": 0.0,
                               "keynesian__gdp_normalized": 0.50}, [], 0)
        d_boom    = t.update({"fisher__new_tech_share": 0.20, "fisher__cost_reduction": 0.0,
                               "keynesian__gdp_normalized": 0.80}, [], 0)
        assert d_boom["fisher__new_tech_share"] > d_neutral["fisher__new_tech_share"]
