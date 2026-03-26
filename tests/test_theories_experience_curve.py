"""
Tests for core/theories/experience_curve.py
"""
from __future__ import annotations

import math

import pytest

from core.theories import get_theory, list_theories
from core.theories.experience_curve import ExperienceCurve


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "experience_curve" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("experience_curve") is ExperienceCurve

    def test_theory_id_attribute(self):
        assert ExperienceCurve.theory_id == "experience_curve"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = ExperienceCurve()
        assert t.params.learning_rate == 0.80
        assert t.params.initial_cost == 1.0
        assert t.params.min_cost == 0.10
        assert t.params.curve_id == "experience"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = ExperienceCurve(parameters={"learning_rate": 0.85, "curve_id": "solar"})
        assert t.params.learning_rate == 0.85
        assert t.params.curve_id == "solar"

    def test_learning_rate_below_minimum_rejected(self):
        with pytest.raises(Exception):
            ExperienceCurve(parameters={"learning_rate": 0.3})

    def test_learning_rate_above_one_rejected(self):
        with pytest.raises(Exception):
            ExperienceCurve(parameters={"learning_rate": 1.1})

    def test_min_cost_above_initial_cost_rejected(self):
        with pytest.raises(Exception):
            ExperienceCurve(parameters={"initial_cost": 0.5, "min_cost": 0.6})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_three_keys(self):
        sv = ExperienceCurve().state_variables
        assert "experience__unit_cost"             in sv.writes
        assert "experience__cumulative_production" in sv.writes
        assert "experience__cost_reduction_pct"    in sv.writes

    def test_production_rate_not_in_writes(self):
        # production_rate is owned by agents, not this theory
        assert "experience__production_rate" not in ExperienceCurve().state_variables.writes

    def test_production_rate_in_initializes(self):
        assert "experience__production_rate" in ExperienceCurve().state_variables.initializes

    def test_custom_curve_id_reflected_in_keys(self):
        t = ExperienceCurve(parameters={"curve_id": "solar"})
        sv = t.state_variables
        assert "solar__unit_cost" in sv.writes
        assert "experience__unit_cost" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_unit_cost_at_initial_cost(self):
        inits = ExperienceCurve().setup({})
        assert inits["experience__unit_cost"] == pytest.approx(1.0)

    def test_seeds_cumulative_production_above_zero(self):
        # Seeded at _Q_SEED (0.01) to avoid log(0)
        inits = ExperienceCurve().setup({})
        assert inits["experience__cumulative_production"] > 0.0

    def test_seeds_production_rate_at_default(self):
        t = ExperienceCurve(parameters={"default_production_rate": 0.08})
        inits = t.setup({})
        assert inits["experience__production_rate"] == pytest.approx(0.08)

    def test_does_not_overwrite_existing_values(self):
        env = {"experience__unit_cost": 0.7, "experience__cumulative_production": 0.3}
        inits = ExperienceCurve().setup(env)
        assert "experience__unit_cost"             not in inits
        assert "experience__cumulative_production" not in inits


# ── update() — core Wright's Law logic ───────────────────────────────────────

class TestUpdate:
    def _env(self, Q=0.10, cost=1.0, prod_rate=0.05) -> dict[str, float]:
        return {
            "experience__cumulative_production": Q,
            "experience__unit_cost":             cost,
            "experience__production_rate":       prod_rate,
        }

    def test_returns_all_three_keys(self):
        delta = ExperienceCurve().update(self._env(), [], 0)
        assert "experience__unit_cost"             in delta
        assert "experience__cumulative_production" in delta
        assert "experience__cost_reduction_pct"    in delta

    def test_does_not_mutate_env(self):
        env = self._env(Q=0.10, cost=1.0)
        ExperienceCurve().update(env, [], 0)
        assert env["experience__cumulative_production"] == pytest.approx(0.10)
        assert env["experience__unit_cost"] == pytest.approx(1.0)

    def test_outputs_clamped_to_0_1(self):
        t = ExperienceCurve(parameters={"learning_rate": 0.50})
        delta = t.update(self._env(Q=0.01, cost=1.0, prod_rate=1.0), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_cost_decreases_with_production(self):
        t = ExperienceCurve(parameters={"learning_rate": 0.80})
        delta = t.update(self._env(Q=0.10, cost=1.0, prod_rate=0.10), [], 0)
        assert delta["experience__unit_cost"] < 1.0

    def test_zero_production_no_cost_change(self):
        # No production → no learning → cost stays flat
        delta = ExperienceCurve().update(self._env(Q=0.10, cost=0.8, prod_rate=0.0), [], 0)
        assert delta["experience__unit_cost"] == pytest.approx(0.8, abs=1e-9)

    def test_cost_never_falls_below_min_cost(self):
        t = ExperienceCurve(parameters={"learning_rate": 0.50, "min_cost": 0.20})
        env = self._env(Q=0.01, cost=1.0, prod_rate=1.0)
        for _ in range(50):
            env.update(t.update(env, [], 0))
        assert env["experience__unit_cost"] >= 0.20

    def test_faster_learning_curve_cheaper_cost(self):
        # learning_rate=0.70 (aggressive) vs 0.95 (slow) — same production
        env = self._env(Q=0.10, cost=1.0, prod_rate=0.10)
        t_fast = ExperienceCurve(parameters={"learning_rate": 0.70})
        t_slow = ExperienceCurve(parameters={"learning_rate": 0.95})
        d_fast = t_fast.update(env, [], 0)
        d_slow = t_slow.update(env, [], 0)
        assert d_fast["experience__unit_cost"] < d_slow["experience__unit_cost"]

    def test_higher_production_rate_faster_learning(self):
        env_slow = self._env(Q=0.10, cost=1.0, prod_rate=0.02)
        env_fast = self._env(Q=0.10, cost=1.0, prod_rate=0.20)
        t = ExperienceCurve()
        d_slow = t.update(env_slow, [], 0)
        d_fast = t.update(env_fast, [], 0)
        assert d_fast["experience__unit_cost"] < d_slow["experience__unit_cost"]

    def test_cost_reduction_pct_increases_over_time(self):
        t = ExperienceCurve(parameters={"learning_rate": 0.80})
        env = self._env(Q=0.01, cost=1.0, prod_rate=0.05)
        prev_reduction = 0.0
        for _ in range(20):
            delta = t.update(env, [], 0)
            env.update(delta)
            assert env["experience__cost_reduction_pct"] >= prev_reduction - 1e-9
            prev_reduction = env["experience__cost_reduction_pct"]

    def test_doubling_production_reduces_cost_by_learning_rate(self):
        # Wright's Law: cost at 2Q = cost at Q × learning_rate
        # Test with a single doubling step
        p = ExperienceCurve(parameters={"learning_rate": 0.80, "min_cost": 0.0})
        # Start at Q=0.1 with cost=1.0; production_rate = 0.1 so Q doubles to 0.2
        env = {"experience__cumulative_production": 0.10,
               "experience__unit_cost":             1.0,
               "experience__production_rate":       0.10}
        delta = p.update(env, [], 0)
        # Expected: C * (0.2/0.1)^(-b) = 1.0 * 2^(-b) = learning_rate = 0.80
        b = -math.log(0.80) / math.log(2.0)
        expected_cost = 1.0 * (0.20 / 0.10) ** (-b)
        assert delta["experience__unit_cost"] == pytest.approx(expected_cost, abs=1e-6)

    def test_tick_unit_month_smaller_progress_than_year(self):
        env = self._env(Q=0.10, cost=1.0, prod_rate=0.10)
        d_year  = ExperienceCurve(parameters={"tick_unit": "year"}).update(env, [], 0)
        d_month = ExperienceCurve(parameters={"tick_unit": "month"}).update(env, [], 0)
        # Monthly: smaller dQ → less learning per tick
        assert d_month["experience__unit_cost"] > d_year["experience__unit_cost"]

    def test_custom_curve_id_in_output(self):
        t = ExperienceCurve(parameters={"curve_id": "solar"})
        delta = t.update(
            {"solar__cumulative_production": 0.1,
             "solar__unit_cost": 1.0,
             "solar__production_rate": 0.05},
            [], 0,
        )
        assert "solar__unit_cost" in delta
        assert "experience__unit_cost" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = ExperienceCurve().update({}, [], 0)
        assert 0.0 <= delta["experience__unit_cost"] <= 1.0
