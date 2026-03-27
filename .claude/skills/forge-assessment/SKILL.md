---
name: forge-assessment
version: 1.0.0
description: |
  Merges a theory brief and data brief into a single, structured assessment
  document for a scenario. Produces forge/research/{slug}-assessment.md —
  the canonical pre-simulation reference document combining theory stack,
  calibration anchors, data context, library gaps, and SimSpec stub.
  Run after /research-theory and /research-data, before /scaffold-sim.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# /forge-assessment: Assessment Document Generator

You are a simulation analyst. Your job is to synthesise a theory brief and data brief
into a single, publication-ready assessment document. This document is the canonical
reference a stakeholder reads before a simulation runs — it explains what is being
modelled, why those models were chosen, what data grounds them, what the library gaps
are, and what the SimSpec looks like.

This document is NOT the findings — it does not contain simulation results. It is the
research artefact that justifies the simulation design.

---

## Parse the request

| Parameter | Description | Example |
|-----------|-------------|---------|
| `slug` | Scenario identifier | `estee-lauder`, `hormuz-2` |
| `theory_brief` | Path to theory brief (auto-detected if not given) | `forge/research/theory-brief-{slug}.md` |
| `data_brief` | Path to data brief (auto-detected if not given) | `forge/research/data-brief-{slug}.md` |
| `output` | Output path (default: `forge/research/{slug}-assessment.md`) | |

Derive slug from the user's description if not explicit.

---

## Phase 1: Read source briefs

```bash
# Auto-detect briefs for the slug
ls forge/research/*{slug}*.md
```

Read both source files in full. Extract:

**From theory brief:**
- Recommended theory stack (priority, module, rationale, parameters)
- Module cascade description
- Calibration anchors from literature
- Library gap candidates (ADD vs FUTURE)
- Academic sources

**From data brief:**
- Entity/company data table
- Macro & sector context
- Live signals table
- Data gaps
- FRED / World Bank series used
- News/web sources

If either brief is missing, ask the user whether to proceed with what's available or run the missing skill first.

---

## Phase 2: Resolve library gaps

Check which gap candidates have since been built:

```bash
ls core/theories/*.py | xargs -I{} basename {} .py
```

For each `CANDIDATE: ADD` gap from the theory brief:
- If the module now exists in `core/theories/`: mark as **RESOLVED** — include library path and test file reference
- If not yet built: mark as **PENDING** — keep the candidate description

---

## Phase 3: Write the assessment document

Write to `forge/research/{slug}-assessment.md` using the standard structure below.
Populate every section from the source briefs. Do not invent data — if a section
cannot be populated from the briefs, mark it `[TO BE DETERMINED]`.

---

### Standard Assessment Structure

```markdown
# {Title} — Assessment & Forward Projection
**Date:** {date} | **Simulation:** {module count}-module cascade | **Skills:** /research-theory + /research-data + /forge-assessment

---

## Executive Summary

{2–3 paragraph summary covering:
  1. What entity/situation is being assessed and why
  2. The three to five key drivers identified in research
  3. The forward question the simulation will answer}

---

## {Entity} Data

{Markdown table: Metric | Value | Date | Source}
{Pull directly from data brief entity data section}

---

## Macro & Sector Context

{Bulleted list of 4–6 macro/sector context points}
{Pull from data brief context section}
{Include FRED series table if present}

---

## Recommended Theory Stack

| Priority | Module | Role | Key Parameters | Status |
|----------|--------|------|----------------|--------|
{Row per module from theory brief — mark NEW modules built from library gaps}

### Module Cascade

```
{ASCII cascade diagram showing which modules write/read each other}
```

{Narrative: "X is the stock price proxy: ... Y fires once on ..."}

---

## Calibration Anchors

| Parameter | Value | Source |
|-----------|-------|--------|
{Pull from both briefs — theory literature + data brief empirical values}

---

## Forward Signals

| Signal | Direction | Confidence | Module |
|--------|-----------|------------|--------|
{Live signals from data brief with module mapping}

{14-day projection narrative: base / bull / bear cases with probability estimates}

---

## Data Gaps & Monte Carlo Guidance

{Bulleted list of parameters that couldn't be grounded}
{MC guidance: N runs, perturbation %, scenario weights}

---

## Library Gaps

{For each gap identified in theory brief:}

### GAP-{N}: {Model Name} ({Citation}) — {RESOLVED | PENDING}
**Citation:** {full citation}

{What it models — 2 sentences}

**Relevance: {N}/5.** {Why it matters for this scenario}

**Library status:** {`core/theories/{module}.py` | Tests: `tests/test_theories_{module}.py`}
  OR
**Status: PENDING** — {recommendation for when to build}

---

## Sources

### Web / Live Data
{Links from data brief}

### Academic
{Citations from theory brief}

### SSRN
{SSRN papers from theory brief}

---

## SimSpec Stub

```python
theories = [
{TheoryRef list — one per line, with calibrated parameters}
]
```
```

---

## Phase 4: Quality check

Before writing, verify:
- [ ] Every recommended theory from the theory brief appears in the stack table
- [ ] Every calibration anchor has a source
- [ ] Library gaps are marked RESOLVED or PENDING (not left as CANDIDATE)
- [ ] SimSpec stub parameters match calibration anchors
- [ ] Forward projection has base / bull / bear with probability estimates

---

## Rules

1. **Synthesise, don't concatenate.** The assessment should read as a coherent document, not two briefs stapled together.
2. **Theory stack is the spine.** Every section should connect back to which module models it.
3. **Mark gaps honestly.** RESOLVED means the module is in the library AND tested. PENDING means it still needs building.
4. **No invented data.** If a data point isn't in a source brief, mark it `[TBD]`.
5. **SimSpec stub must be runnable.** Parameters in the stub should be the calibrated values, not placeholders.
6. **Keep it navigable.** A stakeholder should be able to read the executive summary + theory stack table and understand the full model design in 5 minutes.
