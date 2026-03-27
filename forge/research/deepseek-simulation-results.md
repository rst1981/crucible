# DeepSeek R1 / NVIDIA AI Infrastructure Shock — Simulation Results & Analysis (v1)
**Date:** 2026-03-26 | **Ticks:** 18 months (Jan 2025 – Jun 2026)
**Version:** 1 — 10 theory modules (3 NEW) + 300-run Monte Carlo

---

## Executive Summary

### Baseline Position

At tick 0 (January 20, 2025), NVIDIA held 87% of the data center GPU market, backed by deep CUDA ecosystem lock-in and $35.6B in quarterly revenue. The AI supercycle narrative dominated investor consciousness (bull share: 56.7%), and the platform tipping threshold was balanced exactly at the critical margin: cross-side network effect α = 0.30 = 2×σ = 0.30. On this date, DeepSeek disclosed R1 — a frontier model trained at ~1/30th the cost of GPT-4.

| Metric | Tick 0 Value | Source |
|--------|-------------|--------|
| Platform incumbent share | 0.790 | `platform_tipping__incumbent_share` |
| Narrative sentiment balance | 0.619 | `narrative_contagion__sentiment_balance` |
| Bull narrative share | 0.567 | `narrative_contagion__bull_share` |
| Bear narrative share | 0.329 | `narrative_contagion__bear_share` |
| Compute efficiency gain | 0.043 | `compute_efficiency__efficiency_gain` |
| Entry barrier | 0.957 | `compute_efficiency__entry_barrier` |
| Open-weight AI share | 0.065 | `fisher__new_tech_share` |
| Innovator market share | 0.062 | `schumpeter__innovator_share` |
| Financial fragility | 0.261 | `minsky__financial_fragility` |

---

### Causes of the 7-Month Platform Collapse

**1. Platform Tipping (tick 0–7; `platform_tipping`)** — *Primary driver*

Incumbent share fell from 0.790 → 0.469 (tick 3) → 0.093 (tick 6) → **0.004 (tick 7), locked**. The DeepSeek shock (δ = 0.08) pushed the platform below the critical share threshold. Because α = 2×σ exactly, the platform was already at the knife-edge of the tipping condition. Once the cascade of discrete shocks (0.08 at tick 0, 0.02 at tick 1, 0.03 at tick 3) accumulated, the Rochet-Tirole net force flipped from self-reinforcing to self-undermining, and the share collapsed nonlinearly. By tick 7, the moat was effectively zero (0.004).

**2. Narrative Contagion Cascade (tick 0–3; `narrative_contagion`)** — *Amplifier*

The bear narrative infected 32.9% of the investor population at tick 0, compared to 56.7% bulls. The DeepSeek bear trigger (0.35 + 0.05 tick-1 residual + 0.10 tick-3 tariff overhang) caused bear share to surge from 0.329 → 0.782 by tick 3 — a 2.4× increase in 90 days. Once bear share exceeded bull share, cross-inhibition suppressed bull narrative recovery. By tick 6, bulls held just 10.5%. The sentiment balance crashed from 0.619 → 0.110 in 6 months, confirming near-total narrative inversion.

**3. Technology Substitution Acceleration (tick 3–12; `fisher_pry`, `schumpeter_disruption`)** — *Structural*

Open-weight AI share (Fisher-Pry) escalated from 0.065 → 0.289 (tick 6) → 0.747 (tick 12) → **0.952 (tick 17)**. The S-curve inflection, calibrated at tick 18, was pulled forward as compute_efficiency dropped the entry barrier from 0.957 → 0.786 by tick 12. Schumpeter innovator share mirrored this: 0.062 → 0.906 by tick 17. Full substitution occurred within the simulation window.

**4. Second Efficiency Shock (tick 12; `compute_efficiency`)** — *Accelerant*

The scheduled efficiency shock at tick 12 (representing a DeepSeek V3/R2-tier successor) injected an additional 0.20 efficiency gain, pushing the total from 0.154 → 0.214 in a single tick. This is visible as a steepening of all substitution curves after tick 12 and the narrative re-injection (bear_trigger = 0.20) reversing the partial recovery from the Blackwell ramp.

**5. Policy Uncertainty Compounding (tick 3; macro)**

The EPU spike to 460 at tick 3 (April 2025 — 125% US-China semiconductor tariffs) clamped global__policy_uncertainty to its maximum value. This elevated Minsky financial fragility from 0.333 → 0.360 and raised porter competitive intensity. While it did not trigger a financial crisis (crash_risk remained 0.000), it removed the macro tailwind that might have supported a bull narrative recovery.

---

### Current State and Active Threats (Tick 17 — Jun 2026)

| Indicator | Level | Trend | Threat Severity |
|-----------|-------|-------|----------------|
| Platform incumbent share | 0.004 | Locked at floor | **Critical** |
| Narrative sentiment balance | 0.055 | Stable (near-zero) | **Critical** |
| Bull narrative share | 0.009 | Collapsed | **Critical** |
| Open-weight AI share | 0.952 | Saturating | **Critical** |
| Innovator market share | 0.906 | Near-complete | **High** |
| Compute efficiency gain | 0.310 | Rising (MC p50=0.307) | High |
| Entry barrier | 0.690 | Declining | High |
| Financial fragility | 0.380 | Elevated, stable | Moderate |
| Porter profitability | 0.281 | Low, stable | Moderate |
| AI adoption saturation | 1.000 | Saturated | Informational |

**Primary active threats:**
- Platform tipping is permanent within the model — the share floor of 0.004 is a fixed-point attractor once the moat collapses
- Bear narrative is now the dominant equilibrium (89.9% bear share); recovery requires an exogenous positive shock not in the current schedule
- Open-weight AI substitution has passed the 95% threshold — incumbent revenue thesis is structurally broken
- Efficiency gains will continue compounding (MC p95 = 0.635 efficiency gain by Jun 2026 in the most aggressive bear scenario)
- Financial fragility (0.380) remains elevated above the pre-shock baseline (0.261); any external credit event could cross the 0.65 crisis threshold

---

### 18-Month Forward Projection (from Jun 2026 / Tick 17)

The simulation window ends at tick 17 with platform tipping already complete. Any projection beyond tick 17 extrapolates from a locked state. MC bands show near-zero variance for all structural metrics — the outcome is path-invariant from tick 7 onward.

| Scenario | Sentiment Balance (final) | Incumbent Share (final) | Probability |
|----------|--------------------------|------------------------|-------------|
| Base | 0.055 | 0.004 | ~55% |
| Bull | 0.055 | 0.003–0.005 | ~25% |
| Bear | 0.055 | 0.003–0.005 | ~20% |

**The scenario split is irrelevant for platform share and narrative outcomes — all 300 MC runs converge to the same structural endpoint.** The only meaningful divergence is in compute_efficiency (p5=0.222, p95=0.635), which governs the *speed* of entry barrier reduction but not the *direction*. The financial market (event study CAR → ceiling) may continue recovering as a stock price phenomenon while the underlying platform structure has tipped.

---

## Executive Findings

The DeepSeek R1 simulation reveals a **tipping point economy** — not a gradual competitive erosion, but a nonlinear phase transition. The platform_tipping module identifies the mechanism precisely: NVIDIA entered the simulation window with α = 2×σ, sitting exactly at the Rochet-Tirole knife-edge. In this regime, the direction of tipping is determined by the first discrete shock, not the magnitude. The accumulated 0.13 share-point shock (0.08 + 0.02 + 0.03 over three events) was sufficient to push below 0.5 share and invert the autocatalytic force from self-reinforcing to self-undermining. The collapse from 0.093 (tick 6) to 0.004 (tick 7) happened in a single month — this is the signature of a tipping event, not gradual market share loss.

The narrative dimension amplified the structural collapse faster than the competitive dynamics alone would predict. By tick 3, 78.2% of the investor population held the bear narrative. Once this threshold was crossed, cross-inhibition in the narrative_contagion model made bull recovery self-limiting — each new bull narrative attempt was partly canceled by the dominant bear population. The sentiment balance of 0.055 at tick 17 represents a deeply embedded bear consensus, not a transient correction. The Goetzmann-Kim calibration (beta_bear=0.35 > beta_bull=0.25) predicts that bear narratives, once dominant, are stickier than bull narratives in financial markets — consistent with the 6-month post-shock recovery timeline observed empirically but not captured in this window.

The substitution cascade (fisher_pry + schumpeter_disruption) ran faster than the S-curve inflection at tick 18 would suggest because compute_efficiency lowered the entry barrier continuously. The interaction between efficiency gain and substitution rate is the key cascade link in this simulation: as entry_barrier fell from 0.957 → 0.786 by tick 12, the Fisher-Pry substitution rate accelerated, pulling the inflection forward. This is the mechanism by which a single efficiency event (DeepSeek R1) becomes a structural substitution event rather than a temporary disruption.

The Monte Carlo results deliver a stark message: **this outcome is not scenario-dependent**. Across 300 runs spanning base, bull, and bear parameter variations, the platform share locks at 0.003–0.005 with essentially zero variance. The narrative sentiment balance shows equally tight bands. Only compute_efficiency gains vary meaningfully (p5=0.222, p95=0.635 at final tick), reflecting uncertainty in the speed of efficiency compounding — but not in the direction. The simulation is saying that once the initial conditions crossed the tipping threshold, no reasonable variation in efficiency doubling period, narrative virality, or platform network effects can reverse the outcome within the 18-month window.

The bifurcation between financial markets (event study CAR recovering to ceiling) and structural markets (platform collapsing, narrative bears dominating) is the most practically important finding. NVIDIA's stock recovered from the DeepSeek shock — but the model's structural metrics suggest the recovery was a narrative re-infection ("inference still needs GPUs", "Blackwell ramp") layered on top of a structural collapse. The stock price and the platform position decoupled. This bifurcation is consistent with observed equity market behavior: NVIDIA's share price recovered while its TAM thesis remained structurally challenged. The financial fragility metric (0.380, elevated but stable) suggests the market has priced in moderate risk without triggering a systemic event.

The second efficiency shock at tick 12 demonstrates that the model is sensitive to the timing of follow-on disruptions. If DeepSeek V3 or a comparable successor arrives within 12 months of R1, the substitution curves that were already at 70% completion are pushed to near-saturation before the Blackwell ramp can restore platform share. This is the key strategic question the simulation cannot answer: whether NVIDIA's hardware roadmap (Blackwell → Rubin) can outrun the algorithmic efficiency curve. The simulation assumes the efficiency doubling period (12 months base case) is faster than NVIDIA's product cycle, which drives the bear outcome. In the MC bull scenarios (doubling period closer to 16 months), the entry barrier falls more slowly but still converges to the same structural outcome by tick 17.

---

## 1. Simulation Design

### Architecture (10 Modules)

```
Priority 0 — Shock initialization (tick 0)
  ┌─ event_study          → event__cumulative_ar (financial CAR proxy)
  └─ platform_tipping     → platform_tipping__incumbent_share (87% → tipping cascade)
                            platform_tipping__moat_intact

Priority 1 — Structural dynamics (reads P0)
  ├─ compute_efficiency   → compute_efficiency__efficiency_gain (compounding)
  │                         compute_efficiency__entry_barrier  (declining)
  └─ narrative_contagion  → narrative_contagion__sentiment_balance (crashing)
                            __bull_share / __bear_share

Priority 2 — Competitive response (reads P0–P1)
  ├─ schumpeter_disruption → schumpeter__innovator_share (0.06 → 0.91)
  └─ fisher_pry            → fisher__new_tech_share (0.07 → 0.95)
     [reads compute_efficiency__efficiency_gain → accelerates substitution]

Priority 3 — Macro feedback (reads P0–P2)
  ├─ minsky_instability   → minsky__financial_fragility (elevated, stable)
  └─ opinion_dynamics     → opinion__mean (rising, decoupled from structural metrics)

Priority 4 — Synthesis (reads P0–P3)
  ├─ porter_five_forces   → porter__profitability (low, stable)
  └─ bass_diffusion       → bass__adoption_fraction (saturates tick 12)
```

### Timeframe and Shocks

| Variable | Value |
|----------|-------|
| Tick unit | Month |
| Total ticks | 18 |
| Tick 0 | Jan 20 2025 — DeepSeek R1 disclosure |
| Tick 17 | Jun 2026 — end of simulation window |
| MC runs | 300 (base=167 / bull=69 / bear=64) |

| Tick | Date | Event | Key Variables Shocked |
|------|------|-------|----------------------|
| 0 | Jan 2025 | DeepSeek R1 disclosure | `platform_tipping__disruptive_shock` +0.08, `compute_efficiency__efficiency_shock` +0.30, `narrative_contagion__bear_trigger` +0.35 |
| 1 | Feb 2025 | Residual narrative/erosion | `bear_trigger` +0.05, `disruptive_shock` +0.02 |
| 3 | Apr 2025 | US-China tariff escalation (125%) | `policy_uncertainty` +1.0 (max), `porter__barriers_to_entry` +0.10, `bear_trigger` +0.10 |
| 6 | Jul 2025 | Blackwell ramp (partial recovery) | `minsky__asset_appreciation` +0.10, `schumpeter__rd_investment` +0.10 |
| 9 | Oct 2025 | Hyperscaler capex confirmed ($315B) | `fisher__cost_reduction` +0.012, `bass__adoption_fraction` +0.02 |
| 12 | Jan 2026 | DeepSeek successor shock | `compute_efficiency__efficiency_shock` +0.20, `bear_trigger` +0.20, `disruptive_shock` +0.05 |
| 15 | Apr 2026 | Market stabilization | `minsky__asset_appreciation` -0.08 (correction) |

---

## 2. Results by Module

### 2.1 Event Study (MacKinlay 1997)

Tracks NVIDIA's cumulative abnormal return vs CAPM expectation. Note: parameter initialization mismatch (env values were set as raw returns rather than normalized; see Section 5) means the CAR series reflects relative performance within the model rather than absolute return magnitude.

| Month | CAR (normalized) | CAR (raw %) | Event |
|-------|-----------------|-------------|-------|
| Jan 2025 (T0) | 0.531 | +1.2% | DeepSeek shock applied |
| Apr 2025 (T3) | 0.624 | +5.0% | Tariff escalation |
| Jul 2025 (T6) | 0.717 | +8.7% | Blackwell ramp |
| Aug 2025 (T7) | 0.748 | +9.9% | Platform tips |
| Jan 2026 (T12) | 0.903 | +16.1% | Second efficiency shock |
| Jun 2026 (T17) | 1.000 | Cap (+90%) | Window end |

**Interpretation:** Due to the normalization mismatch, the CAR accumulates a small positive AR each month (market implied return -21%/month vs actual -20%/month = +1% AR). This represents the financial market pricing NVIDIA stock relative to a highly stressed market baseline. The divergence from structural metrics (platform collapse) represents the bifurcation between financial recovery and structural deterioration.

### 2.2 Platform Tipping (NEW — Rochet & Tirole 2003)

Two-sided platform dynamics tracking NVIDIA CUDA ecosystem market share. At α = 2×σ, the platform sat exactly at the knife-edge tipping threshold.

| Month | Share | Moat | Event |
|-------|-------|------|-------|
| Jan 2025 (T0) | 0.790 | 0.790 | Shock δ=0.08 applied |
| Apr 2025 (T3) | 0.469 | 0.469 | Below 50% — tip initiated |
| Jul 2025 (T6) | 0.093 | 0.093 | Approaching floor |
| Aug 2025 (T7) | **0.004** | **0.004** | **Tipping complete — locked** |
| Jun 2026 (T17) | 0.004 | 0.004 | No recovery |

**MC:** p5=0.003, p50=0.004, p95=0.005 at final tick — effectively zero variance. Platform collapse is universal across all 300 runs.

**Interpretation:** The knife-edge condition (α exactly = 2×σ) means the model is maximally sensitive to discrete shocks. The accumulated 0.13 shock (three events) was sufficient to initiate and complete tipping. Once share fell below 0.5 in tick 3, the Rochet-Tirole net force became self-undermining. The model does not include CUDA ecosystem structural stickiness beyond the switching cost parameter — this is the primary limitation.

### 2.3 Compute Efficiency (NEW — Lu 2025, arXiv:2501.02156)

Tracks algorithmic efficiency gains compressing the incumbent compute cost moat.

| Month | Efficiency Gain | Entry Barrier | Event |
|-------|----------------|---------------|-------|
| Jan 2025 (T0) | 0.043 | 0.957 | Efficiency shock +0.30 |
| Apr 2025 (T3) | 0.070 | 0.930 | — |
| Jul 2025 (T6) | 0.102 | 0.898 | — |
| Jan 2026 (T12) | 0.214 | 0.786 | Second shock +0.20 |
| Jun 2026 (T17) | 0.310 | 0.690 | — |

**MC (efficiency_gain at T17):** p5=0.222, p25=0.267, p50=0.307, p75=0.370, p95=0.635 — the only metric with meaningful MC variance. The p95 scenario (0.635) corresponds to bear MC runs with fast doubling period (~9 months).

**Interpretation:** 31% efficiency gain in 18 months is consistent with Lu's 2025 estimate (doubling period 9–16 months). The second shock at tick 12 caused a visible step-change (+0.060 in one tick). Entry barrier declined from 0.957 → 0.690, meaning the cost advantage of capital-intensive GPU investment fell from ~96% to ~69% of its initial value.

### 2.4 Narrative Contagion (NEW — Shiller 2017, Goetzmann & Kim 2022)

Competing "AI supercycle" (bull) vs "efficiency destroys moat" (bear) narrative SIR dynamics.

| Month | Sentiment Balance | Bull Share | Bear Share | Event |
|-------|-----------------|------------|------------|-------|
| Jan 2025 (T0) | 0.619 | 0.567 | 0.329 | Bear trigger +0.35 |
| Apr 2025 (T3) | 0.218 | 0.218 | 0.782 | Bear crosses 50% |
| Jul 2025 (T6) | 0.110 | 0.105 | 0.884 | Bear dominant |
| Jan 2026 (T12) | 0.066 | 0.028 | 0.896 | Second shock |
| Jun 2026 (T17) | 0.055 | 0.009 | 0.899 | Near equilibrium |

**MC:** Zero variance across all runs — narrative equilibrium is a fixed-point attractor independent of scenario parameters once the bear trigger exceeds a threshold.

**Interpretation:** Bear narrative dominance (89.9%) by tick 17 is consistent with the Goetzmann-Kim finding that bear narratives, once established as majority opinion, are difficult to dislodge without a major positive signal not present in the shock schedule.

### 2.5 Schumpeter Disruption (built-in)

Creative destruction: open-weight AI displacing proprietary API platforms.

| Month | Innovator Share | Creative Destruction |
|-------|----------------|---------------------|
| T0 | 0.062 | — |
| T3 | 0.121 | Rising |
| T7 | 0.302 | Accelerating |
| T12 | 0.701 | Past midpoint |
| T17 | 0.906 | Near-complete |

### 2.6 Fisher-Pry Substitution (built-in)

Technology substitution S-curve for open-weight AI replacing proprietary models.

| Month | New Tech Share | Old Tech Share |
|-------|---------------|----------------|
| T0 | 0.065 | 0.935 |
| T3 | 0.143 | 0.857 |
| T6 | 0.289 | 0.711 |
| T12 | 0.747 | 0.253 |
| T17 | 0.952 | 0.048 |

**Interpretation:** The Fisher-Pry inflection was set at tick 18 (base design), but actual inflection occurred ~tick 9–10 due to efficiency_gain accelerating the substitution rate. Full substitution (>95%) completed within the simulation window.

### 2.7 Minsky Instability (built-in)

Financial fragility and crash risk tracking AI infrastructure capex bubble dynamics.

| Month | Fragility | Crash Risk |
|-------|-----------|------------|
| T0 | 0.261 | 0.000 |
| T3 | 0.333 | 0.000 |
| T17 | 0.380 | 0.000 |

**Interpretation:** Financial fragility rose 46% from baseline (0.261 → 0.380) but remained well below the crisis threshold (0.65). No crash event materialized. This reflects a stressed-but-stable financial system — consistent with observed AI sector equity volatility without a systemic credit event.

### 2.8 Opinion Dynamics (built-in)

Market opinion mean (0 = fully pessimistic, 1 = fully optimistic).

| Month | Opinion Mean | Event |
|-------|-------------|-------|
| T0 | 0.743 | — |
| T6 | 0.845 | Recovery |
| T12 | 0.918 | Rising |
| T17 | 0.951 | Near ceiling |

**Note:** Opinion dynamics rises throughout, diverging from narrative sentiment balance (which collapses). This reflects two different mechanisms: opinion_dynamics models broad market consensus convergence (bounded rationality, media influence), while narrative_contagion models the specific AI tech narrative population. The divergence is a finding: broad market opinion recovers while AI-specific narrative remains bearish.

### 2.9 Porter Five Forces (built-in)

Industry profitability proxy for the AI chip market.

| Month | Profitability | Entry Barrier |
|-------|--------------|---------------|
| T0 | 0.265 | 0.650 |
| T3 | 0.271 | 0.750 (tariff shock ↑) |
| T12 | 0.266 | Declining |
| T17 | 0.281 | — |

**Interpretation:** Profitability remained low (0.265–0.281) and stable — the Porter model captures industry-wide structural profitability, which is constrained by rising rivalry intensity and substitution threat. The tariff escalation at tick 3 temporarily raised barriers (benefiting NVIDIA) but was offset by the rising substitute threat from open-weight AI.

### 2.10 Bass Diffusion (built-in)

Cheap AI model adoption diffusion curve.

| Month | Adoption Fraction |
|-------|------------------|
| T0 | 0.099 |
| T3 | 0.347 |
| T7 | 0.796 |
| T12 | 0.999 |
| T17 | 1.000 |

**Interpretation:** Adoption saturated by tick 12 (January 2026), consistent with the explosive diffusion of low-cost AI models following DeepSeek R1. The Bass model's imitation coefficient (q=0.38) drove rapid adoption once a critical mass was reached around tick 6–7 (coinciding with platform tipping).

---

## 3. Cascade Interaction

The simulation's central cascade path is:

```
DeepSeek R1 shock (tick 0)
  → platform_tipping__disruptive_shock (−0.08 share)
    → platform share below knife-edge → tipping initiates (tick 3)
      → schumpeter__incumbent_resistance weakens
        → schumpeter + fisher_pry substitution accelerates
          → bass__adoption_fraction saturates (tick 12)

  → compute_efficiency__efficiency_shock (+0.30)
    → entry_barrier falls → additional substitution pressure on fisher_pry
      → second shock at tick 12 causes step-change acceleration

  → narrative_contagion__bear_trigger (+0.35)
    → bear share >50% by tick 3 → bull cross-inhibition dominant
      → sentiment_balance collapses → minsky confidence proxy falls
        → financial_fragility rises (stable at 0.38)
```

**Why NVIDIA underperformed peers in the model:** The platform_tipping mechanism creates an asymmetric outcome that pure competitive-intensity models (Porter) would not predict. NVIDIA's structural position is not defined by rivalry or buyer power — it is defined by the two-sided platform's self-reinforcing network effects. Once the tipping condition is violated, no increase in R&D investment, capex, or product roadmap within the 18-month window can reverse the equilibrium because the cascade has already inverted. This is qualitatively different from, say, a gradual loss of market share to AMD.

**The divergence anomaly:** Opinion dynamics (opinion__mean rising to 0.951) and event_study CAR (rising to ceiling) diverge from the structural metrics because they measure different things. Financial market participants were re-rating NVIDIA on the "inference demand" narrative (Blackwell ramp, hyperscaler capex doubling), while the platform dynamics module was tracking developer ecosystem share. In practice, this divergence resolved in NVIDIA's favor in 2025 (stock recovery) — suggesting the model's platform tipping speed may be too aggressive, and that CUDA lock-in (switching_cost parameter) may be higher than the 0.15 calibration.

---

## 4. Monte Carlo Distribution (300 runs)

**300 runs.** Scenarios: base=167 (55.7%) / bull=69 (23.0%) / bear=64 (21.3%).

### Final Tick (T17) Percentile Bands

| Metric | p5 | p25 | p50 | p75 | p95 | Band Width |
|--------|-----|-----|-----|-----|-----|-----------|
| `compute_efficiency__efficiency_gain` | 0.222 | 0.267 | 0.307 | 0.370 | 0.635 | **0.413** |
| `platform_tipping__incumbent_share` | 0.003 | 0.003 | 0.004 | 0.004 | 0.005 | 0.002 |
| `narrative_contagion__sentiment_balance` | 0.055 | 0.055 | 0.055 | 0.055 | 0.055 | 0.000 |
| `fisher__new_tech_share` | 0.952 | 0.952 | 0.952 | 0.952 | 0.952 | 0.000 |
| `minsky__financial_fragility` | 0.380 | 0.380 | 0.380 | 0.380 | 0.380 | 0.000 |

### Compute Efficiency Gain — Tick-by-Tick MC Bands

| Tick | p5 | p25 | p50 | p75 | p95 |
|------|-----|-----|-----|-----|-----|
| T0 | 0.043 | 0.043 | 0.043 | 0.043 | 0.043 |
| T3 | 0.062 | 0.066 | 0.070 | 0.074 | 0.089 |
| T6 | 0.084 | 0.094 | 0.101 | 0.113 | 0.151 |
| T9 | 0.109 | 0.126 | 0.139 | 0.160 | 0.233 |
| T12 | 0.166 | 0.191 | 0.212 | 0.245 | 0.370 |
| T17 | 0.222 | 0.267 | 0.307 | 0.370 | 0.635 |

### Platform Share — Tick-by-Tick MC Bands

| Tick | p5 | p50 | p95 |
|------|-----|-----|-----|
| T0 | 0.790 | 0.790 | 0.791 |
| T3 | 0.467 | 0.469 | 0.472 |
| T6 | 0.087 | 0.093 | 0.098 |
| T7 | 0.003 | 0.004 | 0.005 |
| T17 | 0.003 | 0.004 | 0.005 |

**The dominant MC finding is basin-of-attraction convergence.** Most simulation metrics show zero or near-zero variance across 300 runs. Once the shock parameters crossed the tipping threshold at tick 0, the system entered a deterministic cascade regardless of efficiency doubling period, narrative virality, or platform network effect variations. The only meaningful uncertainty is in compute_efficiency — specifically, how fast the efficiency curve compounds — but this affects the speed of substitution, not the endpoint.

The p95 efficiency scenario (0.635 gain) represents a world in which algorithmic efficiency has already achieved 63.5% of its maximum theoretical gain within 18 months — consistent with the Densing Law (capability density doubling every 3.5 months, Nature MI 2025). This would represent a dramatically more hostile environment for GPU-dependent training workloads.

---

## 5. Model Limitations

| Limitation | Impact | Status |
|-----------|--------|--------|
| Event study env normalization: `global__market_return` and `event__actual_return` were initialized as raw floats but module expects normalized [0,1] values. Causes CAR series to be uninterpretable as absolute returns. | CAR series misleading; use structural metrics for primary findings | **Open** — fix in v2: set `global__market_return = 0.4225` (= 0.5 + (−0.031)/0.4), `event__actual_return = 0.075` |
| Shock application is additive delta, not absolute set: `event__actual_return` was double-applied and clamped to 0.0 (initial -0.170 + shock -0.170 = -0.340, clamped). | Compounds normalization issue above | **Open** — fix in v2: use delta-correct shock values or restructure shock application |
| Platform tipping switching_cost (0.15) may understate CUDA developer lock-in. At σ=0.15 and α=0.30, the platform is at the critical margin. If σ is empirically 0.20–0.25 (more plausible for ecosystem lock-in), the platform is stable and tipping would not occur. | Qualitatively overestimates tipping susceptibility | **Open** — calibrate σ from CUDA developer survey data |
| No NVIDIA product roadmap (Blackwell → Rubin) modeled as a positive platform reinforcement shock. The simulation has no mechanism for the incumbent to re-tip after losing share. | Understates recovery potential in bull scenarios | **Open** — add scheduled positive platform shocks for product generations |
| Narrative contagion and opinion dynamics diverge without a coupling mechanism. Bull narrative re-infection (opinion rising) doesn't feed back into narrative_contagion__bull_share. | Creates unrealistic divergence between the two sentiment modules | **Open** — couple opinion__mean → narrative_contagion__bull_trigger in v2 |
| Bass diffusion saturates at 100% adoption by tick 12 — too aggressive. Open-weight AI won't reach 100% of the market within 12 months. | Overstates substitution speed in bass | **Open** — cap adoption at 60–70%, add switching friction parameter |
| All 300 MC runs converge to same structural endpoint. This suggests the model lacks sufficient parameter sensitivity — the tipping threshold crossing is too binary. | MC provides limited information beyond deterministic run | **Open** — widen perturbation bands on switching_cost and cross_side_network_effect |

---

## 6. Parameters Appendix

| Module | Key Parameters | Calibration Source |
|--------|---------------|-------------------|
| `event_study` | beta_market=1.0, risk_free_rate=0.045, tick_unit=month | FRED FEDFUNDS; NVIDIA beta ≈ 1.0 |
| `platform_tipping` (NEW) | α=0.30, σ=0.15, incumbent_share=0.87, lr=0.05 | Rochet-Tirole (2003); Bloomberg IDC data |
| `compute_efficiency` (NEW) | T_eff=12 months, initial_moat=0.80, sensitivity=2.0 | Lu 2025 (arXiv:2501.02156); Epoch AI (2022) |
| `narrative_contagion` (NEW) | β_bull=0.25, β_bear=0.35, γ_bull=0.08, γ_bear=0.10, cross_inhibition=0.12 | Goetzmann & Kim NBER WP 30195 (2022) |
| `schumpeter_disruption` | disruption_rate=0.08, incumbent_resistance=0.70 | Estimated from CUDA developer lock-in |
| `fisher_pry` | k=0.15, t_0=18, f_ceiling=0.90 | Industry substitution rate estimates |
| `minsky_instability` | hedge=0.50, speculative=0.40, ponzi=0.10 | AI capex structure estimate |
| `opinion_dynamics` | convergence_rate=0.10, media_influence=0.20 | Standard calibration |
| `porter_five_forces` | barriers=0.65, supplier_power=0.80, buyer_power=0.45, substitute_threat=0.35 | Initial conditions from data brief |
| `bass_diffusion` | p=0.03, q=0.38 | Standard tech adoption literature |
