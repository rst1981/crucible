"""
Tests for core/theories/richardson_arms_race.py
"""
from __future__ import annotations

import pytest

from core.theories import get_theory, list_theories
from core.theories.richardson_arms_race import RichardsonArmsRace


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registered_in_registry(self):
        assert "richardson_arms_race" in list_theories()

    def test_get_theory_returns_correct_class(self):
        cls = get_theory("richardson_arms_race")
        assert cls is RichardsonArmsRace

    def test_theory_id_attribute(self):
        assert RichardsonArmsRace.theory_id == "richardson_arms_race"


# ── Parameters ────────────────────────────────────────────────────────────────

class TestParameters:
    def test_defaults(self):
        t = RichardsonArmsRace()
        p = t.params
        assert p.k == 0.30
        assert p.l == 0.30
        assert p.a == 0.15
        assert p.b == 0.15
        assert p.g == 0.05
        assert p.h == 0.05
        assert p.tick_unit == "year"
        assert p.actor_a_id == "actor_a"
        assert p.actor_b_id == "actor_b"

    def test_parameter_overrides(self):
        t = RichardsonArmsRace(parameters={"k": 0.4, "l": 0.35, "a": 0.20})
        assert t.params.k == 0.4
        assert t.params.l == 0.35
        assert t.params.a == 0.20

    def test_k_below_zero_rejected(self):
        with pytest.raises(Exception):
            RichardsonArmsRace(parameters={"k": -0.1})

    def test_k_above_one_rejected(self):
        with pytest.raises(Exception):
            RichardsonArmsRace(parameters={"k": 1.5})

    def test_grievance_negative_valid(self):
        # Negative grievance = demilitarizing state — must be accepted
        t = RichardsonArmsRace(parameters={"g": -0.1})
        assert t.params.g == -0.1

    def test_grievance_outside_bounds_rejected(self):
        with pytest.raises(Exception):
            RichardsonArmsRace(parameters={"g": -0.6})

    def test_custom_actor_ids(self):
        t = RichardsonArmsRace(parameters={"actor_a_id": "iran", "actor_b_id": "us"})
        assert t.params.actor_a_id == "iran"
        assert t.params.actor_b_id == "us"

    def test_unstable_params_log_warning(self, caplog):
        import logging
        # k=0.5, l=0.5 → k·l=0.25; a=0.1, b=0.1 → a·b=0.01 < 0.25 — unstable
        with caplog.at_level(logging.WARNING, logger="core.theories.richardson_arms_race"):
            RichardsonArmsRace(parameters={"k": 0.5, "l": 0.5, "a": 0.1, "b": 0.1})
        assert any("UNSTABLE" in r.message for r in caplog.records)

    def test_stable_params_no_warning(self, caplog):
        import logging
        # k=0.1, l=0.1 → k·l=0.01; a=0.3, b=0.3 → a·b=0.09 > 0.01 — stable
        with caplog.at_level(logging.WARNING, logger="core.theories.richardson_arms_race"):
            RichardsonArmsRace(parameters={"k": 0.1, "l": 0.1, "a": 0.3, "b": 0.3})
        assert not any("UNSTABLE" in r.message for r in caplog.records)


# ── state_variables ───────────────────────────────────────────────────────────

class TestStateVariables:
    def test_reads_contains_military_readiness(self):
        sv = RichardsonArmsRace().state_variables
        assert "actor_a__military_readiness" in sv.reads
        assert "actor_b__military_readiness" in sv.reads

    def test_writes_contains_all_four_keys(self):
        sv = RichardsonArmsRace().state_variables
        assert "actor_a__military_readiness" in sv.writes
        assert "actor_b__military_readiness" in sv.writes
        assert "richardson__escalation_index" in sv.writes
        assert "richardson__stable" in sv.writes

    def test_initializes_subset_of_writes(self):
        sv = RichardsonArmsRace().state_variables
        for key in sv.initializes:
            assert key in sv.writes

    def test_custom_actor_ids_reflected_in_state_variables(self):
        t = RichardsonArmsRace(parameters={"actor_a_id": "iran", "actor_b_id": "us"})
        sv = t.state_variables
        assert "iran__military_readiness" in sv.writes
        assert "us__military_readiness" in sv.writes
        assert "actor_a__military_readiness" not in sv.writes


# ── setup() ───────────────────────────────────────────────────────────────────

class TestSetup:
    def test_seeds_missing_military_readiness_at_0_5(self):
        t = RichardsonArmsRace()
        inits = t.setup({})
        assert inits["actor_a__military_readiness"] == 0.5
        assert inits["actor_b__military_readiness"] == 0.5

    def test_setup_does_not_overwrite_existing_readiness(self):
        t = RichardsonArmsRace()
        inits = t.setup({"actor_a__military_readiness": 0.8})
        assert "actor_a__military_readiness" not in inits

    def test_setup_seeds_escalation_index_at_zero(self):
        t = RichardsonArmsRace()
        inits = t.setup({})
        assert inits["richardson__escalation_index"] == 0.0

    def test_setup_seeds_stable_at_zero(self):
        t = RichardsonArmsRace()
        inits = t.setup({})
        assert inits["richardson__stable"] == 0.0

    def test_setup_empty_when_all_keys_present(self):
        t = RichardsonArmsRace()
        full_env = {
            "actor_a__military_readiness": 0.6,
            "actor_b__military_readiness": 0.4,
            "richardson__escalation_index": 0.5,
            "richardson__stable": 1.0,
        }
        inits = t.setup(full_env)
        assert inits == {}


# ── update() — core ODE logic ─────────────────────────────────────────────────

class TestUpdate:
    def _env(self, x=0.5, y=0.5) -> dict[str, float]:
        return {
            "actor_a__military_readiness": x,
            "actor_b__military_readiness": y,
        }

    def test_returns_all_four_keys(self):
        t = RichardsonArmsRace()
        delta = t.update(self._env(), [], 0)
        assert "actor_a__military_readiness" in delta
        assert "actor_b__military_readiness" in delta
        assert "richardson__escalation_index" in delta
        assert "richardson__stable" in delta

    def test_does_not_mutate_env(self):
        t = RichardsonArmsRace()
        env = self._env(0.5, 0.5)
        t.update(env, [], 0)
        assert env["actor_a__military_readiness"] == 0.5
        assert env["actor_b__military_readiness"] == 0.5

    def test_outputs_clamped_to_0_1(self):
        # Even with extreme params, outputs must stay in [0, 1]
        t = RichardsonArmsRace(parameters={"k": 1.0, "l": 1.0, "g": 0.5, "h": 0.5})
        delta = t.update(self._env(0.99, 0.99), [], 0)
        assert 0.0 <= delta["actor_a__military_readiness"] <= 1.0
        assert 0.0 <= delta["actor_b__military_readiness"] <= 1.0

    def test_outputs_clamped_below_at_zero(self):
        # Strong fatigue + negative grievance with low arms → must not go below 0
        t = RichardsonArmsRace(parameters={"a": 0.9, "b": 0.9, "g": -0.5, "h": -0.5})
        delta = t.update(self._env(0.01, 0.01), [], 0)
        assert delta["actor_a__military_readiness"] >= 0.0
        assert delta["actor_b__military_readiness"] >= 0.0

    def test_escalation_index_is_average(self):
        t = RichardsonArmsRace()
        delta = t.update(self._env(), [], 0)
        expected = (delta["actor_a__military_readiness"] + delta["actor_b__military_readiness"]) / 2
        assert abs(delta["richardson__escalation_index"] - expected) < 1e-10

    def test_stable_flag_when_stable(self):
        # k=0.1, l=0.1 → k·l=0.01; a=0.3, b=0.3 → a·b=0.09 > 0.01 — stable
        t = RichardsonArmsRace(parameters={"k": 0.1, "l": 0.1, "a": 0.3, "b": 0.3})
        delta = t.update(self._env(), [], 0)
        assert delta["richardson__stable"] == 1.0

    def test_stable_flag_when_unstable(self):
        # k=0.5, l=0.5 → k·l=0.25; a=0.1, b=0.1 → a·b=0.01 < 0.25 — unstable
        t = RichardsonArmsRace(parameters={"k": 0.5, "l": 0.5, "a": 0.1, "b": 0.1})
        delta = t.update(self._env(), [], 0)
        assert delta["richardson__stable"] == 0.0

    def test_grievance_drives_arming(self):
        # With no adversary arms (y=0) and positive grievance, x should increase
        t = RichardsonArmsRace(parameters={"k": 0.0, "l": 0.0, "a": 0.0, "b": 0.0,
                                            "g": 0.2, "h": 0.2, "tick_unit": "year"})
        delta = t.update(self._env(0.3, 0.3), [], 0)
        assert delta["actor_a__military_readiness"] > 0.3
        assert delta["actor_b__military_readiness"] > 0.3

    def test_fatigue_drives_disarmament(self):
        # With no adversary and no grievance, fatigue alone should reduce arms
        t = RichardsonArmsRace(parameters={"k": 0.0, "l": 0.0, "a": 0.3, "b": 0.3,
                                            "g": 0.0, "h": 0.0, "tick_unit": "year"})
        delta = t.update(self._env(0.7, 0.7), [], 0)
        assert delta["actor_a__military_readiness"] < 0.7
        assert delta["actor_b__military_readiness"] < 0.7

    def test_reaction_drives_escalation(self):
        # If Y is highly armed and X has high k, X should increase arms
        t = RichardsonArmsRace(parameters={"k": 0.8, "l": 0.0, "a": 0.0, "b": 0.0,
                                            "g": 0.0, "h": 0.0, "tick_unit": "year"})
        delta = t.update(self._env(x=0.1, y=0.8), [], 0)
        assert delta["actor_a__military_readiness"] > 0.1  # X reacts to Y

    def test_tick_unit_month_vs_year(self):
        # Monthly ticks should produce smaller per-tick changes than yearly
        env = self._env(0.5, 0.5)
        t_year = RichardsonArmsRace(parameters={"tick_unit": "year"})
        t_month = RichardsonArmsRace(parameters={"tick_unit": "month"})
        d_year = t_year.update(env, [], 0)
        d_month = t_month.update(env, [], 0)
        year_change = abs(d_year["actor_a__military_readiness"] - 0.5)
        month_change = abs(d_month["actor_a__military_readiness"] - 0.5)
        assert month_change < year_change

    def test_symmetric_params_produce_symmetric_output(self):
        # With symmetric params and initial values, x and y should evolve equally
        t = RichardsonArmsRace(parameters={"k": 0.3, "l": 0.3, "a": 0.15, "b": 0.15,
                                            "g": 0.05, "h": 0.05})
        delta = t.update(self._env(0.5, 0.5), [], 0)
        assert abs(delta["actor_a__military_readiness"] - delta["actor_b__military_readiness"]) < 1e-10

    def test_missing_env_keys_default_to_0_5(self):
        # If the theory is called without keys in env, should not crash
        t = RichardsonArmsRace()
        delta = t.update({}, [], 0)  # empty env
        assert "actor_a__military_readiness" in delta
        assert "actor_b__military_readiness" in delta

    def test_custom_actor_ids_in_output(self):
        t = RichardsonArmsRace(parameters={"actor_a_id": "iran", "actor_b_id": "us"})
        delta = t.update(
            {"iran__military_readiness": 0.6, "us__military_readiness": 0.4}, [], 0
        )
        assert "iran__military_readiness" in delta
        assert "us__military_readiness" in delta
        assert "actor_a__military_readiness" not in delta

    def test_multi_tick_convergence_to_equilibrium(self):
        # Stable params: after many ticks, x and y should approach equilibrium
        t = RichardsonArmsRace(parameters={
            "k": 0.1, "l": 0.1, "a": 0.4, "b": 0.4,
            "g": 0.05, "h": 0.05, "tick_unit": "year",
        })
        env = {"actor_a__military_readiness": 0.2, "actor_b__military_readiness": 0.8}
        for _ in range(50):
            delta = t.update(env, [], 0)
            env.update(delta)

        eq = t.equilibrium()
        assert eq is not None
        x_star, y_star = eq
        # After 50 ticks, should be within 0.05 of equilibrium
        assert abs(env["actor_a__military_readiness"] - x_star) < 0.05
        assert abs(env["actor_b__military_readiness"] - y_star) < 0.05


# ── equilibrium() ─────────────────────────────────────────────────────────────

class TestEquilibrium:
    def test_returns_none_when_unstable(self):
        # k=0.5, l=0.5 → k·l=0.25; a=0.1, b=0.1 → a·b=0.01 — unstable
        t = RichardsonArmsRace(parameters={"k": 0.5, "l": 0.5, "a": 0.1, "b": 0.1})
        assert t.equilibrium() is None

    def test_returns_tuple_when_stable(self):
        t = RichardsonArmsRace(parameters={"k": 0.1, "l": 0.1, "a": 0.4, "b": 0.4,
                                            "g": 0.05, "h": 0.05})
        eq = t.equilibrium()
        assert eq is not None
        assert len(eq) == 2

    def test_symmetric_params_give_equal_equilibrium(self):
        # Symmetric params → x* == y*
        t = RichardsonArmsRace(parameters={"k": 0.2, "l": 0.2, "a": 0.4, "b": 0.4,
                                            "g": 0.05, "h": 0.05})
        eq = t.equilibrium()
        assert eq is not None
        x_star, y_star = eq
        assert abs(x_star - y_star) < 1e-10

    def test_equilibrium_matches_analytical_formula(self):
        # x* = (b·g + k·h) / (a·b - k·l)
        # y* = (a·h + l·g) / (a·b - k·l)
        k, l, a, b, g, h = 0.2, 0.15, 0.35, 0.30, 0.06, 0.04
        t = RichardsonArmsRace(parameters={"k": k, "l": l, "a": a, "b": b, "g": g, "h": h})
        denom = a * b - k * l
        expected_x = (b * g + k * h) / denom
        expected_y = (a * h + l * g) / denom
        eq = t.equilibrium()
        assert eq is not None
        x_star, y_star = eq
        assert abs(x_star - expected_x) < 1e-10
        assert abs(y_star - expected_y) < 1e-10
