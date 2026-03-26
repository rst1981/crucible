"""
Tests for core/theories/acquirer_discount.py
Roll (1986) Acquirer's Discount / Hubris Hypothesis
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.acquirer_discount import AcquirerDiscount


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "acquirer_discount" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("acquirer_discount") is AcquirerDiscount

    def test_theory_id_attribute(self):
        assert AcquirerDiscount.theory_id == "acquirer_discount"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = AcquirerDiscount()
        assert t.params.deal_premium == 1.30
        assert t.params.deal_size_ratio == 0.35
        assert t.params.hubris_factor == 0.65
        assert t.params.synergy_realization_probability == 0.40
        assert t.params.acquirer_id == "acquirer"

    def test_parameter_overrides(self):
        t = AcquirerDiscount(parameters={"deal_premium": 1.50, "acquirer_id": "estee_lauder"})
        assert t.params.deal_premium == 1.50
        assert t.params.acquirer_id == "estee_lauder"

    def test_deal_premium_below_one_rejected(self):
        with pytest.raises(Exception):
            AcquirerDiscount(parameters={"deal_premium": 0.9})

    def test_hubris_above_one_rejected(self):
        with pytest.raises(Exception):
            AcquirerDiscount(parameters={"hubris_factor": 1.5})

    def test_synergy_prob_above_one_rejected(self):
        with pytest.raises(Exception):
            AcquirerDiscount(parameters={"synergy_realization_probability": 1.1})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_all_three_keys(self):
        sv = AcquirerDiscount().state_variables
        assert "acquirer__abnormal_return"   in sv.writes
        assert "acquirer__cumulative_ar"     in sv.writes
        assert "acquirer__integration_cost"  in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = AcquirerDiscount().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_acquirer_id_reflected_in_keys(self):
        t = AcquirerDiscount(parameters={"acquirer_id": "el"})
        sv = t.state_variables
        assert "el__abnormal_return"  in sv.writes
        assert "acquirer__abnormal_return" not in sv.writes


# ── Setup ─────────────────────────────────────────────────────────────────────

class TestSetup:
    def test_setup_seeds_neutral_returns(self):
        t = AcquirerDiscount()
        env: dict[str, float] = {}
        inits = t.setup(env)
        assert inits["acquirer__abnormal_return"] == pytest.approx(0.5)
        assert inits["acquirer__cumulative_ar"]   == pytest.approx(0.5)

    def test_setup_does_not_overwrite_existing_env_keys(self):
        t = AcquirerDiscount()
        env = {"acquirer__abnormal_return": 0.3}
        inits = t.setup(env)
        assert "acquirer__abnormal_return" not in inits


# ── Update — Baseline ─────────────────────────────────────────────────────────

class TestUpdateBaseline:
    def _run(self, params: dict, env: dict) -> dict:
        t = AcquirerDiscount(parameters=params)
        env_with_inits = {**t.setup(env), **env}
        return t.update(env_with_inits, [], 0)

    def test_no_announcement_returns_near_neutral(self):
        """Without deal_announced, AR should be slightly negative (integration drag) or neutral."""
        result = self._run({}, {})
        # No announcement and no integration cost: AR should be exactly neutral
        assert result["acquirer__abnormal_return"] == pytest.approx(0.5, abs=0.02)

    def test_announcement_produces_negative_ar(self):
        """On announcement tick, AR should be < 0.5 (negative abnormal return)."""
        result = self._run({}, {"acquirer__deal_announced": 1.0})
        assert result["acquirer__abnormal_return"] < 0.5

    def test_announcement_ar_magnitude_increases_with_hubris(self):
        """Higher hubris → more negative AR."""
        env = {"acquirer__deal_announced": 1.0}
        low_hubris  = self._run({"hubris_factor": 0.2}, env)
        high_hubris = self._run({"hubris_factor": 0.9}, env)
        assert high_hubris["acquirer__abnormal_return"] < low_hubris["acquirer__abnormal_return"]

    def test_announcement_ar_magnitude_increases_with_premium(self):
        """Higher deal premium → more negative AR."""
        env = {"acquirer__deal_announced": 1.0}
        low_premium  = self._run({"deal_premium": 1.10}, env)
        high_premium = self._run({"deal_premium": 1.60}, env)
        assert high_premium["acquirer__abnormal_return"] < low_premium["acquirer__abnormal_return"]

    def test_integration_cost_peaks_on_announcement(self):
        """integration_cost should jump to integration_complexity on announcement day."""
        t = AcquirerDiscount(parameters={"integration_complexity": 0.70})
        env = {"acquirer__deal_announced": 1.0}
        env.update(t.setup({}))
        result = t.update(env, [], 0)
        assert result["acquirer__integration_cost"] == pytest.approx(0.70, abs=0.01)

    def test_integration_cost_decays_after_announcement(self):
        """integration_cost decays on subsequent ticks."""
        t = AcquirerDiscount(parameters={
            "integration_complexity": 0.60,
            "integration_completion_rate": 0.50,
            "tick_unit": "year",
        })
        env = {**t.setup({}), "acquirer__integration_cost": 0.60}
        result = t.update(env, [], 1)
        assert result["acquirer__integration_cost"] < 0.60

    def test_all_outputs_normalized(self):
        """All output values must be in [0, 1]."""
        result = self._run({}, {"acquirer__deal_announced": 1.0, "global__market_stress": 0.8})
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"

    def test_el_puig_calibration(self):
        """EL/Puig deal params should produce ~-10% AR on announcement (≈ -0.5 in normalized)."""
        env = {"acquirer__deal_announced": 1.0}
        result = self._run(
            {
                "deal_premium": 1.30,
                "deal_size_ratio": 0.355,
                "hubris_factor": 0.80,
                "synergy_realization_probability": 0.40,
                "acquirer_id": "acquirer",
            },
            env,
        )
        # Normalized 0.5 = 0%. -10% AR → ~0.5 - 0.10/0.40 = 0.25
        # Accept a range: should be well below 0.45
        assert result["acquirer__abnormal_return"] < 0.45
