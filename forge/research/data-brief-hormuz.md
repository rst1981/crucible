# Data Brief: Strait of Hormuz Escalation
**Date:** 2026-03-26 | **Geo:** Iran, US, Gulf States, Global | **Timeframe:** 2024–2026 | **Skill:** /research-data

---

## Recommended Parameter Values

| SimSpec Parameter | Value | Source | Notes |
|------------------|-------|--------|-------|
| `global__oil_price` (normalized) | 0.68 | WTI $93.61/bbl Mar 2026; lo=$40 hi=$130 | Up ~$15-20 risk premium from Iran conflict |
| `strait__shipping_disruption` | 0.08 (start) → 0.63 (peak) | Lloyd's List Mar 2026 | ~200 tankers stranded at peak; baseline is minor harassment |
| `global__trade_volume` | 0.72 | Hormuz 20.9 mb/d, 20% global supply | EIA H1 2025 baseline |
| `iran__military_readiness` | 0.62 | Iran mil exp 2.01% GDP; political stability -1.694 | WB 2024; elevated but constrained by sanctions |
| `us__military_readiness` | 0.78 | US mil exp 3.42% GDP; carrier group deployed | WB 2024 |
| `saudi__military_readiness` | 0.55 | Saudi mil exp 7.30% GDP | WB 2024; highest % in region but defensive posture |
| `iran__economic_pressure` | 0.75 | Iran GDP $475B; oil rents 18.27% GDP; fuel exports 56.36% | WB 2024/2022; high sanctions exposure |
| `iran__domestic_stability` | 0.40 | WGI political stability -1.694 (normalized) | WB 2023; bottom decile globally |
| `global__economic_stress` | 0.30 | US GDP Q4 2025 +0.7% (ann.); slowing | BEA Q4 2025 second estimate |
| `keynesian.multiplier` | 1.4 | 20% supply disruption → -2.9pp GDP (ann.) | Dallas Fed 2026 |
| `sir.beta` (economic contagion) | 0.25 | Korea trade 84.64% GDP; Japan 46.41%; India 44.65% | WB 2024; high transmission via trade exposure |
| `richardson.k` (Iran reactivity) | 0.35 | Iran political stability -1.694 vs US 0.029 | Asymmetric threat perception confirmed |
| `richardson.a` (Iran fatigue) | 0.30 | Iran GDP $475B; sanctions pressure 0.75 | Economic constraints bind harder on Iran |
| `richardson.g` (Iran grievance) | 0.08 | Fuel exports 56.36%; oil rents 18.27% GDP | Structural grievance from sanctions regime |

---

## Key Economic Context

- **Hormuz is the world's most critical energy chokepoint.** 20.9 mb/d flow (H1 2025) = ~20% of global petroleum consumption. Alternative pipeline capacity covers only 3.5–5.5 mb/d — leaving a 15+ mb/d shortfall if fully closed.

- **Iran's economy is maximally leveraged.** GDP $475B, oil rents 18.27% of GDP, fuel exports 56.36% of merchandise exports. Political stability score -1.694 (bottom 5% globally). Sanctions have driven per-capita GDP from $8,000 (2012) to ~$5,000 (2024). Iran's grievance parameter (g=0.08) is structurally justified.

- **Gulf state oil dependency is acute.** Saudi Arabia oil rents 23.69% GDP, UAE 15.67%, Qatar 15.28%. Saudi military expenditure 7.30% GDP (highest in region) reflects the stakes.

- **Oil importers are highly exposed.** Korea trade/GDP 84.64%, Japan 46.41%, India 44.65%. A prolonged disruption creates severe contagion pressure. SIR beta=0.25 is conservative given these exposure levels.

- **US economy entering the scenario from weakness.** US GDP Q4 2025 just 0.7% annualized (second estimate, down from 1.4% advance). Government shutdown subtracted ~1.0pp. Limits US tolerance for extended military engagement.

---

## Live Signals (as of 2026-03-26)

| Signal | Direction | Affected Parameter | Confidence |
|--------|-----------|--------------------|-----------|
| WTI $93.61 (+3.6% today); $15-20/bbl Iran risk premium baked in | ↑ | `global__oil_price` | High |
| ~200 tankers stranded; strait effectively closed since late Feb 2026 | ↑↑ | `strait__shipping_disruption` | High |
| Iran rejected 15-point US peace plan (Mar 26 2026) | ↓ | `global__negotiation_progress` | High |
| Brent up ~50% since Jan 2026; highest since Sep 2023 | ↑ | `global__oil_price`, `global__economic_stress` | High |
| Baltic Dry Index 2,038 pts, up 135% YoY | ↑ | `porter__rivalry`, `shipping__freight_rate` | High |
| US GDP Q4 2025 revised down to +0.7% annualized | ↓ | `global__economic_stress` baseline | Medium |
| 2026 oil forecast: >$95/bbl through May, then declining to ~$70 by year-end | → | Validates shock schedule arc | Medium |

> **Critical note:** The simulation was designed with a Jan 2025 start date, but live data confirms the crisis arc is playing out in early 2026. The shock schedule and parameter values are well-grounded in current reality — the scenario is not hypothetical.

---

## Data Gaps

- `us__military_readiness` (0.78): No single public series for naval readiness posture. Derived from military expenditure % GDP (3.42%) + carrier group deployment reports. Treat as directionally correct, ±0.05.
- `zartman__mediator_present`: No public data on Oman backchannel status. Live signal (Iran rejected peace plan) suggests mediator is present but ineffective as of Mar 26 2026.
- `porter__*` (shipping industry parameters): No real-time structural data. BDI +135% YoY is a directional signal for `porter__rivalry` and `porter__supplier_power` — both should be higher than baseline params suggest.
- Richardson parameters (k, l, a, b): No declassified time series for Iran/US military expenditure at monthly frequency. WB annual data used for direction; magnitudes from literature (Wagner et al. 1975, Iran-Iraq calibration).

---

## FRED Series Used

| Series ID | Title | Latest Value | Date |
|-----------|-------|-------------|------|
| DCOILWTICO | WTI Crude Oil Spot Price | $93.61/bbl | 2026-03-26 |
| DCOILBRENTEU | Brent Crude Oil Spot Price | $106.81/bbl | 2026-03-26 |
| GDP | US Real GDP Growth (annualized) | +0.7% | Q4 2025 |
| BDI | Baltic Dry Index | 2,038 | 2026-03-16 |

---

## World Bank Indicators Used

| Code | Indicator | Country | Value | Year |
|------|-----------|---------|-------|------|
| MS.MIL.XPND.GD.ZS | Military expenditure % GDP | US | 3.42% | 2024 |
| MS.MIL.XPND.GD.ZS | Military expenditure % GDP | Iran | 2.01% | 2024 |
| MS.MIL.XPND.GD.ZS | Military expenditure % GDP | Saudi Arabia | 7.30% | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | US | $28.75T | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | Iran | $475B | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | Saudi Arabia | $1.24T | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | Japan | $4.03T | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | Korea | $1.88T | 2024 |
| NY.GDP.MKTP.CD | GDP (current USD) | India | $3.91T | 2024 |
| TX.VAL.FUEL.ZS.UN | Fuel exports % merchandise | Iran | 56.36% | 2022 |
| PV.EST | Political Stability (WGI) | Iran | -1.694 | 2023 |
| PV.EST | Political Stability (WGI) | US | 0.029 | 2023 |
| PV.EST | Political Stability (WGI) | Saudi Arabia | -0.213 | 2023 |
| NY.GDP.PETR.RT.ZS | Oil rents % GDP | Saudi Arabia | 23.69% | 2021 |
| NY.GDP.PETR.RT.ZS | Oil rents % GDP | Iran | 18.27% | 2021 |
| NY.GDP.PETR.RT.ZS | Oil rents % GDP | UAE | 15.67% | 2021 |
| NE.TRD.GNFS.ZS | Trade % GDP | Korea | 84.64% | 2024 |
| NE.TRD.GNFS.ZS | Trade % GDP | Japan | 46.41% | 2024 |
| NE.TRD.GNFS.ZS | Trade % GDP | India | 44.65% | 2024 |
