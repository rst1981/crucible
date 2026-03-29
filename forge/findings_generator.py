"""
forge/findings_generator.py — Simulation Findings Document Generator

Generates a rich, consultant-grade findings document from completed simulation
results. Structured like the DeepSeek / Hormuz results documents:
  - Executive summary with baseline → final state table
  - Theory-by-theory impact analysis
  - Key metric trajectories
  - Current state & active threats
  - Strategic implications for the client
  - Full environment state appendix

Output: forge/research/{slug}-findings.md + .pdf
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from anthropic import Anthropic

if TYPE_CHECKING:
    from forge.session import ForgeSession

logger = logging.getLogger(__name__)

_RESEARCH_DIR = Path(__file__).parent / "research"
_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def generate_findings(session: "ForgeSession", sim_results: dict) -> tuple[Path, Path]:
    """
    Generate a findings document from a completed simulation run.

    Args:
        session:     The ForgeSession with full SimSpec and research context.
        sim_results: The results dict from GET /simulations/{sim_id}.

    Returns:
        (md_path, pdf_path)
    """
    client = Anthropic()
    spec = session.simspec

    slug = _slug(spec.name or session.session_id)
    md_path  = _RESEARCH_DIR / f"{slug}-findings.md"
    pdf_path = md_path.with_suffix(".pdf")

    # ── Build context for the LLM ───────────────────────────────────────────

    ticks        = sim_results.get("ticks", 0)
    metric_series = sim_results.get("metric_series", {})
    metric_names  = sim_results.get("metric_names", {})
    final_env     = sim_results.get("final_env", {})
    theory_ids    = sim_results.get("theory_ids", [])
    snapshot_count = sim_results.get("snapshot_count", 0)

    # Build metric trajectory table (tick 0 → mid → final for each metric)
    trajectory_rows = []
    for mid, series in metric_series.items():
        if not series:
            continue
        name = metric_names.get(mid, mid.replace("_", " ").replace("__", ": ").title())
        tick0 = series[0]
        tick_mid = series[len(series)//2] if len(series) > 2 else series[-1]
        tick_final = series[-1]
        delta = tick_final - tick0
        direction = "▲" if delta > 0.01 else ("▼" if delta < -0.01 else "→")
        trajectory_rows.append(
            f"| {name} | {tick0:.3f} | {tick_mid:.3f} | {tick_final:.3f} | "
            f"{direction} {abs(delta):.3f} |"
        )

    trajectory_table = (
        "| Metric | Tick 0 | Mid | Final | Change |\n"
        "|--------|--------|-----|-------|--------|\n"
        + "\n".join(trajectory_rows)
    ) if trajectory_rows else "_No outcome metrics tracked._"

    # Final environment — show top 20 most changed keys
    env_initial = {k: v - 0.0 for k, v in final_env.items()}  # we only have final
    env_rows = "\n".join(
        f"| `{k}` | {v:.4f} |"
        for k, v in sorted(final_env.items())[:40]
    )
    env_table = "| Key | Final Value |\n|-----|-------------|\n" + env_rows

    # Research context summary
    research_summary = ""
    if session.research_context and session.research_context.results:
        ok_results = [r for r in session.research_context.results if r.ok][:8]
        research_summary = "\n".join(
            f"- {r.title}: {r.summary[:120]}..." if r.summary else f"- {r.title}"
            for r in ok_results if r.title
        )

    # Assessment path for cross-reference
    assessment_note = ""
    if session.assessment_path:
        assessment_note = f"(Cross-reference: assessment document at {session.assessment_path})"

    # Gaps resolved
    gaps_summary = ""
    if session.data_gaps:
        closed = session.closed_gaps or []
        gaps_summary = "\n".join(
            f"- {'✓' if g in closed else '○'} {g}"
            for g in session.data_gaps
        )

    # ── LLM call ────────────────────────────────────────────────────────────

    system = (
        "You are a senior consultant writing a simulation findings document for a client. "
        "Write in a professional, analytical style — like the best McKinsey/Accenture output. "
        "Be specific: reference actual numbers from the simulation data. "
        "Every section should contain insights, not just descriptions. "
        "Use markdown tables, headers, and bold text for structure. "
        "Do not write generic placeholders — every sentence should earn its place."
    )

    prompt = f"""Write a complete simulation findings document for the following scenario.

## Scenario
**Name:** {spec.name}
**Domain:** {spec.domain}
**Description:** {spec.description or session.intake_text[:300]}
**Timeframe:** {spec.timeframe.total_ticks} ticks ({spec.timeframe.tick_unit})
**Outcome Focus:** {(spec.metadata or {}).get('outcome_focus', 'Not specified')}

## Simulation Parameters
- **Theories active:** {', '.join(theory_ids) or 'none'}
- **Actors:** {len(spec.actors)} ({', '.join(a.name for a in spec.actors[:6])})
- **Ticks completed:** {ticks}
- **Snapshots:** {snapshot_count}
- **Data gaps resolved:** {len(session.closed_gaps or [])} of {len(session.data_gaps or [])}
{assessment_note}

## Metric Trajectories
{trajectory_table}

## Final Environment State (selected)
{env_table}

## Research Grounding
{research_summary or 'No external research sources available.'}

## Data Gaps
{gaps_summary or 'No gaps identified.'}

---

Write the findings document with these sections:

# {{Scenario Name}} — Simulation Findings
**Date:** {time.strftime('%Y-%m-%d')} | **Ticks:** {ticks} | **Theories:** {len(theory_ids)}

## Executive Summary
(3-4 sentences: what the sim was testing, what happened, and the headline finding)

## Baseline Configuration
(Table: key metrics at tick 0, their interpretation, and calibration source)

## Key Dynamics — What Drove the Outcome
(One subsection per active theory. For each: what it modeled, how it behaved in this run, what values it reached, and what that means for the scenario. Be specific about numbers.)

## Metric Trajectories & Interpretation
(Reference the trajectory table. Explain the shape of each major metric's path — not just the values, but what the pattern means.)

## Final State Assessment
(Table: metric | final value | status (Critical/High/Moderate/Stable) | interpretation)
(Follow with 3-5 bullet points on the most important findings)

## Strategic Implications for {(spec.metadata or {}).get('client_type', 'the client')}
(What should the client actually do with these findings? 4-6 specific, actionable recommendations tied to simulation outputs.)

## Limitations & Caveats
(Brief: what the model can and cannot tell us, what data gaps remain)

## Appendix: Full Simulation Parameters
(List all active theories with their key parameters from the environment state)
"""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )

    md_content = resp.content[0].text.strip()
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Findings MD written: %s", md_path)

    # Convert to PDF
    try:
        from scripts.md_to_pdf import convert
        pdf_path = convert(md_path, quiet=True)
        logger.info("Findings PDF written: %s", pdf_path)
    except Exception as exc:
        logger.warning("Findings PDF conversion failed: %s", exc)
        pdf_path = md_path.with_suffix(".pdf")

    return md_path, pdf_path
