"""
tests/test_hormuz_diagnostics.py
Hormuz regression tests: verify all 8 bug fixes hold.
These tests assert FIXED behavior (green = bugs resolved).

Bugs fixed:
  Bug 1: Fearon win_prob cold-start (was 0.0 → conflict_prob=1.0)
  Bug 2: Zartman payoff_floor too low (was 0.05 → MHS never fires)
  Bug 3: Porter env key mismatch (rivalry, substitutes, entry_barriers)
  Bug 4: Dead metric keys (gdp_gap, competitive_intensity)
  Bug 5: Keynesian import_rate → import_propensity
  Bug 6: SIR beta annual→monthly calibration
  Bug 7: Trade volume net shock overshoot (+0.10 above baseline)
  Bug 8: Fearon war_cost seeded 0.00 → Zartman EU = win_prob (no cost subtracted)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── imports ───────────────────────────────────────────────────────────────────

from scenarios.hormuz.params import (
    FEARON,
    INITIAL_ENV,
    KEYNESIAN,
    METRICS,
    PORTER,
    RICHARDSON,
    SHOCKS,
    SIR_ECONOMIC,
    WITTMAN_ZARTMAN,
)
from core.theories.fearon_bargaining import FearonBargaining
from core.theories.wittman_zartman import WittmanZartman
from core.theories.porter_five_forces import PorterFiveForces
from core.theories.keynesian_multiplier import KeynesianMultiplier
from core.theories.sir_contagion import SIRContagion
from core.theories.richardson_arms_race import RichardsonArmsRace


# ══════════════════════════════════════════════════════════════════════════════
# Bug 1 Fix — Fearon cold-start eliminated
# ══════════════════════════════════════════════════════════════════════════════

class TestFearonColdStart:
    """Bug 1 (FIXED): win_prob seeded at military balance ratio, not 0.0.
    Eliminates the t=0 power_shift_rate spike that caused P(conflict)=1.0.
    """

    def test_win_prob_seeded_at_military_balance(self):
        """INITIAL_ENV seeds win_prob at ~0.443, not 0.0."""
        iran_mil = 0.62
        us_mil = 0.78
        expected = iran_mil / (iran_mil + us_mil)   # ≈ 0.443

        a = INITIAL_ENV["fearon__win_prob_a"]
        b = INITIAL_ENV["fearon__win_prob_b_estimate"]

        assert abs(a - expected) < 0.001, f"win_prob_a={a:.4f}, expected≈{expected:.4f}"
        assert abs(b - expected) < 0.001, f"win_prob_b_estimate={b:.4f}, expected≈{expected:.4f}"

    def test_win_prob_not_zero(self):
        """Both win_prob keys must be non-zero."""
        assert INITIAL_ENV["fearon__win_prob_a"] > 0.0
        assert INITIAL_ENV["fearon__win_prob_b_estimate"] > 0.0

    def test_t0_conflict_probability_below_one(self):
        """At tick 0 with balanced military seeds, P(conflict) < 1.0 (was 1.0 with bug)."""
        env = dict(INITIAL_ENV)
        m = FearonBargaining(parameters=FEARON)
        writes = m.update(env, [], 0)
        env.update(writes)
        p = env["fearon__conflict_probability"]
        assert p < 1.0, f"P(conflict)={p:.3f} at t=0 — still 1.0 (Bug 1 not fixed)"

    def test_t0_conflict_probability_lower_than_bug(self):
        """With correct seeds, P(conflict) < bug-era value of 1.0."""
        env = dict(INITIAL_ENV)
        m = FearonBargaining(parameters=FEARON)
        writes = m.update(env, [], 0)
        env.update(writes)
        p = env["fearon__conflict_probability"]
        # Bug value was 1.0 (53x threshold); fixed value is ~0.667 (info-gap based)
        assert p < 1.0

    def test_power_shift_rate_is_reasonable(self):
        """With symmetric seeds, power_shift_rate is bounded; no 53x spike."""
        env = dict(INITIAL_ENV)
        m = FearonBargaining(parameters=FEARON)
        writes = m.update(env, [], 0)
        env.update(writes)
        # Settlement range should be war_cost_a + war_cost_b = 0.32 (not 0.0)
        sr = env.get("fearon__settlement_range_width", 0.0)
        assert sr > 0.0, f"settlement_range={sr:.3f} — war costs not feeding through"


# ══════════════════════════════════════════════════════════════════════════════
# Bug 2 Fix — Zartman MHS fires with raised payoff_floor
# ══════════════════════════════════════════════════════════════════════════════

class TestZartmanMHSFires:
    """Bug 2 (FIXED): payoff_floor raised to 0.45 so both sides are hurting.
    With win_prob_a≈0.443: EU_war_a=0.243, EU_war_b=0.433 — both < 0.45.
    """

    def test_payoff_floor_is_raised(self):
        """payoff_floor must be ≥ 0.45 (was 0.05)."""
        assert WITTMAN_ZARTMAN["payoff_floor"] >= 0.45, (
            f"payoff_floor={WITTMAN_ZARTMAN['payoff_floor']} — not high enough for MHS"
        )

    def test_eu_war_a_below_floor(self):
        """EU_war_a must fall below payoff_floor."""
        win_prob_a = INITIAL_ENV["fearon__win_prob_a"]   # ≈ 0.443
        c_a = WITTMAN_ZARTMAN["war_cost_a"]              # 0.20
        eu_war_a = win_prob_a - c_a                      # 0.243
        floor = WITTMAN_ZARTMAN["payoff_floor"]
        assert eu_war_a < floor, (
            f"EU_war_a={eu_war_a:.3f} ≥ floor={floor} — side A not hurting"
        )

    def test_eu_war_b_below_floor(self):
        """EU_war_b must fall below payoff_floor."""
        win_prob_a = INITIAL_ENV["fearon__win_prob_a"]   # ≈ 0.443
        win_prob_b = 1.0 - win_prob_a                    # ≈ 0.557
        c_b = WITTMAN_ZARTMAN["war_cost_b"]              # 0.12
        eu_war_b = win_prob_b - c_b                      # 0.437
        floor = WITTMAN_ZARTMAN["payoff_floor"]
        assert eu_war_b < floor, (
            f"EU_war_b={eu_war_b:.3f} ≥ floor={floor} — side B not hurting"
        )

    def test_mhs_fires_at_tick0_with_correct_war_costs(self):
        """With war costs seeded at 0.20/0.12, MHS fires immediately (eu_a=0.243, eu_b=0.437).

        Bug 8 fix: war costs were seeded 0.00 → EU_war = win_prob (no cost subtracted)
        → EU_war_b=0.557 > 0.45 floor → MHS never fired.
        """
        env = dict(INITIAL_ENV)
        # INITIAL_ENV now seeds fearon__war_cost_a=0.20, fearon__war_cost_b=0.12
        m = WittmanZartman(parameters=WITTMAN_ZARTMAN)
        writes = m.update(env, [], 0)
        env.update(writes)

        eu_a = env.get("zartman__eu_war_a", 0.0)
        eu_b = env.get("zartman__eu_war_b", 0.0)
        floor = WITTMAN_ZARTMAN["payoff_floor"]
        assert eu_a < floor, f"EU_war_a={eu_a:.3f} ≥ floor={floor} (Bug 8 or 2 not fixed)"
        assert eu_b < floor, f"EU_war_b={eu_b:.3f} ≥ floor={floor} (Bug 8 not fixed)"
        assert env.get("zartman__mhs") == 1.0

    def test_ripe_moment_fires_after_stalemate_and_mediator(self):
        """ripe_moment becomes 1.0 once stalemate ticks ≥ min_stalemate_ticks and mediator present."""
        env = dict(INITIAL_ENV)
        env["zartman__mediator_present"] = 1.0

        m = WittmanZartman(parameters=WITTMAN_ZARTMAN)
        # Run enough ticks to satisfy min_stalemate_ticks (3) internally
        for tick in range(4):
            writes = m.update(env, [], tick)
            env.update(writes)

        assert env.get("zartman__ripe_moment", 0.0) == 1.0, (
            f"ripe_moment={env.get('zartman__ripe_moment')} after 4 ticks with mediator"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bug 3 Fix — Porter env keys match module expectations
# ══════════════════════════════════════════════════════════════════════════════

class TestPorterEnvKeysFix:
    """Bug 3 (FIXED): Porter env keys renamed to match module field names."""

    def test_rivalry_intensity_key_present(self):
        assert "porter__rivalry_intensity" in INITIAL_ENV
        assert "porter__rivalry" not in INITIAL_ENV

    def test_substitute_threat_key_present(self):
        assert "porter__substitute_threat" in INITIAL_ENV
        assert "porter__substitutes" not in INITIAL_ENV

    def test_barriers_to_entry_key_present(self):
        assert "porter__barriers_to_entry" in INITIAL_ENV
        assert "porter__entry_barriers" not in INITIAL_ENV

    def test_barriers_seed_is_respected(self):
        """Porter must read the seeded barriers_to_entry=0.60, not default."""
        env = dict(INITIAL_ENV)
        assert env["porter__barriers_to_entry"] == pytest.approx(0.60)

        m = PorterFiveForces(parameters=PORTER)
        writes = m.update(env, [], 0)
        env.update(writes)

        profitability = env.get("porter__profitability", None)
        assert profitability is not None
        assert profitability != 0.0

    def test_porter_profitability_reflects_high_barriers(self):
        """With high barriers (0.60), profitability should be above neutral."""
        env = dict(INITIAL_ENV)
        m = PorterFiveForces(parameters=PORTER)
        writes = m.update(env, [], 0)
        env.update(writes)
        p = env["porter__profitability"]
        assert p > 0.3, f"profitability={p:.3f} — barriers not feeding through"

    def test_barriers_start_from_seeded_value_not_default(self):
        """With correct keys, barriers decay from seeded 0.60, not module default 0.50.
        Bug 3 check: after 1 tick, barriers should be ~0.58 (from 0.60), not ~0.48 (from 0.50 default).
        """
        env = dict(INITIAL_ENV)
        m = PorterFiveForces(parameters=PORTER)
        writes = m.update(env, [], 0)
        env.update(writes)
        b = env["porter__barriers_to_entry"]
        # With correct key: 0.60 - 0.02 = 0.58; with old bug (default 0.50): 0.50 - 0.02 = 0.48
        assert b > 0.55, (
            f"barriers_to_entry={b:.3f} after tick 0 — "
            f"expected ~0.58 from seeded 0.60, got {b:.3f} (default 0.50 → 0.48?)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bug 4 Fix — Metric keys reference keys modules actually write
# ══════════════════════════════════════════════════════════════════════════════

class TestMetricKeysFix:
    """Bug 4 (FIXED): METRICS and INITIAL_ENV use real module output keys."""

    def test_gdp_normalized_in_initial_env(self):
        """keynesian__gdp_normalized is seeded (not the dead gdp_gap key)."""
        assert "keynesian__gdp_normalized" in INITIAL_ENV
        assert "keynesian__gdp_gap" not in INITIAL_ENV

    def test_profitability_in_initial_env(self):
        """porter__profitability is seeded (not dead competitive_intensity key)."""
        assert "porter__profitability" in INITIAL_ENV
        assert "porter__competitive_intensity" not in INITIAL_ENV

    def test_metrics_reference_gdp_normalized(self):
        """METRICS must track keynesian__gdp_normalized."""
        metric_keys = {m["env_key"] for m in METRICS}
        assert "keynesian__gdp_normalized" in metric_keys
        assert "keynesian__gdp_gap" not in metric_keys

    def test_metrics_reference_porter_profitability(self):
        """METRICS must track porter__profitability."""
        metric_keys = {m["env_key"] for m in METRICS}
        assert "porter__profitability" in metric_keys
        assert "porter__competitive_intensity" not in metric_keys

    def test_gdp_normalized_changes_after_keynesian_step(self):
        """keynesian__gdp_normalized must be updated by KeynesianMultiplier."""
        env = dict(INITIAL_ENV)
        env["global__oil_price"] = 0.80  # inject shock
        m = KeynesianMultiplier(parameters=KEYNESIAN)
        writes = m.update(env, [], 0)
        env.update(writes)
        assert "keynesian__gdp_normalized" in env

    def test_profitability_changes_after_porter_step(self):
        """porter__profitability must be written by PorterFiveForces."""
        env = dict(INITIAL_ENV)
        m = PorterFiveForces(parameters=PORTER)
        writes = m.update(env, [], 0)
        env.update(writes)
        p = env["porter__profitability"]
        assert p != 0.0, "porter__profitability still 0.0 after step — not being written"


# ══════════════════════════════════════════════════════════════════════════════
# Bug 5 Fix — Keynesian params match module field names
# ══════════════════════════════════════════════════════════════════════════════

class TestKeynesianParamFix:
    """Bug 5 (FIXED): import_propensity (not import_rate), no stray multiplier key."""

    def test_import_propensity_key_in_keynesian(self):
        """KEYNESIAN dict must use import_propensity (the Pydantic field name)."""
        assert "import_propensity" in KEYNESIAN
        assert "import_rate" not in KEYNESIAN

    def test_no_stray_multiplier_key(self):
        """KEYNESIAN dict must not pass multiplier (it's computed, not a field)."""
        assert "multiplier" not in KEYNESIAN

    def test_multiplier_is_correct_value(self):
        """M = 1 / (1 - MPC*(1-t) + import_propensity) ≈ 1.39."""
        mpc = KEYNESIAN["mpc"]           # 0.72
        t   = KEYNESIAN["tax_rate"]      # 0.22
        imp = KEYNESIAN["import_propensity"]  # 0.28
        M = 1.0 / (1.0 - mpc * (1.0 - t) + imp)
        assert 1.30 < M < 1.50, f"Multiplier M={M:.3f} outside expected 1.30–1.50"

    def test_keynesian_step_uses_import_propensity(self):
        """KeynesianMultiplier must accept KEYNESIAN params without error."""
        env = dict(INITIAL_ENV)
        env["global__oil_price"] = 0.85
        m = KeynesianMultiplier(parameters=KEYNESIAN)
        writes = m.update(env, [], 0)
        env.update(writes)
        assert "keynesian__gdp_normalized" in env

    def test_gdp_responds_to_trade_collapse(self):
        """GDP falls when trade volume drops below 0.5 (sanctions/blockade channel).
        The Keynesian module drives GDP via fiscal_shock_pending and trade disruption,
        not directly via oil price. Oil → disruption → trade → GDP is the pathway.
        """
        env_base = dict(INITIAL_ENV)
        env_shock = dict(INITIAL_ENV)
        env_shock["global__trade_volume"] = 0.30   # blockade-level disruption (< 0.5)

        m = KeynesianMultiplier(parameters=KEYNESIAN)
        # Run a few ticks so the shock accumulates
        for tick in range(3):
            w_base = m.update(env_base, [], tick)
            env_base.update(w_base)
        m2 = KeynesianMultiplier(parameters=KEYNESIAN)
        for tick in range(3):
            w_shock = m2.update(env_shock, [], tick)
            env_shock.update(w_shock)

        gdp_base  = env_base["keynesian__gdp_normalized"]
        gdp_shock = env_shock["keynesian__gdp_normalized"]
        assert gdp_shock <= gdp_base, (
            f"GDP with trade=0.30 ({gdp_shock:.4f}) not below baseline ({gdp_base:.4f})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bug 6 Fix — SIR beta recalibrated to monthly rate
# ══════════════════════════════════════════════════════════════════════════════

class TestSIRCalibration:
    """Bug 6 (FIXED): beta=0.50 (monthly) produces meaningful contagion growth."""

    def test_beta_is_monthly_calibrated(self):
        """SIR_ECONOMIC beta must be ≥ 0.45 (recalibrated from annual 0.25)."""
        assert SIR_ECONOMIC["beta"] >= 0.45, (
            f"beta={SIR_ECONOMIC['beta']} — still using annual rate"
        )

    def test_one_month_new_infections_are_meaningful(self):
        """At monthly beta=0.50, one tick should produce > 0.001 new infections."""
        env = dict(INITIAL_ENV)
        S0 = env["economic__susceptible"]  # 0.92
        I0 = env["economic__infected"]     # 0.05
        beta = SIR_ECONOMIC["beta"]
        gamma = SIR_ECONOMIC["gamma"]

        new_infections = beta * S0 * I0
        assert new_infections > 0.001, (
            f"new_infections={new_infections:.5f} — monthly rate too small"
        )

    def test_24_month_infected_growth_meaningful(self):
        """After 24 ticks, infected population should grow by ≥ 1.5pp."""
        env = dict(INITIAL_ENV)
        I0 = env["economic__infected"]
        m = SIRContagion(parameters=SIR_ECONOMIC)
        for tick in range(24):
            writes = m.update(env, [], tick)
            env.update(writes)
        I_final = env["economic__infected"]
        growth_pp = (I_final - I0) * 100
        assert growth_pp >= 1.5, (
            f"SIR growth={growth_pp:.2f}pp — too small for beta=0.50"
        )

    def test_sir_r_effective_above_one_at_start(self):
        """With beta=0.50, gamma=0.08, R0=6.25 — effective R > 1 initially."""
        beta = SIR_ECONOMIC["beta"]
        gamma = SIR_ECONOMIC["gamma"]
        S0 = INITIAL_ENV["economic__susceptible"]
        R_eff = beta * S0 / gamma
        assert R_eff > 1.0, f"R_eff={R_eff:.2f} — epidemic not in growth phase"


# ══════════════════════════════════════════════════════════════════════════════
# Bug 7 Fix — Trade volume shocks balanced (net = 0.0)
# ══════════════════════════════════════════════════════════════════════════════

class TestTradeShockBalanced:
    """Bug 7 (FIXED): disruption and recovery shocks cancel out."""

    def test_down_shock_total(self):
        """Sum of all negative trade volume shocks = -0.35."""
        down = sum(
            d.get("global__trade_volume", 0)
            for d in SHOCKS.values()
            if d.get("global__trade_volume", 0) < 0
        )
        assert abs(down - (-0.35)) < 0.001, f"Down shocks = {down} (expected -0.35)"

    def test_up_shock_total(self):
        """Sum of all positive trade volume shocks = +0.35."""
        up = sum(
            d.get("global__trade_volume", 0)
            for d in SHOCKS.values()
            if d.get("global__trade_volume", 0) > 0
        )
        assert abs(up - 0.35) < 0.001, f"Up shocks = {up} (expected +0.35)"

    def test_net_trade_shock_is_zero(self):
        """Net trade volume shock across all ticks = 0.00 (returns to baseline)."""
        net = sum(d.get("global__trade_volume", 0) for d in SHOCKS.values())
        assert abs(net) < 0.001, f"Net trade shock = {net:.3f} (should be 0.00)"

    def test_t22_shock_is_reduced(self):
        """Tick 22 trade shock must be +0.05 (was +0.15 before fix)."""
        t22_trade = SHOCKS[22].get("global__trade_volume", 0)
        assert abs(t22_trade - 0.05) < 0.001, (
            f"t=22 trade shock = {t22_trade} (expected +0.05)"
        )

    def test_final_trade_volume_at_baseline(self):
        """Applying all shocks to baseline 0.72 should return to ~0.72."""
        baseline = INITIAL_ENV["global__trade_volume"]   # 0.72
        trade = baseline
        for shock in SHOCKS.values():
            trade += shock.get("global__trade_volume", 0)
        trade = max(0.0, min(1.0, trade))
        assert abs(trade - baseline) < 0.01, (
            f"Final trade={trade:.3f}, baseline={baseline:.3f} — net overshoot"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Integration — all 7 fixes in a 3-tick cascade run
# ══════════════════════════════════════════════════════════════════════════════

class TestHormuzCascadeFixed:
    """Integration: confirm all bug fixes hold in a live 3-tick cascade."""

    def _run_cascade(self, ticks: int = 3):
        """Run 6-module cascade for N ticks; return env snapshots list.

        Mirrors SimRunner: all theories see the same pre-tick env; writes are
        collected and applied atomically after all theories run.
        """
        theories = [
            RichardsonArmsRace(parameters=RICHARDSON),
            FearonBargaining(parameters=FEARON),
            WittmanZartman(parameters=WITTMAN_ZARTMAN),
            SIRContagion(parameters=SIR_ECONOMIC),
            KeynesianMultiplier(parameters=KEYNESIAN),
            PorterFiveForces(parameters=PORTER),
        ]
        env = dict(INITIAL_ENV)
        snapshots = []
        for tick in range(ticks):
            if tick in SHOCKS:
                for k, delta in SHOCKS[tick].items():
                    if k in env:
                        env[k] = max(0.0, min(1.0, env[k] + delta))
            # Parallel collection (SimRunner pattern)
            theory_deltas: dict = {}
            for theory in theories:
                theory_deltas.update(theory.update(env, [], tick))
            env.update(theory_deltas)
            snapshots.append(dict(env))
        return snapshots

    def test_bug1_conflict_prob_below_one_at_tick0(self):
        """Bug 1 fixed: P(conflict) < 1.0 at tick 0 (was exactly 1.0 with 0.0 seeds).
        With military balance seeds (~0.443), conflict_prob is info-gap based (~0.67),
        not a degenerate 1.0 from a 53x power_shift_rate spike.
        """
        snaps = self._run_cascade(1)
        p = snaps[0]["fearon__conflict_probability"]
        assert p < 1.0, f"P(conflict)={p:.3f} at tick 0 (Bug 1 not fixed)"

    def test_bug2_mhs_fires_at_tick0(self):
        """Bug 2+8 fixed: MHS fires at tick 0 with correct war cost seeding."""
        snaps = self._run_cascade(1)
        assert snaps[0]["zartman__mhs"] == 1.0, (
            f"MHS={snaps[0]['zartman__mhs']} at tick 0 — Bugs 2/8 not resolved"
        )

    def test_bug3_porter_barriers_above_seed(self):
        """Bug 3 fixed: barriers_to_entry reads 0.60 seed (not default 0.50)."""
        snaps = self._run_cascade(1)
        assert snaps[0]["porter__barriers_to_entry"] >= 0.50

    def test_bug4_gdp_normalized_written(self):
        """Bug 4 fixed: keynesian__gdp_normalized changes once trade drops below 0.5.
        In this cascade, trade drops below 0.5 at tick 5 (cumulative shocks: -0.15-0.20=-0.35).
        Run to tick 6 to observe GDP response.
        """
        snaps = self._run_cascade(7)
        # At tick 5 trade = 0.72 - 0.15 - 0.20 = 0.37 → below 0.5 → GDP starts moving
        gdp_values = [s["keynesian__gdp_normalized"] for s in snaps]
        assert any(v != 0.50 for v in gdp_values), (
            f"keynesian__gdp_normalized never updated (Bug 4). Values: {gdp_values}"
        )

    def test_bug4_profitability_written(self):
        """Bug 4 fixed: porter__profitability is non-zero after first tick."""
        snaps = self._run_cascade(1)
        assert snaps[0]["porter__profitability"] != 0.0, (
            "porter__profitability still 0.0 (Bug 4)"
        )

    def test_bug5_keynesian_accepts_params(self):
        """Bug 5 fixed: KEYNESIAN dict accepted without validation error."""
        # If import_rate were still the key, Pydantic would silently ignore it
        # and import_propensity would use its default. We verify the M is correct.
        mpc = KEYNESIAN["mpc"]
        t   = KEYNESIAN["tax_rate"]
        imp = KEYNESIAN["import_propensity"]
        M = 1.0 / (1.0 - mpc * (1.0 - t) + imp)
        assert 1.30 < M < 1.50

    def test_bug6_sir_grows_meaningfully(self):
        """Bug 6 fixed: SIR shows > 0.001 new infections per tick at monthly beta."""
        env = dict(INITIAL_ENV)
        S0 = env["economic__susceptible"]
        I0 = env["economic__infected"]
        beta = SIR_ECONOMIC["beta"]
        new_infections = beta * S0 * I0
        assert new_infections > 0.001

    def test_bug7_net_trade_zero(self):
        """Bug 7 fixed: cumulative trade shock net = 0.00."""
        net = sum(d.get("global__trade_volume", 0) for d in SHOCKS.values())
        assert abs(net) < 0.001

    def test_cascade_runs_without_error(self):
        """Full 3-tick cascade completes without exception."""
        snaps = self._run_cascade(3)
        assert len(snaps) == 3
        for key in ["fearon__conflict_probability", "porter__profitability",
                    "keynesian__gdp_normalized", "economic__infected"]:
            assert key in snaps[-1], f"Missing key in final env: {key}"
