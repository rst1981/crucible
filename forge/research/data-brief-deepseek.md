# Data Brief: DeepSeek R1 / NVIDIA AI Infrastructure Shock
**Date:** 2026-03-26 | **Geo:** US / Global | **Timeframe:** Jan 2024 – Mar 2026 | **Skill:** /research-data

---

## Recommended Parameter Values

Direct mappings from data to SimSpec parameters:

| SimSpec Parameter | Value | Source | Notes |
|------------------|-------|--------|-------|
| `baseline_sentiment` | 0.72 | FRED:NASDAQCOM | NASDAQ at Jan 24 2025 pre-shock baseline; normalized to [0,1] proxy |
| `vix_baseline` | 14.85 | FRED:VIXCLS | 2025-01-24, day before DeepSeek disclosure |
| `vix_shock` | 17.90 | FRED:VIXCLS | 2025-01-27 intraday spike (+20.5% in 3 days) |
| `market_drop_pct` | −0.031 | FRED:NASDAQCOM | NASDAQ single-day move Jan 27 2025 (−3.07%) |
| `policy_uncertainty_baseline` | 167.0 | FRED:USEPUINDXM | Jan 2025 EPU index |
| `policy_uncertainty_peak` | 460.0 | FRED:USEPUINDXM | Apr 2025 (post-export controls, tariff war) |
| `semiconductor_ppi_trend` | −2.5 | FRED:PCU334413334413 | PPI decline Jan–Sep 2025 (30.72 → 29.56) |
| `risk_free_rate` | 0.0433 | FRED:FEDFUNDS / DGS10 | Mar 2026 effective funds rate / 10Y yield |
| `compute_efficiency_doubling_period` | 12.0 | Lu 2025 (arXiv:2501.02156) | AI efficiency doubling ~12 months per paper |
| `incumbent_platform_share` | 0.87 | Industry data (Bloomberg/IDC) | NVIDIA data center GPU market share peak 2024 |
| `hyperscaler_capex_2025_bn` | 315.0 | Industry consensus (web) | Aggregate hyperscaler AI capex 2025 ($B) |
| `hyperscaler_capex_2026_bn` | 600.0 | Industry consensus (web) | Forward 2026 hyperscaler capex guidance ($B) |
| `us_hightech_export_share` | 0.243 | WB:TX.VAL.TECH.MF.ZS | US high-tech as % of manufactured exports (2024) |
| `us_rnd_gdp_pct` | 0.0359 | WB:GB.XPD.RSDV.GD.ZS | US R&D expenditure % GDP (2022, rising) |
| `cn_rnd_gdp_pct` | 0.0256 | WB:GB.XPD.RSDV.GD.ZS | China R&D % GDP (2022, rising) |
| `cn_fdi_inflows_gdp` | 0.001 | WB:BX.KLT.DINV.WD.GD.ZS | China FDI inflows % GDP (2024) — near-zero; capital flight |
| `cn_hightech_export_share` | 0.263 | WB:TX.VAL.TECH.MF.ZS | China high-tech exports declining (31.3% 2020 → 26.3% 2024) |

---

## Key Economic Context

- **NVIDIA's dominance is structural but contested.** At 87% data center GPU share and $35.6B quarterly revenue (Q4 FY2025), NVIDIA's moat rests on CUDA ecosystem lock-in, not just hardware. DeepSeek demonstrated that frontier AI can be trained at 5–10% of prior cost estimates, directly threatening the incumbent's narrative of ever-growing compute requirements.

- **Policy uncertainty is the dominant macro variable.** The EPU index nearly tripled from Jan to Apr 2025 (167 → 460), driven by export controls on H100/H800 GPUs to China, tariff escalation in semiconductors, and CHIPS Act implementation. This dwarfs normal macro volatility and must be modeled as a discrete shock series, not background noise.

- **Hyperscaler capex is doubling — but the composition is shifting.** $315B in 2025 and $600B guided for 2026 represents genuine demand growth, but the mix is moving from raw GPU clusters toward inference optimization, custom silicon (Google TPU, AWS Trainium, Meta MTIA), and software stack investment. NVIDIA captures less of each incremental dollar than it did in the 2023–2024 training boom.

- **China's structural retreat from global tech integration.** China's FDI inflows collapsed from 1.89% of GDP in 2021 to 0.10% in 2024, and high-tech export share declined from 31.3% to 26.3% over the same period. This signals a domestic-first strategy that insulates DeepSeek-type labs from Western supply chains but also limits their GPU access — creating a capability race with asymmetric constraints.

- **Semiconductor PPI deflation is an early-warning signal.** Semiconductor PPI fell from 30.72 to 29.56 between Jan and Sep 2025 (−2.5%), suggesting pricing pressure at the component level. For a platform business like NVIDIA with 76%+ gross margins, the real risk is not PPI but compute efficiency gains that reduce total addressable cluster size — which DeepSeek directly demonstrated.

---

## Live Signals (last 90 days)

| Signal | Direction | Affected Parameter | Confidence |
|--------|-----------|--------------------|-----------|
| Tariff escalation: 125% US-China semiconductor tariffs (Apr 2025) | ↑ | `policy_uncertainty`, `cn_export_constraint` | High |
| NVIDIA Blackwell ramp: $11B data center chip revenue in single quarter | ↑ | `incumbent_platform_share`, `baseline_sentiment` | High |
| Meta, Microsoft disclose custom silicon programs accelerating | ↓ | `incumbent_platform_share` long-run | Med |
| DeepSeek R2 / V3-tier successors rumored; Chinese labs accelerating | ↑ | `compute_efficiency__efficiency_gain`, `narrative_contagion__bear_share` | Med |
| CHIPS Act $6.6B TSMC grant finalized (Apr 2025) | ↑ | `us_semiconductor_resilience`, `compute_efficiency__entry_barrier` | Med |
| Fed on hold at 4.25–4.50% through mid-2026 | → | `risk_free_rate`, discount rates | High |
| S&P AI subindex -8% QTD Mar 2026 amid macro uncertainty | ↓ | `baseline_sentiment`, `vix` | Med |

---

## Data Gaps

Parameters that could not be grounded in public data:

- `nvidia_cuda_lock_in_coefficient`: No public elasticity estimate for CUDA developer switching cost. **Recommend:** 0.70–0.85 range based on platform_tipping theory calibration (Rochet-Tirole 2003).
- `deepseek_r1_inference_cost_ratio`: Claimed 5–10% of GPT-4 training cost. **Recommend:** 0.07 midpoint; use 0.05–0.12 as MC perturbation band.
- `custom_silicon_share_2026`: Hyperscaler custom chip TAM share uncertain. **Recommend:** 15–25% of data center AI spend by end-2026.
- `narrative_beta_recovery_rate`: Post-shock bullish narrative re-infection rate for NVIDIA. No published estimate. **Recommend:** Use `narrative_contagion` defaults (beta_bull=0.25, gamma_bull=0.08) as calibrated baseline.

---

## FRED Series Used

| Series ID | Title | Latest Value | Date |
|-----------|-------|-------------|------|
| VIXCLS | CBOE Volatility Index (VIX) | 17.90 (shock) / ~19 (Mar 2026) | 2025-01-27 shock |
| NASDAQCOM | NASDAQ Composite Index | −3.07% single-day drop | 2025-01-27 |
| SP500 | S&P 500 Index | Correlated decline | 2025-01-27 |
| USEPUINDXM | Economic Policy Uncertainty Index | 460.0 | Apr 2025 peak |
| PCU334413334413 | PPI: Semiconductors & Electronic Components | 29.56 | Sep 2025 |
| IPG3361T3S | Industrial Production: Computers & Electronic Products | Tracked | 2025 |
| FEDFUNDS | Federal Funds Effective Rate | 4.33% | Mar 2026 |
| DGS10 | 10-Year Treasury Constant Maturity Rate | 4.33% | Mar 2026 |

---

## World Bank Indicators Used

| Code | Indicator | Country | Value | Year |
|------|-----------|---------|-------|------|
| TX.VAL.TECH.MF.ZS | High-technology exports (% of manufactured exports) | US | 24.3% | 2024 |
| TX.VAL.TECH.MF.ZS | High-technology exports (% of manufactured exports) | China | 26.3% | 2024 |
| GB.XPD.RSDV.GD.ZS | R&D expenditure (% of GDP) | US | 3.59% | 2022 |
| GB.XPD.RSDV.GD.ZS | R&D expenditure (% of GDP) | China | 2.56% | 2022 |
| BX.KLT.DINV.WD.GD.ZS | FDI net inflows (% of GDP) | US | 1.03% | 2024 |
| BX.KLT.DINV.WD.GD.ZS | FDI net inflows (% of GDP) | China | 0.10% | 2024 |
| NE.EXP.GNFS.ZS | Exports of goods and services (% of GDP) | US | 11.1% | 2024 |
