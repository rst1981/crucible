"""
scenarios/estee-lauder/run_simulation.py

Estée Lauder Stock Decline Simulation — v2 (9-module cascade + Monte Carlo)
-----------------------------------------------------------------------------
Tick unit : day
Tick 1    = Feb 25, 2026  (Iran war onset; EL ~$104 after Q2 earnings selloff)
Tick 28   = March 24, 2026 (Puig acquisition announcement; EL -10.1% on day)
Tick 30   = March 26, 2026 (today; EL ~$71.60)
Ticks 31–44 = 14-day forward projection

Nine theory modules in cascade:
  [sir_contagion]           priority 0 — market panic transmission
  [keynesian_multiplier]    priority 0 — demand destruction channel
  [opinion_dynamics]        priority 1 — investor sentiment (stock price proxy)
  [porter_five_forces]      priority 1 — industry margin compression
  [regulatory_shock]        priority 2 — tariff + petrochemical input costs
  [acquirer_discount]       priority 2 — Puig M&A announcement AR (Roll 1986)  ← NEW
  [brand_equity_decay]      priority 2 — dupe-culture price premium erosion     ← NEW
  [schumpeter_disruption]   priority 3 — structural market share erosion
  [event_study]             priority 4 — CAPM abnormal return decomposition     ← NEW

Monte Carlo: 300 runs with parameter perturbation + forward scenario sampling.
  Base (60%): Puig uncertainty persists, no resolution
  Bull (25%): Puig talks collapse ~tick 34, partial sentiment recovery
  Bear (15%): Expensive Puig terms confirmed + Iran escalation
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core.theories  # noqa: F401 — auto-discovers all theory modules
from core.spec import (
    OutcomeMetricSpec,
    SimSpec,
    TheoryRef,
    TimeframeSpec,
    UncertaintySpec,
)
from core.sim_runner import SimRunner

TOTAL_TICKS = 44
N_MC = 300

# ── Forward scenario shocks (ticks 31–44 only) ──────────────────────────────

_BULL_SHOCKS: dict[int, dict[str, float]] = {
    # Puig deal collapse confirmed ~tick 34 — relief rally
    34: {
        "investor_sentiment__mean":        +0.15,
        "investor_sentiment__polarization": -0.12,
        "global__trade_volume":            +0.04,
        "global__urgency_factor":          -0.06,
        "el_puig__synergy_realized":       +0.40,
    },
}

_BEAR_SHOCKS: dict[int, dict[str, float]] = {
    # Expensive Puig terms confirmed
    34: {
        "investor_sentiment__mean":        -0.10,
        "investor_sentiment__polarization": +0.06,
        "regulation__shock_magnitude":     +0.04,
        "global__urgency_factor":          +0.04,
    },
    # Iran escalation — Hormuz partial blockage
    36: {
        "global__trade_volume":            -0.06,
        "global__energy_cost":             +0.06,
        "global__urgency_factor":          +0.04,
        "keynesian__fiscal_shock_pending": -0.04,
    },
}


# ── Base shock schedule ──────────────────────────────────────────────────────

_BASE_SHOCKS: dict[int, dict[str, float]] = {
    # ── TICK 1: Iran war onset ────────────────────────────────────────────────
    1: {
        "global__trade_volume":             -0.12,
        "global__urgency_factor":           +0.28,
        "global__energy_cost":              +0.18,
        "global__market_stress":            +0.25,
        "keynesian__fiscal_shock_pending":  -0.12,
        "investor_sentiment__media_bias":   -0.12,
        "global__market_return":            -0.0625,  # market -2.5% on war onset
        "el_30day__actual_return":          -0.1250,  # EL -5% on war onset
        "el_30day__event_active":           +1.0,
    },
    # ── TICK 2: reset daily return signals to neutral ─────────────────────────
    2: {
        "global__market_return":            +0.0625,
        "el_30day__actual_return":          +0.1250,
        "el_30day__event_active":           -1.0,
    },
    # ── TICK 3: Petrochemical cascade + shipping rerouting ────────────────────
    3: {
        "regulation__shock_magnitude":      +0.18,
        "global__trade_volume":             -0.04,
        "porter__supplier_power":           +0.08,
        "global__energy_cost":              +0.05,
        "global__competitive_pressure":     +0.04,
        "global__market_stress":            +0.08,
    },
    # ── TICK 7: Tariff escalation crystallises ────────────────────────────────
    7: {
        "regulation__shock_magnitude":      +0.14,
        "keynesian__fiscal_shock_pending":  -0.08,
        "investor_sentiment__media_bias":   -0.08,
        "investor_sentiment__polarization": +0.06,
        "global__competitive_pressure":     +0.03,
        "global__market_return":            -0.0375,  # market -1.5% on tariff day
        "el_30day__actual_return":          -0.1000,  # EL -4% on tariff day
        "el_30day__event_active":           +1.0,
    },
    # ── TICK 8: reset daily return signals ───────────────────────────────────
    8: {
        "global__market_return":            +0.0375,
        "el_30day__actual_return":          +0.1000,
        "el_30day__event_active":           -1.0,
    },
    # ── TICK 12: China travel retail confirmed depressed ──────────────────────
    12: {
        "porter__substitute_threat":        +0.04,
        "porter__rivalry_intensity":        +0.03,
        "investor_sentiment__media_bias":   -0.04,
        "global__competitive_pressure":     +0.02,
    },
    # ── TICK 18: Wholesale destocking / bullwhip effect ───────────────────────
    18: {
        "keynesian__fiscal_shock_pending":  -0.06,
        "porter__buyer_power":              +0.05,
        "regulation__shock_magnitude":      +0.06,
        "global__competitive_pressure":     +0.02,
    },
    # ── TICK 28: Puig acquisition confirmed ──────────────────────────────────
    28: {
        "investor_sentiment__mean":         -0.18,
        "investor_sentiment__polarization": +0.14,
        "investor_sentiment__media_bias":   -0.12,
        "global__urgency_factor":           +0.08,
        "global__market_stress":            +0.10,
        "el_puig__deal_announced":          +1.0,    # triggers acquirer_discount module
        "global__market_return":            -0.0500,  # market -2% on Puig day
        "el_30day__actual_return":          -0.2525,  # EL -10.1% on Puig day
        "el_30day__event_active":           +1.0,
    },
    # ── TICK 29: reset daily return signals ──────────────────────────────────
    29: {
        "global__market_return":            +0.0500,
        "el_30day__actual_return":          +0.2525,
        "el_30day__event_active":           -1.0,
    },
    # ── TICK 32: Puig uncertainty continues ──────────────────────────────────
    32: {
        "investor_sentiment__polarization": +0.06,
        "investor_sentiment__media_bias":   -0.04,
    },
    # ── TICK 38: No macro recovery catalyst ──────────────────────────────────
    38: {
        "keynesian__fiscal_shock_pending":  -0.04,
        "global__urgency_factor":           +0.03,
    },
}

# ── Base initial environment ─────────────────────────────────────────────────

_BASE_ENV: dict[str, float] = {
    # Global cross-theory signals
    "global__trade_volume":              0.52,
    "global__urgency_factor":            0.28,
    "global__energy_cost":               0.55,
    "global__market_stress":             0.15,
    "global__competitive_pressure":      0.40,
    "global__market_return":             0.50,

    # SIR contagion
    "market_selloff__susceptible":       0.93,
    "market_selloff__infected":          0.07,
    "market_selloff__recovered":         0.00,
    "market_selloff__r_effective":       0.00,
    "market_selloff__active_contagion":  0.00,

    # Keynesian multiplier
    "keynesian__gdp_normalized":         0.50,
    "keynesian__fiscal_shock_pending":   0.50,
    "keynesian__unemployment":           0.042,
    "keynesian__multiplier":             0.00,
    "keynesian__mpc":                    0.72,

    # Opinion dynamics (investor sentiment)
    "investor_sentiment__mean":          0.52,
    "investor_sentiment__polarization":  0.32,
    "investor_sentiment__consensus":     0.68,
    "investor_sentiment__media_bias":    0.44,

    # Porter five forces
    "porter__barriers_to_entry":         0.55,
    "porter__supplier_power":            0.30,
    "porter__buyer_power":               0.42,
    "porter__substitute_threat":         0.45,
    "porter__rivalry_intensity":         0.50,
    "porter__capacity_investment":       0.00,
    "porter__profitability":             0.00,

    # Regulatory shock
    "regulation__shock_magnitude":       0.28,
    "regulation__adaptation_level":      0.05,
    "regulation__compliance_cost":       0.00,
    "regulation__market_exit_risk":      0.00,
    "regulation__competitive_advantage": 0.00,

    # Acquirer discount (Puig deal) — new
    "el_puig__deal_announced":           0.00,
    "el_puig__synergy_realized":         0.00,
    "el_puig__integration_cost":         0.00,
    "el_puig__abnormal_return":          0.50,
    "el_puig__cumulative_ar":            0.50,

    # Brand equity decay — new
    "el_brand__brand_equity":            0.72,
    "el_brand__price_premium":           0.302,  # 0.72 × 0.42
    "el_brand__awareness":               0.85,
    "el_brand__loyalty":                 0.64,
    "el_brand__marketing_investment":    0.08,   # cost-cutting mode
    "el_brand__media_negative":          0.35,

    # Schumpeter disruption
    "schumpeter__incumbent_share":       0.72,
    "schumpeter__innovator_share":       0.18,
    "schumpeter__rd_investment":         0.08,
    "schumpeter__creative_destruction":  0.00,
    "schumpeter__market_renewal":        0.00,

    # Event study — new
    "el_30day__actual_return":           0.50,
    "el_30day__event_active":            0.00,
    "el_30day__expected_return":         0.50,
    "el_30day__abnormal_return":         0.50,
    "el_30day__cumulative_ar":           0.50,
}


# ── Theory builder ────────────────────────────────────────────────────────────

def _make_theories(rng: np.random.Generator | None = None, pct: float = 0.0) -> list[TheoryRef]:
    """Build theory list, optionally perturbing parameters by ±pct (fraction)."""

    def p(base: float, lo: float = 0.001, hi: float = 10.0) -> float:
        if rng is None or pct == 0.0:
            return base
        # Auto-cap at 1.0 when base is a probability/fraction parameter
        hi_actual = min(hi, 1.0) if base <= 1.0 else hi
        return float(np.clip(base * (1.0 + rng.normal(0, pct)), lo, hi_actual))

    def ps(base: float) -> float:  # perturb ±pct, clamped to [0,1]
        return float(np.clip(p(base, 0.0, 1.0), 0.0, 1.0))

    return [
        # ── Priority 0: macro / contagion ────────────────────────────────────
        TheoryRef(
            theory_id="sir_contagion", priority=0,
            parameters={
                "beta":               p(0.35),
                "gamma":              p(0.12),
                "initial_infected":   0.07,
                "trade_amplification": p(0.55),
                "contagion_id":       "market_selloff",
            },
        ),
        TheoryRef(
            theory_id="keynesian_multiplier", priority=0,
            parameters={
                "mpc":                p(0.72, 0.30, 0.95),
                "tax_rate":           0.28,
                "import_propensity":  0.18,
                "decay_rate":         p(0.15),
                "okun_coefficient":   -0.50,
                "sanctions_exposure": p(0.80),
                "tick_unit":          "day",
                "trade_recovery_rate": p(0.004, 0.0001, 0.05),
            },
        ),

        # ── Priority 1: sentiment / competitive structure ─────────────────────
        TheoryRef(
            theory_id="opinion_dynamics", priority=1,
            parameters={
                "epsilon":                    p(0.25),
                "mu":                         0.20,
                "noise_sigma":                0.01,
                "media_sensitivity":          p(0.70),
                "urgency_polarization_factor": p(0.40),
                "domain_id":                  "investor_sentiment",
            },
        ),
        TheoryRef(
            theory_id="porter_five_forces", priority=1,
            parameters={
                "w_barriers":                 0.15,
                "w_supplier":                 0.05,
                "w_buyer":                    ps(0.25),
                "w_substitute":               ps(0.35),
                "w_rivalry":                  ps(0.25),
                "base_margin":                0.50,
                "entry_erosion_rate":         0.02,
                "rivalry_growth_sensitivity": 0.25,
            },
        ),

        # ── Priority 2: shocks + new financial models ─────────────────────────
        TheoryRef(
            theory_id="regulatory_shock", priority=2,
            parameters={
                "cost_sensitivity":            p(0.60),
                "adaptation_rate":             p(0.08),
                "firm_resilience":             0.20,
                "incumbent_advantage_factor":  0.50,
                "gdp_adaptation_sensitivity":  0.40,
                "regulation_id":               "regulation",
            },
        ),
        TheoryRef(
            theory_id="acquirer_discount", priority=2,
            parameters={
                "deal_premium":                        p(1.30, 1.05, 1.80),
                "deal_size_ratio":                     p(0.355, 0.1, 1.0),
                "hubris_factor":                       ps(0.80),
                "synergy_realization_probability":     ps(0.40),
                "integration_complexity":              ps(0.68),
                "integration_completion_rate":         p(0.25, 0.05, 0.80),
                "tick_unit":                           "day",
                "acquirer_id":                         "el_puig",
            },
        ),
        TheoryRef(
            theory_id="brand_equity_decay", priority=2,
            parameters={
                "initial_brand_equity":                0.72,
                "initial_awareness":                   0.85,
                "initial_loyalty":                     0.64,
                "decay_coefficient":                   p(0.12, 0.01, 0.50),
                "competitive_pressure_sensitivity":    p(0.65),
                "media_erosion_rate":                  p(0.35),
                "max_price_premium_fraction":          0.42,
                "marketing_investment_sensitivity":    p(0.45),
                "tick_unit":                           "day",
                "brand_id":                            "el_brand",
            },
        ),

        # ── Priority 3: structural disruption ─────────────────────────────────
        TheoryRef(
            theory_id="schumpeter_disruption", priority=3,
            parameters={
                "incumbent_inertia":     0.04,
                "disruption_coefficient": p(0.18),
                "innovator_growth_rate": p(0.22),
                "incumbent_defense":     0.08,
                "obsolescence_rate":     0.03,
                "innovation_id":         "schumpeter",
                "tick_unit":             "day",
            },
        ),

        # ── Priority 4: post-processing / decomposition ───────────────────────
        TheoryRef(
            theory_id="event_study", priority=4,
            parameters={
                "beta_market":    p(1.15, 0.3, 3.0),
                "risk_free_rate": 0.045,
                "alpha":          0.0,
                "tick_unit":      "day",
                "event_id":       "el_30day",
            },
        ),
    ]


# ── Spec builder ─────────────────────────────────────────────────────────────

def _make_spec(
    theories: list[TheoryRef],
    scenario: str = "base",
    shock_noise_rng: np.random.Generator | None = None,
    obs_noise: float = 0.01,
) -> SimSpec:
    """Build a SimSpec for one run. scenario ∈ {'base', 'bull', 'bear'}."""

    def jitter(v: float) -> float:
        if shock_noise_rng is None:
            return v
        return float(v * (1.0 + shock_noise_rng.normal(0, 0.20)))

    # Build shock schedule: jitter each shock value, then add scenario shocks
    scheduled: dict[int, dict[str, float]] = {}
    for tick, shocks in _BASE_SHOCKS.items():
        scheduled[tick] = {k: jitter(v) for k, v in shocks.items()}

    extra = _BULL_SHOCKS if scenario == "bull" else _BEAR_SHOCKS if scenario == "bear" else {}
    for tick, shocks in extra.items():
        existing = scheduled.get(tick, {})
        scheduled[tick] = {**existing, **{k: jitter(v) for k, v in shocks.items()}}

    return SimSpec(
        name="Estée Lauder — 30-Day Decline & 14-Day Projection (v2)",
        description=(
            "9-module cascade: sir_contagion, keynesian_multiplier, opinion_dynamics, "
            "porter_five_forces, regulatory_shock, acquirer_discount, brand_equity_decay, "
            "schumpeter_disruption, event_study."
        ),
        domain="market",
        theories=theories,
        timeframe=TimeframeSpec(
            total_ticks=TOTAL_TICKS,
            tick_unit="day",
            start_date="2026-02-25",
        ),
        initial_environment=deepcopy(_BASE_ENV),
        uncertainty=UncertaintySpec(
            observation_noise_sigma=obs_noise,
            shock_probability=0.00,
            shock_magnitude=0.0,
            scheduled_shocks=scheduled,
        ),
        metrics=[
            OutcomeMetricSpec(name="investor_sentiment_mean",
                              env_key="investor_sentiment__mean",
                              description="Stock price direction proxy"),
            OutcomeMetricSpec(name="investor_sentiment_polarization",
                              env_key="investor_sentiment__polarization",
                              description="Analyst divergence / implied vol proxy"),
            OutcomeMetricSpec(name="keynesian_gdp",
                              env_key="keynesian__gdp_normalized",
                              description="Macro demand signal"),
            OutcomeMetricSpec(name="market_selloff_infected",
                              env_key="market_selloff__infected",
                              description="Market contagion — fraction infected"),
            OutcomeMetricSpec(name="regulation_compliance_cost",
                              env_key="regulation__compliance_cost",
                              description="Tariff + petrochem margin pressure"),
            OutcomeMetricSpec(name="porter_profitability",
                              env_key="porter__profitability",
                              description="Industry profitability index"),
            OutcomeMetricSpec(name="schumpeter_creative_destruction",
                              env_key="schumpeter__creative_destruction",
                              description="Dupe/masstige disruption intensity"),
            OutcomeMetricSpec(name="schumpeter_incumbent_share",
                              env_key="schumpeter__incumbent_share",
                              description="EL / prestige cohort market share"),
            OutcomeMetricSpec(name="global_trade_volume",
                              env_key="global__trade_volume",
                              description="Hormuz + Red Sea shipping disruption"),
            OutcomeMetricSpec(name="global_energy_cost",
                              env_key="global__energy_cost",
                              description="Energy cost index (oil spike)"),
            OutcomeMetricSpec(name="regulation_shock_magnitude",
                              env_key="regulation__shock_magnitude",
                              description="Combined tariff + petrochem shock"),
            # ── New module metrics ──────────────────────────────────────────
            OutcomeMetricSpec(name="el_puig_cumulative_ar",
                              env_key="el_puig__cumulative_ar",
                              description="Puig deal cumulative abnormal return (Roll 1986)"),
            OutcomeMetricSpec(name="el_puig_integration_cost",
                              env_key="el_puig__integration_cost",
                              description="Post-Puig integration cost burden"),
            OutcomeMetricSpec(name="el_brand_equity",
                              env_key="el_brand__brand_equity",
                              description="EL brand equity stock (Keller 1993)"),
            OutcomeMetricSpec(name="el_brand_price_premium",
                              env_key="el_brand__price_premium",
                              description="Willingness-to-pay premium vs. mass"),
            OutcomeMetricSpec(name="el_brand_loyalty",
                              env_key="el_brand__loyalty",
                              description="Consumer loyalty / repeat purchase rate"),
            OutcomeMetricSpec(name="el_30day_cumulative_ar",
                              env_key="el_30day__cumulative_ar",
                              description="Total EL CAR — event-driven abnormal return"),
            OutcomeMetricSpec(name="el_30day_abnormal_return",
                              env_key="el_30day__abnormal_return",
                              description="Daily AR vs. CAPM (MacKinlay 1997)"),
        ],
    )


# ── Single run ────────────────────────────────────────────────────────────────

def _run_once(spec: SimSpec, seed: int) -> dict[str, list[float]]:
    """Run one sim; return {metric_name: [value_per_tick]}."""
    runner = SimRunner(spec, rng_seed=seed)
    runner.setup()
    runner.run()
    series: dict[str, list[float]] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.name, []).append(rec.value)
    return series


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def run_monte_carlo(n: int = N_MC, master_seed: int = 0) -> dict[str, Any]:
    """
    Run N simulations with:
    - Perturbed model parameters (±15% normal noise on key params)
    - ±20% jitter on shock magnitudes
    - Forward scenario sampling: base 60%, bull 25%, bear 15%

    Returns percentile bands per metric per tick.
    """
    master_rng = np.random.default_rng(master_seed)
    scenario_thresholds = (0.60, 0.85)  # base < 0.60, bull < 0.85, bear otherwise

    # Collect all runs: {metric: array[run, tick]}
    all_runs: dict[str, list[list[float]]] = {}
    scenario_counts = {"base": 0, "bull": 0, "bear": 0}

    print(f"Running Monte Carlo ({n} simulations)...")
    for i in range(n):
        run_rng = np.random.default_rng(master_rng.integers(0, 2**31))

        r = run_rng.random()
        scenario = "base" if r < scenario_thresholds[0] else ("bull" if r < scenario_thresholds[1] else "bear")
        scenario_counts[scenario] += 1

        theories = _make_theories(rng=run_rng, pct=0.15)
        spec = _make_spec(
            theories=theories,
            scenario=scenario,
            shock_noise_rng=run_rng,
            obs_noise=0.015,
        )
        series = _run_once(spec, seed=int(run_rng.integers(0, 2**31)))

        for metric, vals in series.items():
            all_runs.setdefault(metric, []).append(vals)

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{n} complete...")

    print(f"MC complete. Scenarios: {scenario_counts}")

    # Compute percentile bands
    percentiles = [5, 25, 50, 75, 95]
    bands: dict[str, dict[str, list[float]]] = {}
    for metric, runs in all_runs.items():
        arr = np.array(runs)  # shape: (n_runs, n_ticks)
        bands[metric] = {
            f"p{pct}": [round(float(v), 4) for v in np.percentile(arr, pct, axis=0)]
            for pct in percentiles
        }
        bands[metric]["mean"] = [round(float(v), 4) for v in arr.mean(axis=0)]

    return {
        "bands": bands,
        "scenario_counts": scenario_counts,
        "n_runs": n,
    }


# ── Deterministic run ─────────────────────────────────────────────────────────

def run_deterministic() -> dict:
    theories = _make_theories()
    spec = _make_spec(theories, scenario="base", obs_noise=0.01)
    runner = SimRunner(spec, rng_seed=42)
    runner.setup()
    runner.run()

    series: dict[str, list] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.name, []).append({"tick": rec.tick, "value": round(rec.value, 4)})

    final_env = {k: round(v, 4) for k, v in runner.get_current_env().items()}

    key_ticks = [0, 1, 3, 7, 12, 18, 28, 29, 30, 32, 38, 44]
    snap_envs: dict[int, dict] = {}
    for snap in runner.snapshots:
        if snap.tick in key_ticks:
            snap_envs[snap.tick] = {k: round(v, 4) for k, v in snap.env.items()}

    return {"series": series, "final_env": final_env, "snapshots": snap_envs}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running Estée Lauder simulation (v2 — 9 modules)...")

    det = run_deterministic()
    mc  = run_monte_carlo(n=N_MC, master_seed=0)

    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump({"deterministic": det, "monte_carlo": mc}, f, indent=2)
    print(f"Results written to {out_path}")

    # ── Quick stdout summary ──────────────────────────────────────────────────
    series = det["series"]
    mc_bands = mc["bands"]

    print("\n── Investor Sentiment (stock price proxy) ─────────────────────")
    for r in series.get("investor_sentiment_mean", []):
        if r["tick"] in (0, 1, 7, 12, 18, 28, 30, 38, 44):
            p50 = mc_bands.get("investor_sentiment_mean", {}).get("p50", [])
            p50_val = f"  MC_p50={p50[r['tick']]:.3f}" if r["tick"] < len(p50) else ""
            label = ""
            if r["tick"] == 1:   label = " ← Iran war"
            if r["tick"] == 28:  label = " ← PUIG announcement"
            if r["tick"] == 30:  label = " ← today"
            if r["tick"] == 44:  label = " ← projection end"
            bar = "█" * int(r["value"] * 40)
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}{p50_val} | {bar}{label}")

    print("\n── Acquirer Discount — Puig CAR (Roll 1986) ────────────────────")
    for r in series.get("el_puig_cumulative_ar", []):
        if r["tick"] in (27, 28, 29, 30, 35, 44):
            raw_pct = (r["value"] - 0.5) * 40
            print(f"  Day {r['tick']:2d} | norm={r['value']:.3f} | AR={raw_pct:+.1f}%")

    print("\n── Brand Equity Decay (Keller 1993) ────────────────────────────")
    for r in series.get("el_brand_equity", []):
        if r["tick"] in (0, 7, 14, 21, 28, 30, 44):
            print(f"  Day {r['tick']:2d} | equity={r['value']:.3f}")

    print("\n── Event Study CAR — CAPM Abnormal Return (MacKinlay 1997) ─────")
    for r in series.get("el_30day_cumulative_ar", []):
        if r["tick"] in (0, 1, 2, 7, 8, 28, 29, 30, 44):
            raw_pct = (r["value"] - 0.5) * 40
            print(f"  Day {r['tick']:2d} | CAR={raw_pct:+.1f}%")

    print("\n── Monte Carlo Forward Distribution (Day 44) ───────────────────")
    for metric in ("investor_sentiment_mean", "keynesian_gdp", "el_brand_equity"):
        b = mc_bands.get(metric, {})
        if b:
            last = len(b.get("p50", [0])) - 1
            p5, p25, p50, p75, p95 = (b.get(f"p{p}", [0])[last]
                                       for p in (5, 25, 50, 75, 95))
            print(f"  {metric:<35} p5={p5:.3f} p25={p25:.3f} p50={p50:.3f} p75={p75:.3f} p95={p95:.3f}")

    print("\nDone.")
