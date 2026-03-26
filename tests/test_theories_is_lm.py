"""
Tests for core/theories/is_lm.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.is_lm import ISLM


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "is_lm" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("is_lm") is ISLM

    def test_theory_id_attribute(self):
        assert ISLM.theory_id == "is_lm"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = ISLM()
        assert t.params.mpc == pytest.approx(0.75)
        assert t.params.investment_sensitivity == pytest.approx(0.30)
        assert t.params.income_money_demand == pytest.approx(0.50)
        assert t.params.rate_money_demand == pytest.approx(0.40)
        assert t.params.adjustment_speed == pytest.approx(0.50)
        assert t.params.tick_unit == "year"
        assert t.params.market_id == "islm"

    def test_parameter_overrides(self):
        t = ISLM(parameters={"mpc": 0.80, "market_id": "us_macro"})
        assert t.params.mpc == pytest.approx(0.80)
        assert t.params.market_id == "us_macro"

    def test_mpc_at_or_above_one_rejected(self):
        with pytest.raises(Exception):
            ISLM(parameters={"mpc": 1.0})

    def test_rate_money_demand_at_or_below_zero_rejected(self):
        with pytest.raises(Exception):
            ISLM(parameters={"rate_money_demand": 0.0})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = ISLM().state_variables
        assert "islm__output_gap"    in sv.writes
        assert "islm__interest_rate" in sv.writes
        assert "islm__investment"    in sv.writes
        assert "islm__is_lm_gap"     in sv.writes

    def test_fiscal_stimulus_not_in_writes(self):
        # fiscal_stimulus is owned by policy agents, not by this theory
        assert "islm__fiscal_stimulus" not in ISLM().state_variables.writes

    def test_fiscal_stimulus_in_initializes(self):
        assert "islm__fiscal_stimulus" in ISLM().state_variables.initializes

    def test_money_supply_in_initializes(self):
        assert "islm__money_supply" in ISLM().state_variables.initializes

    def test_custom_market_id_reflected_in_keys(self):
        t = ISLM(parameters={"market_id": "eu_macro"})
        sv = t.state_variables
        assert "eu_macro__output_gap" in sv.writes
        assert "islm__output_gap" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_output_gap_at_0_50(self):
        inits = ISLM().setup({})
        assert inits["islm__output_gap"] == pytest.approx(0.50)

    def test_seeds_money_supply_at_0_50(self):
        inits = ISLM().setup({})
        assert inits["islm__money_supply"] == pytest.approx(0.50)

    def test_seeds_interest_rate_at_0_05(self):
        inits = ISLM().setup({})
        assert inits["islm__interest_rate"] == pytest.approx(0.05)

    def test_seeds_fiscal_stimulus_at_0_0(self):
        inits = ISLM().setup({})
        assert inits["islm__fiscal_stimulus"] == pytest.approx(0.0)

    def test_does_not_overwrite_existing(self):
        env = {"islm__output_gap": 0.70, "islm__money_supply": 0.30}
        inits = ISLM().setup(env)
        assert "islm__output_gap"  not in inits
        assert "islm__money_supply" not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, Y=0.50, r=0.05, G=0.0, M=0.50) -> dict[str, float]:
        return {
            "islm__output_gap":     Y,
            "islm__interest_rate":  r,
            "islm__fiscal_stimulus": G,
            "islm__money_supply":   M,
        }

    def test_returns_four_keys(self):
        delta = ISLM().update(self._env(), [], 0)
        assert "islm__output_gap"    in delta
        assert "islm__interest_rate" in delta
        assert "islm__investment"    in delta
        assert "islm__is_lm_gap"     in delta

    def test_does_not_mutate_env(self):
        env = self._env(Y=0.50, r=0.05)
        ISLM().update(env, [], 0)
        assert env["islm__output_gap"]   == pytest.approx(0.50)
        assert env["islm__interest_rate"] == pytest.approx(0.05)

    def test_outputs_clamped_to_0_1(self):
        # Use extreme values to stress-test clamping
        env = {"islm__output_gap": 0.99, "islm__interest_rate": 0.99,
               "islm__fiscal_stimulus": 0.99, "islm__money_supply": 0.99}
        delta = ISLM().update(env, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_fiscal_stimulus_raises_output_gap(self):
        # Higher G shifts IS right → higher Y_IS → Y adjusts upward
        t = ISLM()
        d_none = t.update(self._env(G=0.0), [], 0)
        d_stim = t.update(self._env(G=0.20), [], 0)
        assert d_stim["islm__output_gap"] > d_none["islm__output_gap"]

    def test_higher_money_supply_lowers_interest_rate(self):
        # Higher M shifts LM right → lower r_LM → r adjusts downward.
        # Use Y=0.80, r=0.30 so both M values yield distinct (non-clamped) r_LM targets.
        t = ISLM()
        env_base = {"islm__output_gap": 0.80, "islm__interest_rate": 0.30,
                    "islm__fiscal_stimulus": 0.0, "islm__money_supply": 0.30}
        env_hi_m = {"islm__output_gap": 0.80, "islm__interest_rate": 0.30,
                    "islm__fiscal_stimulus": 0.0, "islm__money_supply": 0.80}
        d_low  = t.update(env_base, [], 0)
        d_high = t.update(env_hi_m, [], 0)
        assert d_high["islm__interest_rate"] < d_low["islm__interest_rate"]

    def test_lower_interest_rate_raises_investment(self):
        # Lower r → lower interest-rate drag on investment → higher I
        t = ISLM()
        d_low_r  = t.update(self._env(r=0.05), [], 0)
        d_high_r = t.update(self._env(r=0.40), [], 0)
        assert d_low_r["islm__investment"] > d_high_r["islm__investment"]

    def test_higher_mpc_amplifies_fiscal_multiplier(self):
        # Higher MPC → larger 1/(1-MPC) → same G produces bigger output response
        env_base = self._env(G=0.10, Y=0.50)
        t_low  = ISLM(parameters={"mpc": 0.50, "adjustment_speed": 1.0})
        t_high = ISLM(parameters={"mpc": 0.90, "adjustment_speed": 1.0})
        d_low  = t_low.update(env_base, [], 0)
        d_high = t_high.update(env_base, [], 0)
        assert d_high["islm__output_gap"] > d_low["islm__output_gap"]

    def test_is_lm_gap_near_zero_at_equilibrium(self):
        # Start near equilibrium (default seeds); gap should be small
        # At Y=0.5, r=0.05 with default params, the system is close to equilibrium
        t = ISLM(parameters={"adjustment_speed": 1.0})
        env = self._env(Y=0.50, r=0.05, G=0.0, M=0.50)
        # Run several ticks to settle
        for _ in range(20):
            env.update(t.update(env, [], 0))
        assert env["islm__is_lm_gap"] < 0.20

    def test_custom_market_id_in_output(self):
        t = ISLM(parameters={"market_id": "eu_macro"})
        delta = t.update(
            {"eu_macro__output_gap": 0.50, "eu_macro__interest_rate": 0.05,
             "eu_macro__fiscal_stimulus": 0.0, "eu_macro__money_supply": 0.50},
            [], 0,
        )
        assert "eu_macro__output_gap"  in delta
        assert "islm__output_gap" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = ISLM().update({}, [], 0)
        assert 0.0 <= delta["islm__output_gap"]    <= 1.0
        assert 0.0 <= delta["islm__interest_rate"] <= 1.0
        assert 0.0 <= delta["islm__investment"]    <= 1.0
        assert 0.0 <= delta["islm__is_lm_gap"]     <= 1.0
