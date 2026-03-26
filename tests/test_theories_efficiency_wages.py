"""
Tests for core/theories/efficiency_wages.py

Covers: Shapiro-Stiglitz efficiency wages / no-shirking condition model.
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.efficiency_wages import EfficiencyWages


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "efficiency_wages" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("efficiency_wages") is EfficiencyWages

    def test_theory_id_attribute(self):
        assert EfficiencyWages.theory_id == "efficiency_wages"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = EfficiencyWages()
        assert t.params.monitoring_intensity == pytest.approx(0.40)
        assert t.params.separation_rate == pytest.approx(0.05)
        assert t.params.effort_cost == pytest.approx(0.30)
        assert t.params.base_effort == pytest.approx(0.20)
        assert t.params.wage_adjustment_speed == pytest.approx(0.40)
        assert t.params.labor_id == "labor"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = EfficiencyWages(parameters={"monitoring_intensity": 0.60, "labor_id": "skilled"})
        assert t.params.monitoring_intensity == pytest.approx(0.60)
        assert t.params.labor_id == "skilled"

    def test_monitoring_intensity_above_one_rejected(self):
        with pytest.raises(Exception):
            EfficiencyWages(parameters={"monitoring_intensity": 1.1})

    def test_effort_cost_at_zero_rejected(self):
        # ge=0.01 means 0.0 is below the minimum — should raise
        with pytest.raises(Exception):
            EfficiencyWages(parameters={"effort_cost": 0.0})

    def test_separation_rate_above_maximum_rejected(self):
        with pytest.raises(Exception):
            EfficiencyWages(parameters={"separation_rate": 0.35})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = EfficiencyWages().state_variables
        assert "labor__effort_level"      in sv.writes
        assert "labor__shirking_rate"     in sv.writes
        assert "labor__unemployment_rate" in sv.writes
        assert "labor__productivity"      in sv.writes

    def test_wage_premium_not_in_writes(self):
        # wage_premium is owned by agents/firms, not written by this theory
        assert "labor__wage_premium" not in EfficiencyWages().state_variables.writes

    def test_wage_premium_in_initializes(self):
        assert "labor__wage_premium" in EfficiencyWages().state_variables.initializes

    def test_custom_labor_id_reflected_in_keys(self):
        t = EfficiencyWages(parameters={"labor_id": "skilled"})
        sv = t.state_variables
        assert "skilled__effort_level" in sv.writes
        assert "labor__effort_level" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_effort_level_at_base_effort(self):
        t = EfficiencyWages(parameters={"base_effort": 0.15})
        inits = t.setup({})
        assert inits["labor__effort_level"] == pytest.approx(0.15)

    def test_seeds_wage_premium_at_1_20(self):
        inits = EfficiencyWages().setup({})
        assert inits["labor__wage_premium"] == pytest.approx(1.20)

    def test_seeds_unemployment_rate(self):
        inits = EfficiencyWages().setup({})
        assert "labor__unemployment_rate" in inits
        assert inits["labor__unemployment_rate"] == pytest.approx(0.05)

    def test_does_not_overwrite_existing_values(self):
        env = {"labor__effort_level": 0.80, "labor__wage_premium": 1.50}
        inits = EfficiencyWages().setup(env)
        assert "labor__effort_level" not in inits
        assert "labor__wage_premium" not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, wage_premium: float = 1.20, labor_id: str = "labor") -> dict[str, float]:
        return {f"{labor_id}__wage_premium": wage_premium}

    def test_returns_four_keys(self):
        delta = EfficiencyWages().update(self._env(), [], 0)
        assert "labor__effort_level"      in delta
        assert "labor__shirking_rate"     in delta
        assert "labor__unemployment_rate" in delta
        assert "labor__productivity"      in delta

    def test_does_not_mutate_env(self):
        env = self._env(wage_premium=1.20)
        original_wp = env["labor__wage_premium"]
        EfficiencyWages().update(env, [], 0)
        assert env["labor__wage_premium"] == pytest.approx(original_wp)

    def test_outputs_clamped_to_0_1(self):
        t = EfficiencyWages()
        for wp in [0.5, 1.0, 1.5, 2.0, 3.0]:
            delta = t.update({"labor__wage_premium": wp}, [], 0)
            for v in delta.values():
                assert 0.0 <= v <= 1.0, f"value {v} out of range for wage_premium={wp}"

    def test_higher_wage_premium_reduces_shirking_rate(self):
        t = EfficiencyWages()
        d_low  = t.update(self._env(wage_premium=1.05), [], 0)
        d_high = t.update(self._env(wage_premium=1.60), [], 0)
        assert d_high["labor__shirking_rate"] < d_low["labor__shirking_rate"]

    def test_higher_wage_premium_reduces_unemployment_rate(self):
        # Higher wage premium → larger excess wage → less unemployment needed to discipline workers
        t = EfficiencyWages()
        d_low  = t.update(self._env(wage_premium=1.10), [], 0)
        d_high = t.update(self._env(wage_premium=1.80), [], 0)
        assert d_high["labor__unemployment_rate"] < d_low["labor__unemployment_rate"]

    def test_higher_monitoring_reduces_shirking(self):
        env = self._env(wage_premium=1.20)
        t_low  = EfficiencyWages(parameters={"monitoring_intensity": 0.10})
        t_high = EfficiencyWages(parameters={"monitoring_intensity": 0.80})
        d_low  = t_low.update(env, [], 0)
        d_high = t_high.update(env, [], 0)
        assert d_high["labor__shirking_rate"] < d_low["labor__shirking_rate"]

    def test_shirking_rate_equals_one_minus_effort_level(self):
        delta = EfficiencyWages().update(self._env(wage_premium=1.30), [], 0)
        assert delta["labor__shirking_rate"] == pytest.approx(
            1.0 - delta["labor__effort_level"], abs=1e-9
        )

    def test_productivity_at_most_effort_level(self):
        # productivity = effort × (1 - unemployment) ≤ effort
        delta = EfficiencyWages().update(self._env(wage_premium=1.20), [], 0)
        assert delta["labor__productivity"] <= delta["labor__effort_level"] + 1e-9

    def test_very_high_wage_premium_effort_approaches_one(self):
        # At very high wage premium, NSC incentive is large → effort approaches 1
        t = EfficiencyWages(parameters={"monitoring_intensity": 0.80, "effort_cost": 0.10})
        delta = t.update({"labor__wage_premium": 2.0}, [], 0)
        assert delta["labor__effort_level"] > 0.95

    def test_custom_labor_id_in_output(self):
        t = EfficiencyWages(parameters={"labor_id": "unskilled"})
        delta = t.update({"unskilled__wage_premium": 1.30}, [], 0)
        assert "unskilled__effort_level" in delta
        assert "labor__effort_level" not in delta

    def test_missing_env_keys_default_gracefully(self):
        # No env keys provided; should use defaults and return valid outputs
        delta = EfficiencyWages().update({}, [], 0)
        assert 0.0 <= delta["labor__effort_level"] <= 1.0
        assert 0.0 <= delta["labor__shirking_rate"] <= 1.0
        assert 0.0 <= delta["labor__unemployment_rate"] <= 1.0
        assert 0.0 <= delta["labor__productivity"] <= 1.0
