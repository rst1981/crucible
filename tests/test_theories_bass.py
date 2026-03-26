"""
Tests for core/theories/bass_diffusion.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.bass_diffusion import BassDiffusion


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "bass_diffusion" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("bass_diffusion") is BassDiffusion

    def test_theory_id_attribute(self):
        assert BassDiffusion.theory_id == "bass_diffusion"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = BassDiffusion()
        assert t.params.p == 0.03
        assert t.params.q == 0.38
        assert t.params.tick_unit == "year"
        assert t.params.market_id == "bass"

    def test_parameter_overrides(self):
        t = BassDiffusion(parameters={"p": 0.05, "q": 0.45, "market_id": "ev"})
        assert t.params.p == 0.05
        assert t.params.q == 0.45
        assert t.params.market_id == "ev"

    def test_p_below_zero_rejected(self):
        with pytest.raises(Exception):
            BassDiffusion(parameters={"p": -0.01})

    def test_p_above_one_rejected(self):
        with pytest.raises(Exception):
            BassDiffusion(parameters={"p": 1.1})

    def test_q_above_one_rejected(self):
        with pytest.raises(Exception):
            BassDiffusion(parameters={"q": 1.5})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_contains_all_four_keys(self):
        sv = BassDiffusion().state_variables
        assert "bass__adoption_fraction" in sv.writes
        assert "bass__adoption_rate"     in sv.writes
        assert "bass__innovator_rate"    in sv.writes
        assert "bass__imitator_rate"     in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = BassDiffusion().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_market_id_reflected_in_keys(self):
        t = BassDiffusion(parameters={"market_id": "ev"})
        sv = t.state_variables
        assert "ev__adoption_fraction" in sv.writes
        assert "bass__adoption_fraction" not in sv.writes

    def test_reads_cross_theory_keys(self):
        sv = BassDiffusion().state_variables
        assert "keynesian__gdp_normalized" in sv.reads
        assert "global__trade_volume" in sv.reads


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_adoption_fraction_at_zero(self):
        inits = BassDiffusion().setup({})
        assert inits["bass__adoption_fraction"] == 0.0

    def test_does_not_overwrite_existing_adoption(self):
        inits = BassDiffusion().setup({"bass__adoption_fraction": 0.3})
        assert "bass__adoption_fraction" not in inits

    def test_seeds_all_four_keys(self):
        inits = BassDiffusion().setup({})
        assert "bass__adoption_fraction" in inits
        assert "bass__adoption_rate"     in inits
        assert "bass__innovator_rate"    in inits
        assert "bass__imitator_rate"     in inits


# ── update() — core ODE logic ─────────────────────────────────────────────────

class TestUpdate:
    def test_returns_all_four_keys(self):
        delta = BassDiffusion().update({}, [], 0)
        assert "bass__adoption_fraction" in delta
        assert "bass__adoption_rate"     in delta
        assert "bass__innovator_rate"    in delta
        assert "bass__imitator_rate"     in delta

    def test_does_not_mutate_env(self):
        env = {"bass__adoption_fraction": 0.3}
        BassDiffusion().update(env, [], 0)
        assert env["bass__adoption_fraction"] == 0.3

    def test_outputs_clamped_to_0_1(self):
        # Even at extreme params, outputs must stay in [0, 1]
        t = BassDiffusion(parameters={"p": 1.0, "q": 1.0})
        delta = t.update({"bass__adoption_fraction": 0.5}, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_zero_adoption_grows_via_innovation(self):
        # At N=0, only p drives growth; adoption must increase
        t = BassDiffusion(parameters={"p": 0.05, "q": 0.4, "tick_unit": "year"})
        delta = t.update({"bass__adoption_fraction": 0.0}, [], 0)
        assert delta["bass__adoption_fraction"] > 0.0

    def test_innovator_rate_nonzero_at_zero_adoption(self):
        t = BassDiffusion(parameters={"p": 0.05, "q": 0.4})
        delta = t.update({"bass__adoption_fraction": 0.0}, [], 0)
        assert delta["bass__innovator_rate"] > 0.0
        assert delta["bass__imitator_rate"] == 0.0  # q·0·(1-0) = 0

    def test_imitator_rate_dominates_at_mid_adoption(self):
        # At N=0.5 with q >> p, imitator_rate should exceed innovator_rate
        t = BassDiffusion(parameters={"p": 0.03, "q": 0.5})
        delta = t.update({"bass__adoption_fraction": 0.5}, [], 0)
        assert delta["bass__imitator_rate"] > delta["bass__innovator_rate"]

    def test_fully_saturated_market_stays_at_one(self):
        # At N=1, remaining market = 0, so dN/dt = 0
        delta = BassDiffusion().update({"bass__adoption_fraction": 1.0}, [], 0)
        assert delta["bass__adoption_fraction"] == 1.0
        assert delta["bass__adoption_rate"] == 0.0

    def test_adoption_increases_monotonically_before_saturation(self):
        t = BassDiffusion(parameters={"p": 0.03, "q": 0.38, "tick_unit": "year"})
        env = {"bass__adoption_fraction": 0.0}
        prev = 0.0
        for _ in range(20):
            delta = t.update(env, [], 0)
            env.update(delta)
            assert env["bass__adoption_fraction"] >= prev
            prev = env["bass__adoption_fraction"]

    def test_tick_unit_month_smaller_than_year(self):
        env = {"bass__adoption_fraction": 0.3}
        d_year  = BassDiffusion(parameters={"tick_unit": "year"}).update(env, [], 0)
        d_month = BassDiffusion(parameters={"tick_unit": "month"}).update(env, [], 0)
        year_change  = d_year["bass__adoption_fraction"]  - 0.3
        month_change = d_month["bass__adoption_fraction"] - 0.3
        assert month_change < year_change

    def test_gdp_above_baseline_increases_adoption_rate(self):
        env_base = {"bass__adoption_fraction": 0.3, "keynesian__gdp_normalized": 0.5}
        env_boom = {"bass__adoption_fraction": 0.3, "keynesian__gdp_normalized": 0.9}
        t = BassDiffusion()
        d_base = t.update(env_base, [], 0)
        d_boom = t.update(env_boom, [], 0)
        assert d_boom["bass__adoption_fraction"] > d_base["bass__adoption_fraction"]

    def test_trade_disruption_reduces_innovator_rate(self):
        env_normal    = {"bass__adoption_fraction": 0.3, "global__trade_volume": 0.5}
        env_disrupted = {"bass__adoption_fraction": 0.3, "global__trade_volume": 0.1}
        t = BassDiffusion()
        d_normal    = t.update(env_normal, [], 0)
        d_disrupted = t.update(env_disrupted, [], 0)
        assert d_disrupted["bass__innovator_rate"] < d_normal["bass__innovator_rate"]

    def test_multi_tick_converges_toward_full_adoption(self):
        t = BassDiffusion(parameters={"p": 0.05, "q": 0.5, "tick_unit": "year"})
        env = {"bass__adoption_fraction": 0.0}
        for _ in range(40):
            env.update(t.update(env, [], 0))
        assert env["bass__adoption_fraction"] > 0.95

    def test_custom_market_id_in_output(self):
        t = BassDiffusion(parameters={"market_id": "ev"})
        delta = t.update({"ev__adoption_fraction": 0.2}, [], 0)
        assert "ev__adoption_fraction" in delta
        assert "bass__adoption_fraction" not in delta

    def test_missing_env_keys_default_gracefully(self):
        # Empty env should not crash; N defaults to 0
        delta = BassDiffusion().update({}, [], 0)
        assert 0.0 <= delta["bass__adoption_fraction"] <= 1.0
