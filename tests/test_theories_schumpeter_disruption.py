"""
Tests for core/theories/schumpeter_disruption.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.schumpeter_disruption import SchumpeterDisruption


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "schumpeter_disruption" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("schumpeter_disruption") is SchumpeterDisruption

    def test_theory_id_attribute(self):
        assert SchumpeterDisruption.theory_id == "schumpeter_disruption"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = SchumpeterDisruption()
        assert t.params.incumbent_inertia    == pytest.approx(0.05)
        assert t.params.disruption_coefficient == pytest.approx(0.25)
        assert t.params.innovator_growth_rate  == pytest.approx(0.20)
        assert t.params.incumbent_defense      == pytest.approx(0.10)
        assert t.params.obsolescence_rate      == pytest.approx(0.03)
        assert t.params.innovation_id == "schumpeter"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = SchumpeterDisruption(parameters={"disruption_coefficient": 0.50,
                                              "innovation_id": "ev_auto"})
        assert t.params.disruption_coefficient == pytest.approx(0.50)
        assert t.params.innovation_id == "ev_auto"

    def test_disruption_coefficient_above_one_rejected(self):
        with pytest.raises(Exception):
            SchumpeterDisruption(parameters={"disruption_coefficient": 1.1})

    def test_obsolescence_rate_above_0_20_rejected(self):
        with pytest.raises(Exception):
            SchumpeterDisruption(parameters={"obsolescence_rate": 0.21})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = SchumpeterDisruption().state_variables
        assert "schumpeter__incumbent_share"      in sv.writes
        assert "schumpeter__innovator_share"      in sv.writes
        assert "schumpeter__creative_destruction" in sv.writes
        assert "schumpeter__market_renewal"       in sv.writes

    def test_rd_investment_not_in_writes(self):
        # rd_investment is owned by agents, not by this theory
        assert "schumpeter__rd_investment" not in SchumpeterDisruption().state_variables.writes

    def test_rd_investment_in_initializes(self):
        assert "schumpeter__rd_investment" in SchumpeterDisruption().state_variables.initializes

    def test_custom_innovation_id_reflected_in_keys(self):
        t = SchumpeterDisruption(parameters={"innovation_id": "ev_auto"})
        sv = t.state_variables
        assert "ev_auto__incumbent_share"      in sv.writes
        assert "schumpeter__incumbent_share" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_incumbent_at_0_80(self):
        inits = SchumpeterDisruption().setup({})
        assert inits["schumpeter__incumbent_share"] == pytest.approx(0.80)

    def test_seeds_rd_investment_at_0_10(self):
        inits = SchumpeterDisruption().setup({})
        assert inits["schumpeter__rd_investment"] == pytest.approx(0.10)

    def test_seeds_innovator_at_0_05(self):
        inits = SchumpeterDisruption().setup({})
        assert inits["schumpeter__innovator_share"] == pytest.approx(0.05)

    def test_does_not_overwrite_existing(self):
        env = {"schumpeter__incumbent_share": 0.60,
               "schumpeter__rd_investment":   0.30}
        inits = SchumpeterDisruption().setup(env)
        assert "schumpeter__incumbent_share" not in inits
        assert "schumpeter__rd_investment"   not in inits


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, I=0.80, N=0.05, rd=0.10) -> dict[str, float]:
        return {
            "schumpeter__incumbent_share": I,
            "schumpeter__innovator_share": N,
            "schumpeter__rd_investment":   rd,
        }

    def test_returns_four_keys(self):
        delta = SchumpeterDisruption().update(self._env(), [], 0)
        assert "schumpeter__incumbent_share"      in delta
        assert "schumpeter__innovator_share"      in delta
        assert "schumpeter__creative_destruction" in delta
        assert "schumpeter__market_renewal"       in delta

    def test_does_not_mutate_env(self):
        env = self._env(I=0.80, N=0.05)
        SchumpeterDisruption().update(env, [], 0)
        assert env["schumpeter__incumbent_share"] == pytest.approx(0.80)
        assert env["schumpeter__innovator_share"] == pytest.approx(0.05)

    def test_outputs_clamped_to_0_1(self):
        env = {"schumpeter__incumbent_share": 0.99,
               "schumpeter__innovator_share": 0.99,
               "schumpeter__rd_investment":   0.99}
        delta = SchumpeterDisruption().update(env, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_incumbent_plus_innovator_le_one(self):
        # After normalization, I + N must never exceed 1.0
        t = SchumpeterDisruption(parameters={"disruption_coefficient": 0.0,
                                              "incumbent_inertia": 0.50,
                                              "innovator_growth_rate": 0.50})
        env = self._env(I=0.60, N=0.50)
        delta = t.update(env, [], 0)
        assert delta["schumpeter__incumbent_share"] + delta["schumpeter__innovator_share"] <= 1.0 + 1e-9

    def test_higher_disruption_coefficient_produces_more_creative_destruction(self):
        # Same I and N; higher γ → higher γ×I×N
        env = self._env(I=0.60, N=0.30)
        t_low  = SchumpeterDisruption(parameters={"disruption_coefficient": 0.10})
        t_high = SchumpeterDisruption(parameters={"disruption_coefficient": 0.80})
        d_low  = t_low.update(env, [], 0)
        d_high = t_high.update(env, [], 0)
        assert d_high["schumpeter__creative_destruction"] > d_low["schumpeter__creative_destruction"]

    def test_higher_rd_investment_accelerates_innovator_growth(self):
        # Higher rd → higher dN → larger new_N
        env_low  = self._env(I=0.50, N=0.10, rd=0.05)
        env_high = self._env(I=0.50, N=0.10, rd=0.50)
        t = SchumpeterDisruption()
        d_low  = t.update(env_low,  [], 0)
        d_high = t.update(env_high, [], 0)
        assert d_high["schumpeter__innovator_share"] > d_low["schumpeter__innovator_share"]

    def test_strong_incumbent_resists_innovator(self):
        # I near 1.0 → I² defense term large → innovator growth suppressed
        t_weak   = SchumpeterDisruption(parameters={"incumbent_defense": 0.0})
        t_strong = SchumpeterDisruption(parameters={"incumbent_defense": 1.0})
        env = self._env(I=0.90, N=0.05)
        d_weak   = t_weak.update(env, [], 0)
        d_strong = t_strong.update(env, [], 0)
        assert d_strong["schumpeter__innovator_share"] <= d_weak["schumpeter__innovator_share"]

    def test_creative_destruction_zero_when_innovator_is_zero(self):
        # γ × I × 0 = 0
        delta = SchumpeterDisruption().update(self._env(I=0.80, N=0.0), [], 0)
        assert delta["schumpeter__creative_destruction"] == pytest.approx(0.0, abs=1e-9)

    def test_creative_destruction_zero_when_incumbent_is_zero(self):
        # γ × 0 × N = 0
        delta = SchumpeterDisruption().update(self._env(I=0.0, N=0.30), [], 0)
        assert delta["schumpeter__creative_destruction"] == pytest.approx(0.0, abs=1e-9)

    def test_market_renewal_near_zero_when_innovator_near_zero(self):
        # N/(I+N) ≈ 0 when N ≈ 0
        delta = SchumpeterDisruption().update(self._env(I=0.90, N=0.001), [], 0)
        assert delta["schumpeter__market_renewal"] < 0.05

    def test_higher_innovator_share_higher_market_renewal(self):
        # N/(I+N) increases with N for fixed I
        t = SchumpeterDisruption()
        d_low  = t.update(self._env(I=0.50, N=0.05), [], 0)
        d_high = t.update(self._env(I=0.50, N=0.40), [], 0)
        assert d_high["schumpeter__market_renewal"] > d_low["schumpeter__market_renewal"]

    def test_custom_innovation_id_in_output(self):
        t = SchumpeterDisruption(parameters={"innovation_id": "ev_auto"})
        delta = t.update(
            {"ev_auto__incumbent_share": 0.80,
             "ev_auto__innovator_share": 0.05,
             "ev_auto__rd_investment":   0.10},
            [], 0,
        )
        assert "ev_auto__incumbent_share"      in delta
        assert "schumpeter__incumbent_share" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = SchumpeterDisruption().update({}, [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0
