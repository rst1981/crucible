"""
Tests for core/theories/minsky_instability.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.minsky_instability import MinskyInstability


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "minsky_instability" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("minsky_instability") is MinskyInstability

    def test_theory_id_attribute(self):
        assert MinskyInstability.theory_id == "minsky_instability"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = MinskyInstability()
        assert t.params.erosion_rate == pytest.approx(0.10)
        assert t.params.escalation_rate == pytest.approx(0.15)
        assert t.params.deleveraging_rate == pytest.approx(0.20)
        assert t.params.interest_sensitivity == pytest.approx(0.50)
        assert t.params.boom_sensitivity == pytest.approx(0.50)
        assert t.params.crash_threshold == pytest.approx(0.30)
        assert t.params.tick_unit == "year"
        assert t.params.cycle_id == "minsky"

    def test_parameter_overrides(self):
        t = MinskyInstability(parameters={"erosion_rate": 0.25, "cycle_id": "corporate"})
        assert t.params.erosion_rate == pytest.approx(0.25)
        assert t.params.cycle_id == "corporate"

    def test_erosion_rate_above_one_rejected(self):
        with pytest.raises(Exception):
            MinskyInstability(parameters={"erosion_rate": 1.5})

    def test_crash_threshold_below_minimum_rejected(self):
        with pytest.raises(Exception):
            MinskyInstability(parameters={"crash_threshold": 0.02})

    def test_crash_threshold_above_maximum_rejected(self):
        with pytest.raises(Exception):
            MinskyInstability(parameters={"crash_threshold": 0.90})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_five_keys(self):
        sv = MinskyInstability().state_variables
        assert "minsky__hedge_fraction" in sv.writes
        assert "minsky__speculative_fraction" in sv.writes
        assert "minsky__ponzi_fraction" in sv.writes
        assert "minsky__financial_fragility" in sv.writes
        assert "minsky__crash_risk" in sv.writes

    def test_interest_rate_not_in_writes(self):
        sv = MinskyInstability().state_variables
        assert "minsky__interest_rate" not in sv.writes

    def test_interest_rate_in_initializes(self):
        sv = MinskyInstability().state_variables
        assert "minsky__interest_rate" in sv.initializes

    def test_asset_appreciation_in_initializes(self):
        sv = MinskyInstability().state_variables
        assert "minsky__asset_appreciation" in sv.initializes

    def test_custom_cycle_id_reflected_in_keys(self):
        t = MinskyInstability(parameters={"cycle_id": "sovereign"})
        sv = t.state_variables
        assert "sovereign__hedge_fraction" in sv.writes
        assert "minsky__hedge_fraction" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_hedge_fraction_at_0_70(self):
        inits = MinskyInstability().setup({})
        assert inits["minsky__hedge_fraction"] == pytest.approx(0.70)

    def test_seeds_speculative_fraction_at_0_20(self):
        inits = MinskyInstability().setup({})
        assert inits["minsky__speculative_fraction"] == pytest.approx(0.20)

    def test_seeds_ponzi_fraction_at_0_10(self):
        inits = MinskyInstability().setup({})
        assert inits["minsky__ponzi_fraction"] == pytest.approx(0.10)

    def test_seeds_interest_rate_at_0_05(self):
        inits = MinskyInstability().setup({})
        assert inits["minsky__interest_rate"] == pytest.approx(0.05)

    def test_does_not_overwrite_existing_keys(self):
        env = {
            "minsky__hedge_fraction": 0.50,
            "minsky__speculative_fraction": 0.30,
            "minsky__ponzi_fraction": 0.20,
        }
        inits = MinskyInstability().setup(env)
        assert "minsky__hedge_fraction" not in inits
        assert "minsky__speculative_fraction" not in inits
        assert "minsky__ponzi_fraction" not in inits


# ── update() ──────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(
        self,
        H=0.70,
        S=0.20,
        P=0.10,
        interest_rate=0.05,
        asset_appreciation=0.05,
    ) -> dict[str, float]:
        return {
            "minsky__hedge_fraction": H,
            "minsky__speculative_fraction": S,
            "minsky__ponzi_fraction": P,
            "minsky__interest_rate": interest_rate,
            "minsky__asset_appreciation": asset_appreciation,
        }

    def test_returns_all_five_keys(self):
        delta = MinskyInstability().update(self._env(), [], 0)
        assert "minsky__hedge_fraction" in delta
        assert "minsky__speculative_fraction" in delta
        assert "minsky__ponzi_fraction" in delta
        assert "minsky__financial_fragility" in delta
        assert "minsky__crash_risk" in delta

    def test_does_not_mutate_env(self):
        env = self._env(H=0.70, S=0.20, P=0.10)
        MinskyInstability().update(env, [], 0)
        assert env["minsky__hedge_fraction"] == pytest.approx(0.70)
        assert env["minsky__speculative_fraction"] == pytest.approx(0.20)
        assert env["minsky__ponzi_fraction"] == pytest.approx(0.10)

    def test_outputs_clamped_to_0_1(self):
        t = MinskyInstability()
        delta = t.update(self._env(), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_compartments_sum_to_one(self):
        delta = MinskyInstability().update(self._env(), [], 0)
        total = (
            delta["minsky__hedge_fraction"]
            + delta["minsky__speculative_fraction"]
            + delta["minsky__ponzi_fraction"]
        )
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_boom_accelerates_hedge_erosion(self):
        # Higher asset_appreciation → more hedge→spec migration → lower hedge
        t = MinskyInstability()
        delta_low  = t.update(self._env(asset_appreciation=0.05), [], 0)
        delta_high = t.update(self._env(asset_appreciation=0.40), [], 0)
        assert delta_high["minsky__hedge_fraction"] < delta_low["minsky__hedge_fraction"]

    def test_stress_accelerates_ponzi_growth(self):
        # Higher interest_rate → more spec→Ponzi migration → higher Ponzi fraction
        t = MinskyInstability()
        delta_low  = t.update(self._env(interest_rate=0.05), [], 0)
        delta_high = t.update(self._env(interest_rate=0.50), [], 0)
        assert delta_high["minsky__ponzi_fraction"] > delta_low["minsky__ponzi_fraction"]

    def test_crash_risk_zero_when_ponzi_below_threshold(self):
        # P well below default crash_threshold (0.30) → crash_risk == 0
        delta = MinskyInstability().update(self._env(H=0.80, S=0.15, P=0.05), [], 0)
        assert delta["minsky__crash_risk"] == pytest.approx(0.0, abs=1e-6)

    def test_crash_risk_positive_when_ponzi_above_threshold(self):
        # P above crash_threshold → crash_risk > 0
        delta = MinskyInstability().update(self._env(H=0.20, S=0.20, P=0.60), [], 0)
        assert delta["minsky__crash_risk"] > 0.0

    def test_financial_fragility_increases_as_ponzi_grows(self):
        # fragility = 0.3·S + 1.0·P; larger P → larger fragility
        t = MinskyInstability()
        delta_low  = t.update(self._env(H=0.80, S=0.15, P=0.05), [], 0)
        delta_high = t.update(self._env(H=0.20, S=0.20, P=0.60), [], 0)
        assert delta_high["minsky__financial_fragility"] > delta_low["minsky__financial_fragility"]

    def test_custom_cycle_id_in_output(self):
        t = MinskyInstability(parameters={"cycle_id": "household"})
        env = {
            "household__hedge_fraction": 0.70,
            "household__speculative_fraction": 0.20,
            "household__ponzi_fraction": 0.10,
            "household__interest_rate": 0.05,
            "household__asset_appreciation": 0.05,
        }
        delta = t.update(env, [], 0)
        assert "household__hedge_fraction" in delta
        assert "minsky__hedge_fraction" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = MinskyInstability().update({}, [], 0)
        assert 0.0 <= delta["minsky__hedge_fraction"] <= 1.0
        assert 0.0 <= delta["minsky__crash_risk"] <= 1.0

    def test_hsp_sums_to_one_with_missing_keys(self):
        delta = MinskyInstability().update({}, [], 0)
        total = (
            delta["minsky__hedge_fraction"]
            + delta["minsky__speculative_fraction"]
            + delta["minsky__ponzi_fraction"]
        )
        assert total == pytest.approx(1.0, abs=1e-9)
