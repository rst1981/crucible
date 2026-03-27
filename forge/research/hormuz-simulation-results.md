# Strait of Hormuz Escalation — Simulation Results & Analysis
**Date:** 2026-03-26 | **Ticks:** 24 months (Jan 2025 – Dec 2026)
**Version:** 1 — 6 theory modules, deterministic run (no Monte Carlo)

---

## Executive Summary

### Baseline Position

At tick 0 (January 2025), the Strait of Hormuz scenario opens with Iran at elevated but not maximal military posture (0.634), the US with a carrier group in the Gulf (0.783), oil at ~$94/bbl (normalized 0.680), and only minor shipping harassment (0.08 disruption). The global economy is under moderate stress (0.30) with full trade volume intact (0.720). Iran is under maximum sanctions pressure (0.75 economic pressure, domestic stability 0.40 — bottom 5% globally).

| Metric | Start (t=0) | Peak | Final (t=23) |
|--------|------------|------|-------------|
| Oil Price (normalized) | 0.680 (~$94/bbl) | 0.950 (~$116/bbl, t=5–8) | 0.680 (~$94/bbl) |
| Strait Disruption | 0.080 | 0.630 (t=5–15) | 0.000 |
| Iran Military | 0.634 | 0.922 (t=18) | 0.894 |
| US Military | 0.783 | 1.000 (t=11, ceiling) | 1.000 |
| Conflict Probability | 1.000* | 0.405 (t=1) | 0.040 |
| Economic Contagion | 5.1% | 6.9% (t=23) | 6.9% |
| Trade Volume | 0.720 | trough 0.370 (t=5–8) | 0.820 |
| Economic Stress | 0.300 | 0.550 (t=5–21) | 0.450 |

*Fearon cold-start artifact; first real value at t=1 is 0.405. See §2.2.

---

### Three-Phase Arc

**Phase 1 — Escalation (t=2–5):** Iran announces navigation restrictions (t=2), shipping disruption jumps from 0.08 to 0.33; oil to $104/bbl. Iranian tanker seizure (t=5) drives disruption to peak 0.63, oil to $116/bbl, trade volume collapses 49% to 0.37. Richardson arms race accelerates — Iran military crosses 0.79 by t=5.

**Phase 2 — Stalemate (t=7–15):** International naval coalition forms (t=7), US military reaches ceiling (1.000) at t=11 and stays there. Strait disruption holds at 0.63 for 10 consecutive months. Oil sustained at $112–116/bbl. Back-channel negotiations begin (t=11, Oman mediating) — progress reaches 0.15 but Zartman ripeness never organically fires. Economic stress plateaus at 0.55.

**Phase 3 — Resolution (t=16–22):** Framework agreement shock (t=16) reduces disruption to 0.43 and oil to $104/bbl. Ceasefire (t=19) brings disruption to 0.13, trade volume surges to 0.67. Full normalization (t=22) closes strait completely (0.00 disruption) and trade volume recovers to 0.82 — above the 0.72 baseline. Economic stress retreats to 0.45 but does not return to baseline 0.30.

**Key anomaly:** The Richardson arms race is structurally unstable (a·b=0.045 < k·l=0.070). Iran's military readiness continues climbing through the entire resolution phase, ending at 0.894 — **41% higher than at scenario start** — even as the strait fully reopens. The US military ceiling of 1.000 persists through tick 23. The crisis resolves diplomatically in the environment model, but the underlying military posture never de-escalates.

---

### Current State (t=23, Dec 2026)

| Indicator | Final Value | Trend | Severity |
|-----------|------------|-------|---------|
| Strait Disruption | 0.000 | Resolved | None |
| Oil Price | 0.680 (~$94/bbl) | Normalized | Low |
| Iran Military | 0.894 | Still rising | High |
| US Military | 1.000 | At ceiling | Critical |
| Richardson Escalation Index | 0.947 | Unstable | High |
| Conflict Probability | 0.040 (4%) | Declining | Low-Medium |
| Economic Stress | 0.450 | Elevated residual | Medium |
| Economic Contagion | 6.9% infected | Slow spread | Low |
| Trade Volume | 0.820 | Above baseline | Positive |
| Iran Domestic Stability | 0.320 | Degraded | Medium |

**Primary active risks at end of simulation:**
- Richardson instability is structural: without de-escalation shocks, the arms race resumes immediately after t=23
- US military at ceiling (1.000) with no modeled drawdown mechanism
- Economic stress residual (0.45 vs 0.30 baseline) persists — shock has not fully cleared
- Iran domestic stability degraded from 0.40 to 0.32 — increased internal fragility
- Negotiation progress frozen at 0.60 — framework not fully ratified

---

## Executive Findings

The simulation produces a clean three-phase crisis arc — escalation, stalemate, diplomatic resolution — that maps closely to the scenario design. However, two structural results are more important than the arc itself.

**First: the Fearon conflict probability starts at 1.000.** This is a cold-start artifact from the Fearon module initializing before the Richardson arms race populates the military balance. By tick 1 it drops to 0.405, and by tick 23 it reaches 0.040 — a low but nonzero 4% residual. The model correctly identifies that by late 2026, diplomatic progress has reduced conflict risk substantially. But the 1.000 cold-start is misleading: it should not be interpreted as a prediction of near-certain war at scenario open.

**Second: the Richardson arms race never stabilizes.** With parameters k=0.35, l=0.20, a=0.30, b=0.15, the stability condition a·b > k·l requires 0.045 > 0.070 — which fails. This is intentional: the scenario is calibrated to Iran–US asymmetric threat perception where Iran's reactivity exceeds fatigue. The practical result is that Iran's military readiness climbs from 0.634 to 0.894 over 24 months, and the Richardson escalation index closes at 0.947. The strait resolves; the arms dynamic does not. This is the most consequential finding: diplomatic normalization in the environment is insufficient to unwind a structurally unstable arms race.

**Third: Wittman-Zartman never organically fires.** The `ripe_moment` variable is 0.000 for all 24 ticks. The ripeness condition (mutually hurting stalemate + mediator + urgency) is never satisfied organically — all negotiation progress is shock-driven (t=11, t=13, t=16 events). The 2015 JCPOA analog that motivated Zartman inclusion required ~2 years of stalemate before ripeness; this simulation does not produce a prolonged enough stalemate period for the MHS condition to fire. This is a model transparency finding, not necessarily an error: it says the negotiated resolution in this scenario is politically imposed, not organically ripe.

**Fourth: economic contagion is modest.** The SIR module produces only a 1.83pp increase in infected fraction (5.1% → 6.9%) over 24 months, with R_effective ending at 0.279 — well below 1.0. The disruption was severe (trade volume collapsed 49%) but the recovery was complete; the beta=0.25/gamma=0.08 calibration produces slow but controlled contagion. The real economic impact is better read from the Keynesian outputs: GDP normalized fell from 0.500 to 0.482 (−1.85%) and fiscal shock remains pending at 0.488 — suggesting the GDP multiplier effects have not fully propagated by tick 23.

**Fifth: the strait fully resolves but trade volume exceeds baseline.** Final trade volume of 0.820 is 13.9% above the scenario opening of 0.720. This is a shock-accumulation artifact: the ceasefire and normalization shocks add +0.25 and +0.15 to trade volume against a baseline already partially recovered, producing a mild overshoot. A future version should apply shock caps or return-to-trend constraints.

---

## 1. Simulation Design

### Architecture (6 Modules)

```
Richardson Arms Race (priority 0)
    → writes iran__military_readiness, us__military_readiness
    ↓
Fearon Bargaining (priority 1)
    → reads military balance → writes fearon__conflict_probability
    ↓
Wittman-Zartman (priority 2)
    → reads fearon__win_prob_a, escalation index → writes zartman__ripe_moment
    ↓
SIR Contagion — economic (priority 3)
    → reads global__trade_volume → writes economic__infected
    ↓
Keynesian Multiplier (priority 4)
    → reads SIR infected fraction, trade volume → writes keynesian__gdp_normalized
    ↓
Porter Five Forces — shipping (priority 5)
    → reads strait__shipping_disruption → writes porter__profitability
```

### Timeframe and Configuration

| Variable | Value |
|----------|-------|
| Tick unit | Month |
| Start | Jan 2025 |
| End | Dec 2026 |
| Total ticks | 24 |
| Actors | 18 |
| Theory modules | 6 |
| Monte Carlo | Not run (deterministic only) |
| Snapshots | Auto-saved every 2 ticks |

### Shock Schedule

| Tick | Month | Event | Key Variables Shocked |
|------|-------|-------|----------------------|
| 2 | Mar 2025 | Iran navigation restrictions | disruption +0.25, oil +0.12, trade −0.15 |
| 3 | Apr 2025 | US additional carrier strike group | US military +0.10, Iran econ pressure +0.05 |
| 5 | Jun 2025 | Iranian tanker seizure | disruption +0.30, oil +0.15, trade −0.20 |
| 7 | Aug 2025 | International naval coalition | US military +0.08, UK military +0.12 |
| 9 | Oct 2025 | Oil importers activate strategic reserves | oil −0.05, trade +0.05 |
| 11 | Dec 2025 | Oman back-channel begins | mediator +1.00, urgency +0.30, progress +0.15 |
| 13 | Feb 2026 | US-Iran direct talks | progress +0.20, Iran military −0.05 |
| 16 | May 2026 | Framework agreement | progress +0.25, disruption −0.20, oil −0.10 |
| 19 | Aug 2026 | Ceasefire + partial strait reopening | disruption −0.30, trade +0.25, oil −0.12 |
| 22 | Nov 2026 | Full normalization | disruption −0.15, trade +0.15, stress −0.10 |

---

## 2. Results by Module

### 2.0 Richardson Arms Race

Models Iran–US mutual military buildup via coupled differential equations. Iran (actor_a) has higher reactivity (k=0.35) than fatigue (a=0.30); US (actor_b) has lower reactivity (l=0.20) but also lower fatigue (b=0.15). The system is in the unstable regime: k·l=0.070 > a·b=0.045.

| Month | Iran Military | US Military | Escalation Index | Event |
|-------|-------------|------------|-----------------|-------|
| Jan 2025 (t=0) | 0.634 | 0.783 | 0.725* | Baseline |
| Mar 2025 (t=2) | 0.661 | 0.790 | 0.725 | Nav restrictions |
| Apr 2025 (t=3) | 0.677 | 0.892 | — | US CSG deployed |
| Jun 2025 (t=5) | 0.786 | 0.899 | — | Tanker seizure |
| Aug 2025 (t=7) | 0.815 | 0.987 | — | Coalition forms |
| Dec 2025 (t=11) | 0.874 | 1.000 | — | US hits ceiling |
| Feb 2026 (t=13) | 0.853 | 1.000 | — | Talks; Iran dips |
| Aug 2026 (t=19) | 0.837 | 1.000 | — | Ceasefire; Iran dips |
| Dec 2026 (t=23) | **0.894** | **1.000** | **0.947** | Resolution |

*Escalation index read from t=2 snapshot.

Iran's military dips slightly at shocks where confidence-building measures are applied (t=13: −0.05, t=19: −0.10) but resumes climbing within 1–2 ticks. The Richardson ODE continues integrating through all diplomatic shocks because the underlying stability condition remains violated. **This is the correct model behavior for an unstable regime.**

### 2.1 Fearon Bargaining

Models conflict onset probability from information asymmetry and power-shift commitment problems. The Iran–US nuclear opacity is the canonical Fearon mechanism.

| Month | Conflict Prob | Iran Win Prob | US Win Prob Est | Event |
|-------|-------------|-------------|----------------|-------|
| Jan 2025 (t=0) | **1.000*** | 0.500 | 0.000 | Cold start |
| Feb 2025 (t=1) | 0.405 | 0.500 | 0.068 | First real tick |
| Mar 2025 (t=2) | 0.365 | 0.500 | 0.136 | Nav restrictions |
| Jun 2025 (t=5) | 0.266 | 0.500 | 0.274 | Tanker seizure |
| Dec 2025 (t=11) | 0.141 | 0.500 | 0.371 | Oman backchannel |
| Feb 2026 (t=13) | 0.114 | 0.500 | 0.405 | Direct talks |
| May 2026 (t=16) | 0.083 | 0.500 | 0.437 | Framework |
| Dec 2026 (t=23) | **0.040** | **0.500** | **0.460** | Resolution |

*Cold-start artifact — see note below.

**Cold-start note:** The Fearon module initializes `fearon__win_prob_b_estimate` at 0.000 before Richardson has run at t=0, producing a 1.000 conflict probability on the first output. This is a module sequencing issue: Fearon reads a Richardson output that doesn't yet have a real value. **The t=0 value should be treated as invalid.** The t=1 value of 0.405 is the first meaningful conflict probability. At scenario end, 4.0% conflict probability represents a low but structurally persistent risk — consistent with an arms race that has not de-escalated.

### 2.2 Wittman-Zartman (Ripeness)

Models the conditions under which negotiation becomes viable via the Mutually Hurting Stalemate (MHS) mechanism.

| Month | Ripe Moment | MHS | Stalemate Duration | Negotiation Prob | Event |
|-------|------------|-----|--------------------|-----------------|-------|
| All ticks | **0.000** | **0.000** | **0.000** | 0.050 | Base rate only |

Zartman never fires organically. The MHS condition requires both parties' expected utility from war to fall below the payoff floor (0.05) for at least 3 consecutive months. With Fearon EU_war values held at 0.50 (the module's static initialization), neither party crosses the hurting threshold. Negotiation progress reaches 0.60 only because of direct shock injections (t=11, t=13, t=16) — not because the ripeness model triggered it.

**Interpretation:** In this run, diplomatic resolution is externally imposed (Oman mediates as a scheduled event). The Zartman model correctly signals that organic ripeness has not been achieved — the settlement is fragile in the sense that it is not grounded in mutual exhaustion. This matches the real-world signal: Iran rejected the 15-point US peace plan on 2026-03-26 (live data), suggesting the ripe moment has not arrived.

### 2.3 SIR Contagion (Economic)

Models economic shock transmission across oil-importing states (Japan, Korea, India) via trade exposure.

| Month | Susceptible | Infected | Recovered | R_effective | Event |
|-------|-----------|---------|----------|------------|-------|
| Jan 2025 (t=0) | 92.0% | 5.1% | 3.0% | 0.287* | Baseline |
| Mar 2025 (t=2) | 91.7% | 5.2% | 3.1% | 0.287 | Nav restrictions |
| Jun 2025 (t=5) | 91.5% | 5.4% | 3.2% | — | Tanker seizure |
| Dec 2025 (t=11) | 91.1% | 5.9% | 3.2% | — | Peak stalemate |
| Aug 2026 (t=19) | 90.6% | 6.6% | 3.4% | — | Ceasefire |
| Dec 2026 (t=23) | **89.2%** | **6.9%** | **3.9%** | **0.279** | Resolution |

*R_effective < 1.0 throughout — contagion is controlled, not explosive.

The SIR model produces slow, linear contagion growth (+1.83pp infected over 24 months) rather than the exponential wave that would occur if R_effective exceeded 1.0. With beta=0.25 and gamma=0.08, R0=3.125 but effective R is damped by trade amplification dynamics. The near-collapse of trade volume (−49%) at t=5 should have amplified contagion more aggressively; the trade_amplification=0.60 parameter may be too conservative given Korea (84.6% trade/GDP) and Japan (46.4% trade/GDP) exposure levels.

### 2.4 Keynesian Multiplier

Models GDP impact of sustained oil supply disruption using fiscal multiplier dynamics.

| Month | GDP Normalized | Fiscal Shock Pending | Unemployment | Event |
|-------|--------------|---------------------|-------------|-------|
| Jan 2025 (t=0) | 0.500 | 0.500 | 5.0% | Baseline |
| Mar 2025 (t=2) | 0.500 | 0.500 | 5.0% | Nav restrictions |
| Jun 2025 (t=5) | — | — | — | Tanker seizure |
| Dec 2026 (t=23) | **0.482** | **0.488** | **6.8%** | Resolution |

GDP normalized fell 1.85% from baseline (0.500 → 0.482) and fiscal shock remains pending at 0.488 — indicating the multiplier propagation has not fully cleared by t=23. Unemployment rose from seeded 5.0% to 6.8% (+1.8pp). The Keynesian model correctly produces persistent GDP effects that outlast the strait disruption itself (strait closed = 0.00 at t=22–23, but GDP gap remains). The multiplier parameter (1.4) from Dallas Fed calibration produces a modest but sustained economic drag consistent with literature estimates for a 20% supply disruption.

### 2.5 Porter Five Forces (Shipping Industry)

Models shipping industry competitive structure under blockade conditions.

| Month | Profitability | Rivalry Intensity | Supplier Power | Barriers to Entry | Event |
|-------|-------------|------------------|---------------|-----------------|-------|
| Jan 2025 (t=0) | — | 0.500 | 0.450 | 0.440* | Baseline |
| Mar 2025 (t=2) | 0.315 | 0.500 | 0.449 | 0.440 | Nav restrictions |
| Apr 2025 (t=4) | 0.315 | 0.500 | 0.448 | 0.440 | US CSG |
| Dec 2026 (t=23) | **0.207** | **0.506** | **0.439** | **0.020** | Resolution |

*Read from t=2 snapshot; t=0 outputs not seeded.

Porter profitability collapsed from 0.315 to 0.207 (−34%) over the simulation period. Rivalry intensity increased modestly (0.500 → 0.506). The most striking result: barriers to entry fell from 0.440 to 0.020 — near zero — by scenario end. This likely reflects the model's interpretation of blockade-driven capacity destruction and insurer exit lowering barriers as surviving operators gain market share. Supplier power (tanker operators) decreased slightly (0.45 → 0.44), which is counterintuitive given the Baltic Dry Index +135% YoY live signal — the model may not be fully capturing the rate spike dynamics that Stopford (2009) would predict.

---

## 3. Cascade Interaction

The cascade runs as designed: Richardson writes military readiness → Fearon reads it for conflict probability → Zartman reads Fearon's outputs for ripeness → SIR reads trade volume for contagion → Keynesian reads SIR infected for GDP impact → Porter reads disruption for competitive intensity.

**The key cascade path that produced the dominant result:**

Richardson (unstable) → persistent Iran military buildup → Fearon reads rising `iran__military_readiness` → shifts power balance → conflict probability decays slowly (high military balance keeps Iran competitive) → Zartman reads Fearon output but EU_war values never cross hurting threshold → ripeness never fires → negotiation is 100% shock-dependent.

**The economic cascade is weaker than expected:** SIR's modest contagion (R_eff=0.279) means Keynesian receives a smaller infected-fraction shock than the trade collapse (−49%) would suggest. The amplification path from `global__trade_volume` through SIR to GDP is working correctly, but the beta=0.25/gamma=0.08 parameters produce slow contagion relative to the severity of the supply disruption. The Dallas Fed calibration (−2.9pp GDP annualized) implies a larger Keynesian effect than the current run produces — this discrepancy is partially explained by the trade_amplification parameter (0.60) smoothing the transmission.

---

## 4. Monte Carlo Distribution

**Not run.** This is a single deterministic simulation. Monte Carlo analysis would require:
- N≥100 runs with perturbation across Richardson k/l/a/b parameters (primary uncertainty source)
- Scenario weighting: base (55%) / bull — early settlement (20%) / bear — prolonged blockade (25%)
- Key output distributions: conflict probability at t=12, oil price peak, trade volume trough

The assessment projected base/bull/bear scenarios with specific probability estimates. A Monte Carlo run would validate whether those probability weights are consistent with model dynamics. Recommended: run 300-run MC as next step, perturbing richardson.k ±0.10 and fearon.info_gap_sigma ±0.05.

---

## 5. Model Limitations

| Limitation | Impact | Status |
|-----------|--------|--------|
| Fearon cold-start at t=0 (conflict_probability=1.000) | Misleading initial value; t=0 output invalid | KNOWN — fix by pre-running Richardson at t=0 before Fearon initializes |
| Richardson arms race never de-escalates (unstable params) | Iran military at 0.894, escalation index 0.947 at resolution | INTENTIONAL — calibrated to unstable crisis regime; de-escalation requires explicit shock |
| Wittman-Zartman never organically fires | Negotiation progress is 100% shock-driven; ripeness test may need EU_war recalibration | INVESTIGATE — EU_war_a/b initialized at 0.50, may need Richardson-derived inputs |
| SIR contagion modest vs. trade collapse severity | Infected fraction only +1.83pp despite 49% trade volume collapse | INVESTIGATE — trade_amplification=0.60 may be too conservative; increase to 0.80 |
| Keynesian GDP gap smaller than Dallas Fed calibration | Model produces −1.85% vs. Dallas Fed −2.9pp annualized | INVESTIGATE — fiscal_shock_pending accumulating but not fully propagating |
| Porter barriers_to_entry collapses to 0.020 | Near-zero barriers counterintuitive during blockade | INVESTIGATE — may reflect module logic error in barriers calculation |
| Trade volume overshoot at t=22–23 (0.820 > baseline 0.720) | Shock accumulation produces above-baseline trade | KNOWN — apply shock cap or return-to-trend constraint |
| No Monte Carlo run | No uncertainty bounds on any output | PENDING — run 300-run MC before presenting to stakeholder |
| No charts generated | Document references no visualizations | PENDING — generate time-series charts for key metrics |
| Kilian (2009) VAR not implemented | Supply vs. demand shock decomposition absent | PENDING (Library Gap GAP-1) |
| Stopford (2009) tanker market not implemented | Freight rate spike dynamics absent from Porter | PENDING (Library Gap GAP-2) |

---

## 6. Parameters Appendix

| Module | Key Parameters | Calibration Source |
|--------|---------------|-------------------|
| Richardson Arms Race | k=0.35, l=0.20, a=0.30, b=0.15, g=0.08, h=0.03 | Wagner et al. (1975) Iran–Iraq; WB mil exp 2024 |
| Fearon Bargaining | war_cost_a=0.20, war_cost_b=0.12, info_gap_sigma=0.15, power_shift_rate=0.05 | Fearon (1995) AER; literature review |
| Wittman-Zartman | payoff_floor=0.05, min_stalemate_ticks=3, ripe_multiplier=4.0 | JCPOA 2015 analog; Zartman (1989) |
| SIR Contagion | beta=0.25, gamma=0.08, initial_infected=0.05, trade_amplification=0.60 | Macchiati et al. (2019); WB trade/GDP (Korea 84.6%, Japan 46.4%) |
| Keynesian Multiplier | multiplier=1.4, mpc=0.72, tax_rate=0.22, import_rate=0.28 | Dallas Fed (2026): 20% disruption → −2.9pp GDP |
| Porter Five Forces | supplier_power_weight=0.25, entry_barriers_weight=0.20, rivalry_weight=0.20 | BDI +135% YoY directional signal |

**Initial environment (key values):**

| Parameter | Value | Source |
|-----------|-------|--------|
| global__oil_price | 0.680 (~$94/bbl) | WTI $93.61 FRED 2026-03-26 |
| strait__shipping_disruption | 0.080 | Lloyd's List Mar 2026 |
| iran__military_readiness | 0.620 | WB mil exp 2.01% GDP 2024 |
| us__military_readiness | 0.780 | WB mil exp 3.42% GDP + carrier group |
| iran__economic_pressure | 0.750 | Oil rents 18.27% GDP; fuel exports 56.36% |
| iran__domestic_stability | 0.400 | WGI political stability −1.694 (2023) |
| global__trade_volume | 0.720 | EIA Hormuz 20.9 mb/d = ~20% global supply |
| global__economic_stress | 0.300 | US GDP Q4 2025 +0.7% annualized (BEA) |
