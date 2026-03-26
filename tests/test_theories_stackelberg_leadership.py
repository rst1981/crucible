"""
Tests for core/theories/stackelberg_leadership.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.stackelberg_leadership import StackelbergLeadership


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "stackelberg_leadership" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("stackelberg_leadership") is StackelbergLeadership

    def test_theory_id_attribute(self):
        assert StackelbergLeadership.theory_id == "stackelberg_leadership"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = StackelbergLeadership()
        assert t.params.p_max == pytest.approx(1.0)
        assert t.params.demand_slope == pytest.approx(1.0)
        assert t.params.cost_leader == pytest.approx(0.20)
        assert t.params.cost_follower == pytest.approx(0.25)
        assert t.params.leader_speed == pytest.approx(0.60)
        assert t.params.follower_speed == pytest.approx(0.90)
        assert t.params.gdp_demand_sensitivity == pytest.approx(0.30)
        assert t.params.tick_unit == "year"
        assert t.params.market_id == "stackelberg"

    def test_parameter_overrides(self):
        t = StackelbergLeadership(parameters={"cost_leader": 0.10, "market_id": "aviation"})
        assert t.params.cost_leader == pytest.approx(0.10)
        assert t.params.market_id == "aviation"

    def test_demand_slope_below_minimum_rejected(self):
        with pytest.raises(Exception):
            StackelbergLeadership(parameters={"demand_slope": 0.05})

    def test_cost_leader_above_one_rejected(self):
        with pytest.raises(Exception):
            StackelbergLeadership(parameters={"cost_leader": 1.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_six_keys(self):
        sv = StackelbergLeadership().state_variables
        assert "stackelberg__leader_quantity"     in sv.writes
        assert "stackelberg__follower_quantity"   in sv.writes
        assert "stackelberg__market_price"        in sv.writes
        assert "stackelberg__leader_margin"       in sv.writes
        assert "stackelberg__follower_margin"     in sv.writes
        assert "stackelberg__leadership_advantage" in sv.writes

    def test_custom_market_id_reflected_in_keys(self):
        t = StackelbergLeadership(parameters={"market_id": "aviation"})
        sv = t.state_variables
        assert "aviation__leader_quantity"        in sv.writes
        assert "stackelberg__leader_quantity" not in sv.writes

    def test_all_six_keys_present_with_custom_id(self):
        t = StackelbergLeadership(parameters={"market_id": "aviation"})
        sv = t.state_variables
        expected = [
            "aviation__leader_quantity",
            "aviation__follower_quantity",
            "aviation__market_price",
            "aviation__leader_margin",
            "aviation__follower_margin",
            "aviation__leadership_advantage",
        ]
        for key in expected:
            assert key in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_quantities_near_equilibrium(self):
        # With default params, equilibrium quantities should be in (0, 1)
        inits = StackelbergLeadership().setup({})
        assert 0.0 < inits["stackelberg__leader_quantity"]   < 1.0
        assert 0.0 < inits["stackelberg__follower_quantity"] < 1.0

    def test_leader_quantity_greater_than_follower_at_seed(self):
        # Stackelberg: leader produces more than follower at equilibrium
        inits = StackelbergLeadership().setup({})
        assert inits["stackelberg__leader_quantity"] > inits["stackelberg__follower_quantity"]

    def test_does_not_overwrite_existing(self):
        env = {"stackelberg__leader_quantity": 0.50,
               "stackelberg__follower_quantity": 0.20}
        inits = StackelbergLeadership().setup(env)
        assert "stackelberg__leader_quantity"   not in inits
        assert "stackelberg__follower_quantity" not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, q_l=0.375, q_f=0.1875) -> dict[str, float]:
        return {
            "stackelberg__leader_quantity":   q_l,
            "stackelberg__follower_quantity": q_f,
        }

    def test_returns_six_keys(self):
        delta = StackelbergLeadership().update(self._env(), [], 0)
        assert "stackelberg__leader_quantity"     in delta
        assert "stackelberg__follower_quantity"   in delta
        assert "stackelberg__market_price"        in delta
        assert "stackelberg__leader_margin"       in delta
        assert "stackelberg__follower_margin"     in delta
        assert "stackelberg__leadership_advantage" in delta

    def test_does_not_mutate_env(self):
        env = self._env(q_l=0.30, q_f=0.15)
        StackelbergLeadership().update(env, [], 0)
        assert env["stackelberg__leader_quantity"]   == pytest.approx(0.30)
        assert env["stackelberg__follower_quantity"] == pytest.approx(0.15)

    def test_outputs_clamped_to_0_1(self):
        env = {"stackelberg__leader_quantity":   0.99,
               "stackelberg__follower_quantity": 0.99,
               "keynesian__gdp_normalized":       0.99}
        delta = StackelbergLeadership().update(env, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_lower_cost_leader_produces_more_than_follower(self):
        # Leader has lower cost AND first-mover → leader_quantity > follower_quantity
        t = StackelbergLeadership(parameters={"cost_leader": 0.10, "cost_follower": 0.30,
                                               "leader_speed": 1.0, "follower_speed": 1.0})
        delta = t.update(self._env(), [], 0)
        assert delta["stackelberg__leader_quantity"] > delta["stackelberg__follower_quantity"]

    def test_higher_price_when_quantities_are_low(self):
        # P = p_max - slope*(q_l+q_f): low quantities → higher price
        t = StackelbergLeadership()
        d_low  = t.update(self._env(q_l=0.05, q_f=0.05), [], 0)
        d_high = t.update(self._env(q_l=0.40, q_f=0.30), [], 0)
        assert d_low["stackelberg__market_price"] > d_high["stackelberg__market_price"]

    def test_gdp_boom_increases_quantities_and_price(self):
        env_base = {**self._env(), "keynesian__gdp_normalized": 0.50}
        env_boom = {**self._env(), "keynesian__gdp_normalized": 0.90}
        t = StackelbergLeadership()
        d_base = t.update(env_base, [], 0)
        d_boom = t.update(env_boom, [], 0)
        total_base = d_base["stackelberg__leader_quantity"] + d_base["stackelberg__follower_quantity"]
        total_boom = d_boom["stackelberg__leader_quantity"] + d_boom["stackelberg__follower_quantity"]
        assert total_boom > total_base
        assert d_boom["stackelberg__market_price"] >= d_base["stackelberg__market_price"]

    def test_leadership_advantage_nonnegative(self):
        # leadership_advantage = max(0, leader_margin - follower_margin) ≥ 0 always
        t = StackelbergLeadership()
        delta = t.update(self._env(), [], 0)
        assert delta["stackelberg__leadership_advantage"] >= 0.0

    def test_leadership_advantage_positive_with_default_params(self):
        # Default: cost_leader=0.20 < cost_follower=0.25 + first-mover → leader earns more
        t = StackelbergLeadership(parameters={"leader_speed": 1.0, "follower_speed": 1.0})
        # Seed near equilibrium and run several ticks to settle
        env = StackelbergLeadership().setup({})
        for _ in range(10):
            env.update(t.update(env, [], 0))
        assert env["stackelberg__leadership_advantage"] > 0.0

    def test_custom_market_id_in_output(self):
        t = StackelbergLeadership(parameters={"market_id": "aviation"})
        delta = t.update(
            {"aviation__leader_quantity": 0.375,
             "aviation__follower_quantity": 0.1875},
            [], 0,
        )
        assert "aviation__leader_quantity"        in delta
        assert "stackelberg__leader_quantity" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = StackelbergLeadership().update({}, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_multi_tick_converges_toward_equilibrium(self):
        # Start far from equilibrium; after many ticks should approach Stackelberg solution
        t = StackelbergLeadership(parameters={"leader_speed": 0.80, "follower_speed": 0.90,
                                               "tick_unit": "year"})
        env = {"stackelberg__leader_quantity": 0.05, "stackelberg__follower_quantity": 0.05}
        for _ in range(40):
            env.update(t.update(env, [], 0))
        eq = t.stackelberg_equilibrium()
        assert eq is not None
        q_l_star, q_f_star, _ = eq
        assert abs(env["stackelberg__leader_quantity"]   - q_l_star) < 0.05
        assert abs(env["stackelberg__follower_quantity"] - q_f_star) < 0.05


# ── stackelberg_equilibrium() ─────────────────────────────────────────────────

class TestStackelbergEquilibrium:
    def test_equilibrium_returns_tuple(self):
        t = StackelbergLeadership()
        eq = t.stackelberg_equilibrium()
        assert eq is not None
        assert len(eq) == 3

    def test_leader_produces_more_than_follower(self):
        # First-mover advantage: leader commits to higher quantity
        t = StackelbergLeadership()
        eq = t.stackelberg_equilibrium()
        assert eq is not None
        q_l_star, q_f_star, _ = eq
        assert q_l_star > q_f_star

    def test_returns_none_when_cost_exceeds_p_max(self):
        # cost_leader > p_max → q_l* ≤ 0 → None
        t = StackelbergLeadership(parameters={"p_max": 0.30, "cost_leader": 0.80,
                                               "cost_follower": 0.90})
        assert t.stackelberg_equilibrium() is None

    def test_analytical_formula(self):
        # q_l* = (p_max + c_f - 2*c_l) / (2*slope)
        p_max, c_l, c_f, slope = 1.0, 0.20, 0.25, 1.0
        t = StackelbergLeadership(parameters={"p_max": p_max, "cost_leader": c_l,
                                               "cost_follower": c_f, "demand_slope": slope})
        eq = t.stackelberg_equilibrium()
        assert eq is not None
        q_l_star, q_f_star, _ = eq
        expected_q_l = (p_max + c_f - 2.0 * c_l) / (2.0 * slope)
        assert q_l_star == pytest.approx(expected_q_l, abs=1e-9)
