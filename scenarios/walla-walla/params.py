"""
scenarios/walla-walla/params.py

Walla Walla Premium Label Survival — Smoke Taint & Water Curtailment Shock (Sim 1)
Revenue continuity focus: lean label owner, 40 acres, $1.5M revenue, <6 mo cash reserves.
Horizon: 120 months (Jan 2026 – Dec 2035), monthly ticks.
"""

TICKS = 120
TICK_UNIT = "month"
START_DATE = "2026-01"
END_DATE = "2035-12"

# ── Initial environment ──────────────────────────────────────────────────────
# All values normalized to [0, 1]
INITIAL_ENV = {
    # Climate state
    "grapevine_gdd_phenology__temperature":     0.52,   # ~2100 GDD/season, Walla Walla current
    "grapevine_gdd_phenology__season_fraction": 0.0,

    # Smoke taint risk
    "smoke_taint_crop_disruption__smoke_prob":  0.50,   # base 5%/yr normalized (0.5 = no event)
    "smoke_taint_crop_disruption__taint_active": 0.0,   # no active event at start

    # Water / CPR
    "hotelling_cpr__stock":           0.72,   # snowpack / water availability (~30% below hist peak)
    "hotelling_cpr__extraction_rate": 0.48,   # current irrigation draw rate

    # Real options / replanting
    "real_options_agri_adapt__quality_stress":  0.15,   # mild GDD stress beginning
    "real_options_agri_adapt__cash_stress":     0.20,   # lean reserves, some stress
    "real_options_agri_adapt__replant_signal":  0.0,    # no trigger yet

    # Porter competitive
    "porter_five_forces__competitive_intensity": 0.55,
    "porter_five_forces__buyer_power":           0.40,  # DTC reduces buyer power

    # Financial health proxy (primary outcome metric)
    "cash_flow_health":     0.65,   # 18-24 mo runway (lean but ok)
    "revenue_normalized":   0.75,   # $1.5M / $2M capacity = 0.75
    "debt_service_stress":  0.30,   # $280K service is manageable at current revenue
    "survival_probability": 0.85,   # baseline survival score

    # Theory output keys (initialized; theories will update each tick)
    "grapevine_gdd_phenology__quality":           0.85,
    "grapevine_gdd_phenology__gdd_normalized":    0.52,
    "grapevine_gdd_phenology__bloom_reached":     0.0,
    "grapevine_gdd_phenology__veraison_reached":  0.0,
    "grapevine_gdd_phenology__harvest_reached":   0.0,
    "grapevine_gdd_phenology__winkler_region":    0.4,
}

# ── Shock schedule (additive deltas) ────────────────────────────────────────
# Shocks are ADDITIVE changes to env values each tick they fire.
SHOCKS = {
    # Year 1 (tick 12): mild smoke season — partial taint, some lots declassified
    12: {
        "smoke_taint_crop_disruption__taint_active": +0.35,  # moderate event
        "cash_flow_health":    -0.12,
        "revenue_normalized":  -0.18,
    },
    # Year 2 (tick 24): water stress begins — snowpack decline, curtailment notices
    24: {
        "hotelling_cpr__stock":       -0.08,
        "hotelling_cpr__extraction_rate": -0.06,
        "debt_service_stress":  +0.08,
    },
    # Year 3 (tick 36): MAJOR smoke taint event (2020-type, 85% revenue loss)
    36: {
        "smoke_taint_crop_disruption__taint_active": +0.80,  # catastrophic
        "cash_flow_health":    -0.42,   # existential stress
        "revenue_normalized":  -0.52,   # bulk declassification at 12 cents/$
        "debt_service_stress": +0.30,   # covenant breach risk
        "survival_probability": -0.25,
    },
    # Year 4 (tick 48): partial recovery — wine club retained, some bridge credit
    48: {
        "smoke_taint_crop_disruption__taint_active": -0.60,  # taint clears
        "cash_flow_health":    +0.15,
        "revenue_normalized":  +0.22,
        "debt_service_stress": -0.10,
    },
    # Year 5 (tick 60): water curtailment order — junior rights 60% cut
    60: {
        "hotelling_cpr__stock":           -0.15,
        "hotelling_cpr__extraction_rate": -0.28,  # forced reduction
        "cash_flow_health":    -0.18,
        "revenue_normalized":  -0.15,   # yield loss from water stress
        "real_options_agri_adapt__cash_stress": +0.25,
        "real_options_agri_adapt__quality_stress": +0.20,
    },
    # Year 6 (tick 72): GDD warming crosses Merlot threshold
    72: {
        "grapevine_gdd_phenology__temperature": +0.06,  # warming trend materializes
        "real_options_agri_adapt__quality_stress": +0.15,
        "real_options_agri_adapt__replant_signal": +0.25,  # replanting now urgent
    },
    # Year 7 (tick 84): second major smoke event (frequency tripling by 2030s)
    84: {
        "smoke_taint_crop_disruption__taint_active": +0.70,
        "cash_flow_health":    -0.35,
        "revenue_normalized":  -0.40,
        "debt_service_stress": +0.25,
        "survival_probability": -0.20,
    },
    # Year 8 (tick 96): compounding — water + smoke + GDD stress simultaneous
    96: {
        "hotelling_cpr__stock":           -0.10,
        "smoke_taint_crop_disruption__taint_active": -0.50,  # clears
        "cash_flow_health":    +0.10,
        "real_options_agri_adapt__replant_signal": +0.20,
    },
    # Year 10 (tick 108): terminal state — replanting decision forced
    108: {
        "grapevine_gdd_phenology__temperature": +0.04,
        "real_options_agri_adapt__replant_signal": +0.30,
        "real_options_agri_adapt__quality_stress": +0.10,
    },
}

# ── Outcome metrics ──────────────────────────────────────────────────────────
METRICS = [
    "cash_flow_health",
    "revenue_normalized",
    "debt_service_stress",
    "survival_probability",
    "smoke_taint_crop_disruption__taint_active",
    "hotelling_cpr__stock",
    "real_options_agri_adapt__replant_signal",
    "real_options_agri_adapt__cash_stress",
    "grapevine_gdd_phenology__quality",
    "grapevine_gdd_phenology__temperature",
]

# ── Theory stack ─────────────────────────────────────────────────────────────
THEORIES = [
    ("smoke_taint_crop_disruption", 1.0),   # primary shock model
    ("grapevine_gdd_phenology",     0.9),   # climate forcing
    ("hotelling_cpr",               0.8),   # water rights constraint
    ("real_options_agri_adapt",     0.7),   # replanting decision timing
    ("bordeaux_wine_quality",       0.6),   # quality → price (passive Sim 1)
    ("porter_five_forces",          0.4),   # competitive context
]

# ── Monte Carlo config ────────────────────────────────────────────────────────
MC_RUNS = 300
MC_SCENARIOS = {
    "base": 0.50,   # shocks as scheduled
    "bull": 0.25,   # smoke events lighter, water holds
    "bear": 0.25,   # two consecutive smoke years + full curtailment
}
