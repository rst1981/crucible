# Theory Brief: Strait of Hormuz Escalation
**Date:** 2026-03-26 | **Depth:** 12 sources reviewed | **Skill:** /research-theory

---

## Recommended Theory Stack

For this scenario, activate these Crucible modules (in priority order):

| Priority | Module | Rationale | Key Parameters to Set |
|----------|--------|-----------|----------------------|
| 0 | `richardson_arms_race` | Canonical model for Iran–US mutual military buildup. Iran's sanctions-driven grievance (g=0.08) drives arming independently of US posture; k > l (Iran more reactive) reflects asymmetric threat perception. | k=0.35, l=0.20, a=0.30, b=0.15, g=0.08, h=0.03 |
| 1 | `fearon_bargaining` | Models conflict probability from private information gap and power-shift commitment problem. Iran–US information asymmetry (nuclear program opacity) is the canonical Fearon mechanism. | war_cost_a=0.20, war_cost_b=0.12, info_gap_sigma=0.15 |
| 2 | `wittman_zartman` | Ripeness theory captures when Oman-mediated negotiation becomes viable — MHS condition fires when both parties' EU_war falls below payoff floor. Historically correct: 2015 JCPOA followed ~2 years of mutually hurting stalemate. | min_stalemate_ticks=3, base_negotiation_rate=0.05, ripe_multiplier=4.0 |
| 3 | `sir_contagion` | Oil price shock propagates as financial/economic contagion across importing states (Japan, Korea, India). SIR models transmission through trade exposure and supply chain interdependence. | beta=0.25, gamma=0.08, contagion_id="economic" |
| 4 | `keynesian_multiplier` | GDP impact of sustained oil supply disruption. Empirical: 20% Hormuz supply removal → −2.9pp GDP (annualized), implying multiplier ~1.4 from a 0.68 normalized price shock. | multiplier=1.4, mpc=0.72 |
| 5 | `porter_five_forces` | Shipping industry structure under blockade: supplier power (tanker operators) spikes; buyer power (oil importers) collapses; entry barriers rise as insurers exit. Captures rate war economics. | supplier_power_weight=0.25, entry_barriers_weight=0.20 |

---

## Composability Note

Richardson (priority 0) writes `iran__military_readiness` and `us__military_readiness` each tick. Fearon (priority 1) reads these as its military balance inputs — so Fearon's conflict probability is dynamically driven by the arms race trajectory rather than static parameters. Wittman-Zartman (priority 2) reads `fearon__win_prob_a` and the escalation index to assess whether conditions for MHS are met. SIR (priority 3) reads `global__trade_volume` — disruption events that reduce trade volume amplify the economic contagion transmission rate. Keynesian (priority 4) reads the SIR infected fraction and trade volume as spending shock drivers. Porter (priority 5) reads the disruption level to update competitive intensity in the shipping industry.

The cascade is: arms dynamics → conflict probability → ripeness → economic contagion → GDP multiplier → industry structure response.

---

## Calibration Anchors

| Parameter | Value | Source |
|-----------|-------|--------|
| Hormuz share of global oil supply | 20% (20 mb/d) | Dallas Fed (2026) |
| Alternative pipeline capacity | 3.5–5.5 mb/d | Dallas Fed (2026) |
| GDP impact: 20% supply disruption (annualized) | −2.9 pp | Dallas Fed (2026) |
| GDP impact: extended closure (global) | −3.15% of GDP (~$3.5T) | Dallas Fed (2026) |
| Oil price at disruption | ~$98/bbl (from $68 baseline) | Dallas Fed (2026) |
| Kilian (2009): supply shock → GDP recovery | ~3 years | Kilian, AER 2009 |
| Oil price elasticity of GDP (US, 4q) | −0.020 | Fed DSGE (2024) |
| GDP impact: 30% price increase | −0.5 pp | IMF rule |
| Peak Keynesian multiplier | 1.5 | Historical estimates |
| Keynesian multiplier (calibrated, oil shock) | 1.4 | Dallas Fed derivation |
| Inflation: 10% oil shock → headline | +0.15 pp | Fed DSGE (2024) |
| Iran oil sector share of GDP | ~25% | EIA CAB (2024) |
| Iran oil exports (2024) | 1.5 mb/d (down from 3.8 in 2017) | EIA (2024) |
| Iran sanctions GDP per capita impact | $8,000 → $5,000 (2012–2024) | World Bank |
| Richardson fatigue params (Iran–Iraq 1956–76) | Estimated via differential equations | Wagner et al. (1975) |
| Strategic reserve coverage | 109–124 days theoretical | IEA / Dallas Fed |
| US military (b): lower fatigue due to deeper resources | b < a (asymmetric) | Model assumption |

---

## Library Gap Candidates

**GAP-1: Kilian (2009) Structural VAR Oil Shock Decomposition**
- **Citation:** Kilian, L. (2009). Not All Oil Price Shocks Are Alike: Disentangling Demand and Supply Shocks in the Crude Oil Market. *American Economic Review*, 99(3), 1053–1069.
- **What it models:** Structural VAR separating oil supply disruptions from demand shocks. Produces impulse responses for oil production, real activity, and oil prices. Supply-driven shocks have qualitatively different GDP paths than demand-driven shocks.
- **Relevance: 4/5.** Hormuz is a supply-side disruption — the Kilian decomposition would correctly distinguish it from a demand-side price rise and produce more accurate transmission estimates.
- **Recommendation: CANDIDATE: FUTURE** — requires multi-equation VAR infrastructure not trivially expressible as a single-tick `update()` function. Higher payoff to implement once the API layer can expose multi-step estimation.

**GAP-2: Stopford (2009) Shipping Economics / Tanker Market Model**
- **Citation:** Stopford, M. (2009). *Maritime Economics* (3rd ed.). Routledge.
- **What it models:** Supply-demand equilibrium in the tanker freight market. Key outputs: day-rate spikes when supply disruption exceeds rerouting capacity; non-linear relationship between fleet utilization and freight rates.
- **Relevance: 3/5.** Direct relevance to marine insurer and tanker operator actors in the scenario. Porter captures the industry-level effect but not the freight rate spike dynamics.
- **Recommendation: CANDIDATE: ADD** — expressible as a `TheoryBase.update()` function: reads `strait__shipping_disruption` and `global__trade_volume`, writes `shipping__freight_rate` and `shipping__fleet_utilization`.

---

## Sources Reviewed

### arXiv
- [The 2023/24 VIEWS Prediction Challenge](https://arxiv.org/abs/2407.11045) — Hegre et al., 2024. Relevance: 4/5
  > Forecasting competition for armed conflict fatalities; establishes prediction methodology for military escalation consequences.
- [The 2006–2008 Oil Bubble and Beyond](https://arxiv.org/abs/0806.1170) — Sornette, Woodard & Zhou, 2008. Relevance: 4/5
  > Diagnoses oil price bubble dynamics and supply-demand divergence; relevant for price spike modeling.
- [Statistical Look at Reasons of Involvement in Wars](https://arxiv.org/abs/1508.06228) — Mackarov, 2015. Relevance: 4/5
  > COW-dataset analysis of political, economic, and religious factors driving conflict initiation.
- [Not All Oil Price Shocks Are Alike — Replication](https://arxiv.org/abs/2409.00769) — Ryan & Michieka, 2024. Relevance: 5/5
  > Replicates Kilian (2009) structural VAR; provides impulse response estimates for supply disruption scenarios.
- [Systemic Liquidity Contagion in Interbank Market](https://arxiv.org/abs/1912.13275) — Macchiati et al., 2019. Relevance: 3/5
  > Epidemic SIR-style model for financial contagion; validates SIR module applicability to economic shock propagation.

### Web / Policy
- [Dallas Fed: Strait of Hormuz Closure](https://www.dallasfed.org/research/economics/2026/0320) — 2026. Relevance: 5/5
  > Quantifies 20% supply disruption → −2.9pp GDP (annualized), oil to $98/bbl; primary calibration anchor.
- [Federal Reserve DSGE: Oil Price Shocks and Inflation](https://www.federalreserve.gov/econres/notes/feds-notes/oil-price-shocks-and-inflation-in-a-dsge-model-of-the-global-economy-20240802.html) — 2024. Relevance: 5/5
  > Provides oil price elasticity of GDP (−0.020 per 10% shock) and inflation transmission parameters.
- [Kilian (2009), AER 99(3)](https://www.aeaweb.org/articles?id=10.1257/aer.99.3.1053) — Relevance: 5/5
  > Canonical decomposition of oil supply vs demand shocks; motivates supply-side treatment in Keynesian module.
- [NBER w31263: Oil Prices, Monetary Policy and Inflation Surges](https://www.nber.org/papers/w31263) — Gagliardone & Gertler, 2023. Relevance: 4/5
  > Labor market parameters (ρ=0.96, bargaining=0.5) and Fed funds rate response to oil shocks.
- [EIA Iran Country Analysis Brief](https://www.eia.gov/international/content/analysis/countries_long/Iran/pdf/Iran%20CAB%202024.pdf) — EIA 2024. Relevance: 5/5
  > Iran oil production, export volumes, sanctions impact, and sector share of GDP.
- [The Influence of the Richardson Arms Race Model](https://link.springer.com/chapter/10.1007/978-3-030-31589-4_3) — 2019. Relevance: 4/5
  > Reviews Richardson parameter estimation literature; Iran–Iraq application from Wagner et al. (1975).
- [Richardson Complete Solution](https://journals.sagepub.com/doi/10.1177/073889427500100206) — Wagner, Perkins & Taagepera, 1975. Relevance: 4/5
  > Analytical solution to Richardson ODEs; stability conditions and equilibrium calculation.
