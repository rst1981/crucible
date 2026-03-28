# Theory Brief: Walla Walla Wine Region — Label Owner Replanting Strategy Under Climate Shift
**Date:** 2026-03-27 | **Depth:** 12 sources reviewed | **Skill:** /research-theory
**Focus:** Revenue continuity simulation (Simulation 1); quality preservation to follow (Simulation 2)

---

## Recommended Theory Stack

| Priority | Module | Rationale | Key Parameters to Set |
|----------|--------|-----------|----------------------|
| 1 | `grapevine_gdd_phenology` *(NEW)* | Core climate driver — GDD accumulation determines varietal viability | `GDD_optimal=2000`, `warming_rate=0.04/yr`, `T_base=10` |
| 2 | `smoke_taint_crop_disruption` *(NEW)* | Primary revenue shock — stochastic vintage wipe events | `smoke_prob_base=0.05`, `prob_rate=0.005/yr`, `revenue_per_acre=8000` |
| 3 | `real_options_agri_adapt` *(NEW)* | Replanting decision timing under GDD/smoke uncertainty | `replant_cost=12000`, `payback_years=7`, `exercise_threshold=0.3` |
| 4 | `bordeaux_wine_quality` *(NEW)* | Climate → quality score → price (needed for Sim 2; included as passive) | `temp_sensitivity=0.616`, `harvest_rain_penalty=0.00386` |
| 5 | `hotelling_cpr` | Water rights constraint as snowpack declines — senior/junior conflict | `depletion_rate=0.03/yr`, `extraction_cost_rise=0.15` |
| 6 | `regulatory_shock` | Water curtailment orders, AVA policy changes | `shock_prob=0.1`, `shock_severity=0.4` |

---

## Composability Note

```
grapevine_gdd_phenology
    ↓ quality, GDD_normalized
bordeaux_wine_quality ──→ price_premium, quality_score
    ↓ quality_score
smoke_taint_crop_disruption → revenue_loss (overrides quality when taint event fires)
    ↓ revenue_loss
real_options_agri_adapt ← (reads quality_degradation + cash_flow_stress)
    ↓ replant_signal
hotelling_cpr → water_availability
    ↓ water_stress
regulatory_shock → curtailment_event
```

For **Sim 1 (revenue continuity):** `smoke_taint_crop_disruption` and `hotelling_cpr` are primary.
`real_options_agri_adapt` fires when cumulative cash flow stress exceeds threshold.

For **Sim 2 (quality preservation):** `bordeaux_wine_quality` and `grapevine_gdd_phenology` are primary.
`real_options_agri_adapt` fires when quality score drops below critic threshold (92 pts ≈ 0.72 normalized).

---

## Calibration Anchors

| Parameter | Value | Source |
|-----------|-------|--------|
| Walla Walla AVA current GDD | ~2100 GDD/season | Jones & Davis (2000); WAWU data |
| GDD projection 2040 | 2500–2800 GDD | IPCC AR6 PNW regional downscaling |
| Merlot quality degradation threshold | >2400 GDD | Jones & Davis (2000) |
| Wildfire smoke event probability (pre-2010) | 5%/year | USFS wildfire incident data |
| Wildfire smoke event probability (2030s) | 15%/year | Climate Central projections |
| 2020 Columbia Valley crop loss from smoke | 15–30% | Wine Business Monthly |
| Replanting cost per acre | $8,000–$15,000 | Washington State wine industry surveys |
| Replanting lead time | 5–7 years | Viticulture practice standard |
| Walla Walla River snowpack decline | −30 to −40% by 2040 | USGS Pacific Northwest hydrology |
| Senior water rights litigation active | Yes | WA Dept. of Ecology, 2023 |
| Ashenfelter temp coefficient | β = 0.616 | Ashenfelter (1989) JSTOR:2555489 |
| Premium label revenue per acre (top tier) | $8,000–$25,000 | Leonetti/L'Ecole comparable |

---

## Library Gap Candidates

All gaps identified below were built and hot-loaded this session:

| Module | Paper | Status |
|--------|-------|--------|
| `grapevine_gdd_phenology` | Behnamian & Fogh (2025) arXiv:2510.09702; Jones & Davis (2000) | **AUTO-APPROVED — in library** |
| `bordeaux_wine_quality` | Ashenfelter (1989) JSTOR:2555489; Oczkowski (2001) | **AUTO-APPROVED — in library** |
| `real_options_agri_adapt` | Dixit & Pindyck (1994) Princeton University Press | **AUTO-APPROVED — in library** |
| `smoke_taint_crop_disruption` | USFS data; Wine Business Monthly 2020 | **AUTO-APPROVED — in library** |

---

## Sources Reviewed

### arXiv
- [Interval-Censored Survival Analysis of Grapevine Phenology](https://arxiv.org/abs/2510.09702) — Behnamian & Fogh, 2025. Relevance: 5/5
  > Thermal controls on flowering and ripening in Vitis vinifera; GDD-based survival model with Winkler region classifications.

- [A multi-agent RL model of common-pool resource appropriation](https://arxiv.org/abs/1707.06600v2) — Perolat et al., 2017. Relevance: 3/5
  > MARL model of CPR appropriation under self-interest — relevant for multi-winery water rights conflict. `hotelling_cpr` covers this.

### Literature (SSRN blocked; sourced via abstract databases)
- **Ashenfelter (1989)** "Bordeaux Wine Vintage Quality and the Weather" — JSTOR 2555489. Relevance: 5/5
  > Canonical hedonic regression linking summer temp (+), winter rain (+), harvest rain (−) to price.

- **Jones & Davis (2000)** "Climate influences on grapevine phenology, grape composition, and wine production" — Am. J. Enol. Vitic. Relevance: 5/5
  > Empirical GDD thresholds for Bordeaux varietals; quality degradation above 2400 GDD confirmed.

- **Dixit & Pindyck (1994)** "Investment Under Uncertainty" — Princeton. Relevance: 5/5
  > Real options framework for irreversible investment; optimal timing under stochastic climate forcing.

- **Winkler (1974)** "General Viticulture" — UC Press. Relevance: 4/5
  > GDD climate region classification system; foundational calibration anchor.

---

## SimSpec Stub (Sim 1 — Revenue Continuity)

```python
theories = [
    TheoryRef("grapevine_gdd_phenology",     priority=1.0),
    TheoryRef("smoke_taint_crop_disruption", priority=0.9),
    TheoryRef("real_options_agri_adapt",     priority=0.8),
    TheoryRef("bordeaux_wine_quality",       priority=0.6),  # passive for Sim 1
    TheoryRef("hotelling_cpr",               priority=0.7),
    TheoryRef("regulatory_shock",            priority=0.5),
]

parameters = {
    # Climate trajectory
    "grapevine_gdd_phenology__temperature":    0.52,   # ~current Walla Walla mean
    "grapevine_gdd_phenology__season_fraction": 0.0,
    "warming_rate": 0.04,                              # GDD/yr increase
    # Smoke taint
    "smoke_taint_crop_disruption__smoke_prob_base": 0.05,
    "smoke_taint_crop_disruption__prob_annual_increase": 0.005,
    "smoke_taint_crop_disruption__revenue_per_acre": 12000,  # top-tier label
    # Water / CPR
    "hotelling_cpr__stock": 0.75,
    "hotelling_cpr__depletion_rate": 0.03,
    # Real options
    "real_options_agri_adapt__replant_cost": 12000,
    "real_options_agri_adapt__exercise_threshold": 0.3,
}
```
