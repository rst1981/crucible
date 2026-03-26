"""
Tests for core/theories/hotelling_cpr.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.hotelling_cpr import HotellingCPR


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "hotelling_cpr" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("hotelling_cpr") is HotellingCPR

    def test_theory_id_attribute(self):
        assert HotellingCPR.theory_id == "hotelling_cpr"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = HotellingCPR()
        assert t.params.discount_rate == 0.05
        assert t.params.sustainable_yield == 0.05
        assert t.params.critical_threshold == 0.20
        assert t.params.initial_extraction_rate == 0.05
        assert t.params.resource_id == "resource"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = HotellingCPR(parameters={"discount_rate": 0.10, "resource_id": "oil"})
        assert t.params.discount_rate == 0.10
        assert t.params.resource_id == "oil"

    def test_discount_rate_above_max_rejected(self):
        with pytest.raises(Exception):
            HotellingCPR(parameters={"discount_rate": 0.6})

    def test_sustainable_yield_above_one_rejected(self):
        with pytest.raises(Exception):
            HotellingCPR(parameters={"sustainable_yield": 1.5})

    def test_critical_threshold_above_one_rejected(self):
        with pytest.raises(Exception):
            HotellingCPR(parameters={"critical_threshold": 1.1})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = HotellingCPR().state_variables
        assert "resource__stock"          in sv.writes
        assert "resource__scarcity_rent"  in sv.writes
        assert "resource__depletion_risk" in sv.writes
        assert "resource__overharvesting" in sv.writes

    def test_extraction_rate_not_in_writes(self):
        # extraction_rate is owned by agents, not this theory
        assert "resource__extraction_rate" not in HotellingCPR().state_variables.writes

    def test_extraction_rate_in_initializes(self):
        assert "resource__extraction_rate" in HotellingCPR().state_variables.initializes

    def test_governance_effectiveness_in_initializes(self):
        assert "resource__governance_effectiveness" in HotellingCPR().state_variables.initializes

    def test_custom_resource_id_reflected_in_keys(self):
        t = HotellingCPR(parameters={"resource_id": "oil"})
        sv = t.state_variables
        assert "oil__stock"          in sv.writes
        assert "resource__stock"     not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_stock_at_full(self):
        inits = HotellingCPR().setup({})
        assert inits["resource__stock"] == pytest.approx(1.0)

    def test_seeds_extraction_rate_at_default(self):
        t = HotellingCPR(parameters={"initial_extraction_rate": 0.08})
        inits = t.setup({})
        assert inits["resource__extraction_rate"] == pytest.approx(0.08)

    def test_seeds_governance_at_moderate(self):
        inits = HotellingCPR().setup({})
        assert inits["resource__governance_effectiveness"] == pytest.approx(0.5)

    def test_does_not_overwrite_existing_stock(self):
        env = {"resource__stock": 0.6}
        inits = HotellingCPR().setup(env)
        assert "resource__stock" not in inits

    def test_does_not_overwrite_existing_extraction_rate(self):
        env = {"resource__extraction_rate": 0.10}
        inits = HotellingCPR().setup(env)
        assert "resource__extraction_rate" not in inits


# ── update() — core Hotelling + CPR logic ─────────────────────────────────────

class TestUpdate:
    def _env(self, S=0.8, rent=0.0, extraction=0.05, governance=0.5) -> dict[str, float]:
        return {
            "resource__stock":                   S,
            "resource__scarcity_rent":           rent,
            "resource__extraction_rate":         extraction,
            "resource__governance_effectiveness": governance,
        }

    def test_returns_all_four_keys(self):
        delta = HotellingCPR().update(self._env(), [], 0)
        assert "resource__stock"          in delta
        assert "resource__scarcity_rent"  in delta
        assert "resource__depletion_risk" in delta
        assert "resource__overharvesting" in delta

    def test_does_not_mutate_env(self):
        env = self._env(S=0.8, extraction=0.05)
        HotellingCPR().update(env, [], 0)
        assert env["resource__stock"] == pytest.approx(0.8)
        assert env["resource__extraction_rate"] == pytest.approx(0.05)

    def test_outputs_clamped_to_0_1(self):
        delta = HotellingCPR().update(self._env(S=0.5, rent=0.9, extraction=0.5), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_stock_decreases_with_extraction(self):
        delta = HotellingCPR().update(self._env(S=0.8, extraction=0.10), [], 0)
        assert delta["resource__stock"] < 0.8

    def test_zero_extraction_no_stock_change(self):
        delta = HotellingCPR().update(self._env(S=0.8, extraction=0.0), [], 0)
        assert delta["resource__stock"] == pytest.approx(0.8)

    def test_stock_never_goes_negative(self):
        # Very high extraction over many ticks
        t = HotellingCPR(parameters={"initial_extraction_rate": 0.5, "sustainable_yield": 1.0})
        env = self._env(S=0.1, extraction=0.5, governance=0.0)
        for _ in range(20):
            env.update(t.update(env, [], 0))
        assert env["resource__stock"] >= 0.0

    def test_full_governance_caps_at_sustainable_yield(self):
        # With governance=1.0, effective extraction = sustainable_yield
        t = HotellingCPR(parameters={"sustainable_yield": 0.03})
        delta = t.update(self._env(S=0.8, extraction=0.20, governance=1.0), [], 0)
        # stock should drop by exactly sustainable_yield * dt
        expected_S = 0.8 - 0.03 * 1.0
        assert delta["resource__stock"] == pytest.approx(expected_S, abs=1e-9)

    def test_zero_governance_uses_raw_extraction(self):
        # With governance=0.0, effective extraction = raw extraction
        t = HotellingCPR()
        env = self._env(S=0.8, extraction=0.10, governance=0.0)
        delta = t.update(env, [], 0)
        expected_S = 0.8 - 0.10 * 1.0
        assert delta["resource__stock"] == pytest.approx(expected_S, abs=1e-9)

    def test_overharvesting_flag_set_when_extraction_exceeds_sustainable(self):
        t = HotellingCPR(parameters={"sustainable_yield": 0.03})
        delta = t.update(self._env(extraction=0.20, governance=0.0), [], 0)
        assert delta["resource__overharvesting"] == pytest.approx(1.0)

    def test_overharvesting_flag_clear_when_within_sustainable_yield(self):
        t = HotellingCPR(parameters={"sustainable_yield": 0.10})
        delta = t.update(self._env(extraction=0.05, governance=0.0), [], 0)
        assert delta["resource__overharvesting"] == pytest.approx(0.0)

    def test_scarcity_rent_grows_over_time(self):
        # Rent should grow each tick via Hotelling price path
        t = HotellingCPR(parameters={"discount_rate": 0.10})
        env = self._env(S=0.8, rent=0.10)
        delta = t.update(env, [], 0)
        assert delta["resource__scarcity_rent"] >= 0.10

    def test_depleted_stock_raises_rent(self):
        # Low stock → high stock_signal → higher rent
        t = HotellingCPR()
        d_high_S = t.update(self._env(S=0.9, rent=0.0), [], 0)
        d_low_S  = t.update(self._env(S=0.1, rent=0.0), [], 0)
        assert d_low_S["resource__scarcity_rent"] > d_high_S["resource__scarcity_rent"]

    def test_depletion_risk_zero_above_threshold(self):
        # S > critical_threshold → depletion_risk = 0
        t = HotellingCPR(parameters={"critical_threshold": 0.20})
        delta = t.update(self._env(S=0.5), [], 0)
        assert delta["resource__depletion_risk"] == pytest.approx(0.0)

    def test_depletion_risk_rises_below_threshold(self):
        # S < critical_threshold → depletion_risk > 0
        t = HotellingCPR(parameters={"critical_threshold": 0.30})
        delta = t.update(self._env(S=0.10, extraction=0.0), [], 0)
        assert delta["resource__depletion_risk"] > 0.0

    def test_depletion_risk_one_at_zero_stock(self):
        # S → 0 → depletion_risk → 1.0
        t = HotellingCPR(parameters={"critical_threshold": 0.50})
        delta = t.update(self._env(S=0.001, extraction=0.0), [], 0)
        assert delta["resource__depletion_risk"] == pytest.approx(1.0, abs=0.01)

    def test_higher_governance_slows_depletion(self):
        # Higher governance → effective extraction closer to sustainable_yield → stock depletes slower
        t = HotellingCPR(parameters={"sustainable_yield": 0.02})
        d_low_gov  = t.update(self._env(S=0.8, extraction=0.20, governance=0.0), [], 0)
        d_high_gov = t.update(self._env(S=0.8, extraction=0.20, governance=1.0), [], 0)
        assert d_high_gov["resource__stock"] > d_low_gov["resource__stock"]

    def test_tick_unit_month_smaller_depletion_than_year(self):
        env = self._env(S=0.8, extraction=0.10, governance=0.0)
        d_year  = HotellingCPR(parameters={"tick_unit": "year"}).update(env, [], 0)
        d_month = HotellingCPR(parameters={"tick_unit": "month"}).update(env, [], 0)
        # Monthly tick: dt=1/12, so smaller dQ per tick → less stock consumed
        assert d_month["resource__stock"] > d_year["resource__stock"]

    def test_custom_resource_id_in_output(self):
        t = HotellingCPR(parameters={"resource_id": "oil"})
        delta = t.update(
            {"oil__stock": 0.8, "oil__scarcity_rent": 0.0,
             "oil__extraction_rate": 0.05, "oil__governance_effectiveness": 0.5},
            [], 0,
        )
        assert "oil__stock"      in delta
        assert "resource__stock" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = HotellingCPR().update({}, [], 0)
        assert 0.0 <= delta["resource__stock"] <= 1.0
        assert 0.0 <= delta["resource__scarcity_rent"] <= 1.0
