"""
Tests for core/theories/lotka_volterra.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.lotka_volterra import LotkaVolterra


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "lotka_volterra" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("lotka_volterra") is LotkaVolterra

    def test_theory_id_attribute(self):
        assert LotkaVolterra.theory_id == "lotka_volterra"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = LotkaVolterra()
        assert t.params.prey_growth_rate == pytest.approx(0.10)
        assert t.params.predator_efficiency == pytest.approx(0.30)
        assert t.params.predator_mortality == pytest.approx(0.05)
        assert t.params.conversion_efficiency == pytest.approx(0.20)
        assert t.params.carrying_capacity == pytest.approx(1.0)
        assert t.params.tick_unit == "year"
        assert t.params.ecosystem_id == "ecosystem"

    def test_parameter_overrides(self):
        t = LotkaVolterra(parameters={"prey_growth_rate": 0.20, "ecosystem_id": "ev_market"})
        assert t.params.prey_growth_rate == pytest.approx(0.20)
        assert t.params.ecosystem_id == "ev_market"

    def test_prey_growth_rate_above_one_rejected(self):
        with pytest.raises(Exception):
            LotkaVolterra(parameters={"prey_growth_rate": 1.5})

    def test_predator_efficiency_above_two_rejected(self):
        with pytest.raises(Exception):
            LotkaVolterra(parameters={"predator_efficiency": 2.5})

    def test_predator_mortality_above_one_rejected(self):
        with pytest.raises(Exception):
            LotkaVolterra(parameters={"predator_mortality": 1.2})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = LotkaVolterra().state_variables
        assert "ecosystem__incumbent_share" in sv.writes
        assert "ecosystem__challenger_share" in sv.writes
        assert "ecosystem__total_market" in sv.writes
        assert "ecosystem__dominance_ratio" in sv.writes

    def test_innovation_boost_not_in_writes(self):
        sv = LotkaVolterra().state_variables
        assert "ecosystem__innovation_boost" not in sv.writes

    def test_innovation_boost_in_initializes(self):
        sv = LotkaVolterra().state_variables
        assert "ecosystem__innovation_boost" in sv.initializes

    def test_custom_ecosystem_id_reflected_in_keys(self):
        t = LotkaVolterra(parameters={"ecosystem_id": "cloud"})
        sv = t.state_variables
        assert "cloud__incumbent_share" in sv.writes
        assert "ecosystem__incumbent_share" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_incumbent_at_0_80(self):
        inits = LotkaVolterra().setup({})
        assert inits["ecosystem__incumbent_share"] == pytest.approx(0.80)

    def test_seeds_challenger_at_0_05(self):
        inits = LotkaVolterra().setup({})
        assert inits["ecosystem__challenger_share"] == pytest.approx(0.05)

    def test_seeds_innovation_boost_at_zero(self):
        inits = LotkaVolterra().setup({})
        assert inits["ecosystem__innovation_boost"] == pytest.approx(0.0)

    def test_does_not_overwrite_existing_incumbent(self):
        env = {"ecosystem__incumbent_share": 0.60}
        inits = LotkaVolterra().setup(env)
        assert "ecosystem__incumbent_share" not in inits

    def test_does_not_overwrite_existing_challenger(self):
        env = {"ecosystem__challenger_share": 0.20}
        inits = LotkaVolterra().setup(env)
        assert "ecosystem__challenger_share" not in inits


# ── update() ──────────────────────────────────────────────────────────────────

class TestUpdate:
    def _env(self, X=0.80, Y=0.05, innovation_boost=0.0) -> dict[str, float]:
        return {
            "ecosystem__incumbent_share": X,
            "ecosystem__challenger_share": Y,
            "ecosystem__innovation_boost": innovation_boost,
        }

    def test_returns_four_keys(self):
        delta = LotkaVolterra().update(self._env(), [], 0)
        assert "ecosystem__incumbent_share" in delta
        assert "ecosystem__challenger_share" in delta
        assert "ecosystem__total_market" in delta
        assert "ecosystem__dominance_ratio" in delta

    def test_does_not_mutate_env(self):
        env = self._env(X=0.80, Y=0.05)
        LotkaVolterra().update(env, [], 0)
        assert env["ecosystem__incumbent_share"] == pytest.approx(0.80)
        assert env["ecosystem__challenger_share"] == pytest.approx(0.05)

    def test_outputs_clamped_to_0_1(self):
        t = LotkaVolterra()
        delta = t.update(self._env(), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_total_market_equals_incumbent_plus_challenger(self):
        delta = LotkaVolterra().update(self._env(), [], 0)
        expected = delta["ecosystem__incumbent_share"] + delta["ecosystem__challenger_share"]
        assert delta["ecosystem__total_market"] == pytest.approx(expected, abs=1e-9)

    def test_dominance_ratio_near_one_when_challenger_tiny(self):
        # Tiny challenger → incumbent dominates
        delta = LotkaVolterra().update(self._env(X=0.90, Y=0.001), [], 0)
        assert delta["ecosystem__dominance_ratio"] > 0.95

    def test_dominance_ratio_near_zero_when_incumbent_tiny(self):
        # Tiny incumbent → challenger dominates ratio
        delta = LotkaVolterra().update(self._env(X=0.001, Y=0.80), [], 0)
        assert delta["ecosystem__dominance_ratio"] < 0.05

    def test_incumbent_declines_under_strong_predation(self):
        # Large challenger + high predator_efficiency → incumbent share falls
        t = LotkaVolterra(parameters={"predator_efficiency": 1.0})
        delta = t.update(self._env(X=0.70, Y=0.50), [], 0)
        assert delta["ecosystem__incumbent_share"] < 0.70

    def test_challenger_grows_when_incumbent_large(self):
        # Large incumbent provides plenty of prey for challenger to grow
        t = LotkaVolterra(parameters={"predator_efficiency": 0.50, "conversion_efficiency": 0.40})
        delta = t.update(self._env(X=0.80, Y=0.10), [], 0)
        assert delta["ecosystem__challenger_share"] > 0.10

    def test_innovation_boost_accelerates_challenger_growth(self):
        # Same state; innovation_boost > 0 should yield larger challenger share
        t = LotkaVolterra()
        delta_no_boost   = t.update(self._env(X=0.80, Y=0.10, innovation_boost=0.0), [], 0)
        delta_with_boost = t.update(self._env(X=0.80, Y=0.10, innovation_boost=0.50), [], 0)
        assert delta_with_boost["ecosystem__challenger_share"] > delta_no_boost["ecosystem__challenger_share"]

    def test_incumbent_recovers_when_challenger_absent(self):
        # No challenger → no predation → incumbent grows logistically
        t = LotkaVolterra()
        delta = t.update(self._env(X=0.50, Y=0.0), [], 0)
        assert delta["ecosystem__incumbent_share"] > 0.50

    def test_custom_ecosystem_id_in_output(self):
        t = LotkaVolterra(parameters={"ecosystem_id": "streaming"})
        env = {
            "streaming__incumbent_share": 0.80,
            "streaming__challenger_share": 0.05,
            "streaming__innovation_boost": 0.0,
        }
        delta = t.update(env, [], 0)
        assert "streaming__incumbent_share" in delta
        assert "ecosystem__incumbent_share" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = LotkaVolterra().update({}, [], 0)
        assert 0.0 <= delta["ecosystem__incumbent_share"] <= 1.0
        assert 0.0 <= delta["ecosystem__challenger_share"] <= 1.0
        assert 0.0 <= delta["ecosystem__total_market"] <= 1.0
        assert 0.0 <= delta["ecosystem__dominance_ratio"] <= 1.0

    def test_total_market_at_most_one(self):
        # Even with large initial values total market stays ≤ 1
        delta = LotkaVolterra().update(self._env(X=0.70, Y=0.70), [], 0)
        assert delta["ecosystem__total_market"] <= 1.0 + 1e-9
