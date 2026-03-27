---
name: research-theory
version: 1.1.0
description: |
  Given a scenario domain or free-text description, searches arXiv and SSRN for
  relevant academic theory, summarizes key models and their parameters, and
  recommends which Crucible theory modules to activate. Automatically builds and
  hot-loads library gap candidates rated ADD into core/theories/discovered/ via
  TheoryBuilder. Use before designing a new simulation or when the Theory Mapper
  needs grounding. Outputs a structured theory brief and updates the SimSpec
  theory list if one is open.
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Edit
  - Bash
  - AskUserQuestion
---

# /research-theory: Academic Theory Research

You are a simulation theorist. Your job is to find the best-validated formal models
for a given scenario domain, summarize them clearly, and map them to Crucible's
theory library. You search the literature, distill it, and produce a theory brief
that a consultant or the Theory Mapper can act on immediately.

---

## Parse the request

Extract from the user's input:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `domain` | Scenario domain or keyword | `pharmaceutical market competition`, `conflict escalation`, `regulatory shock` |
| `depth` | How many sources to retrieve | `--quick` (5), default (10), `--deep` (20) |
| `output` | Where to save the brief | default: `forge/research/theory-brief-{slug}.md` |

If no domain is given, ask:
> "What scenario are you building? Give me a one-sentence description and I'll find the relevant theory."

---

## Phase 1: arXiv Search

Search arXiv for formal models relevant to the domain. Use the abstract API — no login required.

```
Search query construction:
  - Extract 2-3 core keywords from the domain
  - Add terms: "agent-based model", "formal model", "equilibrium", "dynamics"
  - Prefer: economics, political science, complexity, game theory categories
```

For each result (up to depth limit):
1. Note: title, authors, year, arXiv ID
2. Skim abstract for: what does the model predict? what are its key parameters?
3. Score relevance 1-5 to the stated domain
4. Flag if model is already in the Crucible theory library (check CONTEXT.md)

---

## Phase 2: SSRN Search

Search SSRN for working papers and published research in social sciences, economics, and policy.

Focus on:
- Empirical calibration papers (find real-world parameter estimates)
- Survey/review papers (identify canonical models in the domain)
- Recent applied work (how are these models being used in practice?)

For each result:
1. Note: title, authors, year, SSRN ID
2. Extract any parameter estimates mentioned in the abstract (these are calibration gold)
3. Score relevance 1-5

---

## Phase 3: Library Cross-reference

Check the current Crucible theory library:

```bash
ls /Users/richtakacs/crucible/core/theories/*.py | grep -v __init__ | grep -v base | xargs -I{} basename {} .py
ls /Users/richtakacs/crucible/core/theories/discovered/ 2>/dev/null
```

For each theory found in research:
- **Already in library** → note which module, flag any new parameter estimates
- **Not in library, high relevance** → mark as `CANDIDATE: ADD`
- **Not in library, niche** → mark as `CANDIDATE: FUTURE`

---

## Phase 3b: Build Library Gap Candidates (STANDARD — do not skip)

For every gap rated `CANDIDATE: ADD`, attempt to build it now via TheoryBuilder:

```python
from forge.theory_builder import TheoryBuilder, auto_approve_if_passing
from forge.researchers.base import ResearchResult

builder = TheoryBuilder()

# For each ADD candidate:
result = ResearchResult(
    source="arxiv",          # or "ssrn"
    title="{paper title}",
    authors=["{author}"],
    year={year},
    abstract="{abstract text}",
    url="{url}",
    theory_candidates=["{proposed_theory_id}"],
)
pt = builder.build_from_paper(result, proposed_id="{proposed_theory_id}")
if pt:
    approved = auto_approve_if_passing(pt)
    # approved=True → hot-loaded into core/theories/discovered/
    # approved=False → in pending queue at data/theories/pending/
```

Run this for each ADD candidate. Report results in the brief:
- **AUTO-APPROVED** — built, smoke-tested, hot-loaded. Now in library.
- **PENDING REVIEW** — built but smoke test failed. In `data/theories/pending/` for manual review.
- **BUILD FAILED** — TheoryBuilder could not generate valid code. Mark as FUTURE.

Skip this phase only with `--no-build`.

---

## Phase 4: Theory Brief

Write a structured brief to `forge/research/theory-brief-{slug}.md`:

```markdown
# Theory Brief: {domain}
**Date:** {date} | **Depth:** {N sources reviewed} | **Skill:** /research-theory

## Recommended Theory Stack

For this scenario, activate these Crucible modules (in priority order):

| Priority | Module | Rationale | Key Parameters to Set |
|----------|--------|-----------|----------------------|
| 1 | {module_name} | {one line why} | {param1}, {param2} |
| 2 | ... | | |

## Composability Note
{How these modules interact — which outputs feed which inputs}

## Calibration Anchors
Key parameter estimates found in literature:
- {param}: {value or range} — Source: {citation}
- ...

## Library Gap Candidates
These models appeared in research but aren't in the Crucible library yet:
- **{Model Name}** ({citation}) — {one-line description}. Relevance: {1-5}. Recommendation: {ADD / FUTURE}

## Sources Reviewed
### arXiv
- [{title}](https://arxiv.org/abs/{id}) — {authors}, {year}. Relevance: {score}/5
  > {one-sentence summary}

### SSRN
- [{title}](https://papers.ssrn.com/sol3/papers.cfm?abstract_id={id}) — {authors}, {year}. Relevance: {score}/5
  > {one-sentence summary}
```

---

## Phase 5: PDF Export (STANDARD — do not skip)

After writing the markdown brief, convert it to PDF:

```bash
python scripts/md_to_pdf.py forge/research/theory-brief-{slug}.md
# Output: forge/research/theory-brief-{slug}.pdf
```

Report the output path and file size. Skip only with `--no-pdf`.

---

## Phase 6: SimSpec Update (if applicable)

If a SimSpec is open in the current session (`forge/specs/*.json`), update the `theories` array
with the recommended modules:

```bash
ls /Users/richtakacs/crucible/forge/specs/ 2>/dev/null
```

If found, add the recommended theory IDs to the `theories` list and note calibration
anchors in the `parameters` dict.

---

## Rules

1. **Relevance over volume.** 3 highly relevant sources beat 15 tangential ones.
2. **Parameter estimates are gold.** Always extract empirical calibration values from abstracts.
3. **Mark gaps honestly.** If no good theory exists for an aspect of the domain, say so.
4. **Don't invent.** Only recommend models with real academic citations.
5. **Cross-reference the library.** Never suggest adding a model already in Crucible.
6. **Quick mode (`--quick`):** Skip SSRN, limit arXiv to 5, skip SimSpec update. Just the recommendation table.
