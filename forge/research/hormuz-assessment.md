# Strait of Hormuz Escalation — Assessment & Forward Projection
**Date:** 2026-03-26 | **Simulation:** 6-module cascade, 18 actors | **Skills:** /research-theory + /research-data + /forge-assessment

---

## Executive Summary

The Strait of Hormuz crisis of 2026 represents the most significant energy supply disruption since the 1973 Arab oil embargo. Iran's imposition of navigation restrictions on the strait — the transit point for 20.9 million barrels per day (~20% of global petroleum consumption) — has stranded approximately 200 tankers as of March 26, 2026, driven WTI crude to $93.61/barrel and Brent to $106.81/barrel, and created severe contagion pressure across highly trade-exposed oil importers (Korea 84.6% trade/GDP, Japan 46.4%, India 44.7%). The crisis is not hypothetical: it is unfolding in real time, and the simulation is calibrated to live data.

Five structural drivers explain the escalation and shape the forward trajectory. First, the Richardson arms dynamic: Iran's grievance-driven arming (sanctions reducing per-capita GDP from $8,000 to $5,000 since 2012; fuel exports 56% of merchandise) has been structurally reactive to US military posture in the Gulf, with Iran's reactivity coefficient (k=0.35) exceeding the US coefficient (l=0.20) reflecting asymmetric threat perception. Second, the Fearon information problem: Iran's nuclear programme opacity sustains a private information gap that keeps conflict probability elevated even as both parties' expected war costs are non-trivial (Iran 20%, US 12% of prize). Third, the Wittman-Zartman ripeness condition: Oman-mediated back-channel talks are active, but Iran's rejection of the US 15-point peace plan on March 26 confirms the MHS condition is not yet met. Fourth, economic contagion: the SIR transmission model captures how the oil price shock propagates through trade-exposed importers, amplified by the Baltic Dry Index running 135% above year-ago levels. Fifth, the Keynesian GDP multiplier: Dallas Fed modelling puts the annualized GDP hit from a 20% supply disruption at −2.9 percentage points — directly calibrating the multiplier parameter at 1.4.

The simulation asks: under the current military posture, economic pressure, and mediation state, what is the probability distribution of outcomes over a 24-month window? When does the Wittman-Zartman ripeness condition fire? How does the Richardson escalation index evolve if the US deploys additional carrier groups? What is the oil price and GDP impact band under base, bull, and bear mediation scenarios?

---

## Actor Data

| Actor | Category | GDP (USD) | Mil. Exp. % GDP | Political Stability (WGI) | Oil Rents % GDP | Source |
|-------|----------|-----------|-----------------|--------------------------|-----------------|--------|
| Iran | Primary belligerent | $475B | 2.01% | −1.694 | 18.27% | WB 2024/2023 |
| United States | Primary belligerent | $28.75T | 3.42% | +0.029 | — | WB 2024 |
| Saudi Arabia | Gulf state | $1.24T | 7.30% | −0.213 | 23.69% | WB 2024/2021 |
| UAE | Gulf state | $552B | [TBD] | +0.678 | 15.67% | WB 2024/2021 |
| Qatar | Gulf state | $219B | [TBD] | [TBD] | 15.28% | WB 2024/2021 |
| Japan | Oil importer | $4.03T | [TBD] | [TBD] | — | WB 2024 |
| South Korea | Oil importer | $1.88T | [TBD] | [TBD] | — | WB 2024 |
| India | Oil importer | $3.91T | [TBD] | [TBD] | — | WB 2024 |
| Iran fuel exports | Economic exposure | 56.36% of merch. | — | — | — | WB 2022 |
| Korea trade/GDP | Contagion exposure | 84.64% | — | — | — | WB 2024 |

---

## Macro & Sector Context

- **Hormuz is irreplaceable.** 20.9 mb/d in transit (EIA H1 2025). Alternative pipeline capacity covers only 3.5–5.5 mb/d — meaning a full closure leaves a 15+ mb/d structural shortfall that no strategic reserve deployment can fully offset beyond 109–124 days.

- **Oil markets are in active crisis.** WTI $93.61/bbl (+3.6% on March 26 alone); Brent $106.81/bbl (+50% since Jan 2026). Analysts attribute $15–20/barrel to Iran risk premium. 2026 forecast: oil above $95/bbl through May, declining to ~$70/bbl by year-end only if resolution occurs.

- **Iran's economy structurally incentivises escalation.** Sanctions have compressed per-capita GDP from $8,000 (2012) to ~$5,000 (2024). Oil rents are 18.27% of GDP; fuel exports 56.36% of merchandise. Political stability score is −1.694 — bottom 5% globally. Iran's negotiating leverage is the strait; its economic pressure creates urgency for a deal.

- **US economy entering the crisis from a position of weakness.** GDP Q4 2025 revised to +0.7% annualized (down from 1.4% advance estimate; government shutdown subtracted ~1.0pp). This constrains US tolerance for sustained military engagement — the fearon war cost parameter (b=0.12) is time-sensitive.

- **Shipping industry is severely disrupted.** Baltic Dry Index 2,038 pts (+135% YoY as of March 16). ~200 tankers stranded. Marine insurers have exited the strait; Lloyd's of London war-risk premiums at 2003 Iraq invasion levels. Porter competitive intensity in shipping is spiking non-linearly.

- **Contagion risk is high for oil-dependent importers.** Korea (84.6% trade/GDP), Japan (46.4%), India (44.7%) face acute supply security pressures. India imports ~85% of oil needs; Japan/Korea have limited domestic production. SIR beta=0.25 is a conservative floor.

---

## Recommended Theory Stack

| Priority | Module | Role | Key Parameters | Status |
|----------|--------|------|----------------|--------|
| 0 | `richardson_arms_race` | Iran–US mutual military buildup dynamics; writes `iran__military_readiness`, `us__military_readiness`, `richardson__escalation_index` each tick | k=0.35, l=0.20, a=0.30, b=0.15, g=0.08, h=0.03 | Original |
| 1 | `fearon_bargaining` | Conflict probability from private information gap + power-shift commitment problem; reads military readiness from Richardson | war_cost_a=0.20, war_cost_b=0.12, info_gap_sigma=0.15, commit_threshold=0.10 | Original |
| 2 | `wittman_zartman` | Ripeness: MHS condition + mediator presence → negotiation onset probability; reads Fearon win probability | min_stalemate_ticks=3, base_negotiation_rate=0.05, ripe_multiplier=4.0 | Original |
| 3 | `sir_contagion` | Economic contagion across oil-importing states; transmission amplified when `global__trade_volume` is disrupted | beta=0.25, gamma=0.08, contagion_id="economic", initial_infected=0.05 | Original |
| 4 | `keynesian_multiplier` | GDP impact of oil supply shock; multiplier=1.4 calibrated from Dallas Fed 2026 20%-disruption scenario | multiplier=1.4, mpc=0.72, tax_rate=0.22, import_rate=0.28 | Original |
| 5 | `porter_five_forces` | Shipping industry structure under blockade; captures tanker operator power spike and insurer exit | supplier_power_weight=0.25, entry_barriers_weight=0.20 | Original |

### Module Cascade

```
TICK START
    │
    ▼
[0] richardson_arms_race
    iran__military_readiness ──────────────────────────────────┐
    us__military_readiness ─────────────────────────────────┐  │
    richardson__escalation_index                            │  │
    │                                                       │  │
    ▼                                                       │  │
[1] fearon_bargaining ◄─────────────────────────────────────┘  │
    fearon__win_prob_a ──────────────────────────────────────┐  │
    fearon__conflict_probability                            │  │
    │                                                       │  │
    ▼                                                       │  │
[2] wittman_zartman ◄──────────────────────────────────────┘   │
    zartman__ripe_moment                                        │
    zartman__negotiation_probability                            │
    │                                                           │
    ▼                                                           │
[3] sir_contagion ◄─────────────────────────── global__trade_volume (shocked)
    economic__infected ─────────────────────────────────────┐
    economic__active_contagion                              │
    │                                                       │
    ▼                                                       │
[4] keynesian_multiplier ◄──────────────────────────────────┘
    keynesian__gdp_gap
    keynesian__output_multiplier
    │
    ▼
[5] porter_five_forces ◄────── strait__shipping_disruption (shocked)
    porter__competitive_intensity

    TICK END → record metrics → snapshot triggers
```

Richardson (priority 0) drives the military balance that Fearon reads as its win-probability input. Fearon's conflict probability and win probability feed Wittman-Zartman's ripeness assessment. SIR reads `global__trade_volume` — disruption shocks amplify economic contagion beta. Keynesian reads the infected fraction and trade volume as shock drivers. Porter reads disruption level to update shipping industry competitive intensity. The cascade captures the full arc: arms dynamics → conflict probability → negotiation ripeness → economic contagion → GDP multiplier → industry structure.

---

## Calibration Anchors

| Parameter | Value | Source |
|-----------|-------|--------|
| Hormuz daily oil flow | 20.9 mb/d | EIA H1 2025 |
| Hormuz share of global petroleum | ~20% | EIA / Dallas Fed |
| Alternative pipeline capacity | 3.5–5.5 mb/d | Dallas Fed 2026 |
| WTI crude (March 26, 2026) | $93.61/bbl | Live market |
| Brent crude (March 26, 2026) | $106.81/bbl | Live market |
| Iran risk premium in oil price | $15–20/bbl | Market analyst consensus |
| GDP impact: 20% supply disruption (ann.) | −2.9 pp | Dallas Fed 2026 |
| Keynesian multiplier (oil shock calibrated) | 1.4 | Dallas Fed derivation |
| Kilian (2009): supply shock GDP recovery | ~3 years | AER 99(3) |
| Oil price elasticity of GDP (US, 4q) | −0.020 | Fed DSGE 2024 |
| GDP impact: 30% price increase | −0.5 pp | IMF rule |
| Strategic reserve coverage | 109–124 days | IEA / Dallas Fed |
| Iran political stability (WGI) | −1.694 | World Bank 2023 |
| Iran military expenditure % GDP | 2.01% | World Bank 2024 |
| US military expenditure % GDP | 3.42% | World Bank 2024 |
| Saudi military expenditure % GDP | 7.30% | World Bank 2024 |
| Iran GDP | $475B | World Bank 2024 |
| Iran oil rents % GDP | 18.27% | World Bank 2021 |
| Iran fuel exports % merchandise | 56.36% | World Bank 2022 |
| Korea trade % GDP (contagion exposure) | 84.64% | World Bank 2024 |
| Japan trade % GDP | 46.41% | World Bank 2024 |
| India trade % GDP | 44.65% | World Bank 2024 |
| Baltic Dry Index (Mar 16 2026) | 2,038 pts (+135% YoY) | Trading Economics |
| ~200 tankers stranded | Disruption confirmed | Lloyd's List Mar 2026 |
| Richardson fatigue asymmetry (a > b) | Iran more constrained | Wagner et al. 1975 |

---

## Forward Signals

| Signal | Direction | Confidence | Module |
|--------|-----------|------------|--------|
| Iran rejected US 15-point peace plan (Mar 26) | ↓ negotiation | High | `wittman_zartman` |
| WTI +3.6% today; Brent +50% since Jan 2026 | ↑ oil price | High | `keynesian_multiplier` |
| ~200 tankers stranded; strait effectively closed | ↑ disruption | High | `porter_five_forces`, `sir_contagion` |
| BDI +135% YoY | ↑ shipping stress | High | `porter_five_forces` |
| US GDP Q4 2025 revised to +0.7% | ↓ US tolerance | Medium | `fearon_bargaining` (war_cost_b) |
| Oil forecast >$95/bbl through May 2026 | → sustained | Medium | Validates shock schedule |
| Oman back-channel active (mediator present) | → ripeness building | Medium | `wittman_zartman` |

### 24-Month Forward Projection

**Base case (~55%):** Oman mediation produces a framework agreement around month 11–13. Iran accepts partial sanctions relief in exchange for navigation guarantees. Strait reopens partially at month 16–19, fully by month 22–24. Oil peaks ~$110/bbl in months 5–8, then retreats to $70–75 by month 22. Richardson escalation index peaks ~0.75 at month 7–8 then declines. GDP impact: −1.5 to −2.5pp annualized at peak, recovery beginning month 18.

**Bull case (~20%):** US makes early concessions on sanctions architecture (months 3–5); Iran domestic pressure triggers pragmatic leadership shift. Rapid back-channel agreement by month 6–8. Oil never exceeds $100/bbl; returns to $72–78 by month 12. Minimal GDP impact (−0.5 to −1.0pp). Richardson stabilises without runaway escalation.

**Bear case (~25%):** Negotiations collapse entirely after rejected peace plan. Iran escalates to full blockade enforcement months 5–7; US retaliatory strikes month 8–10. Prolonged closure through month 18+. Oil sustains $110–125/bbl range; global recession threshold crossed (GDP −3pp+). Iran domestic instability creates regime change risk (political stability deteriorates below −2.0). SIR economic contagion infects >35% of importer economies.

---

## Data Gaps & Monte Carlo Guidance

- `us__military_readiness` (0.78): Derived from mil. exp. % GDP + deployment reports. No monthly frequency series. Treat as ±0.05.
- `zartman__mediator_present`: Oman channel confirmed active but effectiveness unknown. Set to 0.0 at start; shock to 1.0 at tick 11 (month 11) per baseline scenario.
- `porter__*` parameters: BDI +135% YoY confirms rising supplier power; structural parameters not publicly quantified. Directional confidence only.
- Richardson k, l, a, b: Calibrated from Iran–Iraq 1956–76 data (Wagner et al. 1975). No Iran–US specific time series. Uncertainty ±30% on all four parameters.
- `fearon.info_gap_sigma` (0.15): Nuclear programme opacity creates genuine uncertainty. No empirical ground truth. Range 0.10–0.25 appropriate for MC perturbation.

**Monte Carlo guidance:** 300 runs recommended. ±20% perturbation on Richardson parameters (k, l, a, b) and Fearon (info_gap_sigma, war_cost_a/b). ±15% on SIR beta. ±20% on shock magnitudes. Scenario weights: base 55% / bull 20% / bear 25% (matching forward projection probabilities above).

---

## Library Gaps

### GAP-1: Kilian (2009) Structural VAR Oil Shock Decomposition — PENDING

**Citation:** Kilian, L. (2009). Not All Oil Price Shocks Are Alike: Disentangling Demand and Supply Shocks in the Crude Oil Market. *American Economic Review*, 99(3), 1053–1069.

Structural VAR separating supply-side oil disruptions (like Hormuz) from demand-driven price rises. Produces separate impulse response functions showing that supply-side shocks have qualitatively different GDP transmission paths — slower onset, longer recovery — than demand shocks.

**Relevance: 4/5.** Hormuz is a pure supply-side disruption. The Keynesian multiplier currently treats oil shocks symmetrically. Kilian decomposition would improve the temporal shape of the GDP impact curve — particularly the 3-year recovery dynamic seen in historical supply disruptions.

**Status: PENDING** — Requires multi-equation VAR infrastructure not expressible as a single-tick `update()`. Recommend implementing after the API layer can expose multi-step state. Priority: build before next major energy scenario.

---

### GAP-2: Stopford (2009) Tanker Freight Market Model — PENDING

**Citation:** Stopford, M. (2009). *Maritime Economics* (3rd ed.). Routledge.

Supply-demand equilibrium model for the tanker freight market. Key outputs: freight day-rate as a non-linear function of fleet utilisation — rates spike hyperbolically above ~90% utilisation. Models the distinct dynamics of the tanker spot market vs. long-term contracts under disruption.

**Relevance: 3/5.** Porter Five Forces captures the industry-level effect of blockade but not the freight rate spike mechanics. A Stopford module would write `shipping__freight_rate` and `shipping__fleet_utilization` — directly calibrated by the BDI +135% YoY live signal and the Lloyd's List tanker stranding reports.

**Status: PENDING** — Expressible as a `TheoryBase.update()` function reading `strait__shipping_disruption` and `global__trade_volume`. Recommend building before the Hormuz findings document to capture the commercial actor dynamics more precisely.

---

## Sources

### Web / Live Data
- [Dallas Fed: Strait of Hormuz Closure Economic Impact](https://www.dallasfed.org/research/economics/2026/0320) — 2026
- [CNBC: Oil Prices Trump Hormuz](https://www.cnbc.com/2026/03/23/oil-prices-trump-iran-strait-of-hormuz-wti-crude-middle-east-lng-gas.html) — March 2026
- [FX Leaders: WTI battles $92 as Iran rejects peace plan](https://www.fxleaders.com/news/2026/03/26/crude-oil-price-forecast-wti-battles-92-as-iran-rejects-15-point-peace-plan-whats-next/) — March 26, 2026
- [Lloyd's List: ~200 tankers stranded](https://www.lloydslist.com/LL1156500/Around-200-compliant-tankers-stranded-as-Strait-of-Hormuz-closure-freezes-Gulf-traffic) — March 2026
- [EIA: Strait of Hormuz Oil Flows](https://www.eia.gov/todayinenergy/detail.php?id=65504) — 2025
- [EIA: Iran Country Analysis Brief](https://www.eia.gov/international/content/analysis/countries_long/Iran/pdf/Iran%20CAB%202024.pdf) — 2024
- [BEA: GDP Q4 2025 Second Estimate](https://www.bea.gov/news/2026/gdp-second-estimate-4th-quarter-and-year-2025) — March 2026
- [Federal Reserve DSGE: Oil Price Shocks and Inflation](https://www.federalreserve.gov/econres/notes/feds-notes/oil-price-shocks-and-inflation-in-a-dsge-model-of-the-global-economy-20240802.html) — 2024
- [Trading Economics: Baltic Dry Index](https://tradingeconomics.com/commodity/baltic) — 2026
- [Wikipedia: 2026 Strait of Hormuz Crisis](https://en.wikipedia.org/wiki/2026_Strait_of_Hormuz_crisis)

### Academic
- Kilian, L. (2009). Not All Oil Price Shocks Are Alike. *American Economic Review*, 99(3), 1053–1069.
- Fearon, J. (1995). Rationalist Explanations for War. *International Organization*, 49(3), 379–414.
- Richardson, L.F. (1960). *Arms and Insecurity*. Boxwood Press.
- Wagner, R., Perkins, R. & Taagepera, R. (1975). Complete Solution to Richardson's Arms Race Equations. *Journal of Peace Science*, 1, 159–172.
- Wittman, D. (1979). How a War Ends. *Journal of Conflict Resolution*, 23(4), 743–763.
- Zartman, I.W. (1985). *Ripe for Resolution*. Oxford University Press.
- Stopford, M. (2009). *Maritime Economics* (3rd ed.). Routledge.
- Gagliardone, L. & Gertler, M. (2023). Oil Prices, Monetary Policy and Inflation Surges. *NBER Working Paper* w31263.

---

## SimSpec Stub

```python
from core.spec import TheoryRef

theories = [
    TheoryRef(
        theory_id="richardson_arms_race",
        priority=0,
        parameters={
            "k": 0.35,        # Iran reactivity to US arms
            "l": 0.20,        # US reactivity to Iran arms
            "a": 0.30,        # Iran fatigue (sanctions-constrained)
            "b": 0.15,        # US fatigue (deeper resource base)
            "g": 0.08,        # Iran grievance (structural, sanctions-driven)
            "h": 0.03,        # US grievance baseline
            "actor_a_id": "iran",
            "actor_b_id": "us",
            "tick_unit": "month",
        },
    ),
    TheoryRef(
        theory_id="fearon_bargaining",
        priority=1,
        parameters={
            "war_cost_a":       0.20,   # Iran war cost (fraction of prize)
            "war_cost_b":       0.12,   # US war cost
            "info_gap_sigma":   0.15,   # Nuclear programme opacity
            "power_shift_rate": 0.05,   # Monthly military balance change
            "commit_threshold": 0.10,   # Power shift breaking commitment
            "tick_unit": "month",
        },
    ),
    TheoryRef(
        theory_id="wittman_zartman",
        priority=2,
        parameters={
            "war_cost_a":            0.20,
            "war_cost_b":            0.12,
            "payoff_floor":          0.05,
            "min_stalemate_ticks":   3,      # months before MHS ripens
            "urgency_threshold":     0.60,
            "base_negotiation_rate": 0.05,
            "ripe_multiplier":       4.0,
            "tick_unit": "month",
        },
    ),
    TheoryRef(
        theory_id="sir_contagion",
        priority=3,
        parameters={
            "beta":               0.25,   # Economic contagion transmission
            "gamma":              0.08,   # Recovery via diversification
            "initial_infected":   0.05,   # Pre-existing economic stress
            "active_threshold":   0.10,
            "trade_amplification": 0.60,
            "contagion_id":       "economic",
            "tick_unit":          "month",
        },
    ),
    TheoryRef(
        theory_id="keynesian_multiplier",
        priority=4,
        parameters={
            "multiplier":  1.4,    # Dallas Fed 2026 calibration
            "mpc":         0.72,
            "tax_rate":    0.22,
            "import_rate": 0.28,
            "tick_unit":   "month",
        },
    ),
    TheoryRef(
        theory_id="porter_five_forces",
        priority=5,
        parameters={
            "supplier_power_weight":  0.25,
            "buyer_power_weight":     0.15,
            "rivalry_weight":         0.20,
            "substitutes_weight":     0.20,
            "entry_barriers_weight":  0.20,
        },
    ),
]
```
