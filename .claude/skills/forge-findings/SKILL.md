---
name: forge-findings
version: 1.0.0
description: |
  Generates a structured simulation results and findings document from a
  completed scenario run. Reads results.json and the scenario's run_simulation.py,
  produces forge/research/{slug}-simulation-results.md. Replaces ad-hoc
  writeups with a reproducible, standard findings format. Run after the
  simulation completes. Use core/reporting.py utilities to extract data.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# /forge-findings: Simulation Findings Document Generator

You are a quantitative analyst. Your job is to turn raw simulation output — a results.json
with deterministic series, Monte Carlo bands, and environment snapshots — into a structured
findings document that a non-technical stakeholder can read alongside the assessment.

This document answers: what did the simulation produce, what does it mean, and what are the
limits of the model? It is the second half of the research-to-findings pipeline:

```
/research-theory + /research-data → /forge-assessment → [simulate] → /forge-findings
```

---

## Parse the request

| Parameter | Description | Example |
|-----------|-------------|---------|
| `slug` | Scenario identifier | `estee-lauder`, `hormuz-2` |
| `results` | Path to results.json (auto-detected if not given) | `scenarios/{slug}/results.json` |
| `assessment` | Path to assessment doc for context (optional) | `forge/research/{slug}-assessment.md` |
| `output` | Output path (default: `forge/research/{slug}-simulation-results.md`) | |

---

## Phase 1: Load simulation output

```bash
# Verify results file exists
ls scenarios/{slug}/results.json
```

Load and parse `results.json`. Determine format:
- **v2 format:** `{"deterministic": {"series": {...}, "final_env": {...}}, "monte_carlo": {"bands": {...}}}`
- **v1 format (legacy):** `{"series": {...}, "final_env": {...}}`

Use `core/reporting.py` utilities to extract data:

```python
from core.reporting import SimResults, fmt_pct, fmt_price
r = SimResults.load("scenarios/{slug}/results.json")
```

---

## Phase 2: Read scenario design

Read the scenario's `run_simulation.py` or `run.py` to extract:
- Total ticks and tick unit
- Theory modules used (names, priorities, parameters)
- Shock schedule (tick → variables shocked)
- Outcome metrics tracked
- MC configuration (N runs, scenario weights if present)

If an assessment doc exists, skim it for:
- The three to five key causes identified in research
- Library gap status (which modules are new)
- Calibration anchors (to cross-check model outputs)

---

## Phase 3: Compute key numbers

Before writing, extract the following numbers from results.json. You will use these
throughout the document — do not write placeholder values, compute the real ones.

**Sentiment / Stock proxy:**
- Value at tick 0, first major shock, Puig/key event, today (tick 30), projection end
- MC p50 at projection end; MC p5 and p95 range

**Per new module (if present):**
- `acquirer_discount`: CAR at announcement tick and final tick (convert: `(val - 0.5) * 40` → %)
- `brand_equity_decay`: equity at tick 0 and final; % erosion
- `event_study`: per-event AR and cumulative CAR (same conversion)

**MC:**
- N runs, scenario weights
- p5/p25/p50/p75/p95 for primary metric at final tick
- Band width (p95 - p5) as uncertainty measure

---

## Phase 4: Write the findings document

Write to `forge/research/{slug}-simulation-results.md` using the standard structure below.
All numbers must come from the actual simulation output, not from the assessment or
prior expectations.

---

### Standard Findings Structure

```markdown
# {Title} — Simulation Results & Analysis {(v{N} if versioned)}
**Date:** {date} | **Ticks:** {N} {unit}s ({start_date} – {end_date})
**Version:** {N} — {module count} theory modules + {MC runs}-run Monte Carlo
(if applicable)

---

## Executive Summary

### Baseline Position
{2–3 sentences describing the entity's position at tick 0 from the assessment.}
{Data table: key metrics at start of window}

---

### Causes of the {N}-{unit} Decline / Change
{For each major cause (3–5):}
**{N}. {Cause Name}** *(tick {X}; {module} AR contribution: {±N%} if available)*
{2–3 sentence explanation grounded in model outputs, not just theory}

**Total identified event CAR: {N}%** (if event_study is present)

---

### Current State and Active Threats

| Indicator | Level | Trend | Threat Severity |
|-----------|-------|-------|----------------|
{Row per key metric from final_env or last tick of series}

**Primary active threats:** (bulleted list of 3–5)

---

### {N}-{unit} Projection

{Model-derived if MC present; hand-labeled if deterministic only}

| Scenario | {Primary metric} range | Trigger | Probability |
|----------|----------------------|---------|-------------|
| Base | ... | ... | ~{N}% |
| Bull | ... | ... | ~{N}% |
| Bear | ... | ... | ~{N}% |

{Note on relationship between sentiment proxy and analyst price targets if applicable}

---

## Executive Findings

{4–6 paragraph narrative covering:
  - The overall shape of the decline / change
  - The three shock waves or phases
  - The cascade interaction (why this entity underperformed peers if applicable)
  - What the MC bands say about uncertainty}

{Embed chart references: ![Caption](../../scenarios/{slug}/charts/{fig}.png)}

---

## 1. Simulation Design

### Architecture ({N} Modules)

```
{ASCII priority cascade diagram}
```

### Timeframe and Shocks

| Variable | Value |
|----------|-------|
| Tick unit | {unit} |
| Tick 0 | {date} — {event} |
...

| Tick | Event | Key Variables |
|------|-------|---------------|
{Row per scheduled shock}

---

## 2. Results by Module

{One subsection per theory module:}

### 2.{N} {Module Display Name} {(NEW if library gap)}

{1–2 sentence description of what this module models in this scenario}

| Day | {metric 1} | {metric 2} | ... | Event |
|-----|-----------|-----------|-----|-------|
{Data table at key ticks from results.json}

{2–3 sentence interpretation of the results}

---

## 3. Cascade Interaction

{How module outputs fed into each other — which cascade produced the anomalous result?}
{Why did this entity underperform comparables?}

---

## 4. Monte Carlo Distribution (if present)

**{N} runs.** Scenarios: {base N%} / {bull N%} / {bear N%}.

{MC summary table: metric | p5 | p25 | p50 | p75 | p95}

{Interpretation: band width, forward uncertainty, what drives divergence}

---

## 5. Model Limitations

| Limitation | Impact | Status |
|-----------|--------|--------|
{Row per limitation — mark RESOLVED if fixed vs prior version}

---

## 6. Parameters Appendix

| Module | Key Parameters | Calibration Source |
|--------|---------------|-------------------|
{Row per module}
```

---

## Phase 5: Generate charts (STANDARD — do not skip)

Run the shared chart generator before writing the document so chart paths are known:

```bash
python scripts/generate_charts.py {slug}
# Output: scenarios/{slug}/charts/fig1_metrics_dashboard.png
#                                  fig2_shock_cascade.png
#                                  fig3_mc_fan.png
#                                  fig4_secondary_indicators.png
#                                  fig5_mc_final_distribution.png
```

If the script is missing a scenario plan for this slug it will auto-detect metrics from
results.json and produce a best-effort chart set.  Add a named plan to
`scripts/generate_charts.py _SCENARIO_PLANS` after the run if you want to customise
labels, colours, or shock annotations.

Skip only with `--no-charts`.

---

## Phase 6: Embed chart references

After charts are generated, embed them in the findings document at these standard locations
using **absolute paths** (required for weasyprint PDF rendering):

| Figure | Placement |
|--------|-----------|
| `fig1_metrics_dashboard.png` | After the Simulation Design section header |
| `fig2_shock_cascade.png` | End of Executive Findings narrative |
| `fig3_mc_fan.png` | End of Executive Findings narrative (after fig2) |
| `fig4_secondary_indicators.png` | Before the Cascade Interaction section |
| `fig5_mc_final_distribution.png` | End of Monte Carlo section |

Use absolute paths for all image references (required for PDF):

```markdown
![Caption](/absolute/path/to/scenarios/{slug}/charts/fig1_metrics_dashboard.png)
```

To get the absolute path:
```bash
python -c "import pathlib; print(pathlib.Path('scenarios/{slug}/charts').resolve())"
```

---

## Phase 7: PDF Export (STANDARD — do not skip)

After writing the markdown findings document with chart references, convert it to PDF:

```bash
python scripts/md_to_pdf.py forge/research/{slug}-simulation-results.md
# Output: forge/research/{slug}-simulation-results.pdf
```

The shared CSS (`forge/research/forge-research.css`) includes `max-width: 100%; height: auto`
on all `img` elements — charts will scale correctly to A4 page width automatically.

Report the output path and file size. Skip only with `--no-pdf`.

---

## Phase 8: Quality check

Before finalising:
- [ ] `python scripts/generate_charts.py {slug}` ran without errors
- [ ] Every chart reference in the document uses an absolute path
- [ ] PDF export produced no image fetch warnings
- [ ] Every number in the Executive Summary is sourced from results.json (not estimated)
- [ ] Every module has a results section with actual data table values
- [ ] MC section is present if MC data exists; absent or noted if not
- [ ] Limitations table marks previously open items as RESOLVED if the v2 sim fixed them
- [ ] Parameters appendix covers all modules in the cascade

---

## Rules

1. **Numbers first.** Extract all key values before writing a word. Writing around placeholder numbers produces wrong documents.
2. **Results drive narrative, not vice versa.** If the model produced a surprising result, report it and explain it — don't smooth it over to match expectations.
3. **Distinguish deterministic from MC.** Always be clear which numbers come from the deterministic run vs. MC bands.
4. **Mark new modules.** Any module built from a library gap should be labelled `(NEW — Roll 1986)` or similar in its section heading.
5. **Limitations are honest.** If the model has a known weakness, say so. The limitations table should get shorter across versions as gaps are resolved.
6. **Findings ≠ Assessment.** Do not repeat research context that belongs in the assessment. The findings doc assumes the reader has read the assessment.
