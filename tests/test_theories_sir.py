"""
Tests for core/theories/sir_contagion.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.sir_contagion import SIRContagion


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "sir_contagion" in list_theories()

    def test_get_theory_returns_correct_class(self):
        assert get_theory("sir_contagion") is SIRContagion

    def test_theory_id_attribute(self):
        assert SIRContagion.theory_id == "sir_contagion"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = SIRContagion()
        assert t.params.beta == 0.30
        assert t.params.gamma == 0.10
        assert t.params.initial_infected == 0.01
        assert t.params.tick_unit == "year"
        assert t.params.contagion_id == "sir"

    def test_parameter_overrides(self):
        t = SIRContagion(parameters={"beta": 0.5, "gamma": 0.2, "contagion_id": "banking"})
        assert t.params.beta == 0.5
        assert t.params.gamma == 0.2
        assert t.params.contagion_id == "banking"

    def test_beta_below_zero_rejected(self):
        with pytest.raises(Exception):
            SIRContagion(parameters={"beta": -0.1})

    def test_gamma_above_one_rejected(self):
        with pytest.raises(Exception):
            SIRContagion(parameters={"gamma": 1.5})

    def test_initial_infected_above_one_rejected(self):
        with pytest.raises(Exception):
            SIRContagion(parameters={"initial_infected": 1.1})

    def test_r0_above_one_with_defaults(self):
        t = SIRContagion()
        r0 = t.params.beta / t.params.gamma
        assert r0 > 1.0  # default params produce an epidemic


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_writes_contains_all_five_keys(self):
        sv = SIRContagion().state_variables
        assert "sir__susceptible"      in sv.writes
        assert "sir__infected"         in sv.writes
        assert "sir__recovered"        in sv.writes
        assert "sir__r_effective"      in sv.writes
        assert "sir__active_contagion" in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = SIRContagion().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_contagion_id_reflected_in_keys(self):
        t = SIRContagion(parameters={"contagion_id": "banking"})
        sv = t.state_variables
        assert "banking__infected" in sv.writes
        assert "sir__infected" not in sv.writes

    def test_reads_trade_volume(self):
        assert "global__trade_volume" in SIRContagion().state_variables.reads


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_infected_from_initial_infected_param(self):
        t = SIRContagion(parameters={"initial_infected": 0.02})
        inits = t.setup({})
        assert inits["sir__infected"] == pytest.approx(0.02)

    def test_seeds_susceptible_as_complement(self):
        t = SIRContagion(parameters={"initial_infected": 0.02})
        inits = t.setup({})
        assert inits["sir__susceptible"] == pytest.approx(0.98)

    def test_seeds_recovered_at_zero(self):
        inits = SIRContagion().setup({})
        assert inits["sir__recovered"] == 0.0

    def test_does_not_overwrite_existing_state(self):
        env = {"sir__infected": 0.3, "sir__susceptible": 0.7, "sir__recovered": 0.0}
        inits = SIRContagion().setup(env)
        assert "sir__infected"    not in inits
        assert "sir__susceptible" not in inits
        assert "sir__recovered"   not in inits


# ── update() — core ODE logic ─────────────────────────────────────────────────

class TestUpdate:
    def _env(self, S=0.99, I=0.01, R=0.0) -> dict[str, float]:
        return {"sir__susceptible": S, "sir__infected": I, "sir__recovered": R}

    def test_returns_all_five_keys(self):
        delta = SIRContagion().update(self._env(), [], 0)
        assert "sir__susceptible"      in delta
        assert "sir__infected"         in delta
        assert "sir__recovered"        in delta
        assert "sir__r_effective"      in delta
        assert "sir__active_contagion" in delta

    def test_does_not_mutate_env(self):
        env = self._env(0.99, 0.01, 0.0)
        SIRContagion().update(env, [], 0)
        assert env["sir__susceptible"] == pytest.approx(0.99)
        assert env["sir__infected"]    == pytest.approx(0.01)

    def test_sir_conservation_s_plus_i_plus_r_equals_one(self):
        t = SIRContagion()
        env = self._env()
        for _ in range(20):
            delta = t.update(env, [], 0)
            env.update(delta)
            total = env["sir__susceptible"] + env["sir__infected"] + env["sir__recovered"]
            assert total == pytest.approx(1.0, abs=1e-9)

    def test_outputs_clamped_to_0_1(self):
        t = SIRContagion(parameters={"beta": 5.0, "gamma": 0.01})
        delta = t.update(self._env(0.99, 0.01, 0.0), [], 0)
        for key in ("sir__susceptible", "sir__infected", "sir__recovered",
                    "sir__r_effective", "sir__active_contagion"):
            assert 0.0 <= delta[key] <= 1.0

    def test_epidemic_grows_when_r0_above_one(self):
        # beta=0.5, gamma=0.1 → R0=5; infected should grow from small seed
        t = SIRContagion(parameters={"beta": 0.5, "gamma": 0.1, "tick_unit": "year"})
        env = self._env(S=0.99, I=0.01, R=0.0)
        delta = t.update(env, [], 0)
        assert delta["sir__infected"] > 0.01

    def test_epidemic_declines_when_r0_below_one(self):
        # beta=0.05, gamma=0.3 → R0≈0.17; infected should shrink
        t = SIRContagion(parameters={"beta": 0.05, "gamma": 0.3, "tick_unit": "year"})
        env = self._env(S=0.99, I=0.01, R=0.0)
        delta = t.update(env, [], 0)
        assert delta["sir__infected"] < 0.01

    def test_zero_infected_stays_zero(self):
        # No spontaneous infection: I=0 → no new infections
        delta = SIRContagion().update(
            {"sir__susceptible": 1.0, "sir__infected": 0.0, "sir__recovered": 0.0},
            [], 0,
        )
        assert delta["sir__infected"] == pytest.approx(0.0, abs=1e-9)

    def test_susceptible_decreases_during_epidemic(self):
        t = SIRContagion(parameters={"beta": 0.5, "gamma": 0.1})
        delta = t.update(self._env(0.99, 0.01, 0.0), [], 0)
        assert delta["sir__susceptible"] < 0.99

    def test_recovered_monotonically_increases(self):
        t = SIRContagion()
        env = self._env(0.99, 0.01, 0.0)
        prev_R = 0.0
        for _ in range(30):
            delta = t.update(env, [], 0)
            env.update(delta)
            assert env["sir__recovered"] >= prev_R - 1e-9
            prev_R = env["sir__recovered"]

    def test_r_effective_decreases_as_s_depletes(self):
        # As herd immunity builds, R_eff should trend downward
        t = SIRContagion(parameters={"beta": 0.5, "gamma": 0.1, "tick_unit": "year"})
        env = self._env(0.99, 0.01, 0.0)
        r_eff_values = []
        for _ in range(30):
            delta = t.update(env, [], 0)
            env.update(delta)
            r_eff_values.append(delta["sir__r_effective"])
        # Peak must eventually be followed by decline
        peak_idx = r_eff_values.index(max(r_eff_values))
        assert r_eff_values[-1] < r_eff_values[peak_idx]

    def test_active_contagion_flag_above_threshold(self):
        t = SIRContagion(parameters={"active_threshold": 0.005})
        delta = t.update(self._env(S=0.99, I=0.05, R=0.0), [], 0)
        assert delta["sir__active_contagion"] == 1.0

    def test_active_contagion_flag_below_threshold(self):
        t = SIRContagion(parameters={"active_threshold": 0.10})
        delta = t.update(
            {"sir__susceptible": 0.995, "sir__infected": 0.001, "sir__recovered": 0.004},
            [], 0,
        )
        assert delta["sir__active_contagion"] == 0.0

    def test_trade_disruption_amplifies_spread(self):
        env_normal    = {**self._env(), "global__trade_volume": 0.5}
        env_disrupted = {**self._env(), "global__trade_volume": 0.1}
        t = SIRContagion(parameters={"trade_amplification": 1.0})
        d_normal    = t.update(env_normal, [], 0)
        d_disrupted = t.update(env_disrupted, [], 0)
        # More spread under disruption → fewer susceptible
        assert d_disrupted["sir__susceptible"] < d_normal["sir__susceptible"]

    def test_tick_unit_month_smaller_spread_than_year(self):
        env = self._env(0.99, 0.01, 0.0)
        d_year  = SIRContagion(parameters={"tick_unit": "year"}).update(env, [], 0)
        d_month = SIRContagion(parameters={"tick_unit": "month"}).update(env, [], 0)
        year_drop  = 0.99 - d_year["sir__susceptible"]
        month_drop = 0.99 - d_month["sir__susceptible"]
        assert month_drop < year_drop

    def test_custom_contagion_id_in_output(self):
        t = SIRContagion(parameters={"contagion_id": "banking"})
        delta = t.update(
            {"banking__susceptible": 0.99, "banking__infected": 0.01, "banking__recovered": 0.0},
            [], 0,
        )
        assert "banking__infected" in delta
        assert "sir__infected" not in delta

    def test_full_epidemic_cycle_ends_in_recovered_majority(self):
        # Run until epidemic burns out; most population should be recovered
        t = SIRContagion(parameters={"beta": 0.5, "gamma": 0.1, "tick_unit": "year"})
        env = self._env(S=0.99, I=0.01, R=0.0)
        for _ in range(80):
            env.update(t.update(env, [], 0))
        assert env["sir__recovered"] > 0.5
        assert env["sir__infected"] < 0.01
