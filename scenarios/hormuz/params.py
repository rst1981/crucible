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
WITTMAN_ZARTMAN = {
    "war_cost_a":           0.20,
    "war_cost_b":           0.12,
    "payoff_floor":         0.05,  # EU_war below this = "hurting"
    "min_stalemate_ticks":  3,     # months of stalemate before ripe
    "urgency_threshold":    0.60,
    "base_negotiation_rate": 0.05,
    "ripe_multiplier":      4.0,
    "tick_unit":            TICK_UNIT,
}

# ── SIR Contagion (economic) ──────────────────────────────────────────────────
SIR_ECONOMIC = {
    "beta":              0.25,   # financial contagion transmission rate
    "gamma":             0.08,   # recovery rate (diversification / substitution)
    "initial_infected":  0.05,   # early economic stress already present
    "active_threshold":  0.10,
    "trade_amplification": 0.60,
    "contagion_id":      "economic",
    "tick_unit":         TICK_UNIT,
}

# ── Keynesian Multiplier ──────────────────────────────────────────────────────
KEYNESIAN = {
    "multiplier":        1.4,    # fiscal multiplier for oil shock
    "mpc":               0.72,   # marginal propensity to consume
    "tax_rate":          0.22,
    "import_rate":       0.28,
    "tick_unit":         TICK_UNIT,
}

# ── Porter's Five Forces (shipping industry) ──────────────────────────────────
PORTER = {
    "supplier_power_weight":  0.25,
    "buyer_power_weight":     0.15,
    "rivalry_weight":         0.20,
    "substitutes_weight":     0.20,
    "entry_barriers_weight":  0.20,
}

# ── Initial environment ───────────────────────────────────────────────────────
# All values normalized [0, 1]
INITIAL_ENV = {
    # Military
    "iran__military_readiness":    0.62,   # elevated after exercises
    "us__military_readiness":      0.78,   # carrier group in Gulf
    "saudi__military_readiness":   0.55,
    "uk__military_readiness":      0.40,

    # Economic / energy
    "global__oil_price":           0.68,   # ~$85/bbl normalized (40=0, 120=1)
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

    # Porter signals (shipping industry)
    "porter__supplier_power":      0.45,
    "porter__buyer_power":         0.30,
    "porter__rivalry":             0.35,
    "porter__substitutes":         0.25,
    "porter__entry_barriers":      0.60,

    # Theory-owned keys (seeded at 0; theories write real values at tick 0)
    "richardson__escalation_index":    0.00,
    "richardson__stable":              0.00,
    "fearon__win_prob_a":              0.00,
    "fearon__win_prob_b_estimate":     0.00,
    "fearon__war_cost_a":              0.00,
    "fearon__war_cost_b":              0.00,
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
    "keynesian__gdp_gap":              0.00,
    "keynesian__output_multiplier":    0.00,
    "porter__competitive_intensity":   0.00,
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
        "strait__shipping_disruption": -0.15,
        "global__trade_volume":        +0.15,
        "global__economic_stress":     -0.10,
        "iran__economic_pressure":     -0.10,  # partial sanctions relief
    },
}

# ── Outcome metrics ───────────────────────────────────────────────────────────
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
]
