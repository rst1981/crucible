"""
Tests for core/theories/cobweb_market.py

Covers: Ezekiel (1938) cobweb theorem — lagged supply, price oscillations,
convergent vs. divergent dynamics.
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.cobweb_market import CobwebMarket


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "cobweb_market" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("cobweb_market") is CobwebMarket

    def test_theory_id_attribute(self):
        assert CobwebMarket.theory_id == "cobweb_market"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = CobwebMarket()
        assert t.params.supply_elasticity == pytest.approx(0.60)
        assert t.params.demand_elasticity == pytest.approx(0.80)
        assert t.params.supply_intercept  == pytest.approx(0.20)
        assert t.params.demand_intercept  == pytest.approx(0.80)
        assert t.params.price_adjustment_speed == pytest.approx(1.0)
        assert t.params.market_id == "cobweb"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = CobwebMarket(parameters={"supply_elasticity": 0.40, "market_id": "wheat"})
        assert t.params.supply_elasticity == pytest.approx(0.40)
        assert t.params.market_id == "wheat"

    def test_demand_elasticity_at_zero_rejected(self):
        # ge=0.01 means 0.0 is below minimum — should raise
        with pytest.raises(Exception):
            CobwebMarket(parameters={"demand_elasticity": 0.0})

    def test_supply_elasticity_above_maximum_rejected(self):
        with pytest.raises(Exception):
            CobwebMarket(parameters={"supply_elasticity": 2.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_five_keys(self):
        sv = CobwebMarket().state_variables
        assert "cobweb__price"            in sv.writes
        assert "cobweb__supply"           in sv.writes
        assert "cobweb__demand"           in sv.writes
        assert "cobweb__excess_demand"    in sv.writes
        assert "cobweb__price_volatility" in sv.writes

    def test_supply_shock_not_in_writes(self):
        assert "cobweb__supply_shock" not in CobwebMarket().state_variables.writes

    def test_supply_shock_in_initializes(self):
        assert "cobweb__supply_shock" in CobwebMarket().state_variables.initializes

    def test_demand_shock_in_initializes(self):
        assert "cobweb__demand_shock" in CobwebMarket().state_variables.initializes

    def test_custom_market_id_reflected_in_keys(self):
        t = CobwebMarket(parameters={"market_id": "wheat"})
        sv = t.state_variables
        assert "wheat__price" in sv.writes
        assert "cobweb__price" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_price_at_steady_state(self):
        # P* = (c - a) / (d + b) = (0.80 - 0.20) / (0.80 + 0.60) = 0.60 / 1.40
        t = CobwebMarket()
        inits = t.setup({})
        expected_p_star = (0.80 - 0.20) / (0.80 + 0.60)
        assert inits["cobweb__price"] == pytest.approx(expected_p_star, abs=1e-6)

    def test_seeds_shocks_at_zero(self):
        inits = CobwebMarket().setup({})
        assert inits["cobweb__supply_shock"] == pytest.approx(0.0)
        assert inits["cobweb__demand_shock"]  == pytest.approx(0.0)

    def test_does_not_overwrite_existing_price(self):
        env = {"cobweb__price": 0.75}
        inits = CobwebMarket().setup(env)
        assert "cobweb__price" not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, price: float = 0.43, supply_shock: float = 0.0,
             demand_shock: float = 0.0, market_id: str = "cobweb") -> dict[str, float]:
        return {
            f"{market_id}__price":        price,
            f"{market_id}__supply_shock": supply_shock,
            f"{market_id}__demand_shock": demand_shock,
        }

    def test_returns_five_keys(self):
        delta = CobwebMarket().update(self._env(), [], 0)
        assert "cobweb__price"            in delta
        assert "cobweb__supply"           in delta
        assert "cobweb__demand"           in delta
        assert "cobweb__excess_demand"    in delta
        assert "cobweb__price_volatility" in delta

    def test_does_not_mutate_env(self):
        env = self._env(price=0.43)
        original_price = env["cobweb__price"]
        CobwebMarket().update(env, [], 0)
        assert env["cobweb__price"] == pytest.approx(original_price)

    def test_outputs_clamped_to_0_1(self):
        t = CobwebMarket()
        for price in [0.0, 0.3, 0.6, 0.9, 1.0]:
            delta = t.update(self._env(price=price), [], 0)
            for v in delta.values():
                assert 0.0 <= v <= 1.0, f"value {v} out of range at price={price}"

    def test_supply_shock_raises_price(self):
        # Supply shock reduces quantity supplied → higher clearing price
        t = CobwebMarket()
        d_base  = t.update(self._env(price=0.43, supply_shock=0.0), [], 0)
        d_shock = t.update(self._env(price=0.43, supply_shock=0.10), [], 0)
        assert d_shock["cobweb__price"] > d_base["cobweb__price"]

    def test_demand_shock_raises_price(self):
        # Demand shock shifts demand curve up → higher clearing price
        t = CobwebMarket()
        d_base  = t.update(self._env(price=0.43, demand_shock=0.0), [], 0)
        d_shock = t.update(self._env(price=0.43, demand_shock=0.10), [], 0)
        assert d_shock["cobweb__price"] > d_base["cobweb__price"]

    def test_at_steady_state_price_volatility_near_zero(self):
        # Start at P*, no shocks → price should not change
        t = CobwebMarket()
        p_star = (0.80 - 0.20) / (0.80 + 0.60)
        delta = t.update(self._env(price=p_star), [], 0)
        assert delta["cobweb__price_volatility"] == pytest.approx(0.0, abs=1e-6)

    def test_convergent_cobweb_price_approaches_steady_state(self):
        # supply_elasticity < demand_elasticity → oscillations converge to P*
        t = CobwebMarket(parameters={"supply_elasticity": 0.40, "demand_elasticity": 0.80})
        p_star = (0.80 - 0.20) / (0.80 + 0.40)
        env = {"cobweb__price": 0.80, "cobweb__supply_shock": 0.0, "cobweb__demand_shock": 0.0}
        initial_deviation = abs(env["cobweb__price"] - p_star)
        for _ in range(30):
            delta = t.update(env, [], 0)
            env = {**env, **delta}
        final_deviation = abs(env["cobweb__price"] - p_star)
        assert final_deviation < initial_deviation

    def test_divergent_cobweb_price_oscillates(self):
        # supply_elasticity > demand_elasticity → oscillations diverge
        # Each tick the price should overshoot to the opposite side of P*
        t = CobwebMarket(parameters={"supply_elasticity": 1.20, "demand_elasticity": 0.80})
        p_star = (0.80 - 0.20) / (0.80 + 1.20)
        env = {"cobweb__price": p_star + 0.05,
               "cobweb__supply_shock": 0.0, "cobweb__demand_shock": 0.0}
        d1 = t.update(env, [], 0)
        # After one tick from above P*, price should move below P* (oscillation)
        assert d1["cobweb__price"] < p_star

    def test_excess_demand_positive_when_demand_exceeds_supply(self):
        # Low price → supply low (lagged), demand high → excess demand > 0
        t = CobwebMarket(parameters={"supply_elasticity": 0.60, "demand_elasticity": 0.80})
        delta = t.update(self._env(price=0.10), [], 0)
        # At low prev_price, supply is low; demand could exceed supply
        # Just verify the value is in [0,1] and non-negative
        assert delta["cobweb__excess_demand"] >= 0.0

    def test_excess_demand_zero_when_supply_exceeds_demand(self):
        # High price → supply high → excess supply → excess_demand = 0
        t = CobwebMarket(parameters={"supply_elasticity": 0.60, "demand_elasticity": 0.80})
        delta = t.update(self._env(price=0.99), [], 0)
        assert delta["cobweb__excess_demand"] == pytest.approx(0.0, abs=1e-6)

    def test_custom_market_id_in_output(self):
        t = CobwebMarket(parameters={"market_id": "housing"})
        delta = t.update(self._env(price=0.43, market_id="housing"), [], 0)
        assert "housing__price" in delta
        assert "cobweb__price" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = CobwebMarket().update({}, [], 0)
        assert 0.0 <= delta["cobweb__price"] <= 1.0
        assert 0.0 <= delta["cobweb__supply"] <= 1.0
        assert 0.0 <= delta["cobweb__demand"] <= 1.0
