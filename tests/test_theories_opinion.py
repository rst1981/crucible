"""
Tests for core/theories/opinion_dynamics.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.opinion_dynamics import OpinionDynamics


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "opinion_dynamics" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("opinion_dynamics") is OpinionDynamics

    def test_theory_id_attribute(self):
        assert OpinionDynamics.theory_id == "opinion_dynamics"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = OpinionDynamics()
        assert t.params.epsilon == 0.30
        assert t.params.mu == 0.20
        assert t.params.tick_unit == "year"
        assert t.params.domain_id == "opinion"

    def test_parameter_overrides(self):
        t = OpinionDynamics(parameters={"epsilon": 0.5, "mu": 0.3, "domain_id": "public"})
        assert t.params.epsilon == 0.5
        assert t.params.mu == 0.3
        assert t.params.domain_id == "public"

    def test_epsilon_above_one_rejected(self):
        with pytest.raises(Exception):
            OpinionDynamics(parameters={"epsilon": 1.5})

    def test_mu_above_half_rejected(self):
        # mu > 0.5 would overshoot: agents would jump past each other
        with pytest.raises(Exception):
            OpinionDynamics(parameters={"mu": 0.6})

    def test_noise_sigma_above_half_rejected(self):
        with pytest.raises(Exception):
            OpinionDynamics(parameters={"noise_sigma": 0.6})


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_three_keys(self):
        sv = OpinionDynamics().state_variables
        assert "opinion__mean"         in sv.writes
        assert "opinion__polarization" in sv.writes
        assert "opinion__consensus"    in sv.writes

    def test_media_bias_not_in_writes(self):
        # media_bias is owned by agents/shocks, not the theory
        assert "opinion__media_bias" not in OpinionDynamics().state_variables.writes

    def test_media_bias_in_initializes(self):
        assert "opinion__media_bias" in OpinionDynamics().state_variables.initializes

    def test_reads_urgency_factor(self):
        assert "global__urgency_factor" in OpinionDynamics().state_variables.reads

    def test_custom_domain_id_reflected_in_keys(self):
        t = OpinionDynamics(parameters={"domain_id": "public"})
        sv = t.state_variables
        assert "public__mean" in sv.writes
        assert "opinion__mean" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_mean_at_neutral(self):
        inits = OpinionDynamics().setup({})
        assert inits["opinion__mean"] == 0.5

    def test_seeds_polarization_at_moderate(self):
        inits = OpinionDynamics().setup({})
        assert inits["opinion__polarization"] == 0.5

    def test_seeds_media_bias_at_neutral(self):
        inits = OpinionDynamics().setup({})
        assert inits["opinion__media_bias"] == 0.5

    def test_does_not_overwrite_existing_values(self):
        env = {"opinion__mean": 0.7, "opinion__polarization": 0.8}
        inits = OpinionDynamics().setup(env)
        assert "opinion__mean"         not in inits
        assert "opinion__polarization" not in inits


# ── update() — core dynamics ──────────────────────────────────────────────────

class TestUpdate:
    def _env(self, mean=0.5, polarization=0.5, media_bias=0.5, urgency=0.0):
        return {
            "opinion__mean":         mean,
            "opinion__polarization": polarization,
            "opinion__media_bias":   media_bias,
            "global__urgency_factor": urgency,
        }

    def test_returns_all_three_keys(self):
        delta = OpinionDynamics().update(self._env(), [], 0)
        assert "opinion__mean"         in delta
        assert "opinion__polarization" in delta
        assert "opinion__consensus"    in delta

    def test_does_not_mutate_env(self):
        env = self._env(mean=0.4, polarization=0.6)
        OpinionDynamics().update(env, [], 0)
        assert env["opinion__mean"]         == 0.4
        assert env["opinion__polarization"] == 0.6

    def test_outputs_clamped_to_0_1(self):
        t = OpinionDynamics(parameters={"noise_sigma": 0.5, "urgency_polarization_factor": 1.0})
        delta = t.update(self._env(urgency=1.0), [], 0)
        for v in delta.values():
            assert 0.0 <= v <= 1.0

    def test_consensus_equals_one_minus_polarization(self):
        delta = OpinionDynamics().update(self._env(), [], 0)
        assert delta["opinion__consensus"] == pytest.approx(
            1.0 - delta["opinion__polarization"], abs=1e-9
        )

    def test_high_epsilon_reduces_polarization(self):
        # epsilon=0.6 (> 0.5 → consensus regime): polarization should shrink
        t = OpinionDynamics(parameters={
            "epsilon": 0.6, "mu": 0.3, "noise_sigma": 0.0, "tick_unit": "year",
        })
        delta = t.update(self._env(polarization=0.8), [], 0)
        assert delta["opinion__polarization"] < 0.8

    def test_zero_epsilon_prevents_convergence(self):
        # epsilon=0: no agents interact → no convergence (noise only)
        t = OpinionDynamics(parameters={
            "epsilon": 0.0, "mu": 0.3, "noise_sigma": 0.0,
            "urgency_polarization_factor": 0.0, "tick_unit": "year",
        })
        initial_pol = 0.6
        delta = t.update(self._env(polarization=initial_pol), [], 0)
        # Without noise and without contact, polarization should not decrease
        assert delta["opinion__polarization"] >= initial_pol - 1e-9

    def test_high_urgency_increases_polarization(self):
        # Crisis injects polarization noise
        t = OpinionDynamics(parameters={
            "urgency_polarization_factor": 0.5, "noise_sigma": 0.0,
            "epsilon": 0.0,  # no convergence — only noise effect
        })
        env_calm   = self._env(polarization=0.3, urgency=0.0)
        env_crisis = self._env(polarization=0.3, urgency=1.0)
        d_calm   = t.update(env_calm, [], 0)
        d_crisis = t.update(env_crisis, [], 0)
        assert d_crisis["opinion__polarization"] > d_calm["opinion__polarization"]

    def test_media_bias_shifts_mean_toward_bias(self):
        # Media bias above current mean should pull mean upward
        t = OpinionDynamics(parameters={"media_sensitivity": 0.5, "noise_sigma": 0.0})
        delta = t.update(self._env(mean=0.3, media_bias=0.8), [], 0)
        assert delta["opinion__mean"] > 0.3

    def test_neutral_media_bias_does_not_shift_mean(self):
        # media_bias = mean → no drift
        t = OpinionDynamics(parameters={"media_sensitivity": 0.5, "noise_sigma": 0.0})
        delta = t.update(self._env(mean=0.5, media_bias=0.5), [], 0)
        assert delta["opinion__mean"] == pytest.approx(0.5, abs=1e-9)

    def test_multi_tick_high_epsilon_converges_to_consensus(self):
        # Large epsilon, no noise: population should eventually reach near-consensus
        t = OpinionDynamics(parameters={
            "epsilon": 0.6, "mu": 0.4,
            "noise_sigma": 0.0, "urgency_polarization_factor": 0.0,
            "tick_unit": "year",
        })
        env = self._env(polarization=0.9)
        for _ in range(30):
            delta = t.update(env, [], 0)
            env.update(delta)
        assert env["opinion__polarization"] < 0.1

    def test_tick_unit_month_slower_convergence_than_year(self):
        # Monthly ticks → smaller dt → slower convergence per tick
        t_year  = OpinionDynamics(parameters={"epsilon": 0.5, "noise_sigma": 0.0, "tick_unit": "year"})
        t_month = OpinionDynamics(parameters={"epsilon": 0.5, "noise_sigma": 0.0, "tick_unit": "month"})
        env = self._env(polarization=0.8)
        d_year  = t_year.update(env, [], 0)
        d_month = t_month.update(env, [], 0)
        year_drop  = 0.8 - d_year["opinion__polarization"]
        month_drop = 0.8 - d_month["opinion__polarization"]
        assert month_drop < year_drop

    def test_custom_domain_id_in_output(self):
        t = OpinionDynamics(parameters={"domain_id": "public"})
        delta = t.update(
            {"public__mean": 0.5, "public__polarization": 0.5, "public__media_bias": 0.5},
            [], 0,
        )
        assert "public__mean" in delta
        assert "opinion__mean" not in delta

    def test_missing_env_keys_default_gracefully(self):
        delta = OpinionDynamics().update({}, [], 0)
        assert 0.0 <= delta["opinion__mean"] <= 1.0
        assert 0.0 <= delta["opinion__polarization"] <= 1.0
