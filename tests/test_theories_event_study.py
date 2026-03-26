"""
Tests for core/theories/event_study.py
MacKinlay (1997) CAPM-based Event Study / Abnormal Return
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.event_study import EventStudy


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "event_study" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("event_study") is EventStudy

    def test_theory_id_attribute(self):
        assert EventStudy.theory_id == "event_study"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = EventStudy()
        assert t.params.beta_market == 1.0
        assert t.params.risk_free_rate == pytest.approx(0.045)
        assert t.params.alpha == 0.0
        assert t.params.event_id == "event"
        assert t.params.tick_unit == "day"

    def test_parameter_overrides(self):
        t = EventStudy(parameters={"beta_market": 1.15, "event_id": "puig_deal"})
        assert t.params.beta_market == 1.15
        assert t.params.event_id == "puig_deal"

    def test_risk_free_above_twenty_pct_rejected(self):
        with pytest.raises(Exception):
            EventStudy(parameters={"risk_free_rate": 0.25})

    def test_alpha_out_of_range_rejected(self):
        with pytest.raises(Exception):
            EventStudy(parameters={"alpha": 0.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_all_three_keys(self):
        sv = EventStudy().state_variables
        assert "event__expected_return" in sv.writes
        assert "event__abnormal_return" in sv.writes
        assert "event__cumulative_ar"   in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = EventStudy().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_event_id_reflected_in_keys(self):
        t = EventStudy(parameters={"event_id": "puig"})
        sv = t.state_variables
        assert "puig__abnormal_return"  in sv.writes
        assert "event__abnormal_return" not in sv.writes


# ── Setup ─────────────────────────────────────────────────────────────────────

class TestSetup:
    def test_setup_seeds_neutral_values(self):
        t = EventStudy()
        inits = t.setup({})
        assert inits["event__expected_return"] == pytest.approx(0.5)
        assert inits["event__abnormal_return"]  == pytest.approx(0.5)
        assert inits["event__cumulative_ar"]    == pytest.approx(0.5)

    def test_setup_does_not_overwrite_existing(self):
        t = EventStudy()
        env = {"event__cumulative_ar": 0.3}
        inits = t.setup(env)
        assert "event__cumulative_ar" not in inits


# ── Update — CAPM mechanics ───────────────────────────────────────────────────

class TestCAPM:
    def _run_tick(self, params: dict, env: dict) -> dict:
        t = EventStudy(parameters=params)
        full_env = {**t.setup({}), **env}
        return t.update(full_env, [], 0)

    def test_neutral_market_no_actual_return_ar_near_zero(self):
        """Flat market, flat actual return → AR near zero → normalized ≈ 0.5."""
        result = self._run_tick({}, {
            "global__market_return": 0.5,     # 0% market return
            "event__actual_return":  0.5,     # 0% actual return
        })
        # Expected return ≈ R_f_daily + alpha (both ~0 on day scale)
        # AR ≈ 0 → normalized ≈ 0.5
        assert result["event__abnormal_return"] == pytest.approx(0.5, abs=0.02)

    def test_positive_surprise_produces_ar_above_half(self):
        """Actual return > expected return → AR > 0 → normalized > 0.5."""
        result = self._run_tick({}, {
            "global__market_return": 0.5,   # flat market
            "event__actual_return":  0.75,  # +10% actual (0.75 = +10% at scale 0.40)
        })
        assert result["event__abnormal_return"] > 0.5

    def test_negative_surprise_produces_ar_below_half(self):
        """Actual return < expected return → AR < 0 → normalized < 0.5."""
        result = self._run_tick({}, {
            "global__market_return": 0.5,   # flat market
            "event__actual_return":  0.25,  # -10% actual
        })
        assert result["event__abnormal_return"] < 0.5

    def test_high_beta_amplifies_expected_return(self):
        """Higher beta → larger expected return when market is up → smaller AR for same actual."""
        env = {"global__market_return": 0.75, "event__actual_return": 0.60}
        low_beta  = self._run_tick({"beta_market": 0.5},  env)
        high_beta = self._run_tick({"beta_market": 2.0},  env)
        # High beta expects more → AR should be smaller (or more negative)
        assert high_beta["event__abnormal_return"] <= low_beta["event__abnormal_return"]

    def test_car_accumulates_across_ticks(self):
        """CAR should shift from 0.5 after multiple negative AR ticks."""
        t = EventStudy(parameters={"tick_unit": "day"})
        env = {**t.setup({}), "global__market_return": 0.5, "event__actual_return": 0.25}
        result1 = t.update({**env}, [], 0)
        result2 = t.update({**env}, [], 1)
        # Each tick has negative AR → CAR_2 should be less than CAR_1
        assert result2["event__cumulative_ar"] < result1["event__cumulative_ar"]

    def test_all_outputs_normalized(self):
        """All output values must be in [0, 1]."""
        result = self._run_tick({"beta_market": 3.0}, {
            "global__market_return": 0.0,
            "event__actual_return":  1.0,
        })
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"

    def test_beta_one_market_flat_zero_rf_ar_equals_actual(self):
        """β=1, flat market (0.5), zero risk-free, zero alpha → AR = actual - 0 = actual."""
        result = self._run_tick(
            {"beta_market": 1.0, "risk_free_rate": 0.0, "alpha": 0.0},
            {"global__market_return": 0.5, "event__actual_return": 0.625},
        )
        # actual = 0.625 → raw = +5%; market flat → expected ≈ 0; AR ≈ +5% → norm ≈ 0.625
        assert result["event__abnormal_return"] == pytest.approx(0.625, abs=0.01)

    def test_el_puig_announcement_calibration(self):
        """EL dropped ~10% while market dropped ~2% on announcement. AR ≈ -8%."""
        # Normalized: -10% actual = 0.5 - 0.10/0.40 = 0.25
        # Market -2% = 0.5 - 0.02/0.40 = 0.45
        # EL beta ≈ 1.15 → expected ≈ 1.15 × (-2%) = -2.3% per day
        # AR ≈ -10% - (-2.3%) = -7.7%
        result = self._run_tick(
            {"beta_market": 1.15, "risk_free_rate": 0.045, "tick_unit": "day"},
            {
                "global__market_return": 0.45,   # market -2%
                "event__actual_return":  0.25,   # EL -10%
            },
        )
        # AR should be significantly negative (well below 0.5)
        assert result["event__abnormal_return"] < 0.40
