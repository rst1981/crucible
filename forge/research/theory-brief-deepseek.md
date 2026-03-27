# Theory Brief: DeepSeek R1 — NVIDIA Shock & AI Platform Disruption
**Date:** 2026-03-26 | **Depth:** 12 sources reviewed | **Skill:** /research-theory v1.1.0

---

## Recommended Theory Stack

For this scenario, activate these Crucible modules (in priority order):

| Priority | Module | Status | Rationale | Key Parameters to Set |
|----------|--------|--------|-----------|----------------------|
| 0 | `event_study` | built-in | Jan 20 2025 shock: compute AR, cumulative CAR | `market_return`, `actual_return` at tick 0 |
| 0 | `platform_tipping` | **NEW** | NVIDIA CUDA ecosystem tipping dynamics | `cross_side_network_effect=0.30`, `switching_cost=0.15`, `initial_incumbent_share=0.80` |
| 1 | `compute_efficiency` | **NEW** | Algorithmic efficiency eroding GPU cost moat | `efficiency_doubling_period=12`, `initial_incumbent_moat=0.80`, `moat_erosion_sensitivity=2.0` |
| 1 | `narrative_contagion` | **NEW** | "AI supercycle" vs "efficiency negates moat" competing narratives | `beta_bear=0.35`, `initial_bull_share=0.65`, `initial_bear_share=0.05` |
| 2 | `schumpeter_disruption` | built-in | Creative destruction: open-weight displacing proprietary API | `disruption_rate`, `incumbent_resistance` |
| 2 | `fisher_pry` | built-in | Technology substitution S-curve: open-weight vs proprietary | `k` (substitution rate), `t_0` (inflection point) |
| 3 | `minsky_instability` | built-in | AI infrastructure capex bubble + deleveraging | `hedge_fraction`, `speculative_fraction`, `ponzi_fraction` |
| 3 | `opinion_dynamics` | built-in | Market sentiment recovery or continued erosion | `epsilon` (opinion convergence threshold) |
| 4 | `porter_five_forces` | built-in | Competitive intensity in AI chip market post-shock | `competitive_intensity`, `barrier_to_entry` |
| 4 | `bass_diffusion` | built-in | Cheap-AI adoption diffusion — does DeepSeek accelerate or cannibalize demand? | `p` (innovation coeff), `q` (imitation coeff) |

**10 modules total.** 3 are new library additions built from this research run.

---

## Composability Note

```
Priority 0 (tick 0):
  event_study          → writes: event_study__cumulative_ar (sentiment proxy)
  platform_tipping     → writes: platform_tipping__incumbent_share, __moat_intact
                         reads:  platform_tipping__disruptive_shock (set at tick 0)

Priority 1 (reads P0 outputs):
  compute_efficiency   → writes: compute_efficiency__incumbent_moat, __entry_barrier
                         reads:  compute_efficiency__efficiency_shock (set at tick 0)
  narrative_contagion  → writes: narrative_contagion__sentiment_balance
                         reads:  narrative_contagion__bear_trigger (set at tick 0)

Priority 2 (reads P0-P1):
  schumpeter_disruption → reads: platform_tipping__incumbent_share, compute_efficiency__entry_barrier
  fisher_pry            → reads: compute_efficiency__efficiency_gain (accelerates substitution)

Priority 3 (reads P0-P2):
  minsky_instability   → reads: narrative_contagion__sentiment_balance (confidence proxy)
  opinion_dynamics     → reads: event_study__cumulative_ar, narrative_contagion__sentiment_balance

Priority 4 (reads P0-P3):
  porter_five_forces   → reads: platform_tipping__incumbent_share, compute_efficiency__entry_barrier
  bass_diffusion       → reads: compute_efficiency__efficiency_gain (reduces adoption barrier)
```

Key cascade: `compute_efficiency__entry_barrier` (falls as efficiency rises) → `fisher_pry` (accelerates substitution) → `schumpeter_disruption` (incumbent resistance erodes) → `minsky_instability` (bubble deflates as revenue thesis weakens).

---

## Calibration Anchors

| Parameter | Value | Source |
|-----------|-------|--------|
| NVIDIA stock AR on Jan 20 2025 | −17.0% | Observed market data |
| NVIDIA market cap loss (single day) | −$593B | Bloomberg, Jan 20 2025 |
| Total AI sector market cap loss | −$1T+ | Bloomberg, Jan 20 2025 |
| DeepSeek R1 training cost vs GPT-4 | ~1/30th | DeepSeek technical report 2025 |
| Algorithmic efficiency doubling period | 9–16 months | Epoch AI (2022) |
| Capability density doubling (Densing Law) | 3.5 months | Nature MI (2025) |
| Platform tipping threshold: alpha > 2*sigma | alpha=0.30, sigma=0.15 | Rochet & Tirole (2003) |
| Narrative virality (bull): beta_bull | 0.20–0.30 | Goetzmann & Kim (2022) |
| Narrative virality (bear): beta_bear | 0.25–0.35 | Goetzmann & Kim (2022) |
| Cross-narrative inhibition | 0.10–0.15 | Goetzmann & Kim (2022) |
| AI narrative recovery window (post-shock) | 60–90 days | Observed: NVIDIA recovery to Jan 2025 highs |

---

## Library Gap Candidates — Build Results

All three ADD candidates were built, smoke-tested, and auto-approved during this research run:

| Model | Citation | Theory ID | Status |
|-------|----------|-----------|--------|
| Platform Tipping | Rochet & Tirole (2003) | `platform_tipping` | ✅ AUTO-APPROVED — `core/theories/discovered/platform_tipping.py` |
| Narrative Contagion | Shiller (2017), Goetzmann & Kim (2022) | `narrative_contagion` | ✅ AUTO-APPROVED — `core/theories/discovered/narrative_contagion.py` |
| Compute Efficiency Erosion | Lu (2025), arXiv:2501.02156 | `compute_efficiency` | ✅ AUTO-APPROVED — `core/theories/discovered/compute_efficiency.py` |

**Library size after this run: 28 theories** (was 25).

### FUTURE candidates (not built — insufficient formal model for direct implementation):
- **Limited Attention Asset Pricing** (Peng & Xiong 2006, RFS) — requires microstructure data feed; mark-to-implement when portfolio-level attention signal is available
- **Two-Sided Market Profit Tension** (Belleflamme, Peitz & Toulemonde 2020, SSRN:3688156) — extends Rochet-Tirole but adds platform profit optimization layer; add when portal-side revenue modeling is needed

---

## Sources Reviewed

### arXiv
- [The Race to Efficiency: A New Perspective on AI Scaling Laws](https://arxiv.org/abs/2501.02156) — Lu, C.P., 2025. Relevance: 5/5
  > Extends classical scaling laws with efficiency-doubling rate; directly models DeepSeek-type efficiency jumps eroding compute cost moats.

- [Increased Compute Efficiency and the Diffusion of AI Capabilities](https://arxiv.org/abs/2311.15377) — Erdil & Besiroglu, 2023. Relevance: 4/5
  > Access effect + performance effect model; AI capability diffusion as efficiency enables more actors to reach frontier performance.

- [The Price of Progress: Algorithmic Efficiency and the Falling Cost of AI Inference](https://arxiv.org/abs/2511.23455) — 2025. Relevance: 4/5
  > Cost decomposition of AI inference: hardware, algorithmic, and economic forces all drive cost reduction.

- [The role of investor attention in global asset price variation](https://arxiv.org/abs/2205.05985) — 2022. Relevance: 3/5
  > Google Trends attention indices predict price variation during geopolitical/market shocks; validates narrative_contagion bear_trigger mechanism.

- [A Model of Competing Narratives](https://arxiv.org/abs/1811.04232) — 2018. Relevance: 4/5
  > Formal agent-based model of competing narratives driving financial volatility; validates SIR-analog structure of narrative_contagion.

### SSRN / Published
- [Two-Sided Markets, Pricing, and Network Effects](https://www.tse-fr.eu/sites/default/files/TSE/documents/doc/wp/2021/wp_tse_1238.pdf) — Rochet & Tirole (2003/2021). Relevance: 5/5
  > Canonical two-sided platform model; tipping condition alpha > 2*sigma; basis for platform_tipping module.

- [Narrative Economics](https://www.nber.org/papers/w23075) — Shiller (2017), NBER WP 23075. Relevance: 5/5
  > Epidemiological model for economic narratives; basis for narrative_contagion module.

- [Crash Narratives](https://www.nber.org/system/files/working_papers/w30195/w30195.pdf) — Goetzmann & Kim (2022), NBER WP 30195. Relevance: 4/5
  > Empirical calibration of narrative virality and decay rates across historical market crashes.

- [The Tension between Market Shares and Profit Under Platform Competition](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3688156) — Belleflamme, Peitz & Toulemonde (2020). Relevance: 3/5
  > Extends Rochet-Tirole with profit-market share tension; FUTURE candidate.

- [AI competition and firm value: Evidence from DeepSeek's disruption](https://www.sciencedirect.com/science/article/pii/S154461232500707X) — 2025. Relevance: 5/5
  > Empirical event study of DeepSeek shock on AI firm valuations; calibrates AR and CAR estimates for event_study module.

- [Densing Law of LLMs](https://www.nature.com/articles/s42256-025-01137-0) — Nature Machine Intelligence, 2025. Relevance: 4/5
  > Capability density doubles every 3.5 months; informs compute_efficiency efficiency_doubling_period upper bound.

- [Tipping and Concentration in Markets with Indirect Network Effects](https://www.jp-dube.com/research/papers/216full.pdf) — Dube et al. Relevance: 4/5
  > Empirical measurement of tipping via video game console data; calibrates platform_tipping cross_side_network_effect.
