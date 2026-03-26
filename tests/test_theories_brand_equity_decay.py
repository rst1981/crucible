"""
Tests for core/theories/brand_equity_decay.py
Keller (1993) Customer-Based Brand Equity Decay
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.brand_equity_decay import BrandEquityDecay


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "brand_equity_decay" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("brand_equity_decay") is BrandEquityDecay

    def test_theory_id_attribute(self):
        assert BrandEquityDecay.theory_id == "brand_equity_decay"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = BrandEquityDecay()
        assert t.params.initial_brand_equity == 0.75
        assert t.params.decay_coefficient == 0.08
        assert t.params.brand_id == "brand"
        assert t.params.tick_unit == "quarter"

    def test_parameter_overrides(self):
        t = BrandEquityDecay(parameters={"initial_brand_equity": 0.60, "brand_id": "clinique"})
        assert t.params.initial_brand_equity == 0.60
        assert t.params.brand_id == "clinique"

    def test_decay_above_one_rejected(self):
        with pytest.raises(Exception):
            BrandEquityDecay(parameters={"decay_coefficient": 1.5})

    def test_equity_above_one_rejected(self):
        with pytest.raises(Exception):
            BrandEquityDecay(parameters={"initial_brand_equity": 1.1})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_all_four_keys(self):
        sv = BrandEquityDecay().state_variables
        assert "brand__brand_equity"  in sv.writes
        assert "brand__price_premium" in sv.writes
        assert "brand__awareness"     in sv.writes
        assert "brand__loyalty"       in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = BrandEquityDecay().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_brand_id_reflected_in_keys(self):
        t = BrandEquityDecay(parameters={"brand_id": "mac"})
        sv = t.state_variables
        assert "mac__brand_equity"  in sv.writes
        assert "brand__brand_equity" not in sv.writes


# ── Setup ─────────────────────────────────────────────────────────────────────

class TestSetup:
    def test_setup_seeds_initial_equity(self):
        t = BrandEquityDecay(parameters={"initial_brand_equity": 0.80})
        inits = t.setup({})
        assert inits["brand__brand_equity"] == pytest.approx(0.80)

    def test_setup_seeds_price_premium_proportional(self):
        t = BrandEquityDecay(parameters={
            "initial_brand_equity": 0.80,
            "max_price_premium_fraction": 0.40,
        })
        inits = t.setup({})
        assert inits["brand__price_premium"] == pytest.approx(0.80 * 0.40, abs=0.01)

    def test_setup_does_not_overwrite_existing_keys(self):
        t = BrandEquityDecay()
        env = {"brand__brand_equity": 0.30}
        inits = t.setup(env)
        assert "brand__brand_equity" not in inits


# ── Update — Decay ────────────────────────────────────────────────────────────

class TestUpdateDecay:
    def _run(self, params: dict, env: dict) -> dict:
        t = BrandEquityDecay(parameters=params)
        full_env = {**t.setup({}), **env}
        return t.update(full_env, [], 0)

    def test_equity_decays_without_marketing(self):
        """Brand equity should decrease each tick without marketing investment."""
        result = self._run({}, {})
        assert result["brand__brand_equity"] < 0.75

    def test_higher_competitive_pressure_faster_decay(self):
        """More competitive pressure → faster equity decay."""
        low_pressure  = self._run({}, {"global__competitive_pressure": 0.1})
        high_pressure = self._run({}, {"global__competitive_pressure": 0.9})
        assert high_pressure["brand__brand_equity"] < low_pressure["brand__brand_equity"]

    def test_marketing_investment_slows_decay(self):
        """Marketing investment rebuilds equity and can offset decay."""
        no_marketing   = self._run({}, {"brand__marketing_investment": 0.0})
        high_marketing = self._run({}, {"brand__marketing_investment": 1.0})
        assert high_marketing["brand__brand_equity"] > no_marketing["brand__brand_equity"]

    def test_awareness_decays_slower_than_equity(self):
        """Awareness should lose less than equity in one tick at equal decay rates."""
        t = BrandEquityDecay(parameters={"tick_unit": "year"})
        env = {**t.setup({}), "global__competitive_pressure": 0.5}
        result = t.update(env, [], 0)
        equity_loss    = 0.75 - result["brand__brand_equity"]
        awareness_loss = 0.85 - result["brand__awareness"]
        assert awareness_loss < equity_loss

    def test_loyalty_decays_slower_than_awareness(self):
        """Loyalty should be more persistent than awareness."""
        t = BrandEquityDecay(parameters={"tick_unit": "year"})
        env = {**t.setup({}), "global__competitive_pressure": 0.5}
        result = t.update(env, [], 0)
        awareness_loss = 0.85 - result["brand__awareness"]
        loyalty_loss   = 0.65 - result["brand__loyalty"]
        assert loyalty_loss < awareness_loss

    def test_price_premium_scales_with_equity(self):
        """Price premium should equal equity × max_price_premium_fraction."""
        t = BrandEquityDecay(parameters={"max_price_premium_fraction": 0.40})
        env = {**t.setup({})}
        result = t.update(env, [], 0)
        expected_premium = result["brand__brand_equity"] * 0.40
        assert result["brand__price_premium"] == pytest.approx(expected_premium, abs=0.001)

    def test_all_outputs_normalized(self):
        """All output values must be in [0, 1]."""
        result = self._run(
            {"tick_unit": "year"},
            {"global__competitive_pressure": 1.0, "brand__media_negative": 1.0},
        )
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"

    def test_equity_does_not_decay_below_zero(self):
        """Brand equity is clamped to [0, 1] even under extreme decay."""
        t = BrandEquityDecay(parameters={
            "decay_coefficient": 0.99,
            "tick_unit": "year",
        })
        env = {**t.setup({}), "global__competitive_pressure": 1.0}
        result = t.update(env, [], 0)
        assert result["brand__brand_equity"] >= 0.0

    def test_media_negativity_accelerates_decay(self):
        """Negative media coverage amplifies equity decay."""
        no_media  = self._run({}, {"brand__media_negative": 0.0})
        neg_media = self._run({}, {"brand__media_negative": 1.0})
        assert neg_media["brand__brand_equity"] < no_media["brand__brand_equity"]
