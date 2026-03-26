"""
Tests for core/theories/regulatory_shock.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.regulatory_shock import RegulatoryShock


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "regulatory_shock" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("regulatory_shock") is RegulatoryShock

    def test_theory_id_attribute(self):
        assert RegulatoryShock.theory_id == "regulatory_shock"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = RegulatoryShock()
        assert t.params.cost_sensitivity == 0.60
        assert t.params.adaptation_rate == 0.15
        assert t.params.firm_resilience == 0.20
        assert t.params.regulation_id == "regulation"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = RegulatoryShock(parameters={"adaptation_rate": 0.3, "regulation_id": "carbon_tax"})
        assert t.params.adaptation_rate == 0.3
        assert t.params.regulation_id == "carbon_tax"

    def test_cost_sensitivity_above_one_rejected(self):
        with pytest.raises(Exception):
            RegulatoryShock(parameters={"cost_sensitivity": 1.5})

    def test_incumbent_advantage_above_one_rejected(self):
        with pytest.raises(Exception):
            RegulatoryShock(parameters={"incumbent_advantage_factor": 1.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = RegulatoryShock().state_variables
        assert "regulation__compliance_cost"       in sv.writes
        assert "regulation__adaptation_level"      in sv.writes
        assert "regulation__market_exit_risk"      in sv.writes
        assert "regulation__competitive_advantage" in sv.writes

    def test_shock_magnitude_not_in_writes(self):
        # shock is owned by agents/events, not this theory
        assert "regulation__shock_magnitude" not in RegulatoryShock().state_variables.writes

    def test_shock_magnitude_in_initializes(self):
        assert "regulation__shock_magnitude" in RegulatoryShock().state_variables.initializes

    def test_reads_gdp_and_porter(self):
        sv = RegulatoryShock().state_variables
        assert "keynesian__gdp_normalized"  in sv.reads
        assert "porter__barriers_to_entry"  in sv.reads

    def test_custom_regulation_id_reflected_in_keys(self):
        t = RegulatoryShock(parameters={"regulation_id": "carbon_tax"})
        sv = t.state_variables
        assert "carbon_tax__compliance_cost" in sv.writes
        assert "regulation__compliance_cost" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_shock_at_zero(self):
        inits = RegulatoryShock().setup({})
        assert inits["regulation__shock_magnitude"] == 0.0

    def test_seeds_adaptation_at_zero(self):
        inits = RegulatoryShock().setup({})
        assert inits["regulation__adaptation_level"] == 0.0

    def test_does_not_overwrite_existing_adaptation(self):
        inits = RegulatoryShock().setup({"regulation__adaptation_level": 0.7})
        assert "regulation__adaptation_level" not in inits


# ── update() — core dynamics ──────────────────────────────────────────────────

class TestUpdate:
    def _env(self, shock=0.0, adaptation=0.0, gdp=0.5, barriers=0.5):
        return {
            "regulation__shock_magnitude":  shock,
            "regulation__adaptation_level": adaptation,
            "keynesian__gdp_normalized":    gdp,
            "porter__barriers_to_entry":    barriers,
        }

    def test_returns_all_four_keys(self):
        delta = RegulatoryShock().update(self._env(), [], 0)
        assert "regulation__compliance_cost"       in delta
        assert "regulation__adaptation_level"      in delta
        assert "regulation__market_exit_risk"      in delta
        assert "regulation__competitive_advantage" in delta

    def test_does_not_mutate_env(self):
        env = self._env(shock=0.8, adaptation=0.2)
        RegulatoryShock().update(env, [], 0)
        assert env["regulation__shock_magnitude"]  == pytest.approx(0.8)
        assert env["regulation__adaptation_level"] == pytest.approx(0.2)

    def test_outputs_clamped_to_0_1(self):
        t = RegulatoryShock(parameters={"cost_sensitivity": 1.0,
                                         "incumbent_advantage_factor": 1.0})
        delta = t.update(self._env(shock=1.0, adaptation=0.0, barriers=1.0), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_zero_shock_zero_compliance_cost(self):
        delta = RegulatoryShock().update(self._env(shock=0.0), [], 0)
        assert delta["regulation__compliance_cost"] == pytest.approx(0.0, abs=1e-9)

    def test_zero_shock_zero_exit_risk(self):
        delta = RegulatoryShock().update(self._env(shock=0.0), [], 0)
        assert delta["regulation__market_exit_risk"] == pytest.approx(0.0, abs=1e-9)

    def test_high_shock_high_compliance_cost(self):
        delta = RegulatoryShock().update(self._env(shock=1.0, adaptation=0.0), [], 0)
        assert delta["regulation__compliance_cost"] > 0.3

    def test_compliance_cost_falls_as_adaptation_rises(self):
        t = RegulatoryShock()
        d_low_adapt  = t.update(self._env(shock=0.8, adaptation=0.1), [], 0)
        d_high_adapt = t.update(self._env(shock=0.8, adaptation=0.9), [], 0)
        assert d_high_adapt["regulation__compliance_cost"] < d_low_adapt["regulation__compliance_cost"]

    def test_adaptation_increases_each_tick(self):
        t = RegulatoryShock(parameters={"adaptation_rate": 0.2})
        env = self._env(shock=0.8, adaptation=0.0)
        prev = 0.0
        for _ in range(10):
            delta = t.update(env, [], 0)
            env.update(delta)
            assert env["regulation__adaptation_level"] > prev
            prev = env["regulation__adaptation_level"]

    def test_adaptation_bounded_at_one(self):
        t = RegulatoryShock(parameters={"adaptation_rate": 1.0})
        env = self._env(shock=1.0, adaptation=0.99)
        for _ in range(20):
            delta = t.update(env, [], 0)
            env.update(delta)
        assert env["regulation__adaptation_level"] <= 1.0

    def test_exit_risk_zero_below_resilience_threshold(self):
        t = RegulatoryShock(parameters={"firm_resilience": 0.5, "cost_sensitivity": 0.4})
        # compliance_cost = 0.5 * 0.4 = 0.2 < resilience=0.5 → no exit risk
        delta = t.update(self._env(shock=0.5, adaptation=0.0), [], 0)
        assert delta["regulation__market_exit_risk"] == pytest.approx(0.0, abs=1e-9)

    def test_exit_risk_positive_above_resilience_threshold(self):
        t = RegulatoryShock(parameters={"firm_resilience": 0.1, "cost_sensitivity": 1.0})
        delta = t.update(self._env(shock=1.0, adaptation=0.0), [], 0)
        assert delta["regulation__market_exit_risk"] > 0.0

    def test_gdp_recession_slows_adaptation(self):
        t = RegulatoryShock(parameters={"gdp_adaptation_sensitivity": 0.8})
        d_boom     = t.update(self._env(shock=0.8, adaptation=0.0, gdp=0.8), [], 0)
        d_recession = t.update(self._env(shock=0.8, adaptation=0.0, gdp=0.2), [], 0)
        assert d_recession["regulation__adaptation_level"] < d_boom["regulation__adaptation_level"]

    def test_high_barriers_amplify_competitive_advantage(self):
        t = RegulatoryShock(parameters={"incumbent_advantage_factor": 0.5})
        d_low  = t.update(self._env(shock=0.8, adaptation=0.0, barriers=0.1), [], 0)
        d_high = t.update(self._env(shock=0.8, adaptation=0.0, barriers=0.9), [], 0)
        assert d_high["regulation__competitive_advantage"] > d_low["regulation__competitive_advantage"]

    def test_full_adaptation_eliminates_compliance_burden(self):
        # After full adaptation, compliance cost → 0 regardless of shock magnitude
        delta = RegulatoryShock().update(self._env(shock=1.0, adaptation=1.0), [], 0)
        assert delta["regulation__compliance_cost"] == pytest.approx(0.0, abs=1e-9)
        assert delta["regulation__market_exit_risk"] == pytest.approx(0.0, abs=1e-9)

    def test_custom_regulation_id_in_output(self):
        t = RegulatoryShock(parameters={"regulation_id": "carbon_tax"})
        delta = t.update(
            {"carbon_tax__shock_magnitude": 0.5, "carbon_tax__adaptation_level": 0.0},
            [], 0,
        )
        assert "carbon_tax__compliance_cost" in delta
        assert "regulation__compliance_cost" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = RegulatoryShock().update({}, [], 0)
        assert delta["regulation__compliance_cost"] == pytest.approx(0.0, abs=1e-9)
