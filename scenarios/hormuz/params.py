"""
Parameters for scenario: hormuz
Strait of Hormuz — 2025 Escalation & Resolution
24-month simulation starting Q1 2025

Theory stack (priority order):
  0 — Richardson Arms Race   (Iran ↔ US military dynamics)
  1 — Fearon Bargaining      (conflict probability from information gap)
  2 — Wittman-Zartman        (ripeness, negotiation onset)
  3 — SIR Contagion          (economic/financial contagion across importers)
  4 — Keynesian Multiplier   (GDP impact of oil price shock)
  5 — Porter's Five Forces   (shipping industry structure under blockade)

Fixes applied (2026-03-26):
  Bug 1: fearon__win_prob_a / fearon__win_prob_b_estimate seeded at military
          balance ratio (0.44) instead of 0.00 — eliminates t=0 cold-start
  Bug 2: wittman_zartman payoff_floor raised from 0.05 to 0.45 — MHS fires at
          tick 0: EU_war_a=0.243, EU_war_b=0.437 (both < 0.45 floor)
  Bug 3: Porter env keys renamed to match module (rivalry_intensity,
          substitute_threat, barriers_to_entry)
  Bug 4: keynesian__gdp_gap replaced by keynesian__gdp_normalized in INITIAL_ENV;
          porter__competitive_intensity replaced by porter__profitability;
          METRICS updated to reference keys the modules actually write
  Bug 5: KEYNESIAN dict: import_rate → import_propensity; multiplier removed
  Bug 6: SIR beta recalibrated to 0.50 (monthly rate) — produces meaningful
          contagion growth vs 0.25 annual rate applied monthly
  Bug 7: Trade shock at t=22 reduced +0.15 → +0.05 so net shock = 0.00
          (trade returns to baseline, not 0.10 above it)
  Bug 8: fearon__war_cost_a/b seeded at 0.00 (not config values) — Fearon passed
          zeros through to env → Zartman EU_war = win_prob (no cost subtracted) →
          EU_war_b = 0.557 > 0.45 floor → MHS never fires regardless of floor.
          Fixed: seed at FEARON["war_cost_a"]=0.20, FEARON["war_cost_b"]=0.12
"""

SCENARIO_ID  = "hormuz"
TITLE        = "Strait of Hormuz — 2025 Escalation"
DOMAIN       = "geopolitics conflict"
TICK_UNIT    = "month"
TOTAL_TICKS  = 24          # Jan 2025 – Dec 2026
START_DATE   = "2025-01-01"

# ── Richardson Arms Race ──────────────────────────────────────────────────────
# Iran (actor_a) ↔ United States (actor_b)
RICHARDSON = {
    "k":         0.35,   # Iran's reactivity to US arms buildup
    "l":         0.20,   # US reactivity to Iran arms buildup (asymmetric — larger base)
    "a":         0.30,   # Iran fatigue coefficient (sanctions bite)
    "b":         0.15,   # US fatigue coefficient (lower — deeper resources)
    "g":         0.08,   # Iran grievance (sanctions, proxy war costs)
    "h":         0.03,   # US grievance baseline
    "actor_a_id": "iran",
    "actor_b_id": "us",
    "tick_unit":  TICK_UNIT,
}

# ── Fearon Bargaining ─────────────────────────────────────────────────────────
FEARON = {
    "war_cost_a":         0.20,  # Iran's war cost (fraction of prize)
    "war_cost_b":         0.12,  # US war cost
    "info_gap_sigma":     0.15,  # std of private information gap
    "power_shift_rate":   0.05,  # monthly change in military balance
    "commit_threshold":   0.10,  # power shift that breaks commitment
    "tick_unit":          TICK_UNIT,
}

# ── Wittman-Zartman ───────────────────────────────────────────────────────────
# FIX Bug 2: payoff_floor raised from 0.05 → 0.40
# With c_A=0.20, c_B=0.12, win_prob≈0.50:
#   EU_war_a = 0.50 - 0.20 = 0.30  <  0.40 floor → hurting ✓
#   EU_war_b = 0.50 - 0.12 = 0.38  <  0.40 floor → hurting ✓
WITTMAN_ZARTMAN = {
    "war_cost_a":           0.20,
    "war_cost_b":           0.12,
    "payoff_floor":         0.45,  # was 0.05; raised to match actual EU_war range
    # With military balance win_prob_a≈0.443: eu_a=0.243, eu_b=0.433 — both < 0.45
    "min_stalemate_ticks":  3,     # months of stalemate before ripe
    "urgency_threshold":    0.60,
    "base_negotiation_rate": 0.05,
    "ripe_multiplier":      4.0,
    "tick_unit":            TICK_UNIT,
}

# ── SIR Contagion (economic) ──────────────────────────────────────────────────
# FIX Bug 6: beta recalibrated from 0.25 (annual) to 0.50 (monthly)
# At monthly resolution (dt=1/12), beta=0.25 produced 0.00096 new infections/month.
# beta=0.50 produces ~0.00192/month → ~5pp infected growth over the crisis arc.
# Calibration: financial contagion literature (Allen & Gale 2000) suggests
# monthly R0 of 1.5–2.0 in severe crises; gamma=0.08 → beta=0.50 gives R0=6.25
# (annual), monthly effective growth ≈ 0.4% per month.
SIR_ECONOMIC = {
    "beta":              0.50,   # monthly-calibrated transmission rate (was 0.25 annual)
    "gamma":             0.08,   # recovery rate (diversification / substitution)
    "initial_infected":  0.05,   # early economic stress already present
    "active_threshold":  0.10,
    "trade_amplification": 0.60,
    "contagion_id":      "economic",
    "tick_unit":         TICK_UNIT,
}

# ── Keynesian Multiplier ──────────────────────────────────────────────────────
# FIX Bug 5: import_rate → import_propensity; multiplier removed (computed internally)
# M = 1 / (1 - MPC*(1-t) + import_propensity)
#   = 1 / (1 - 0.72*0.78 + 0.28) = 1 / 0.7184 ≈ 1.39  (intended value)
KEYNESIAN = {
    "mpc":               0.72,   # marginal propensity to consume
    "tax_rate":          0.22,
    "import_propensity": 0.28,   # was "import_rate" — ignored by Pydantic; fixed
    "tick_unit":         TICK_UNIT,
}

# ── Porter's Five Forces (shipping industry) ──────────────────────────────────
PORTER = {
    "w_barriers":   0.25,
    "w_supplier":   0.15,
    "w_buyer":      0.20,
    "w_substitute": 0.20,
    "w_rivalry":    0.20,
}

# ── Initial environment ───────────────────────────────────────────────────────
# All values normalized [0, 1]
_IRAN_MIL  = 0.62
_US_MIL    = 0.78
_WIN_PROB_A = _IRAN_MIL / (_IRAN_MIL + _US_MIL)   # ≈ 0.443; used to seed Fearon

INITIAL_ENV = {
    # Military
    "iran__military_readiness":    _IRAN_MIL,  # elevated after exercises
    "us__military_readiness":      _US_MIL,    # carrier group in Gulf
    "saudi__military_readiness":   0.55,
    "uk__military_readiness":      0.40,

    # Economic / energy
    "global__oil_price":           0.68,   # ~$94/bbl normalized (lo=$40 hi=$120)
    "global__trade_volume":        0.72,   # Hormuz carries ~20% world oil
    "strait__shipping_disruption": 0.08,   # minor harassment at start
    "global__economic_stress":     0.30,

    # Contagion seed
    "economic__susceptible":       0.92,
    "economic__infected":          0.05,
    "economic__recovered":         0.03,

    # Political / negotiation
    "iran__economic_pressure":     0.75,   # max sanctions regime
    "iran__domestic_stability":    0.40,
    "global__urgency_factor":      0.20,
    "zartman__mediator_present":   0.00,
    "global__negotiation_progress": 0.00,

    # Porter signals — FIX Bug 3: keys renamed to match module
    "porter__supplier_power":      0.45,
    "porter__buyer_power":         0.30,
    "porter__rivalry_intensity":   0.35,   # was porter__rivalry
    "porter__substitute_threat":   0.25,   # was porter__substitutes
    "porter__barriers_to_entry":   0.60,   # was porter__entry_barriers

    # Theory-owned keys (seeded; theories write real values at tick 0)
    "richardson__escalation_index":    0.00,
    "richardson__stable":              0.00,

    # FIX Bug 1: seed at military balance ratio, not 0.00
    # Eliminates the t=0 power_shift_rate spike that caused conflict_prob=1.0
    "fearon__win_prob_a":              round(_WIN_PROB_A, 3),  # ≈ 0.443
    "fearon__win_prob_b_estimate":     round(_WIN_PROB_A, 3),  # same; no info gap yet
    # FIX Bug 8: war costs seeded at config values (0.00 caused Fearon to pass-through
    #            zero → Zartman EU = win_prob (never < 0.45 floor) → MHS never fires)
    "fearon__war_cost_a":              FEARON["war_cost_a"],   # 0.20 — Iran's war cost
    "fearon__war_cost_b":              FEARON["war_cost_b"],   # 0.12 — US war cost
    "fearon__conflict_probability":    0.00,
    "fearon__settlement_range_width":  0.00,

    "zartman__eu_war_a":               0.00,
    "zartman__eu_war_b":               0.00,
    "zartman__mhs":                    0.00,
    "zartman__ripe_moment":            0.00,
    "zartman__negotiation_probability":0.00,
    "zartman__stalemate_duration":     0.00,

    "economic__r_effective":           0.00,
    "economic__active_contagion":      0.00,

    # FIX Bug 4: replaced dead keys with keys modules actually write
    "keynesian__gdp_normalized":   0.50,   # was keynesian__gdp_gap (never written)
    "keynesian__output_multiplier": 0.00,  # kept for observability
    "porter__profitability":        0.00,  # was porter__competitive_intensity (never written)
}

# ── Shock schedule ────────────────────────────────────────────────────────────
# {tick: {env_key: delta}}
SHOCKS = {
    2:  {   # Iran announces navigation restrictions
        "strait__shipping_disruption": +0.25,
        "global__oil_price":           +0.12,
        "global__trade_volume":        -0.15,
        "global__economic_stress":     +0.10,
    },
    3:  {   # US deploys additional carrier strike group
        "us__military_readiness":      +0.10,
        "iran__economic_pressure":     +0.05,  # additional sanctions
    },
    5:  {   # Iranian naval incident — tanker seizure
        "strait__shipping_disruption": +0.30,
        "global__oil_price":           +0.15,
        "global__trade_volume":        -0.20,
        "iran__military_readiness":    +0.08,
        "global__economic_stress":     +0.15,
    },
    7:  {   # International naval coalition forms (US, UK, EU)
        "us__military_readiness":      +0.08,
        "uk__military_readiness":      +0.12,
        "iran__domestic_stability":    -0.08,
    },
    9:  {   # Oil importers (Japan, Korea, India) activate strategic reserves
        "global__oil_price":           -0.05,
        "global__trade_volume":        +0.05,  # partial alternative routing
    },
    11: {   # Back-channel negotiations begin (Oman mediating)
        "zartman__mediator_present":   +1.00,
        "global__urgency_factor":      +0.30,
        "global__negotiation_progress": +0.15,
    },
    13: {   # US-Iran direct talks
        "global__negotiation_progress": +0.20,
        "iran__military_readiness":    -0.05,  # confidence-building
    },
    16: {   # Framework agreement announced
        "global__negotiation_progress": +0.25,
        "strait__shipping_disruption": -0.20,
        "global__oil_price":           -0.10,
    },
    19: {   # Ceasefire + partial strait reopening
        "strait__shipping_disruption": -0.30,
        "global__trade_volume":        +0.25,
        "global__oil_price":           -0.12,
        "iran__military_readiness":    -0.10,
    },
    22: {   # Full normalization
        # FIX Bug 7: trade shock reduced +0.15 → +0.05 so cumulative net = 0.00
        # (down: -0.35; up: +0.05 + +0.25 + +0.05 = +0.35; net = 0.00)
        "strait__shipping_disruption": -0.15,
        "global__trade_volume":        +0.05,  # was +0.15; reduced to avoid overshoot
        "global__economic_stress":     -0.10,
        "iran__economic_pressure":     -0.10,  # partial sanctions relief
    },
}

# ── Outcome metrics ───────────────────────────────────────────────────────────
# FIX Bug 4: updated env_keys to reference keys modules actually write
METRICS = [
    {"name": "Oil Price Index",        "env_key": "global__oil_price"},
    {"name": "Strait Disruption",      "env_key": "strait__shipping_disruption"},
    {"name": "Iran Military",          "env_key": "iran__military_readiness"},
    {"name": "US Military",            "env_key": "us__military_readiness"},
    {"name": "Conflict Probability",   "env_key": "fearon__conflict_probability"},
    {"name": "Negotiation Ripeness",   "env_key": "zartman__ripe_moment"},
    {"name": "Negotiation Progress",   "env_key": "global__negotiation_progress"},
    {"name": "Economic Contagion",     "env_key": "economic__infected"},
    {"name": "Global Economic Stress", "env_key": "global__economic_stress"},
    {"name": "Trade Volume",           "env_key": "global__trade_volume"},
    {"name": "GDP (normalized)",       "env_key": "keynesian__gdp_normalized"},  # was gdp_gap
    {"name": "Shipping Profitability", "env_key": "porter__profitability"},       # was competitive_intensity
]
