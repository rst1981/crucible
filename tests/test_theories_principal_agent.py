"""
Tests for core/theories/principal_agent.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.principal_agent import PrincipalAgent


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "principal_agent" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("principal_agent") is PrincipalAgent

    def test_theory_id_attribute(self):
        assert PrincipalAgent.theory_id == "principal_agent"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = PrincipalAgent()
        assert t.params.beta == 0.40
        assert t.params.intrinsic_motivation == 0.30
        assert t.params.risk_aversion == 0.30
        assert t.params.agent_id == "agent"
        assert t.params.tick_unit == "year"

    def test_parameter_overrides(self):
        t = PrincipalAgent(parameters={"beta": 0.8, "agent_id": "subsidiary"})
        assert t.params.beta == 0.8
        assert t.params.agent_id == "subsidiary"

    def test_beta_above_one_rejected(self):
        with pytest.raises(Exception):
            PrincipalAgent(parameters={"beta": 1.5})

    def test_risk_aversion_above_one_rejected(self):
        with pytest.raises(Exception):
            PrincipalAgent(parameters={"risk_aversion": 1.1})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_four_keys(self):
        sv = PrincipalAgent().state_variables
        assert "agent__effort_level"        in sv.writes
        assert "agent__compliance"          in sv.writes
        assert "agent__shirking_risk"       in sv.writes
        assert "agent__incentive_alignment" in sv.writes

    def test_monitoring_not_in_writes(self):
        # monitoring_intensity is owned by the principal / shocks, not this theory
        assert "agent__monitoring_intensity" not in PrincipalAgent().state_variables.writes

    def test_monitoring_in_initializes(self):
        assert "agent__monitoring_intensity" in PrincipalAgent().state_variables.initializes

    def test_custom_agent_id_reflected_in_keys(self):
        t = PrincipalAgent(parameters={"agent_id": "subsidiary"})
        sv = t.state_variables
        assert "subsidiary__effort_level" in sv.writes
        assert "agent__effort_level" not in sv.writes

    def test_initializes_subset_includes_writes(self):
        sv = PrincipalAgent().state_variables
        for key in sv.initializes:
            assert key in sv.writes or key == "agent__monitoring_intensity"


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_monitoring_at_half(self):
        inits = PrincipalAgent().setup({})
        assert inits["agent__monitoring_intensity"] == 0.5

    def test_seeds_effort_near_equilibrium(self):
        # Default params: beta=0.4, risk_aversion=0.3, intrinsic=0.3
        # effort_target ≈ 0.4*(1-0.3*0.4) + 0.3*(1-0.4) = 0.4*0.88 + 0.3*0.6 ≈ 0.352+0.18=0.532
        inits = PrincipalAgent().setup({})
        assert 0.0 < inits["agent__effort_level"] < 1.0

    def test_does_not_overwrite_existing_monitoring(self):
        inits = PrincipalAgent().setup({"agent__monitoring_intensity": 0.9})
        assert "agent__monitoring_intensity" not in inits

    def test_does_not_overwrite_existing_effort(self):
        inits = PrincipalAgent().setup({"agent__effort_level": 0.7})
        assert "agent__effort_level" not in inits


# ── update() — core incentive dynamics ───────────────────────────────────────

class TestUpdate:
    def _env(self, effort=0.5, monitoring=0.5) -> dict[str, float]:
        return {"agent__effort_level": effort, "agent__monitoring_intensity": monitoring}

    def test_returns_all_four_keys(self):
        delta = PrincipalAgent().update(self._env(), [], 0)
        assert "agent__effort_level"        in delta
        assert "agent__compliance"          in delta
        assert "agent__shirking_risk"       in delta
        assert "agent__incentive_alignment" in delta

    def test_does_not_mutate_env(self):
        env = self._env(0.4, 0.6)
        PrincipalAgent().update(env, [], 0)
        assert env["agent__effort_level"]        == 0.4
        assert env["agent__monitoring_intensity"] == 0.6

    def test_outputs_clamped_to_0_1(self):
        t = PrincipalAgent(parameters={"beta": 1.0, "intrinsic_motivation": 1.0})
        delta = t.update(self._env(0.0, 0.0), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_high_beta_raises_effort(self):
        t_low  = PrincipalAgent(parameters={"beta": 0.1, "intrinsic_motivation": 0.0})
        t_high = PrincipalAgent(parameters={"beta": 0.9, "intrinsic_motivation": 0.0})
        env = self._env(effort=0.3, monitoring=0.5)
        d_low  = t_low.update(env, [], 0)
        d_high = t_high.update(env, [], 0)
        assert d_high["agent__effort_level"] > d_low["agent__effort_level"]

    def test_high_monitoring_reduces_shirking_risk(self):
        t = PrincipalAgent(parameters={"beta": 0.0, "intrinsic_motivation": 0.0})
        d_low  = t.update(self._env(monitoring=0.1), [], 0)
        d_high = t.update(self._env(monitoring=0.9), [], 0)
        assert d_high["agent__shirking_risk"] < d_low["agent__shirking_risk"]

    def test_high_intrinsic_motivation_reduces_shirking(self):
        t_low  = PrincipalAgent(parameters={"intrinsic_motivation": 0.0, "beta": 0.0})
        t_high = PrincipalAgent(parameters={"intrinsic_motivation": 0.9, "beta": 0.0})
        env = self._env(monitoring=0.0)
        d_low  = t_low.update(env, [], 0)
        d_high = t_high.update(env, [], 0)
        assert d_high["agent__shirking_risk"] < d_low["agent__shirking_risk"]

    def test_pure_commission_zero_shirking_risk(self):
        # beta=1.0: agent is residual claimant → no incentive to shirk regardless of monitoring
        t = PrincipalAgent(parameters={"beta": 1.0, "intrinsic_motivation": 0.0})
        delta = t.update(self._env(monitoring=0.0), [], 0)
        assert delta["agent__shirking_risk"] == pytest.approx(0.0, abs=1e-9)

    def test_compliance_at_least_as_high_as_effort(self):
        # Monitoring reveals compliance ≥ underlying effort
        delta = PrincipalAgent().update(self._env(effort=0.5, monitoring=0.8), [], 0)
        assert delta["agent__compliance"] >= delta["agent__effort_level"] - 1e-9

    def test_effort_adjusts_gradually(self):
        # With low adjustment_speed, effort changes slowly each tick
        t = PrincipalAgent(parameters={"adjustment_speed": 0.1, "beta": 1.0,
                                       "intrinsic_motivation": 0.0})
        # Effort is at 0.0, target is high — should move only partially
        delta = t.update(self._env(effort=0.0, monitoring=0.5), [], 0)
        assert 0.0 < delta["agent__effort_level"] < 0.5

    def test_custom_agent_id_in_output(self):
        t = PrincipalAgent(parameters={"agent_id": "subsidiary"})
        delta = t.update(
            {"subsidiary__effort_level": 0.5, "subsidiary__monitoring_intensity": 0.5},
            [], 0,
        )
        assert "subsidiary__effort_level" in delta
        assert "agent__effort_level" not in delta

    def test_tick_unit_month_slower_adjustment_than_year(self):
        env = self._env(effort=0.0, monitoring=0.9)
        t_year  = PrincipalAgent(parameters={"tick_unit": "year",  "beta": 0.8})
        t_month = PrincipalAgent(parameters={"tick_unit": "month", "beta": 0.8})
        d_year  = t_year.update(env, [], 0)
        d_month = t_month.update(env, [], 0)
        assert d_month["agent__effort_level"] < d_year["agent__effort_level"]

    def test_missing_env_keys_default_gracefully(self):
        delta = PrincipalAgent().update({}, [], 0)
        assert 0.0 <= delta["agent__effort_level"] <= 1.0
