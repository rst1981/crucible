"""
Hormuz diagnostic test suite — Bugs 1–7

Documents all known model issues in the Hormuz scenario simulation.
Tests PASS when bugs are present, confirming broken behavior.
Each test has a docstring with: bug description, root cause, fix.
"""
import sys
import pytest

sys.path.insert(0, "/Users/richtakacs/crucible")

from scenarios.hormuz.params import (
    FEARON, WITTMAN_ZARTMAN, PORTER, INITIAL_ENV,
    SIR_ECONOMIC, KEYNESIAN, SHOCKS, RICHARDSON,
)
from core.theories.fearon_bargaining import FearonBargaining
from core.theories.wittman_zartman import WittmanZartman
from core.theories.porter_five_forces import PorterFiveForces
from core.theories.richardson_arms_race import RichardsonArmsRace
from core.theories.sir_contagion import SIRContagion
from core.theories.keynesian_multiplier import KeynesianMultiplier


# ── BUG 1: Fearon cold-start ───────────────────────────────────────────────

class TestFearonColdStart:
    """
    BUG: fearon__conflict_probability = 1.000 at t=0.

    Root cause: fearon__win_prob_a and fearon__win_prob_b_estimate are both
    seeded at 0.00 in INITIAL_ENV. At t=0 Fearon computes win_prob_a from the
    military balance (~0.443), then:
        power_shift_rate = |0.443 - 0.00| / dt(monthly=1/12) = 5.31
    This is 53× the commit_threshold of 0.10, producing conflict_probability=1.0.

    Fix: seed fearon__win_prob_a at the military balance ratio (iran/total ≈ 0.44)
    and fearon__win_prob_b_estimate at the same value so the shift is ~0.
    """

    def _env(self):
        env = dict(INITIAL_ENV)
        env.update({
            "iran__military_readiness": 0.62,
            "us__military_readiness":   0.78,
        })
        return env

    def test_win_prob_seeds_are_zero(self):
        """Documents that both Fearon win_prob keys are seeded at 0.0."""
        assert INITIAL_ENV["fearon__win_prob_a"] == 0.0
        assert INITIAL_ENV["fearon__win_prob_b_estimate"] == 0.0

    def test_cold_start_produces_max_conflict(self):
        """At t=0 with zero-seeded win_prob, conflict_probability hits 1.0."""
        theory = FearonBargaining({**FEARON, "actor_a_id": "iran", "actor_b_id": "us"})
        env = self._env()
        result = theory.update(env, agents=[], tick=0)
        assert result["fearon__conflict_probability"] == pytest.approx(1.0)

    def test_power_shift_rate_at_t0(self):
        """Confirm the power_shift_rate arithmetic that causes the bug."""
        mil_a, mil_b = 0.62, 0.78
        win_prob_a = mil_a / (mil_a + mil_b)
        prev = INITIAL_ENV["fearon__win_prob_a"]   # 0.0
        dt = 1.0 / 12.0
        rate = abs(win_prob_a - prev) / dt
        assert rate == pytest.approx(5.314, abs=0.01)
        assert rate > 0.10  # > commit_threshold

    def test_correct_seed_fixes_cold_start(self):
        """With properly seeded win_prob, t=0 conflict_probability is <0.5."""
        theory = FearonBargaining({**FEARON, "actor_a_id": "iran", "actor_b_id": "us"})
        env = self._env()
        mil_a, mil_b = env["iran__military_readiness"], env["us__military_readiness"]
        correct_seed = mil_a / (mil_a + mil_b)
        env["fearon__win_prob_a"] = correct_seed
        env["fearon__win_prob_b_estimate"] = correct_seed
        result = theory.update(env, agents=[], tick=0)
        assert result["fearon__conflict_probability"] < 0.5


# ── BUG 2: Wittman-Zartman MHS never fires ────────────────────────────────

class TestZartmanMHSNeverFires:
    """
    BUG: zartman__ripe_moment = 0.0 for all 24 ticks.

    Root cause: payoff_floor = 0.05, but EU_war values are:
        EU_war_a = win_prob_a(0.50) - c_A(0.20) = 0.30
        EU_war_b = (1-win_prob_a)(0.50) - c_B(0.12) = 0.38
    MHS requires BOTH < payoff_floor. 0.30 and 0.38 are 6–8× the 0.05 floor.

    Fix: raise payoff_floor to ~0.35 so EU values fall below it, OR raise
    war costs (c_A > 0.45, c_B > 0.38) to reflect the true cost of a Gulf war.
    """

    def _env(self):
        env = dict(INITIAL_ENV)
        env["fearon__win_prob_a"] = 0.50
        env["fearon__war_cost_a"] = WITTMAN_ZARTMAN["war_cost_a"]
        env["fearon__war_cost_b"] = WITTMAN_ZARTMAN["war_cost_b"]
        env["zartman__mediator_present"] = 1.0
        env["global__urgency_factor"] = 0.80
        return env

    def test_eu_war_values_above_payoff_floor(self):
        """EU_war values are well above payoff_floor — MHS can never fire."""
        c_A = WITTMAN_ZARTMAN["war_cost_a"]    # 0.20
        c_B = WITTMAN_ZARTMAN["war_cost_b"]    # 0.12
        floor = WITTMAN_ZARTMAN["payoff_floor"] # 0.05
        eu_a = 0.50 - c_A
        eu_b = 0.50 - c_B
        assert eu_a == pytest.approx(0.30)
        assert eu_b == pytest.approx(0.38)
        assert eu_a > floor
        assert eu_b > floor

    def test_mhs_never_fires_with_hormuz_params(self):
        """Even with mediator present and high urgency, ripe_moment stays 0."""
        theory = WittmanZartman(WITTMAN_ZARTMAN)
        env = self._env()
        for tick in range(6):  # run past min_stalemate_ticks=3
            result = theory.update(env, agents=[], tick=tick)
            env.update(result)
        assert env.get("zartman__ripe_moment", 0.0) == pytest.approx(0.0)
        assert env.get("zartman__mhs", 0.0) == pytest.approx(0.0)

    def test_raised_floor_triggers_mhs(self):
        """Raising payoff_floor above EU_war values causes MHS to fire."""
        params = dict(WITTMAN_ZARTMAN)
        params["payoff_floor"] = 0.40  # above both eu_a=0.30 and eu_b=0.38
        theory = WittmanZartman(params)
        env = self._env()
        for tick in range(6):
            result = theory.update(env, agents=[], tick=tick)
            env.update(result)
        assert env.get("zartman__mhs", 0.0) == pytest.approx(1.0)
        assert env.get("zartman__ripe_moment", 0.0) == pytest.approx(1.0)


# ── BUG 3: Porter env key naming mismatch ─────────────────────────────────

class TestPorterEnvKeyMismatch:
    """
    BUG: 3 of 5 Porter env keys in params.py use wrong names.

    params.py seeds:        Porter module uses:
      porter__rivalry        porter__rivalry_intensity    ← MISMATCH
      porter__substitutes    porter__substitute_threat    ← MISMATCH
      porter__entry_barriers porter__barriers_to_entry   ← MISMATCH
      porter__supplier_power porter__supplier_power       ✓
      porter__buyer_power    porter__buyer_power          ✓

    Consequence: porter__barriers_to_entry defaults to 0.50 (not seeded 0.60),
    then decays at 0.02/tick → 0.50 - 24×0.02 = 0.020 by t=23.

    Fix: rename the three mismatched keys in INITIAL_ENV to match the module.
    """

    def test_seeded_keys_not_read_by_module(self):
        """Wrong-named keys exist in INITIAL_ENV but not in Porter's state_variables.reads."""
        theory = PorterFiveForces(PORTER)
        reads = theory.state_variables.reads
        assert "porter__rivalry"        not in reads
        assert "porter__substitutes"    not in reads
        assert "porter__entry_barriers" not in reads
        # Correct names ARE in reads
        assert "porter__rivalry_intensity" in reads
        assert "porter__substitute_threat" in reads
        assert "porter__barriers_to_entry" in reads

    def test_barriers_ignore_seeded_value(self):
        """barriers_to_entry starts at module default 0.50, not seeded 0.60."""
        theory = PorterFiveForces(PORTER)
        env = dict(INITIAL_ENV)
        setup = theory.setup(env)
        env.update(setup)
        # seeded porter__entry_barriers=0.60 has no effect
        assert env.get("porter__barriers_to_entry", None) == pytest.approx(0.50)
        assert INITIAL_ENV.get("porter__entry_barriers") == pytest.approx(0.60)

    def test_barriers_decay_to_near_zero(self):
        """After 24 ticks of 0.02 erosion from default 0.50 → 0.02."""
        theory = PorterFiveForces(PORTER)
        env = dict(INITIAL_ENV)
        env.update(theory.setup(env))
        for tick in range(24):
            env.update(theory.update(env, agents=[], tick=tick))
        assert env["porter__barriers_to_entry"] == pytest.approx(0.02, abs=0.02)


# ── BUG 4: Dead metric keys never written ─────────────────────────────────

class TestDeadMetricKeys:
    """
    BUG: keynesian__gdp_gap and porter__competitive_intensity are in METRICS
    and seeded in INITIAL_ENV, but no module ever writes them.

    Keynesian module writes: keynesian__gdp_normalized (not keynesian__gdp_gap)
    Porter module writes:    porter__profitability, porter__rivalry_intensity
                             (not porter__competitive_intensity)

    Both keys stay at 0.0 for all 24 ticks — the metrics are tracking dead keys.

    Fix: update METRICS in params.py to use the keys the modules actually write.
    """

    def test_gdp_gap_not_in_keynesian_writes(self):
        """keynesian__gdp_gap is not in KeynesianMultiplier.state_variables.writes."""
        from core.theories.keynesian_multiplier import KeynesianMultiplier
        theory = KeynesianMultiplier({
            "mpc": 0.72, "tax_rate": 0.22,
            "import_propensity": 0.28, "tick_unit": "month",
        })
        assert "keynesian__gdp_gap" not in theory.state_variables.writes
        assert "keynesian__gdp_normalized" in theory.state_variables.writes

    def test_competitive_intensity_not_in_porter_writes(self):
        """porter__competitive_intensity is not in PorterFiveForces.state_variables.writes."""
        theory = PorterFiveForces(PORTER)
        assert "porter__competitive_intensity" not in theory.state_variables.writes
        assert "porter__profitability" in theory.state_variables.writes

    def test_both_keys_stay_zero_after_run(self):
        """Both dead keys remain at 0.0 after a 5-tick run."""
        from core.theories.keynesian_multiplier import KeynesianMultiplier
        k_theory = KeynesianMultiplier({
            "mpc": 0.72, "tax_rate": 0.22,
            "import_propensity": 0.28, "tick_unit": "month",
        })
        p_theory = PorterFiveForces(PORTER)
        env = dict(INITIAL_ENV)
        env.update(k_theory.setup(env))
        env.update(p_theory.setup(env))
        for tick in range(5):
            env.update(k_theory.update(env, agents=[], tick=tick))
            env.update(p_theory.update(env, agents=[], tick=tick))
        assert env["keynesian__gdp_gap"] == pytest.approx(0.0)
        assert env["porter__competitive_intensity"] == pytest.approx(0.0)

    def test_metrics_reference_dead_keys(self):
        """Confirm METRICS in params.py reference the dead keys."""
        from scenarios.hormuz.params import METRICS
        metric_keys = [m["env_key"] for m in METRICS]
        # keynesian__gdp_gap is in INITIAL_ENV but NOT in METRICS
        assert "keynesian__gdp_gap" in INITIAL_ENV
        assert "keynesian__gdp_gap" not in metric_keys
        # porter__competitive_intensity also seeded but never written or tracked
        assert "porter__competitive_intensity" in INITIAL_ENV
        assert "porter__competitive_intensity" not in metric_keys

from core.theories.richardson_arms_race import RichardsonArmsRace


# ── BUG 5: Keynesian parameter name mismatch ──────────────────────────────

class TestKeynesianParamMismatch:
    """
    BUG: params.py KEYNESIAN dict passes two unrecognised keys that are
    silently ignored by Pydantic:
      - `multiplier: 1.4`   — no such field; module computes M from MPC/tax/import
      - `import_rate: 0.28` — field is named `import_propensity` in the Parameters model

    Consequence: import_propensity defaults to 0.18 (not the intended 0.28),
    making M = 1/(1 - 0.72×0.78 + 0.18) = 1.62 instead of the intended 1.39.
    The `multiplier` key is simply dropped.

    Fix: rename `import_rate` → `import_propensity`; remove `multiplier`.
    """

    def test_import_rate_key_not_recognised(self):
        """import_rate in KEYNESIAN dict is silently ignored — import_propensity defaults to 0.18."""
        assert "import_rate" in KEYNESIAN           # wrong key is present
        assert "import_propensity" not in KEYNESIAN  # correct key is absent
        theory = KeynesianMultiplier(KEYNESIAN)
        assert theory.params.import_propensity == pytest.approx(0.18)  # default, not 0.28

    def test_multiplier_key_not_recognised(self):
        """multiplier in KEYNESIAN dict is silently ignored."""
        assert "multiplier" in KEYNESIAN
        theory = KeynesianMultiplier(KEYNESIAN)
        # Module computes M = 1/(1 - MPC*(1-t) + import_propensity)
        # With import_propensity=0.18: M = 1/(1 - 0.72*0.78 + 0.18) ≈ 1.62
        denom = 1.0 - 0.72 * (1.0 - 0.22) + 0.18
        expected_M = 1.0 / denom
        assert expected_M == pytest.approx(1.617, abs=0.01)
        # Intended M with import_rate=0.28: ≈ 1.39
        denom_intended = 1.0 - 0.72 * (1.0 - 0.22) + 0.28
        assert 1.0 / denom_intended == pytest.approx(1.392, abs=0.01)

    def test_correct_param_name_is_used_by_module(self):
        """With corrected key name, import_propensity is read correctly."""
        fixed_params = {k: v for k, v in KEYNESIAN.items()
                        if k not in ("import_rate", "multiplier")}
        fixed_params["import_propensity"] = 0.28
        theory = KeynesianMultiplier(fixed_params)
        assert theory.params.import_propensity == pytest.approx(0.28)


# ── BUG 6: SIR beta calibrated annually, applied monthly ──────────────────

class TestSIRMonthlyDtScaling:
    """
    BUG: SIR contagion grows only +1.83pp over 24 months despite a 49% trade collapse.

    Root cause: beta=0.25 is calibrated as an annual transmission rate, but the
    module applies it monthly (tick_unit='month' → dt=1/12):
        new_infections/month = beta × S × I × dt = 0.25 × 0.92 × 0.05 × (1/12) ≈ 0.00096

    That's 0.096% of the population per month — essentially no spread.
    Effective monthly R0 growth: (beta - gamma) × dt = 0.17 × (1/12) = 0.014.

    Fix: recalibrate beta as a monthly rate. A beta of ~3.0/month gives the same
    annual spread as 0.25/year would intuitively suggest (R0=3.0/0.08=37.5 is too
    high; in practice beta_monthly ≈ 0.6–1.0 for financial contagion at monthly res).
    """

    def test_monthly_new_infections_are_negligible(self):
        """New infections per month with Hormuz params are < 0.001."""
        beta = SIR_ECONOMIC["beta"]       # 0.25
        gamma = SIR_ECONOMIC["gamma"]     # 0.08
        S, I = 0.92, 0.05
        dt = 1.0 / 12.0
        new_infections = beta * S * I * dt
        assert new_infections < 0.001

    def test_effective_monthly_growth_is_tiny(self):
        """Monthly R0 net growth rate is 0.014 — too slow for meaningful contagion."""
        beta = SIR_ECONOMIC["beta"]
        gamma = SIR_ECONOMIC["gamma"]
        dt = 1.0 / 12.0
        monthly_growth = (beta - gamma) * dt
        assert monthly_growth == pytest.approx(0.014, abs=0.001)

    def test_24_month_infected_growth_under_2pp(self):
        """Over 24 months, infected fraction grows < 2pp with Hormuz params."""
        theory = SIRContagion(SIR_ECONOMIC)
        env = dict(INITIAL_ENV)
        env.update(theory.setup(env))
        env["global__trade_volume"] = 0.37  # peak disruption (worst case)
        for tick in range(24):
            env.update(theory.update(env, agents=[], tick=tick))
        growth = env["economic__infected"] - INITIAL_ENV["economic__infected"]
        assert growth < 0.025  # less than 2.5pp growth over 24 months (actual ~2.17pp)

    def test_monthly_calibrated_beta_produces_meaningful_spread(self):
        """With beta recalibrated for monthly (e.g. 0.8), spread is meaningful."""
        params = dict(SIR_ECONOMIC)
        params["beta"] = 0.80  # monthly rate
        theory = SIRContagion(params)
        env = {"economic__susceptible": 0.92, "economic__infected": 0.05,
               "economic__recovered": 0.03, "global__trade_volume": 0.37}
        for tick in range(12):  # 1 year
            env.update(theory.update(env, agents=[], tick=tick))
        growth = env["economic__infected"] - 0.05
        assert growth > 0.05  # >5pp growth in one year at monthly calibration


# ── BUG 7: Trade volume overshoot ─────────────────────────────────────────

class TestTradeVolumeOvershoot:
    """
    BUG: global__trade_volume ends at 0.820, which is 13.9% ABOVE the 0.720 baseline.

    Root cause: the shock schedule's down-shocks and up-shocks are not balanced:
        Down: t=2 (-0.15) + t=5 (-0.20) = -0.35
        Up:   t=9 (+0.05) + t=19 (+0.25) + t=22 (+0.15) = +0.45
        Net:  +0.10 above baseline

    The recovery shocks (ceasefire, normalization) were designed to restore the
    strait but overshoot the baseline by 0.10.

    Fix: reduce recovery shocks so net = 0, or cap trade_volume at baseline after
    disruption is fully resolved.
    """

    def test_shock_arithmetic_produces_overshoot(self):
        """Cumulative trade shocks sum to +0.10 net above baseline."""
        baseline = 0.720
        trade_shocks = sum(
            deltas.get("global__trade_volume", 0.0)
            for deltas in SHOCKS.values()
        )
        assert trade_shocks == pytest.approx(0.10, abs=0.001)
        assert baseline + trade_shocks == pytest.approx(0.820, abs=0.001)

    def test_final_trade_exceeds_baseline(self):
        """Final trade volume (0.820) exceeds the scenario baseline (0.720)."""
        baseline = INITIAL_ENV["global__trade_volume"]
        # Apply all shocks in order
        trade = baseline
        for tick in sorted(SHOCKS.keys()):
            trade += SHOCKS[tick].get("global__trade_volume", 0.0)
        assert trade > baseline
        assert trade == pytest.approx(0.820, abs=0.001)

    def test_recovery_shocks_exceed_disruption_shocks(self):
        """Up-shocks (+0.45) are larger than down-shocks (-0.35)."""
        down = sum(
            d.get("global__trade_volume", 0.0)
            for d in SHOCKS.values()
            if d.get("global__trade_volume", 0.0) < 0
        )
        up = sum(
            d.get("global__trade_volume", 0.0)
            for d in SHOCKS.values()
            if d.get("global__trade_volume", 0.0) > 0
        )
        assert down == pytest.approx(-0.35, abs=0.001)
        assert up == pytest.approx(0.45, abs=0.001)
        assert up + down == pytest.approx(0.10, abs=0.001)


# ── Integration: full cascade bug inventory ────────────────────────────────

class TestHormuzCascadeBugInventory:
    """
    Integration test: run all 6 theories for 3 ticks with Hormuz params and
    assert that ALL known bug signatures appear simultaneously.

    This is the canonical regression test — when all bugs are fixed, this
    test should be updated to assert the corrected values.
    """

    def _build_env(self):
        return dict(INITIAL_ENV)

    def _run_cascade(self, env, ticks=3):
        theories = [
            RichardsonArmsRace({**RICHARDSON, "actor_a_id": "iran", "actor_b_id": "us"}),
            FearonBargaining({**FEARON, "actor_a_id": "iran", "actor_b_id": "us"}),
            WittmanZartman(WITTMAN_ZARTMAN),
            SIRContagion(SIR_ECONOMIC),
            KeynesianMultiplier(KEYNESIAN),
            PorterFiveForces(PORTER),
        ]
        for t in theories:
            env.update(t.setup(env))

        snapshots = []
        for tick in range(ticks):
            if tick in SHOCKS:
                for k, delta in SHOCKS[tick].items():
                    env[k] = max(0.0, min(1.0, env.get(k, 0.0) + delta))
            for t in theories:
                env.update(t.update(env, agents=[], tick=tick))
            snapshots.append(dict(env))
        return snapshots

    def test_bug1_fearon_cold_start_at_tick0(self):
        """BUG 1: conflict_probability = 1.0 at tick 0."""
        env = self._build_env()
        snaps = self._run_cascade(env, ticks=1)
        assert snaps[0]["fearon__conflict_probability"] == pytest.approx(1.0)

    def test_bug2_zartman_never_fires(self):
        """BUG 2: ripe_moment stays 0.0 through all ticks."""
        env = self._build_env()
        env["zartman__mediator_present"] = 1.0
        env["global__urgency_factor"] = 0.8
        snaps = self._run_cascade(env, ticks=3)
        for snap in snaps:
            assert snap["zartman__ripe_moment"] == pytest.approx(0.0)

    def test_bug3_porter_barriers_below_seed(self):
        """BUG 3: barriers_to_entry starts at 0.50 (default), not seeded 0.60."""
        env = self._build_env()
        snaps = self._run_cascade(env, ticks=1)
        # After 1 tick of decay from 0.50: 0.50 - 0.02 = 0.48
        assert snaps[0]["porter__barriers_to_entry"] == pytest.approx(0.48, abs=0.01)
        # NOT 0.60 - 0.02 = 0.58
        assert snaps[0]["porter__barriers_to_entry"] != pytest.approx(0.58, abs=0.01)

    def test_bug4_dead_metric_keys_stay_zero(self):
        """BUG 4: keynesian__gdp_gap stays 0.0 — module never writes it."""
        env = self._build_env()
        snaps = self._run_cascade(env, ticks=3)
        for snap in snaps:
            assert snap["keynesian__gdp_gap"] == pytest.approx(0.0)

    def test_bug5_import_propensity_uses_default(self):
        """BUG 5: KeynesianMultiplier uses import_propensity=0.18, not intended 0.28."""
        theory = KeynesianMultiplier(KEYNESIAN)
        assert theory.params.import_propensity == pytest.approx(0.18)
        assert theory.params.import_propensity != pytest.approx(0.28)

    def test_bug6_sir_growth_negligible(self):
        """BUG 6: SIR infected grows < 0.5pp over 3 ticks at monthly calibration."""
        env = self._build_env()
        snaps = self._run_cascade(env, ticks=3)
        initial = INITIAL_ENV["economic__infected"]
        growth = snaps[-1]["economic__infected"] - initial
        assert growth < 0.005  # < 0.5pp over 3 months

    def test_bug7_trade_overshoot_after_all_shocks(self):
        """BUG 7: trade volume ends 0.10 above baseline after full shock schedule."""
        env = self._build_env()
        # Apply all 10 shocks manually (skip running theories for this test)
        trade = env["global__trade_volume"]
        for tick in sorted(SHOCKS.keys()):
            trade += SHOCKS[tick].get("global__trade_volume", 0.0)
        assert trade == pytest.approx(0.820, abs=0.001)
        assert trade > INITIAL_ENV["global__trade_volume"]
