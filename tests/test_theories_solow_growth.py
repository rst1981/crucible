"""
Tests for core/theories/solow_growth.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.solow_growth import SolowGrowth


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "solow_growth" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("solow_growth") is SolowGrowth

    def test_theory_id_attribute(self):
        assert SolowGrowth.theory_id == "solow_growth"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = SolowGrowth()
        assert t.params.savings_rate == pytest.approx(0.20)
        assert t.params.depreciation_rate == pytest.approx(0.05)
        assert t.params.labor_growth_rate == pytest.approx(0.01)
        assert t.params.tfp_growth_rate == pytest.approx(0.02)
        assert t.params.capital_share == pytest.approx(0.33)
        assert t.params.adjustment_speed == pytest.approx(1.0)
        assert t.params.tick_unit == "year"
        assert t.params.economy_id == "solow"

    def test_parameter_overrides(self):
        t = SolowGrowth(parameters={"savings_rate": 0.35, "economy_id": "usa"})
        assert t.params.savings_rate == pytest.approx(0.35)
        assert t.params.economy_id == "usa"

    def test_savings_rate_above_maximum_rejected(self):
        with pytest.raises(Exception):
            SolowGrowth(parameters={"savings_rate": 0.65})

    def test_capital_share_below_minimum_rejected(self):
        with pytest.raises(Exception):
            SolowGrowth(parameters={"capital_share": 0.05})

    def test_savings_rate_below_minimum_rejected(self):
        with pytest.raises(Exception):
            SolowGrowth(parameters={"savings_rate": 0.005})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_three_keys(self):
        sv = SolowGrowth().state_variables
        assert "solow__capital_intensity" in sv.writes
        assert "solow__output_per_worker" in sv.writes
        assert "solow__convergence_gap" in sv.writes

    def test_tfp_shock_not_in_writes(self):
        sv = SolowGrowth().state_variables
        assert "solow__tfp_shock" not in sv.writes

    def test_tfp_shock_in_initializes(self):
        sv = SolowGrowth().state_variables
        assert "solow__tfp_shock" in sv.initializes

    def test_custom_economy_id_reflected_in_keys(self):
        t = SolowGrowth(parameters={"economy_id": "germany"})
        sv = t.state_variables
        assert "germany__capital_intensity" in sv.writes
        assert "solow__capital_intensity" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_capital_intensity_at_0_50(self):
        inits = SolowGrowth().setup({})
        assert inits["solow__capital_intensity"] == pytest.approx(0.50)

    def test_seeds_output_per_worker_consistent_with_capital(self):
        t = SolowGrowth()
        inits = t.setup({})
        expected = 0.50 ** t.params.capital_share
        assert inits["solow__output_per_worker"] == pytest.approx(expected, rel=1e-6)

    def test_seeds_tfp_shock_at_zero(self):
        inits = SolowGrowth().setup({})
        assert inits["solow__tfp_shock"] == pytest.approx(0.0)

    def test_does_not_overwrite_existing_capital(self):
        env = {"solow__capital_intensity": 0.75}
        inits = SolowGrowth().setup(env)
        assert "solow__capital_intensity" not in inits

    def test_does_not_overwrite_existing_tfp_shock(self):
        env = {"solow__tfp_shock": 0.10}
        inits = SolowGrowth().setup(env)
        assert "solow__tfp_shock" not in inits


# ── update() ──────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, capital=0.50, tfp_shock=0.0) -> dict[str, float]:
        return {
            "solow__capital_intensity": capital,
            "solow__tfp_shock": tfp_shock,
        }

    def test_returns_three_keys(self):
        delta = SolowGrowth().update(self._env(), [], 0)
        assert "solow__capital_intensity" in delta
        assert "solow__output_per_worker" in delta
        assert "solow__convergence_gap" in delta

    def test_does_not_mutate_env(self):
        env = self._env(capital=0.50)
        SolowGrowth().update(env, [], 0)
        assert env["solow__capital_intensity"] == pytest.approx(0.50)

    def test_outputs_clamped_to_0_1(self):
        delta = SolowGrowth().update(self._env(capital=0.50), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_below_ss_capital_grows(self):
        # κ=0.30 is below steady state (κ=1) → capital_intensity should increase
        t = SolowGrowth()
        delta = t.update(self._env(capital=0.30), [], 0)
        assert delta["solow__capital_intensity"] > 0.30

    def test_capital_increases_from_low_start(self):
        # κ=0.50 is below SS → increases
        t = SolowGrowth()
        delta = t.update(self._env(capital=0.50), [], 0)
        assert delta["solow__capital_intensity"] > 0.50

    def test_positive_tfp_shock_increases_output(self):
        # TFP shock boosts A_factor → higher output per worker
        t = SolowGrowth()
        delta_no_shock  = t.update(self._env(capital=0.50, tfp_shock=0.0), [], 0)
        delta_with_shock = t.update(self._env(capital=0.50, tfp_shock=0.30), [], 0)
        assert delta_with_shock["solow__output_per_worker"] > delta_no_shock["solow__output_per_worker"]

    def test_output_per_worker_equals_capital_to_alpha(self):
        # Mathematical identity: output = capital^alpha (Cobb-Douglas)
        # In the normalized Solow form, savings_rate sets steady-state level but
        # does not change normalized convergence speed — both theories at same κ get same dk.
        t = SolowGrowth(parameters={"capital_share": 0.33})
        for capital in [0.20, 0.50, 0.80]:
            delta = t.update({"solow__capital_intensity": capital}, [], 0)
            new_k = delta["solow__capital_intensity"]
            expected_y = new_k ** 0.33
            assert delta["solow__output_per_worker"] == pytest.approx(expected_y, abs=1e-5)

    def test_convergence_gap_is_distance_from_ss(self):
        # capital at 0.50 → gap should be approximately |1 - 0.50+| > 0
        delta = SolowGrowth().update(self._env(capital=0.50), [], 0)
        assert delta["solow__convergence_gap"] > 0.0

    def test_output_per_worker_monotone_in_capital(self):
        # higher capital → higher output per worker
        t = SolowGrowth()
        d_low  = t.update(self._env(capital=0.20), [], 0)
        d_high = t.update(self._env(capital=0.80), [], 0)
        assert d_high["solow__output_per_worker"] > d_low["solow__output_per_worker"]

    def test_custom_economy_id_in_output(self):
        t = SolowGrowth(parameters={"economy_id": "brazil"})
        delta = t.update({"brazil__capital_intensity": 0.50, "brazil__tfp_shock": 0.0}, [], 0)
        assert "brazil__capital_intensity" in delta
        assert "solow__capital_intensity" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = SolowGrowth().update({}, [], 0)
        assert 0.0 <= delta["solow__capital_intensity"] <= 1.0
        assert 0.0 <= delta["solow__output_per_worker"] <= 1.0
        assert 0.0 <= delta["solow__convergence_gap"] <= 1.0

    def test_faster_adjustment_speed_larger_change(self):
        # Higher adjustment_speed → larger dk per tick
        env = self._env(capital=0.30)
        t_slow = SolowGrowth(parameters={"adjustment_speed": 0.5})
        t_fast = SolowGrowth(parameters={"adjustment_speed": 3.0})
        d_slow = t_slow.update(env, [], 0)
        d_fast = t_fast.update(env, [], 0)
        assert d_fast["solow__capital_intensity"] > d_slow["solow__capital_intensity"]
