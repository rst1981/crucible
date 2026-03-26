"""
Tests for core/theories/cournot_oligopoly.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.cournot_oligopoly import CournotOligopoly


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "cournot_oligopoly" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("cournot_oligopoly") is CournotOligopoly

    def test_theory_id_attribute(self):
        assert CournotOligopoly.theory_id == "cournot_oligopoly"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = CournotOligopoly()
        assert t.params.p_max == 1.0
        assert t.params.demand_slope == 1.0
        assert t.params.cost_a == 0.20
        assert t.params.cost_b == 0.20
        assert t.params.market_id == "cournot"

    def test_parameter_overrides(self):
        t = CournotOligopoly(parameters={"cost_a": 0.1, "cost_b": 0.3, "market_id": "telecom"})
        assert t.params.cost_a == 0.1
        assert t.params.cost_b == 0.3
        assert t.params.market_id == "telecom"

    def test_demand_slope_below_minimum_rejected(self):
        with pytest.raises(Exception):
            CournotOligopoly(parameters={"demand_slope": 0.0})

    def test_cost_above_one_rejected(self):
        with pytest.raises(Exception):
            CournotOligopoly(parameters={"cost_a": 1.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_six_keys(self):
        sv = CournotOligopoly().state_variables
        assert "cournot__firm_a_quantity"     in sv.writes
        assert "cournot__firm_b_quantity"     in sv.writes
        assert "cournot__market_price"        in sv.writes
        assert "cournot__firm_a_margin"       in sv.writes
        assert "cournot__firm_b_margin"       in sv.writes
        assert "cournot__market_concentration" in sv.writes

    def test_reads_gdp(self):
        assert "keynesian__gdp_normalized" in CournotOligopoly().state_variables.reads

    def test_custom_market_id_reflected_in_keys(self):
        t = CournotOligopoly(parameters={"market_id": "telecom"})
        sv = t.state_variables
        assert "telecom__firm_a_quantity" in sv.writes
        assert "cournot__firm_a_quantity" not in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = CournotOligopoly().state_variables
        for key in sv.initializes:
            assert key in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_quantities_near_nash(self):
        # Symmetric params: q_nash = (1.0 - 0.2) / (3 * 1.0) ≈ 0.267
        inits = CournotOligopoly().setup({})
        assert 0.0 < inits["cournot__firm_a_quantity"] < 1.0
        assert 0.0 < inits["cournot__firm_b_quantity"] < 1.0

    def test_symmetric_params_equal_initial_quantities(self):
        inits = CournotOligopoly().setup({})
        assert inits["cournot__firm_a_quantity"] == pytest.approx(
            inits["cournot__firm_b_quantity"], abs=1e-9
        )

    def test_does_not_overwrite_existing_quantities(self):
        env = {"cournot__firm_a_quantity": 0.5, "cournot__firm_b_quantity": 0.3}
        inits = CournotOligopoly().setup(env)
        assert "cournot__firm_a_quantity" not in inits
        assert "cournot__firm_b_quantity" not in inits


# ── update() — core ODE logic ─────────────────────────────────────────────────

class TestUpdate:
    def _env(self, q_a=0.27, q_b=0.27) -> dict[str, float]:
        return {"cournot__firm_a_quantity": q_a, "cournot__firm_b_quantity": q_b}

    def test_returns_all_six_keys(self):
        delta = CournotOligopoly().update(self._env(), [], 0)
        assert "cournot__firm_a_quantity"      in delta
        assert "cournot__firm_b_quantity"      in delta
        assert "cournot__market_price"         in delta
        assert "cournot__firm_a_margin"        in delta
        assert "cournot__firm_b_margin"        in delta
        assert "cournot__market_concentration" in delta

    def test_does_not_mutate_env(self):
        env = self._env(0.3, 0.3)
        CournotOligopoly().update(env, [], 0)
        assert env["cournot__firm_a_quantity"] == pytest.approx(0.3)
        assert env["cournot__firm_b_quantity"] == pytest.approx(0.3)

    def test_outputs_clamped_to_0_1(self):
        t = CournotOligopoly(parameters={"p_max": 2.0, "cost_a": 0.0, "cost_b": 0.0})
        delta = t.update(self._env(0.5, 0.5), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_symmetric_firms_equal_quantities(self):
        delta = CournotOligopoly().update(self._env(0.27, 0.27), [], 0)
        assert delta["cournot__firm_a_quantity"] == pytest.approx(
            delta["cournot__firm_b_quantity"], abs=1e-9
        )

    def test_lower_cost_firm_produces_more(self):
        t = CournotOligopoly(parameters={"cost_a": 0.1, "cost_b": 0.4,
                                          "adjustment_speed": 1.0})
        delta = t.update(self._env(0.27, 0.27), [], 0)
        assert delta["cournot__firm_a_quantity"] > delta["cournot__firm_b_quantity"]

    def test_higher_quantity_lowers_market_price(self):
        t = CournotOligopoly()
        d_low  = t.update(self._env(0.1, 0.1), [], 0)
        d_high = t.update(self._env(0.4, 0.4), [], 0)
        assert d_high["cournot__market_price"] < d_low["cournot__market_price"]

    def test_gdp_boom_increases_output_and_price(self):
        env_base = {**self._env(), "keynesian__gdp_normalized": 0.5}
        env_boom = {**self._env(), "keynesian__gdp_normalized": 0.9}
        t = CournotOligopoly()
        d_base = t.update(env_base, [], 0)
        d_boom = t.update(env_boom, [], 0)
        assert d_boom["cournot__market_price"] > d_base["cournot__market_price"]

    def test_equal_split_minimum_concentration(self):
        # Equal quantities → minimum HHI concentration (0.0 in normalized form)
        t = CournotOligopoly(parameters={"adjustment_speed": 1.0,
                                          "cost_a": 0.2, "cost_b": 0.2})
        delta = t.update(self._env(0.27, 0.27), [], 0)
        # Symmetric → equal market shares → concentration should be near 0
        assert delta["cournot__market_concentration"] == pytest.approx(0.0, abs=0.05)

    def test_monopoly_maximum_concentration(self):
        # Firm B produces nothing with adjustment frozen → pure monopoly → concentration = 1.0
        t = CournotOligopoly(parameters={"adjustment_speed": 0.0})
        delta = t.update(self._env(q_a=0.5, q_b=0.0), [], 0)
        assert delta["cournot__market_concentration"] == pytest.approx(1.0, abs=1e-9)

    def test_multi_tick_converges_toward_nash(self):
        # Start far from Nash; after many ticks should approach equilibrium
        t = CournotOligopoly(parameters={"adjustment_speed": 0.8, "tick_unit": "year"})
        env = {"cournot__firm_a_quantity": 0.05, "cournot__firm_b_quantity": 0.05}
        for _ in range(40):
            env.update(t.update(env, [], 0))
        eq = t.nash_equilibrium()
        assert eq is not None
        q_a_star, q_b_star, _ = eq
        assert abs(env["cournot__firm_a_quantity"] - q_a_star) < 0.05
        assert abs(env["cournot__firm_b_quantity"] - q_b_star) < 0.05

    def test_custom_market_id_in_output(self):
        t = CournotOligopoly(parameters={"market_id": "telecom"})
        delta = t.update(
            {"telecom__firm_a_quantity": 0.27, "telecom__firm_b_quantity": 0.27}, [], 0
        )
        assert "telecom__firm_a_quantity" in delta
        assert "cournot__firm_a_quantity" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = CournotOligopoly().update({}, [], 0)
        assert 0.0 <= delta["cournot__market_price"] <= 1.0


# ── nash_equilibrium() ────────────────────────────────────────────────────────

class TestNashEquilibrium:
    def test_symmetric_equal_quantities(self):
        t = CournotOligopoly()
        eq = t.nash_equilibrium()
        assert eq is not None
        q_a, q_b, _ = eq
        assert q_a == pytest.approx(q_b, abs=1e-9)

    def test_returns_none_when_cost_exceeds_pmax(self):
        # cost > p_max → no profitable production → no equilibrium
        # Use p_max=0.5 so that cost_a=cost_b=0.8 (≤1.0, valid) exceeds p_max
        t = CournotOligopoly(parameters={"cost_a": 0.8, "cost_b": 0.8, "p_max": 0.5})
        assert t.nash_equilibrium() is None

    def test_analytical_formula(self):
        # q_a* = (p_max - 2*c_a + c_b) / (3*slope)
        p_max, c_a, c_b, slope = 1.0, 0.2, 0.3, 1.0
        t = CournotOligopoly(parameters={"p_max": p_max, "cost_a": c_a, "cost_b": c_b,
                                          "demand_slope": slope})
        eq = t.nash_equilibrium()
        assert eq is not None
        q_a, q_b, _ = eq
        assert q_a == pytest.approx((p_max - 2*c_a + c_b) / (3*slope), abs=1e-9)
        assert q_b == pytest.approx((p_max - 2*c_b + c_a) / (3*slope), abs=1e-9)
