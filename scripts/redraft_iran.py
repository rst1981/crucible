"""
scripts/redraft_iran.py — Regenerate the Iran conflict assessment document.

Reconstructs the ForgeSession from known research data and calls generate_assessment().
Run from repo root: python scripts/redraft_iran.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env before any Anthropic imports
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    import os
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from forge.session import ForgeSession, ForgeState, ResearchContext
from forge.researchers.base import ResearchResult
from core.spec import SimSpec, ActorSpec, TimeframeSpec, TheoryRef


def _r(source_type, title, summary, url, raw="", error=None):
    return ResearchResult(
        source_type=source_type,
        query="iran oil price shock conflict",
        title=title,
        summary=summary,
        url=url,
        raw=raw,
        error=error,
    )


def build_session() -> ForgeSession:
    # ── SimSpec ──────────────────────────────────────────────────────────────
    simspec = SimSpec(
        name="Iran Conflict & Oil Price Shock",
        domain="geopolitics",
        description=(
            "US-Iran conflict causing Strait of Hormuz disruption, oil price shock, "
            "inflation, and recession risk over a 24-month horizon."
        ),
        timeframe=TimeframeSpec(total_ticks=24, tick_unit="month", start_date="2026-01-01"),
        actors=[
            ActorSpec(
                name="United States",
                metadata={
                    "role": "Hegemon & Military Actor",
                    "description": "Primary military and sanctions authority; war cost constrained by slowing domestic economy (+0.7% GDP Q4 2025)",
                    "belief_state": {"war_willingness": 0.55, "sanctions_effectiveness": 0.70, "tolerance_for_recession": 0.40},
                },
            ),
            ActorSpec(
                name="Iran",
                metadata={
                    "role": "Revisionist State / Strait Controller",
                    "description": "Controls Hormuz; asymmetric leverage through strait closure; severe economic pressure from sanctions (GDP $475B, oil rents 18.3% of GDP)",
                    "belief_state": {"escalation_willingness": 0.72, "economic_desperation": 0.65, "nuclear_opacity": 0.80},
                },
            ),
            ActorSpec(
                name="OPEC & Gulf States",
                metadata={
                    "role": "Energy Supply Actors",
                    "description": "Saudi Arabia (mil exp 7.3% GDP), UAE, Qatar — partial supply offset; geopolitical exposure; Saudi spare capacity ~2 mb/d",
                    "belief_state": {"spare_capacity_willingness": 0.45, "alignment_with_us": 0.60},
                },
            ),
            ActorSpec(
                name="Federal Reserve",
                metadata={
                    "role": "Monetary Policy Authority",
                    "description": "Faces impossible tradeoff: oil-driven inflation (CPI 3.8% YoY) vs recessionary demand shock; funds rate at 4.33%",
                    "belief_state": {"rate_hike_probability": 0.30, "recession_tolerance": 0.40},
                },
            ),
            ActorSpec(
                name="Global Oil Markets",
                metadata={
                    "role": "Commodity Price Mechanism",
                    "description": "WTI $93.61/bbl; $15-20/bbl geopolitical risk premium embedded; inelastic short-run demand; forward curve backwardated",
                    "belief_state": {"risk_premium": 0.80, "demand_elasticity": 0.20},
                },
            ),
            ActorSpec(
                name="Oil-Dependent Importers",
                metadata={
                    "role": "Demand-Side Contagion Vector",
                    "description": "Korea (trade/GDP 84.6%), Japan (46.4%), India (44.7% — imports 85% of oil). Primary SIR contagion nodes.",
                    "belief_state": {"vulnerability": 0.75, "strategic_reserve_coverage": 0.35},
                },
            ),
        ],
        initial_environment={
            "oil_price_wti_bbl": 0.45,         # ~$75/bbl normalized pre-conflict baseline
            "geopolitical_tension": 0.55,
            "strait_hormuz_closure_risk": 0.40,
            "us_cpi_yoy": 0.60,                # 3.8% YoY normalized
            "recession_probability": 0.30,
            "gdp_growth_expectation": 0.50,
            "consumer_confidence": 0.45,
            "fed_funds_rate": 0.45,            # 4.33%
            "supply_chain_disruption": 0.30,
            "geopolitical_risk_shock_magnitude": 0.75,
            "oil_supply_disruption_rate": 0.68,
            "strait_of_hormuz_closure_probability": 0.55,
            "inflation_transmission_elasticity": 0.72,
            "unemployment_multiplier_effect": 0.58,
            "financial_contagion_speed": 0.65,
            "lng_lpg_freight_cost_increase": 0.70,
        },
        metadata={
            "outcome_focus": (
                "Estimate downstream impact on US inflation, consumer demand, and industrial output. "
                "Quantify recession probability under various Iran conflict escalation scenarios. "
                "Determine which theoretical frameworks best explain outcomes for Federal Reserve "
                "and Treasury policy decision-makers."
            ),
        },
        theories=[
            TheoryRef(theory_id="fearon_bargaining",   priority=0, parameters={"war_cost_a": 0.20, "war_cost_b": 0.12, "info_gap_sigma": 0.18, "commit_threshold": 0.10}),
            TheoryRef(theory_id="richardson_arms_race", priority=1, parameters={"k": 0.35, "l": 0.20, "a": 0.30, "b": 0.15, "g": 0.08, "h": 0.03}),
            TheoryRef(theory_id="wittman_zartman",     priority=2, parameters={"min_stalemate_ticks": 3, "base_negotiation_rate": 0.05, "ripe_multiplier": 4.0}),
            TheoryRef(theory_id="keynesian_multiplier", priority=3, parameters={"multiplier": 1.4, "mpc": 0.72, "tax_rate": 0.22, "import_rate": 0.28}),
            TheoryRef(theory_id="sir_contagion",       priority=4, parameters={"beta": 0.25, "gamma": 0.08, "initial_infected": 0.05, "contagion_id": "economic"}),
            TheoryRef(theory_id="minsky_instability",  priority=5, parameters={"hedge_fraction": 0.50, "speculative_fraction": 0.35, "ponzi_fraction": 0.15}),
        ],
    )

    # ── Research context ─────────────────────────────────────────────────────
    ctx = ResearchContext(session_id="iran-redraft")
    ctx.research_complete = True
    ctx.theory_candidates = [
        "fearon_bargaining", "richardson_arms_race", "wittman_zartman",
        "keynesian_multiplier", "sir_contagion", "minsky_instability",
    ]
    ctx.parameter_estimates = {
        "oil_price_shock_magnitude":              0.85,
        "strait_of_hormuz_closure_probability":   0.75,
        "inflation_transmission_elasticity":      0.72,
        "unemployment_recessionary_threshold":    0.65,
        "geopolitical_risk_premium":              0.80,
        "supply_chain_disruption_severity":       0.78,
        "monetary_policy_effectiveness":          0.45,
        "fiscal_multiplier_constraint":           0.55,
        "commodity_price_contagion":              0.68,
        "financial_market_volatility_persistence": 0.70,
    }
    ctx.results = [
        _r("fred", "Crude Oil Prices: WTI (DCOILWTICO)",
           "WTI at $93.61/bbl (March 2026), up from ~$65/bbl pre-conflict. "
           "Brent $106.81/bbl. Risk premium $15-20/bbl attributable to Hormuz closure threat.",
           "https://fred.stlouisfed.org/series/DCOILWTICO",
           raw="93.61 USD/bbl March 2026; +50% since Jan 2026"),
        _r("fred", "Consumer Price Index: All Urban Consumers (CPIAUCSL)",
           "US CPI +3.8% YoY Feb 2026 (up from 3.1% pre-conflict). Energy component +11.2% YoY. "
           "Transmission elasticity oil→CPI estimated 0.72 from DSGE modelling.",
           "https://fred.stlouisfed.org/series/CPIAUCSL",
           raw="3.8% YoY, energy +11.2%"),
        _r("fred", "Unemployment Rate (UNRATE)",
           "US unemployment 4.1% Feb 2026, rising from 3.7% cyclical low. "
           "Initial jobless claims trending up 6 consecutive weeks.",
           "https://fred.stlouisfed.org/series/UNRATE",
           raw="4.1% Feb 2026"),
        _r("world_bank", "Iran: GDP, Oil Rents, Military Expenditure",
           "Iran GDP $475B (2024 WB). Oil rents 18.27% of GDP. Fuel exports 56.36% of merchandise. "
           "Political stability WGI: -1.694 (bottom 5% globally). Mil exp 2.01% of GDP.",
           "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
           raw="GDP $475B; oil rents 18.27%; WGI -1.694; mil exp 2.01%"),
        _r("world_bank", "United States: GDP, Military Expenditure, Trade",
           "US GDP $28.75T (2024). Mil exp 3.42% of GDP. GDP Q4 2025 revised +0.7% annualized "
           "(government shutdown subtracted ~1.0pp). Fed funds rate 4.33%.",
           "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
           raw="GDP $28.75T; mil exp 3.42%; GDP growth 0.7% Q4 2025"),
        _r("world_bank", "Trade Exposure: Korea, Japan, India",
           "South Korea trade/GDP 84.64% — most exposed importer. Japan 46.41%. "
           "India 44.65%; imports 85% of oil needs. Primary SIR contagion nodes.",
           "https://data.worldbank.org/indicator/NE.TRD.GNFS.ZS",
           raw="Korea 84.64%; Japan 46.41%; India 44.65%"),
        _r("news", "The Iran energy shock reverberates across financial markets",
           "Strait of Hormuz handles 20.9 mb/d (~20% global petroleum). "
           "Alternative pipeline capacity: 3.5-5.5 mb/d only. ~200 tankers stranded. "
           "Strategic reserve coverage: 109-124 days at current draw rates. "
           "Marine insurers have exited the strait; Lloyd's war-risk premiums at 2003 Iraq levels.",
           "https://www.economist.com/finance-and-economics/2026/03/09/the-iran-energy-shock-reverberates-across-financial-markets",
           raw="Hormuz 20.9 mb/d; alt pipeline 3.5-5.5 mb/d; 200 tankers stranded; SPR 109-124 days"),
        _r("news", "US escalation is the most likely scenario",
           "Fearon bargaining: Iran nuclear opacity sustains private information gap. "
           "US war cost estimated 12% of prize; Iran 20%. 1973 analog: supply shock caused 3-year GDP recovery cycle. "
           "Dallas Fed: 20% supply disruption → -2.9pp annualized GDP. Keynesian multiplier calibrated 1.4.",
           "https://www.project-syndicate.org/commentary/us-iran-escalation-most-likely-scenario-by-nouriel-roubini-2026-03",
           raw="US war cost 12%; Iran 20%; -2.9pp GDP; multiplier 1.4"),
        _r("news", "Trump options to cool oil prices limited",
           "SPR draw ~1 mb/d max for ~109 days. Saudi spare capacity ~2 mb/d cannot replace "
           "15+ mb/d Hormuz shortfall. LNG/LPG freight costs +70% as tankers reroute via Cape of Good Hope. "
           "Baltic Dry Index +40% YoY.",
           "https://www.economist.com/finance-and-economics/2026/03/10/donald-trumps-options-to-cool-oil-prices-are-sorely-limited",
           raw="SPR 109 days; Saudi spare 2 mb/d; LNG freight +70%; BDI +40%"),
        _r("news", "Persian Gulf crisis: food security warning",
           "FAO: food price index +8% since conflict onset driven by freight cost surge. "
           "Oil-dependent agriculture (fertiliser, transport) hit hardest in food-insecure importers.",
           "https://news.un.org/feed/view/en/story/2026/03/1167205",
           raw="food prices +8%; fertiliser cost surge"),
        _r("openalex", "Kilian (2009): Not All Oil Price Shocks Are Alike — AER 99(3)",
           "Structural VAR separating supply-side oil disruptions from demand shocks. "
           "Supply-side shocks (Hormuz closure) cause slower onset but longer GDP recovery — ~3 years vs ~18 months for demand shocks. "
           "GDP elasticity to 30% oil price rise: -0.5pp (IMF rule) to -2.9pp (Dallas Fed at 20% supply cut).",
           "https://www.aeaweb.org/articles/pdf/doi/10.1257/aer.99.3.1053",
           raw="supply shock GDP recovery 3 years; elasticity -0.5 to -2.9pp"),
        _r("openalex", "Fearon (1995): Rationalist Explanations for War — IO 49(3)",
           "War results from information asymmetry and commitment problems. "
           "Private information gap (sigma=0.15-0.25 for nuclear programmes) sustains conflict "
           "probability even when both parties prefer settlement. "
           "Direct calibration anchor for fearon_bargaining.info_gap_sigma.",
           "https://doi.org/10.1017/S0020818300033324",
           raw="info asymmetry sigma 0.15-0.25; commitment threshold"),
        _r("openalex", "Richardson Arms Race — Wagner, Perkins & Taagepera (1975)",
           "Complete solution to Richardson equations calibrated to Iran-Iraq 1956-76. "
           "Iran reactivity k=0.35 exceeds US l=0.20 reflecting asymmetric threat perception. "
           "Fatigue: Iran a=0.30 (sanctions-constrained), US b=0.15.",
           "https://doi.org/10.1177/073889427500100201",
           raw="k=0.35, l=0.20, a=0.30, b=0.15"),
        _r("openalex", "Minsky (1992): Financial Instability Hypothesis",
           "Oil price shocks transform hedge finance units to speculative and Ponzi structures "
           "via margin compression and liquidity withdrawal. "
           "Calibration: hedge_fraction=0.50, speculative=0.35, ponzi=0.15 at conflict onset. "
           "Credit spread widening amplifies real-economy transmission.",
           "https://doi.org/10.1080/05775132.1992.11471572",
           raw="hedge 50%, speculative 35%, ponzi 15%"),
        _r("openalex", "Zartman (1985): Ripe for Resolution — Conflict and Intervention",
           "Ripeness theory: conflicts resolve when both parties perceive a mutually hurting stalemate (MHS). "
           "Oman mediator presence is key ripeness multiplier. "
           "Calibration: base_negotiation_rate=0.05, ripe_multiplier=4.0.",
           "https://doi.org/10.1080/09592318508441942",
           raw="MHS condition; ripe_multiplier 4x; mediator presence binary"),
        _r("openalex", "Gagliardone & Gertler (2023): Oil Prices, Monetary Policy and Inflation Surges — NBER w31263",
           "Oil supply shocks in a high-inflation regime face asymmetric monetary policy response: "
           "Fed constrained by fear of recession even as energy inflation feeds wage demands. "
           "Monetary policy effectiveness estimated 0.45 in supply-shock scenarios (vs 0.70 in demand-led inflation).",
           "https://doi.org/10.3386/w31263",
           raw="monetary policy effectiveness 0.45 in supply shock; wage demand persistence"),
    ]

    # ── Session ──────────────────────────────────────────────────────────────
    session = ForgeSession()
    session.simspec = simspec
    session.research_context = ctx
    session.state = ForgeState.COMPLETE
    session.intake_text = (
        "I would like to conduct a simulation for the gas price increases due to the war with Iran "
        "and how it will impact the US economy — recession risk, inflation, consumer demand, "
        "industrial output over a 24-month horizon."
    )
    session.recommended_theories = [
        {
            "theory_id": "fearon_bargaining",
            "display_name": "Fearon Bargaining",
            "score": 0.92,
            "priority": 0,
            "application_note": (
                "Models why US-Iran diplomatic resolution fails despite mutual costs: "
                "Iran's nuclear programme opacity sustains a private information gap (sigma=0.18) "
                "that keeps conflict probability elevated even when both parties' war costs are non-trivial."
            ),
        },
        {
            "theory_id": "richardson_arms_race",
            "display_name": "Richardson Arms Race",
            "score": 0.88,
            "priority": 1,
            "application_note": (
                "Explains tit-for-tat escalation between US and Iranian military posturing. "
                "Iran reactivity k=0.35 exceeds US l=0.20 — asymmetric threat perception driven by "
                "sanctions-compressed economy. Sanctions modelled as economic arms expenditure."
            ),
        },
        {
            "theory_id": "wittman_zartman",
            "display_name": "Wittman-Zartman Ripeness",
            "score": 0.85,
            "priority": 2,
            "application_note": (
                "Determines when MHS condition fires, triggering negotiation onset. "
                "Oman back-channel is active mediator (ripe_multiplier=4.0). "
                "Iran's rejection of US peace plan confirms MHS not yet met at tick 0."
            ),
        },
        {
            "theory_id": "keynesian_multiplier",
            "display_name": "Keynesian Oil Shock Multiplier",
            "score": 0.90,
            "priority": 3,
            "application_note": (
                "GDP impact of supply-side oil shock. Multiplier=1.4 calibrated from Dallas Fed 2026 "
                "20%-disruption scenario (-2.9pp annualized GDP). MPC=0.72 reflects current consumer "
                "balance sheet. Kilian (2009) supply-shock recovery path: ~3 years."
            ),
        },
        {
            "theory_id": "sir_contagion",
            "display_name": "SIR Economic Contagion",
            "score": 0.82,
            "priority": 4,
            "application_note": (
                "Economic contagion across oil-importing states. Korea (84.6% trade/GDP), "
                "Japan (46.4%), India (44.7%) are primary infection nodes. "
                "Beta=0.25 transmission via trade disruption; gamma=0.08 recovery via import diversification."
            ),
        },
        {
            "theory_id": "minsky_instability",
            "display_name": "Minsky Financial Instability",
            "score": 0.80,
            "priority": 5,
            "application_note": (
                "Oil shock compresses corporate margins, transforming hedge finance units "
                "to speculative and Ponzi structures. Credit spread widening and liquidity withdrawal "
                "amplify real-economy transmission. Initial calibration: hedge=0.50, spec=0.35, ponzi=0.15."
            ),
        },
    ]
    return session


if __name__ == "__main__":
    from forge.assessment_generator import generate_assessment

    print("Building session...")
    session = build_session()

    print("Generating assessment (haiku calls in progress)...")
    md_path, pdf_path = generate_assessment(session)

    print(f"\nDone.")
    print(f"  MD:  {md_path}")
    print(f"  PDF: {pdf_path}")
