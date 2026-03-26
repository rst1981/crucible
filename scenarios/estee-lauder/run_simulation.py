"""
scenarios/estee-lauder/run_simulation.py

Estée Lauder Stock Decline Simulation
--------------------------------------
Tick unit : day
Tick 1    = Feb 25, 2026  (Iran war onset; EL ~$104 after Q2 earnings selloff)
Tick 28   = March 24, 2026 (Puig acquisition announcement; EL -10.1% on day)
Tick 30   = March 26, 2026 (today; EL ~$71.60)
Ticks 31–44 = 14-day forward projection

Six theory modules wired in cascade:
  sir_contagion → keynesian_multiplier → opinion_dynamics
                → porter_five_forces
                → regulatory_shock
                → schumpeter_disruption

Iran war channel is modelled through:
  - global__trade_volume shock (Hormuz + Red Sea shipping disruption)
  - global__energy_cost shock (oil price spike → petrochemical COGS)
  - keynesian__fiscal_shock_pending (energy inflation → consumer demand contraction)
  - regulatory__shock_magnitude amplification (petrochemical input cost pass-through)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ── repo root on path ───────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core.theories  # noqa: F401 — auto-discovers and registers all theory modules
from core.spec import (
    OutcomeMetricSpec,
    SimSpec,
    TheoryRef,
    TimeframeSpec,
    UncertaintySpec,
)
from core.sim_runner import SimRunner


# ── helpers ─────────────────────────────────────────────────────────────────

def encode_shock(signed_shock: float) -> float:
    """Encode a signed shock [-1, 1] into [0, 1] storage for keynesian__fiscal_shock_pending."""
    return max(0.0, min(1.0, 0.5 + signed_shock / 2.0))


def decode_pending(stored: float) -> float:
    """Decode stored keynesian__fiscal_shock_pending back to signed shock."""
    return (stored - 0.5) * 2.0


# ── SimSpec ─────────────────────────────────────────────────────────────────

TOTAL_TICKS = 44  # 30 historical + 14 forward

spec = SimSpec(
    name="Estée Lauder — 30-Day Decline & 14-Day Projection",
    description=(
        "Multi-theory cascade model explaining EL's ~40% stock decline from Feb–March 2026. "
        "Shocks: Iran war (Feb 25), US tariff escalation, Puig M&A announcement (March 23-24). "
        "Structural: dupe/masstige disruption, China travel retail headwind."
    ),
    domain="market",
    theories=[
        # Priority 0 — runs first: macro/contagion layer
        TheoryRef(
            theory_id="sir_contagion",
            priority=0,
            parameters={
                "beta": 0.35,          # elevated: VIX 25-29, war onset
                "gamma": 0.12,         # slow recovery: structural headwinds
                "initial_infected": 0.07,
                "trade_amplification": 0.55,
                "contagion_id": "market_selloff",
            },
        ),
        TheoryRef(
            theory_id="keynesian_multiplier",
            priority=0,
            parameters={
                "mpc": 0.72,
                "tax_rate": 0.28,
                "import_propensity": 0.18,
                "decay_rate": 0.15,
                "okun_coefficient": -0.50,
                "sanctions_exposure": 0.80,
                "tick_unit": "day",           # FIX: scale ODE to daily granularity
                "trade_recovery_rate": 0.004, # slow mean-reversion (~125 days to full recovery)
            },
        ),

        # Priority 1 — reads GDP + contagion outputs
        TheoryRef(
            theory_id="opinion_dynamics",
            priority=1,
            parameters={
                "epsilon": 0.25,           # bounded-confidence: 9B/12H analyst split
                "mu": 0.20,
                "noise_sigma": 0.01,
                "media_sensitivity": 0.70, # high: Bloomberg saturation, GDELT tone -12 to -18
                "urgency_polarization_factor": 0.40,
                "domain_id": "investor_sentiment",
            },
        ),
        TheoryRef(
            theory_id="porter_five_forces",
            priority=1,
            parameters={
                "w_barriers":  0.15,
                "w_supplier":  0.05,
                "w_buyer":     0.25,   # masstige fastest-growing; trade-down visible
                "w_substitute": 0.35,  # dupe penetration 27% US
                "w_rivalry":   0.25,   # ELF/NYX/Rare Beauty share gains
                "base_margin": 0.50,
                "entry_erosion_rate": 0.02,
                "rivalry_growth_sensitivity": 0.25,
            },
        ),

        # Priority 2 — reads Porter barriers + GDP
        TheoryRef(
            theory_id="regulatory_shock",
            priority=2,
            parameters={
                "cost_sensitivity": 0.60,   # $100M H2 FY2026 tariff = 2.5% margin
                "adaptation_rate": 0.08,    # 4-6 quarters to fully adapt supply chain
                "firm_resilience": 0.20,
                "incumbent_advantage_factor": 0.50,
                "gdp_adaptation_sensitivity": 0.40,
                "regulation_id": "regulation",
            },
        ),

        # Priority 3 — structural layer; reads GDP + profitability
        TheoryRef(
            theory_id="schumpeter_disruption",
            priority=3,
            parameters={
                "incumbent_inertia":    0.04,
                "disruption_coefficient": 0.18,
                "innovator_growth_rate": 0.22,
                "incumbent_defense":    0.08,
                "obsolescence_rate":    0.03,
                "innovation_id": "schumpeter",
                "tick_unit": "day",             # FIX: scale ODE to daily granularity
            },
        ),
    ],

    timeframe=TimeframeSpec(
        total_ticks=TOTAL_TICKS,
        tick_unit="day",
        start_date="2026-02-25",
    ),

    # ── Initial environment (Day 0 = Feb 25, 2026) ───────────────────────
    # EL at ~$104, already -14% from $121 peak after Q2 earnings selloff
    # Iran war starts today; market stress beginning to build
    initial_environment={
        # Global cross-theory signals
        "global__trade_volume":      0.52,   # near-normal; war not yet priced in
        "global__urgency_factor":    0.28,   # moderate: existing uncertainty, now war onset
        "global__energy_cost":       0.55,   # slightly elevated pre-war

        # SIR contagion (market selloff)
        "market_selloff__susceptible":       0.93,
        "market_selloff__infected":          0.07,  # initial_infected
        "market_selloff__recovered":         0.00,
        "market_selloff__r_effective":       0.00,
        "market_selloff__active_contagion":  0.00,

        # Keynesian multiplier
        "keynesian__gdp_normalized":         0.50,  # at baseline (US GDP growth 2.79%)
        "keynesian__fiscal_shock_pending":   0.50,  # encoded 0.0 — no pending shock yet
        "keynesian__unemployment":           0.042, # US unemployment ~4.2%
        "keynesian__multiplier":             0.00,
        "keynesian__mpc":                    0.72,

        # Opinion dynamics (investor sentiment → stock price proxy)
        "investor_sentiment__mean":          0.52,  # slightly bearish post-Q2-earnings-selloff
        "investor_sentiment__polarization":  0.32,  # moderate analyst divergence
        "investor_sentiment__consensus":     0.68,
        "investor_sentiment__media_bias":    0.44,  # slightly negative media tone

        # Porter five forces (prestige beauty competitive structure)
        "porter__barriers_to_entry":    0.55,  # still meaningful barriers for true prestige
        "porter__supplier_power":       0.30,  # EL has scale leverage
        "porter__buyer_power":          0.42,  # trade-down already visible pre-war
        "porter__substitute_threat":    0.45,  # elevated: 27% dupe penetration
        "porter__rivalry_intensity":    0.50,  # ELF/NYX/Rare Beauty growing fast
        "porter__capacity_investment":  0.00,
        "porter__profitability":        0.00,

        # Regulatory shock (tariff + petrochemical input costs)
        "regulation__shock_magnitude":      0.28,  # pre-existing tariff uncertainty
        "regulation__adaptation_level":     0.05,  # minor early adaptation started
        "regulation__compliance_cost":      0.00,
        "regulation__market_exit_risk":     0.00,
        "regulation__competitive_advantage": 0.00,

        # Schumpeter disruption (mass/dupe vs prestige incumbent)
        "schumpeter__incumbent_share":      0.72,  # EL + prestige cohort holding 72%
        "schumpeter__innovator_share":      0.18,  # mass/dupe brands at 18%
        "schumpeter__rd_investment":        0.08,  # low: EL in cost-cut mode
        "schumpeter__creative_destruction": 0.00,
        "schumpeter__market_renewal":       0.00,
    },

    # ── Scheduled shocks ─────────────────────────────────────────────────
    uncertainty=UncertaintySpec(
        observation_noise_sigma=0.01,
        shock_probability=0.00,   # disable random shocks — deterministic run
        shock_magnitude=0.0,
        scheduled_shocks={
            # ── TICK 1: Iran war onset ──────────────────────────────────
            # Strait of Hormuz threat + Red Sea rerouting fully activates
            # Oil spikes from ~$75 → ~$95-100/bbl (+25-30%)
            # Shipping insurance war-risk premiums triple
            # Petrochemical feedstock costs begin rising
            1: {
                "global__trade_volume":          -0.12,  # Hormuz + Red Sea disruption
                "global__urgency_factor":        +0.28,  # geopolitical emergency declared
                "global__energy_cost":           +0.18,  # oil +25%; energy markets spike
                "keynesian__fiscal_shock_pending": -0.12, # energy inflation → demand contraction
                "investor_sentiment__media_bias": -0.12,  # war coverage dominates
            },

            # ── TICK 3: Petrochemical cascade reaches beauty supply chain ──
            # Ethylene, propylene, surfactant precursors up 15-25%
            # EL's packaging (PE, PP, PET), emollients (mineral oil, silicones),
            # surfactants (SLS, PEG) all see cost pressure
            # Asia-Europe shipping add +10-14 days via Cape of Good Hope rerouting
            3: {
                "regulation__shock_magnitude":   +0.18,  # input cost shock amplifies tariff shock
                "global__trade_volume":          -0.04,  # ongoing routing disruption compounds
                "porter__supplier_power":        +0.08,  # suppliers passing through petrochem costs
                "global__energy_cost":           +0.05,  # energy cost firms up further
            },

            # ── TICK 7: Tariff escalation crystallizes ──────────────────
            # US tariffs 2.4%→30% fully confirmed on beauty/cosmetics imports
            # EL management confirms $100M H2 FY2026 headwind on earnings call
            # Analysts revise forward estimates downward
            7: {
                "regulation__shock_magnitude":   +0.14,  # tariff shock stacks on petrochem shock
                "keynesian__fiscal_shock_pending": -0.08, # tariff inflation → further demand hit
                "investor_sentiment__media_bias": -0.08,
                "investor_sentiment__polarization": +0.06,
            },

            # ── TICK 12: China travel retail remains depressed ──────────
            # Hainan duty-free data confirms -29.3% YoY channel
            # Iran war also disrupting APAC luxury travel routes
            # But mainland China +13% (Q2) is a partial offset
            12: {
                "porter__substitute_threat":     +0.04,  # travel retail vacuum fills with local alternatives
                "porter__rivalry_intensity":     +0.03,  # regional APAC brands fill Hainan channel
                "investor_sentiment__media_bias": -0.04,
            },

            # ── TICK 18: Shipping cost pass-through to wholesale margin ─
            # Cape rerouting adds ~$1.5M per vessel voyage for EL shipments
            # Wholesale channel starts to feel margin pressure
            # Retail partners begin reducing orders (bullwhip effect begins)
            18: {
                "keynesian__fiscal_shock_pending": -0.06,  # wholesale demand contracts ahead of retail
                "porter__buyer_power":            +0.05,  # retailers extracting margin concessions
                "regulation__shock_magnitude":   +0.06,  # logistics cost shock layer
            },

            # ── TICK 28: Puig acquisition announcement ──────────────────
            # March 23-24: EL confirms merger talks with Puig (~€8.8B / $10.2B)
            # EL falls -10.1% in single session
            # Concerns: dilution, Puig family as largest shareholder, leverage ($40B combined EV)
            # 61.5% of luxury M&A destroys acquirer value at announcement (SSRN 4845123)
            28: {
                "investor_sentiment__mean":        -0.18,  # -10.1% single day → large sentiment shock
                "investor_sentiment__polarization": +0.14,  # analyst divergence explodes (9B/12H split)
                "investor_sentiment__media_bias":  -0.12,  # Bloomberg, CNBC, Morningstar coverage negative
                "global__urgency_factor":          +0.08,  # corporate uncertainty adds to macro urgency
            },

            # ── TICK 32: Puig deal uncertainty continues (base case) ────
            # No resolution; analysts issue competing notes
            # Wells Fargo cut to $90 leads a wave of PT reductions
            # Uncertainty ceiling prevents recovery
            32: {
                "investor_sentiment__polarization": +0.06,
                "investor_sentiment__media_bias":  -0.04,
            },

            # ── TICK 38: Macro environment — no recovery catalyst ───────
            # Next UoM reading expected ~54 (below current 55.5)
            # No Iran ceasefire talks; VIX sticky 20-28
            # EL structural story not rebuilt in 14-day window
            38: {
                "keynesian__fiscal_shock_pending": -0.04,
                "global__urgency_factor":          +0.03,
            },
        },
    ),

    # ── Outcome metrics ──────────────────────────────────────────────────
    metrics=[
        OutcomeMetricSpec(name="investor_sentiment_mean",
                          env_key="investor_sentiment__mean",
                          description="Stock price direction proxy (opinion mean)"),
        OutcomeMetricSpec(name="investor_sentiment_polarization",
                          env_key="investor_sentiment__polarization",
                          description="Implied volatility proxy (analyst divergence)"),
        OutcomeMetricSpec(name="keynesian_gdp",
                          env_key="keynesian__gdp_normalized",
                          description="Macro demand signal"),
        OutcomeMetricSpec(name="market_selloff_infected",
                          env_key="market_selloff__infected",
                          description="Contagion spread — fraction of market actors infected"),
        OutcomeMetricSpec(name="regulation_compliance_cost",
                          env_key="regulation__compliance_cost",
                          description="Margin pressure from tariff + petrochem shocks"),
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
                          description="Global trade disruption from Iran war"),
        OutcomeMetricSpec(name="global_energy_cost",
                          env_key="global__energy_cost",
                          description="Energy cost index (oil price proxy)"),
        OutcomeMetricSpec(name="regulation_shock_magnitude",
                          env_key="regulation__shock_magnitude",
                          description="Combined tariff + petrochem input cost shock"),
    ],
)


# ── Run ──────────────────────────────────────────────────────────────────────

def run() -> dict:
    runner = SimRunner(spec, rng_seed=42)
    runner.setup()
    runner.run()

    # ── Extract metric time series ────────────────────────────────────────
    series: dict[str, list] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.name, []).append({
            "tick": rec.tick,
            "value": round(rec.value, 4),
        })

    # ── Final environment state ───────────────────────────────────────────
    final_env = {k: round(v, 4) for k, v in runner.get_current_env().items()}

    # ── Snapshots at key ticks ────────────────────────────────────────────
    key_ticks = [0, 1, 3, 7, 12, 18, 28, 30, 32, 38, 44]
    snap_envs: dict[int, dict] = {}
    for snap in runner.snapshots:
        if snap.tick in key_ticks:
            snap_envs[snap.tick] = {k: round(v, 4) for k, v in snap.env.items()}

    return {
        "series":    series,
        "final_env": final_env,
        "snapshots": snap_envs,
    }


if __name__ == "__main__":
    print("Running Estée Lauder simulation...")
    results = run()

    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {out_path}")

    # ── Quick summary to stdout ───────────────────────────────────────────
    series = results["series"]

    print("\n── Investor Sentiment (stock price proxy) ─────────────────────")
    for r in series.get("investor_sentiment_mean", []):
        bar = "█" * int(r["value"] * 40)
        label = ""
        if r["tick"] == 1:   label = "  ← Iran war onset"
        if r["tick"] == 7:   label = "  ← tariff + petrochem shock"
        if r["tick"] == 28:  label = "  ← PUIG announcement"
        if r["tick"] == 30:  label = "  ← today (March 26)"
        if r["tick"] == 44:  label = "  ← projection end (April 9)"
        if r["tick"] in (1, 5, 7, 10, 12, 15, 18, 20, 25, 28, 30, 32, 35, 38, 41, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f} | {bar}{label}")

    print("\n── GDP Normalized (macro demand) ───────────────────────────────")
    for r in series.get("keynesian_gdp", []):
        if r["tick"] in (1, 7, 12, 18, 28, 30, 38, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Contagion Infected (market stress spread) ───────────────────")
    for r in series.get("market_selloff_infected", []):
        if r["tick"] in (1, 5, 10, 15, 20, 25, 28, 30, 35, 40, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Regulation Compliance Cost (tariff + petrochem) ─────────────")
    for r in series.get("regulation_compliance_cost", []):
        if r["tick"] in (1, 5, 7, 10, 15, 20, 25, 28, 30, 40, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Porter Profitability (industry margin) ──────────────────────")
    for r in series.get("porter_profitability", []):
        if r["tick"] in (1, 7, 14, 21, 28, 30, 40, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Schumpeter Incumbent Share (EL prestige position) ───────────")
    for r in series.get("schumpeter_incumbent_share", []):
        if r["tick"] in (1, 10, 20, 28, 30, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Global Trade Volume (Hormuz + Red Sea disruption) ───────────")
    for r in series.get("global_trade_volume", []):
        if r["tick"] in (1, 3, 7, 14, 21, 28, 30, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\n── Energy Cost Index (oil price proxy) ─────────────────────────")
    for r in series.get("global_energy_cost", []):
        if r["tick"] in (1, 3, 7, 14, 28, 30, 44):
            print(f"  Day {r['tick']:2d} | {r['value']:.3f}")

    print("\nDone.")
