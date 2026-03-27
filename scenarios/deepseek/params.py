"""
Scenario parameters: DeepSeek R1 / NVIDIA AI Infrastructure Shock
Jan 2025 – Jun 2026  (18 monthly ticks)

Calibration sources:
  - FRED: VIXCLS, NASDAQCOM, USEPUINDXM, PCU334413334413, FEDFUNDS, DGS10
  - World Bank: TX.VAL.TECH.MF.ZS, GB.XPD.RSDV.GD.ZS, BX.KLT.DINV.WD.GD.ZS
  - Bloomberg: NVIDIA market cap loss, GPU market share data
  - Lu 2025 (arXiv:2501.02156): efficiency_doubling_period
  - Goetzmann & Kim (2022) NBER WP 30195: narrative virality calibration
"""
from __future__ import annotations

SCENARIO_ID = "deepseek"
TITLE       = "DeepSeek R1 / NVIDIA AI Infrastructure Shock"
DOMAIN      = "technology_market_disruption"
TICK_UNIT   = "month"
TOTAL_TICKS = 18          # Jan 2025 (tick 0) → Jun 2026 (tick 17)
START_DATE  = "2025-01-20"

# ── Theory parameters ────────────────────────────────────────────────────────

PLATFORM_TIPPING = {
    "cross_side_network_effect": 0.30,   # Rochet-Tirole / Dube calibration
    "switching_cost":            0.15,   # CUDA developer switching cost
    "initial_incumbent_share":   0.87,   # NVIDIA GPU market share 2024 peak
    "learning_rate":             0.05,
}

COMPUTE_EFFICIENCY = {
    "efficiency_doubling_period":  12.0,  # Lu 2025 midpoint (9–16 months)
    "initial_incumbent_moat":       0.80,
    "moat_erosion_sensitivity":     2.0,  # Elevated: DeepSeek = regime shift, not normal
}

NARRATIVE_CONTAGION = {
    "beta_bull":             0.25,   # Goetzmann & Kim (2022)
    "gamma_bull":            0.08,
    "beta_bear":             0.35,   # Elevated post-DeepSeek shock
    "gamma_bear":            0.10,
    "cross_inhibition":      0.12,
    "initial_bull_share":    0.65,   # Pre-shock AI bull consensus
    "initial_bear_share":    0.05,
}

SCHUMPETER = {
    "disruption_rate":       0.08,
    "incumbent_resistance":  0.70,   # CUDA lock-in estimate
    "innovation_rate":       0.10,
    "market_size":           1.0,
}

FISHER_PRY = {
    "k":         0.15,   # Substitution rate (accelerated by efficiency gain)
    "t_0":       18,     # S-curve inflection at tick 18 (~Jun 2026)
    "f_ceiling": 0.90,
}

MINSKY = {
    "interest_rate_sensitivity": 0.40,
    "asset_appreciation_weight": 0.50,
    "fragility_threshold":       0.65,
}

OPINION = {
    "convergence_rate": 0.10,
    "media_influence":  0.20,
    "polarization_decay": 0.05,
}

PORTER = {
    "capacity_elasticity":  0.20,
    "trade_elasticity":     0.15,
}

BASS = {
    "p":           0.03,   # Innovation coefficient
    "q":           0.38,   # Imitation coefficient
    "market_size": 1.0,
}

# ── Initial environment ──────────────────────────────────────────────────────

INITIAL_ENV: dict[str, float] = {
    # --- Event study ---
    "global__market_return":    -0.031,  # NASDAQ Jan 27 2025 drop
    "event__actual_return":     -0.170,  # NVIDIA AR Jan 20 2025
    "event__event_active":       0.0,    # activated at tick 0 shock
    "event__cumulative_ar":      0.0,    # primary sentiment proxy

    # --- Platform tipping ---
    "platform_tipping__incumbent_share":  0.87,
    "platform_tipping__tipping_pressure": 0.50,
    "platform_tipping__moat_intact":      1.0,
    "platform_tipping__disruptive_shock": 0.0,  # set at tick 0

    # --- Compute efficiency ---
    "compute_efficiency__efficiency_gain":  0.0,
    "compute_efficiency__incumbent_moat":   0.80,
    "compute_efficiency__entry_barrier":    1.0,
    "compute_efficiency__efficiency_shock": 0.0,  # set at tick 0

    # --- Narrative contagion ---
    "narrative_contagion__bull_share":       0.65,
    "narrative_contagion__bear_share":       0.05,
    "narrative_contagion__sentiment_balance": 0.80,
    "narrative_contagion__bear_trigger":      0.0,  # set at tick 0

    # --- Schumpeter ---
    "schumpeter__incumbent_share":      0.87,   # mirrors platform share
    "schumpeter__innovator_share":      0.05,   # open-weight / DeepSeek
    "schumpeter__rd_investment":        0.65,   # normalized R&D intensity
    "schumpeter__creative_destruction": 0.0,
    "schumpeter__market_renewal":       0.0,

    # --- Fisher-Pry ---
    "fisher__new_tech_share":    0.05,   # open-weight AI share at tick 0
    "fisher__old_tech_share":    0.95,
    "fisher__cost_reduction":    0.033,  # DeepSeek cost ratio vs GPT-4
    "fisher__substitution_flow": 0.0,
    "fisher__takeoff_index":     0.0,

    # --- Minsky ---
    "minsky__hedge_fraction":       0.50,
    "minsky__speculative_fraction": 0.40,
    "minsky__ponzi_fraction":       0.10,
    "minsky__interest_rate":        0.0433,  # FRED FEDFUNDS Mar 2026
    "minsky__asset_appreciation":   0.55,    # AI sector appreciation proxy (normalized)
    "minsky__financial_fragility":  0.30,
    "minsky__crash_risk":           0.10,

    # --- Opinion dynamics ---
    "opinion__mean":          0.72,   # pre-shock sentiment baseline (NASDAQ normalized)
    "opinion__polarization":  0.20,
    "opinion__media_bias":    0.60,   # slightly pro-tech media stance
    "opinion__consensus":     0.65,
    "global__urgency_factor": 0.30,

    # --- Porter five forces ---
    "porter__barriers_to_entry":  0.65,  # CUDA + capital costs (eroding)
    "porter__supplier_power":     0.80,  # TSMC dependency
    "porter__buyer_power":        0.45,  # hyperscalers have leverage
    "porter__substitute_threat":  0.35,  # pre-shock; rises with efficiency
    "porter__rivalry_intensity":  0.55,
    "porter__profitability":      0.75,  # NVIDIA 76% gross margin
    "porter__capacity_investment": 0.70,

    # --- Bass diffusion ---
    "bass__adoption_fraction":  0.05,   # open-weight AI adoption fraction
    "bass__adoption_rate":      0.0,
    "bass__innovator_rate":     0.0,
    "bass__imitator_rate":      0.0,

    # --- Shared global ---
    "keynesian__gdp_normalized": 0.72,  # US GDP growth normalized (solid but slowing)
    "global__trade_volume":      0.65,  # global trade normalized
    "global__policy_uncertainty": 0.36, # EPU 167 normalized on 0–1 scale (167/460)
}

# ── Shock schedule ────────────────────────────────────────────────────────────
# Format: {tick: {env_key: value, ...}}

SHOCKS: dict[int, dict[str, float]] = {
    # Tick 0 — Jan 20 2025: DeepSeek R1 disclosure
    0: {
        "event__event_active":               1.0,
        "event__actual_return":             -0.170,
        "platform_tipping__disruptive_shock": 0.08,  # 8% share erosion shock
        "compute_efficiency__efficiency_shock": 0.30, # 30% efficiency gain injected
        "narrative_contagion__bear_trigger":  0.35,  # major bear narrative injection
        "opinion__media_bias":                0.35,  # media turns sharply bearish
    },
    # Tick 1 — Feb 2025: Initial recovery attempt
    1: {
        "event__event_active":               0.0,
        "platform_tipping__disruptive_shock": 0.02,  # residual erosion
        "narrative_contagion__bear_trigger":  0.05,  # secondary bear wave
        "compute_efficiency__efficiency_shock": 0.0,
    },
    # Tick 3 — Apr 2025: Export controls + tariff escalation (125% US-China)
    3: {
        "global__policy_uncertainty":        1.0,    # EPU spike to 460 (max)
        "porter__barriers_to_entry":         0.75,   # export control = barrier ↑
        "porter__substitute_threat":         0.50,   # custom silicon programs announced
        "narrative_contagion__bear_trigger":  0.10,  # policy overhang fear
        "platform_tipping__disruptive_shock": 0.03,
    },
    # Tick 6 — Jul 2025: Blackwell ramp — partial recovery
    6: {
        "platform_tipping__disruptive_shock": 0.0,
        "narrative_contagion__bear_trigger":  0.0,
        "opinion__media_bias":                0.55,   # media turns more neutral
        "schumpeter__rd_investment":          0.75,   # NVIDIA capex ramp
        "minsky__asset_appreciation":         0.65,   # recovery rally
    },
    # Tick 9 — Oct 2025: Hyperscaler capex acceleration confirmed ($315B)
    9: {
        "narrative_contagion__bear_trigger":  0.0,
        "minsky__asset_appreciation":         0.70,
        "fisher__cost_reduction":             0.045,  # efficiency gains compounding
        "bass__adoption_fraction":            0.12,   # open-weight AI adoption rising
    },
    # Tick 12 — Jan 2026: DeepSeek successor release (rumored R2 / V3-tier)
    12: {
        "compute_efficiency__efficiency_shock": 0.20,  # second efficiency shock
        "narrative_contagion__bear_trigger":    0.20,  # renewed bear narrative
        "platform_tipping__disruptive_shock":   0.05,  # renewed share pressure
        "porter__substitute_threat":            0.60,  # custom silicon share rising
        "opinion__media_bias":                  0.40,  # media turns bearish again
    },
    # Tick 15 — Apr 2026: Stabilization — hyperscalers lock in NVIDIA for inference
    15: {
        "narrative_contagion__bear_trigger":    0.0,
        "platform_tipping__disruptive_shock":   0.0,
        "minsky__asset_appreciation":           0.62,
        "global__policy_uncertainty":           0.70,  # still elevated but stabilizing
    },
}

# ── Outcome metrics ──────────────────────────────────────────────────────────

METRICS: list[dict] = [
    # Primary: event study cumulative AR (sentiment / stock proxy)
    {"name": "nvidia_sentiment", "env_key": "event__cumulative_ar"},
    # Platform dynamics
    {"name": "incumbent_share",  "env_key": "platform_tipping__incumbent_share"},
    {"name": "moat_intact",      "env_key": "platform_tipping__moat_intact"},
    # Efficiency
    {"name": "efficiency_gain",  "env_key": "compute_efficiency__efficiency_gain"},
    {"name": "entry_barrier",    "env_key": "compute_efficiency__entry_barrier"},
    # Narratives
    {"name": "bull_share",       "env_key": "narrative_contagion__bull_share"},
    {"name": "bear_share",       "env_key": "narrative_contagion__bear_share"},
    {"name": "sentiment_balance","env_key": "narrative_contagion__sentiment_balance"},
    # Disruption
    {"name": "innovator_share",  "env_key": "schumpeter__innovator_share"},
    {"name": "open_weight_share","env_key": "fisher__new_tech_share"},
    # Financial stability
    {"name": "financial_fragility", "env_key": "minsky__financial_fragility"},
    {"name": "crash_risk",          "env_key": "minsky__crash_risk"},
    # Synthesis
    {"name": "porter_profitability","env_key": "porter__profitability"},
    {"name": "ai_adoption",         "env_key": "bass__adoption_fraction"},
    # Opinion
    {"name": "market_opinion",      "env_key": "opinion__mean"},
]
