"""
forge/assessment_generator.py — Assessment document generator

Given a ForgeSession (post-ensemble-review), generates:
  - forge/research/{slug}-assessment.md   (Markdown)
  - forge/research/charts/{slug}/         (charts)
  - forge/research/{slug}-assessment.pdf  (PDF via pandoc + weasyprint)

Called via POST /forge/intake/{session_id}/assessment.
Uses claude-haiku for prose sections, matplotlib for charts.

Document structure matches the Hormuz/DeepSeek reference format:
  Executive Summary → Actor Data → Macro & Sector Context →
  Recommended Theory Stack → Calibration Anchors → Forward Signals →
  Data Gaps & MC Guidance → Library Gaps (if any) → Sources → SimSpec Stub
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import textwrap
from datetime import date
from typing import TYPE_CHECKING, Any

from anthropic import Anthropic

if TYPE_CHECKING:
    from forge.session import ForgeSession

logger = logging.getLogger(__name__)

_REPO = pathlib.Path(__file__).parent.parent
_RESEARCH_DIR = _REPO / "forge" / "research"
_MODEL = "claude-haiku-4-5-20251001"


# ── Public API ──────────────────────────────────────────────────────────────

def generate_assessment(session: "ForgeSession") -> tuple[pathlib.Path, pathlib.Path]:
    """
    Generate assessment MD + PDF for a ForgeSession.

    Returns (md_path, pdf_path).
    Writes charts to forge/research/charts/{slug}/ first.
    """
    slug = _slugify(session.simspec.name if session.simspec else "scenario")
    md_path = _RESEARCH_DIR / f"{slug}-assessment.md"
    charts_dir = _RESEARCH_DIR / "charts" / slug
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate charts
    chart_paths = _generate_charts(session, charts_dir)

    # 2. Generate markdown
    md = _build_markdown(session, slug, chart_paths)
    md_path.write_text(md, encoding="utf-8")
    logger.info("Assessment MD written: %s", md_path)

    # 3. Convert to PDF
    try:
        from scripts.md_to_pdf import convert
        pdf_path = convert(md_path, quiet=True)
        logger.info("Assessment PDF written: %s", pdf_path)
    except Exception as exc:
        logger.warning("PDF conversion failed: %s", exc)
        pdf_path = md_path.with_suffix(".pdf")

    return md_path, pdf_path


# ── Chart generation ────────────────────────────────────────────────────────

PALETTE = [
    "#6B7F8C", "#8A9E8A", "#7A8A9E", "#9E9A8A", "#6A8A8A",
    "#8A8A9E", "#9E8A8A", "#7A9A8A", "#8A9A9E", "#909090",
]
STYLE = {"dpi": 150, "bbox_inches": "tight"}

THEORY_FEATURE_MAP = {
    "fearon_bargaining": ["conflict probability", "information asymmetry", "war costs", "power balance", "bargaining range"],
    "richardson_arms_race": ["military readiness", "escalation index", "arms expenditure", "mutual fatigue"],
    "wittman_zartman": ["negotiation probability", "ripeness condition", "mediator presence", "stalemate duration"],
    "keynesian_multiplier": ["gdp gap", "fiscal multiplier", "consumption", "investment demand"],
    "sir_contagion": ["economic contagion", "trade disruption", "recovery rate", "infected fraction"],
    "porter_five_forces": ["competitive intensity", "supplier power", "market structure", "entry barriers"],
    "minsky_instability": ["financial fragility", "debt deflation", "credit spreads", "leverage ratio"],
    "hotelling_resource": ["resource scarcity", "price trajectory", "extraction constraint", "depletion rate"],
    "oil_price_shock": ["oil price", "inflation", "recession probability", "demand contraction"],
}

# Map theory_id → key env output keys for cascade display
_THEORY_OUTPUT_MAP: dict[str, list[str]] = {
    "fearon_bargaining":    ["fearon__conflict_probability", "fearon__win_prob_a"],
    "richardson_arms_race": ["richardson__escalation_index", "actor__military_readiness"],
    "wittman_zartman":      ["zartman__ripe_moment", "zartman__negotiation_probability"],
    "keynesian_multiplier": ["keynesian__gdp_gap", "keynesian__output_multiplier"],
    "sir_contagion":        ["economic__infected", "economic__active_contagion"],
    "porter_five_forces":   ["porter__competitive_intensity"],
    "minsky_instability":   ["minsky__financial_fragility", "minsky__leverage_ratio"],
    "hotelling_resource":   ["hotelling__price_trajectory", "hotelling__depletion_rate"],
    "oil_price_shock":      ["oil__price", "macro__inflation_rate", "macro__recession_probability"],
}


def _apply_rcparams():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
        "grid.color": "#d0d4d8",
        "axes.facecolor": "#f8f8f8",
        "figure.facecolor": "#ffffff",
        "axes.edgecolor": "#c8cacf",
        "xtick.color": "#4a4a4a",
        "ytick.color": "#4a4a4a",
        "axes.labelcolor": "#4a4a4a",
        "text.color": "#2a2a2a",
    })
    return plt


def _generate_charts(session: "ForgeSession", charts_dir: pathlib.Path) -> list[pathlib.Path]:
    """Generate a single calibration confidence chart (fig1_calibration.png)."""
    paths: list[pathlib.Path] = []

    try:
        plt = _apply_rcparams()

        # Chart 1: Theory ensemble scores (both tiers)
        recs = session.recommended_theories + (session.discovered_theories or [])
        if recs:
            fig, ax = plt.subplots(figsize=(8, max(3, len(recs) * 0.6)))
            names = [r["display_name"] for r in recs]
            scores = [r["score"] for r in recs]
            bars = ax.barh(names, scores, color=PALETTE[:len(recs)])
            ax.set_xlabel("Relevance Score")
            ax.set_title("Theory Ensemble — Relevance Scores", fontweight="bold", pad=12)
            ax.set_xlim(0, 1)
            for bar, score in zip(bars, scores):
                ax.text(score + 0.01, bar.get_y() + bar.get_height() / 2,
                        f"{score:.2f}", va="center", fontsize=9)
            fig.tight_layout()
            p = charts_dir / "fig1_theory_scores.png"
            fig.savefig(p, **STYLE)
            plt.close(fig)
            paths.append(p)

        # Calibration confidence chart
        ctx = session.research_context
        calib = ctx.parameter_estimates if ctx else {}
        if calib:
            keys = list(calib.keys())[:16]
            vals = [calib[k] for k in keys]
            short_keys = [k.replace("global__", "").replace("_", " ") for k in keys]
            colors = [
                "#5A7A8A" if v > 0.7 else "#A0A8A0" if v < 0.5 else "#8A9E8A"
                for v in vals
            ]
            fig, ax = plt.subplots(figsize=(8, max(3, len(keys) * 0.5)))
            ax.barh(short_keys, vals, color=colors)
            ax.set_xlabel("Parameter Value [0–1]")
            ax.set_title("Calibration Anchors — Parameter Values", fontweight="bold", pad=12)
            ax.set_xlim(0, 1)
            fig.tight_layout()
            p = charts_dir / "fig1_calibration.png"
            fig.savefig(p, **STYLE)
            plt.close(fig)
            paths.append(p)

    except Exception as exc:
        logger.warning("Chart generation failed: %s", exc)

    return paths


# ── Markdown builder ────────────────────────────────────────────────────────

def _build_markdown(
    session: "ForgeSession",
    slug: str,
    chart_paths: list[pathlib.Path],
) -> str:
    spec = session.simspec
    ctx  = session.research_context
    # Combine Tier 1 (library) + Tier 2 (discovered) for the full ensemble view
    recs = session.recommended_theories + (session.discovered_theories or [])

    today = date.today().strftime("%B %d, %Y")
    name  = spec.name if spec else "Unnamed Scenario"
    domain = spec.domain if spec else "—"
    raw_focus = (spec.metadata or {}).get("outcome_focus", "—") if spec else "—"
    outcome_focus = re.sub(r'^#{1,6}\s*', '', raw_focus, flags=re.MULTILINE)
    outcome_focus = re.sub(r'\*+', '', outcome_focus).strip()
    if "empirically" in outcome_focus.lower() and len(outcome_focus) < 120:
        outcome_focus = "Model-driven — theoretical framework selected empirically from research"
    ticks = spec.timeframe.total_ticks if spec else 0
    tick_unit = spec.timeframe.tick_unit if spec else "month"
    start_date = spec.timeframe.start_date if spec else "—"
    n = len(recs)

    # Prose via haiku (single call returns dict with all keys)
    exec_summary, _data_gaps_haiku = _generate_prose(session)

    # Use the scoping agent's gaps if already identified — haiku may drift on count
    if session.data_gaps or session.proprietary_gaps:
        all_gaps = (session.proprietary_gaps or []) + (session.data_gaps or [])
        closed = set(session.closed_gaps or [])
        data_gaps = "\n".join(
            f"- {'✓' if g in closed else '○'} {g}" for g in session.data_gaps or []
        )
        if session.proprietary_gaps:
            data_gaps = "\n".join(f"- ⊘ {g}" for g in session.proprietary_gaps) + "\n" + data_gaps
    else:
        data_gaps = _data_gaps_haiku

    # Sections
    actors_md        = _actors_table(spec, session)
    actor_data_md    = _actor_data_section(session, {})
    env_md           = _env_table(spec)
    theories_md      = _theories_table(recs)
    calib_md         = _calibration_table(ctx)
    calib_v2_md      = _calibration_table_v2(ctx)
    sources_md       = _sources_section_v2(ctx)
    cascade_ascii    = _module_cascade_ascii(recs)
    signals_md       = _forward_signals(session)
    library_gaps     = _discovered_theories_section(ctx, recs)
    simspec_stub     = _simspec_stub(session)
    gap_section_raw  = _gap_research_section(session)
    gap_section      = f"\n{gap_section_raw}\n" if gap_section_raw else ""
    comparative_md   = _comparative_analysis(session, recs)

    # Chart embeds
    chart_embed = ""
    for cp in chart_paths:
        if cp.name == "fig1_calibration.png":
            rel = f"charts/{slug}/fig1_calibration.png"
            chart_embed = f"![Calibration Anchors — Parameter Values]({rel})\n*Figure: Calibration Anchors — Parameter Values*\n"
            break

    # Also embed fig1_theory_scores for backward-compat with embed test
    chart_embeds_theory = ""
    for cp in chart_paths:
        if cp.name == "fig1_theory_scores.png":
            rel = f"charts/{slug}/fig1_theory_scores.png"
            chart_embeds_theory = f"\n![Figure 1: Theory ensemble relevance scores]({rel})\n*Figure 1: Theory ensemble relevance scores*\n"
            break

    # Monte Carlo guidance
    domain_mc = {
        "market":      "300–500 runs; perturb price_sensitivity ±20%, churn_rate ±15%",
        "geopolitics": "200–400 runs; perturb escalation_prob ±25%, resolve_threshold ±20%",
        "conflict":    "200–400 runs; perturb escalation_prob ±25%, resolve_threshold ±20%",
        "macro":       "200–300 runs; perturb gdp_growth ±15%, inflation ±10%",
        "corporate":   "200–400 runs; perturb market_share ±15%, cost_pressure ±20%",
        "ecology":     "300–500 runs; perturb climate_stress ±20%, resource_availability ±25%",
    }.get(domain, "200–400 runs; perturb key parameters ±15–25%")

    top_params = list((ctx.parameter_estimates or {}).keys())[:4] if ctx else []
    sensitivity_params = ", ".join(top_params) if top_params else "key initial environment parameters"

    custom_note = ""
    if session.custom_theories:
        custom_note = (
            f"\n**Custom ensemble** ({len(session.custom_theories)} modules) also configured "
            f"— both will run in parallel for comparison.\n"
        )

    # Pull richer sections from prose_data stored by _generate_prose
    prose_data = getattr(session, '_prose_data', {}) or {}
    base_pct  = prose_data.get("base_pct", 55)
    bull_pct  = prose_data.get("bull_pct", 25)
    bear_pct  = prose_data.get("bear_pct", 20)
    s_base = prose_data.get("scenario_base") or f"{outcome_focus} under current trajectory."
    s_bull = prose_data.get("scenario_bull") or "Upside scenario if key risks resolve."
    s_bear = prose_data.get("scenario_bear") or "Downside if primary risks materialize."
    scenario_projection = (
        f"**Base case (~{base_pct}%):** {s_base}\n\n"
        f"**Bull case (~{bull_pct}%):** {s_bull}\n\n"
        f"**Bear case (~{bear_pct}%):** {s_bear}"
    )

    macro_context_bullets = ""
    mc_list = prose_data.get("macro_context", [])
    if mc_list:
        macro_context_bullets = "\n".join(
            f"- {item}" if not str(item).startswith("-") else str(item)
            for item in mc_list
        )
    else:
        macro_context_bullets = _macro_context_md(ctx)

    doc = f"""# {name} — Scenario Assessment
**Date:** {today} | **Simulation:** {n}-module cascade | **Generated by:** Crucible Forge

---

## Executive Summary

{exec_summary}

---

## Comparative Analysis

{comparative_md}

---

## Scenario

**Simulation Horizon:** {ticks} {tick_unit}s (starting {start_date})
**Outcome Focus:** {outcome_focus}

### Actors

{actors_md}

### Initial Conditions

{env_md}

---

## Macro & Sector Context

{macro_context_bullets}

---

## Recommended Theory Stack

{theories_md}

### Module Cascade

```
{cascade_ascii}
```
{chart_embeds_theory}

---

## Calibration Anchors

{chart_embed}
{calib_v2_md}

---

## Forward Signals

{signals_md}

---

## Data Gaps & Monte Carlo Guidance

{data_gaps}

**Monte Carlo guidance:** {domain_mc}. Perturb: {sensitivity_params}. Horizon: {ticks} {tick_unit}s. Run 1 deterministic baseline first, then launch MC.
{custom_note}{gap_section}

---

{library_gaps}

## Sources

{sources_md}

---

## SimSpec Stub

```python
{simspec_stub}
```
"""
    return doc.strip()


# ── Prose generation (haiku) ────────────────────────────────────────────────

def _generate_prose(session: "ForgeSession") -> tuple[str, str]:
    """
    Generate executive summary and data gaps via a single haiku call.

    Returns (exec_summary, data_gaps) as strings.
    Also extracts macro_context, actor_data_rows, forward_signals, scenario
    projections — stored on session if available, but the public API is the
    same tuple for backward compatibility with tests.
    """
    spec = session.simspec
    ctx  = session.research_context

    # Build research snippets (first 12 ok results)
    snippets_list = []
    if ctx and ctx.results:
        for r in ctx.results[:12]:
            if getattr(r, 'ok', True):
                snippets_list.append(getattr(r, 'to_context_snippet', lambda: str(r))())
    snippets = "\n\n".join(snippets_list)[:4000]

    all_recs = session.recommended_theories + (session.discovered_theories or [])
    theory_ids = ", ".join(r["theory_id"] for r in all_recs)
    theory_names = ", ".join(r["display_name"] for r in all_recs)
    actor_names = ", ".join(a.name for a in spec.actors) if spec and spec.actors else "none"

    context = f"""Scenario: {spec.name if spec else 'Unnamed'}
Domain: {spec.domain if spec else 'unknown'}
Outcome focus: {(spec.metadata or {}).get('outcome_focus', 'not specified') if spec else 'not specified'}
Actors: {actor_names}
Timeframe: {spec.timeframe.total_ticks if spec else 0} {spec.timeframe.tick_unit if spec else 'months'}
Theory IDs: {theory_ids}
Theory display names: {theory_names}
Parameter estimates: {json.dumps(ctx.parameter_estimates if ctx else {}, indent=2)}
Research results count: {len(ctx.results) if ctx else 0}
Library additions: {', '.join(ctx.library_additions) if ctx and ctx.library_additions else 'none'}

Research snippets:
{snippets}"""

    prompt = f"""You are a simulation analyst writing a pre-run assessment document.

{context}

Return a JSON object with EXACTLY these keys:

"exec_summary": 3-4 analytical paragraphs (plain text, no markdown headers).
  Cover: what entity/situation is being assessed and why it matters; the 3-5 key drivers
  from research with real numbers where available; what the simulation will answer.

"macro_context": list of 5-6 strings, each a bullet point with a real data point
  (e.g. "WTI $93.61/bbl (+3.6% today)", "US CPI 3.2% YoY (BLS Jan 2026)").
  Extract from research snippets where possible; infer plausible values if not.

"actor_data_rows": list of dicts, one per actor. Each dict:
  {{"actor": str, "category": str, "metric1_label": str, "metric1_val": str,
    "metric2_label": str, "metric2_val": str, "source": str}}
  Extract real metrics from research snippets (e.g. GDP, military budget, market share).

"data_gaps": list of 4-5 strings (each is a bullet point starting with "- ").
  Cover: parameters not empirically grounded, inaccessible sources, what would reduce
  uncertainty most, Monte Carlo guidance given gaps.

"forward_signals": list of 3-5 dicts:
  {{"signal": str, "direction": str, "confidence": str, "module": str}}
  direction: "↑" or "↓" or "→". confidence: "High"/"Medium"/"Low". module: theory_id.

Write in a direct, analytical consulting voice. No fluff. Return ONLY valid JSON."""

    try:
        client = Anthropic()
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        exec_summary = data.get("exec_summary", "")

        # data_gaps: handle list or string
        # Never overwrite session.data_gaps if already populated by the scoping agent
        data_gaps_raw = data.get("data_gaps", "")
        if isinstance(data_gaps_raw, list):
            data_gaps = "\n".join(
                item if str(item).startswith("-") else f"- {item}"
                for item in data_gaps_raw
            )
            if not session.data_gaps:
                session.data_gaps = [str(item).lstrip("- ").strip() for item in data_gaps_raw]
        else:
            data_gaps = data_gaps_raw

        # Stash full prose data on session for use in richer sections
        try:
            session._prose_data = data  # type: ignore[attr-defined]
        except Exception:
            pass

        return exec_summary, data_gaps

    except Exception as exc:
        logger.warning("Prose generation failed: %s", exc)
        spec_name = spec.name if spec else "this scenario"
        return (
            f"This assessment covers {spec_name}. "
            f"Research identified {len(session.recommended_theories) + len(session.discovered_theories or [])} relevant theory modules."
        ), "- Parameter estimates require empirical validation before launch."


# ── Gap research section ────────────────────────────────────────────────────

def _gap_research_section(session: "ForgeSession") -> str:
    """
    Build the gap research results section for the assessment document.

    If gap_research_complete is False: returns empty string (original gaps already
    rendered in the Data Gaps section above).
    If True: returns a subsection showing closed vs remaining gaps.
    """
    if not getattr(session, "gap_research_complete", False):
        return ""

    closed = getattr(session, "closed_gaps", []) or []
    remaining = getattr(session, "remaining_gaps", []) or []

    if not closed and not remaining:
        return ""

    lines = ["### Gap Research Results\n"]
    for gap in closed:
        lines.append(f"- ✓ {gap}")
    for gap in remaining:
        lines.append(f"- ○ {gap}")

    return "\n".join(lines)


# ── Actor Data section ───────────────────────────────────────────────────────

def _actor_data_section(session: "ForgeSession", prose_data: dict) -> str:
    """
    Build Actor Data table from prose_data["actor_data_rows"].
    Falls back to listing actor names with spec metadata if empty.
    """
    spec = session.simspec
    rows_data = prose_data.get("actor_data_rows", []) if prose_data else []

    # Also try session._prose_data if available
    if not rows_data:
        try:
            rows_data = getattr(session, '_prose_data', {}).get("actor_data_rows", [])
        except Exception:
            rows_data = []

    if rows_data:
        header = "| Actor | Category | Metric 1 | Value 1 | Metric 2 | Value 2 | Source |"
        sep    = "|-------|----------|----------|---------|----------|---------|--------|"
        lines  = [header, sep]
        for row in rows_data:
            actor  = row.get("actor", "—")
            cat    = row.get("category", "—")
            m1l    = row.get("metric1_label", "—")
            m1v    = row.get("metric1_val", "—")
            m2l    = row.get("metric2_label", "—")
            m2v    = row.get("metric2_val", "—")
            src    = row.get("source", "—")
            lines.append(f"| {actor} | {cat} | {m1l} | {m1v} | {m2l} | {m2v} | {src} |")
        return "\n".join(lines)

    # Fallback: spec-based table with research context
    if not spec or not spec.actors:
        return "*No actor data available.*"

    ctx = session.research_context
    header = "| Actor | Category | Notes |"
    sep    = "|-------|----------|-------|"
    lines  = [header, sep]
    for a in spec.actors:
        meta = getattr(a, 'metadata', {}) or {}
        cat  = meta.get('role', '—')
        desc = meta.get('description', '') or ''
        # Try to find a research snippet mentioning this actor
        if ctx and ctx.results:
            for r in ctx.results[:5]:
                if getattr(r, 'ok', True):
                    raw = str(getattr(r, 'raw', '') or '')
                    summary = getattr(r, 'summary', '') or ''
                    if a.name.lower() in raw.lower() or a.name.lower() in summary.lower():
                        if summary:
                            desc = summary[:120]
                        break
        lines.append(f"| {a.name} | {cat} | {desc or '—'} |")
    return "\n".join(lines)


# ── Macro context section ────────────────────────────────────────────────────

def _macro_context_md(ctx: Any) -> str:
    """Return macro context bullets from session._prose_data if available."""
    # This function is called with ctx (ResearchContext) — we can't access
    # session._prose_data here directly, so we build from ctx.parameter_estimates
    # The rich version is populated after _generate_prose runs.
    if not ctx or not ctx.parameter_estimates:
        return "*Macro context will be populated from research data.*"
    lines = []
    for k, v in list(ctx.parameter_estimates.items())[:6]:
        label = k.replace("global__", "").replace("_", " ").title()
        lines.append(f"- **{label}:** {v:.3f} (calibrated estimate)")
    return "\n".join(lines) if lines else "*No macro data available.*"


# ── Module cascade ASCII ─────────────────────────────────────────────────────

def _module_cascade_ascii(recs: list[dict]) -> str:
    """Generate ASCII art cascade showing theory read/write flow."""
    if not recs:
        return "No theories selected."
    if len(recs) == 1:
        tid   = recs[0]["theory_id"]
        dname = recs[0]["display_name"]
        outs  = _THEORY_OUTPUT_MAP.get(tid, [f"{tid}__state"])
        return f"[P0] {tid}\n     writes: {', '.join(outs)}"

    lines = []
    all_written: list[str] = []

    for i, r in enumerate(recs):
        tid   = r["theory_id"]
        outs  = _THEORY_OUTPUT_MAP.get(tid, [f"{tid}__state"])
        reads = list(all_written)[-3:] if all_written else []  # reads from prior module outputs

        writes_str = ", ".join(outs)
        if reads:
            reads_str  = ", ".join(reads)
            lines.append(f"[P{i}] {tid}")
            lines.append(f"     writes: {writes_str}")
            lines.append(f"     reads:  {reads_str}")
        else:
            lines.append(f"[P{i}] {tid}")
            lines.append(f"     writes: {writes_str}")
            lines.append(f"     reads:  (initial environment)")

        all_written.extend(outs)
        if i < len(recs) - 1:
            lines.append("       |")
            lines.append("       v")

    return "\n".join(lines)


# ── Calibration table v2 (real source attribution) ──────────────────────────

def _calibration_table_v2(ctx: Any) -> str:
    """Calibration table with real source attribution from research results."""
    if not ctx or not ctx.parameter_estimates:
        return "*No calibration data available from research.*"

    rows = [
        "| Parameter | Value | Source |",
        "|-----------|-------|--------|",
    ]
    for k, v in ctx.parameter_estimates.items():
        short = k.replace("_", " ")
        source = _find_source_for_param(k, ctx)
        rows.append(f"| {short} | {v:.3f} | {source} |")
    return "\n".join(rows)


def _find_source_for_param(param: str, ctx: Any) -> str:
    """Search research results for a result that mentions param; return attribution."""
    param_words = param.replace("_", " ").replace("global__", "").lower().split()

    for r in (ctx.results or []):
        if not getattr(r, 'ok', True):
            continue
        raw     = str(getattr(r, 'raw', '') or '')
        title   = getattr(r, 'title', '') or ''
        summary = getattr(r, 'summary', '') or ''
        combined = (raw + " " + title + " " + summary).lower()

        if any(w in combined for w in param_words if len(w) > 3):
            if title and 'fetch failed' not in title.lower():
                src_type = getattr(r, 'source_type', '') or ''
                src_type_label = {
                    "fred": "FRED",
                    "world_bank": "World Bank",
                    "arxiv": "arXiv",
                    "openalex": "OpenAlex",
                    "semantic_scholar": "Semantic Scholar",
                    "ssrn": "SSRN",
                    "news": "News",
                    "eia": "EIA",
                }.get(src_type, src_type.upper() if src_type else "")
                trunc = title[:47] + "…" if len(title) > 50 else title
                if src_type_label:
                    return f"{trunc} ({src_type_label})"
                return trunc

    # Fallback: use source_type of first ok result
    for r in (ctx.results or []):
        if not getattr(r, 'ok', True):
            continue
        src_type = getattr(r, 'source_type', '') or ''
        if src_type:
            return {
                "fred": "FRED",
                "world_bank": "World Bank",
                "arxiv": "arXiv",
                "openalex": "OpenAlex",
                "semantic_scholar": "Semantic Scholar",
                "ssrn": "SSRN",
                "news": "News",
                "eia": "EIA",
            }.get(src_type, src_type.upper())

    return "Research data"


# ── Library gaps section ─────────────────────────────────────────────────────

def _discovered_theories_section(ctx: Any, recs: list[dict]) -> str:
    """
    Generate a Discovered Theories section showing:
    - Theories auto-built from research and added to the library (library_additions)
    - Theories extracted from papers but pending review (library_gaps)

    Also flags which recommended theories are discovered (source == "discovered").
    """
    if not ctx:
        return ""

    additions  = ctx.library_additions or []
    gaps       = ctx.library_gaps or []
    discovered_recs = [r for r in recs if r.get("source") == "discovered"]

    if not additions and not gaps and not discovered_recs:
        return ""

    lines = ["## Discovered Theories\n"]
    lines.append(
        "These theories were extracted from academic research during this session "
        "and are scenario-specific — distinct from the generic library ensemble.\n"
    )

    if discovered_recs:
        lines.append("### In This Ensemble\n")
        lines.append("The following theories were discovered during research and are included in the recommended ensemble:\n")
        for r in discovered_recs:
            lines.append(f"- **{r['display_name']}** (`{r['theory_id']}`) — score {r['score']:.2f}")
            note = r.get("application_note") or r.get("rationale", "")
            if note:
                lines.append(f"  {note}")
        lines.append("")

    if additions:
        lines.append("### Auto-Approved & Added to Library\n")
        lines.append(
            "These theories passed the smoke test and were hot-loaded into "
            "`core/theories/discovered/` during this session:\n"
        )
        # Try to match each addition to a research result for citation
        for theory_id in additions:
            display = theory_id.replace("_", " ").title()
            citation = ""
            if ctx.results:
                for r in ctx.results:
                    if getattr(r, 'ok', True):
                        raw = str(getattr(r, 'raw', '') or '').lower()
                        title = getattr(r, 'title', '') or ''
                        if theory_id.replace("_", " ") in raw or theory_id in raw:
                            citation = f"**Source:** {title}"
                            break
            lines.append(f"**{display}** (`{theory_id}`)")
            if citation:
                lines.append(citation)
            lines.append(f"**Status:** `core/theories/discovered/{theory_id}.py` — AUTO-APPROVED\n")

    if gaps:
        lines.append("### Pending Review\n")
        lines.append(
            "These theories were identified in research but did not pass the automated smoke test. "
            "Review in `data/theories/pending/` before use:\n"
        )
        for theory_id in gaps:
            display = theory_id.replace("_", " ").title()
            lines.append(f"- **{display}** (`{theory_id}`) — `data/theories/pending/`")
        lines.append("")

    return "\n".join(lines)


# ── SimSpec stub ─────────────────────────────────────────────────────────────

def _simspec_stub(session: "ForgeSession") -> str:
    """Generate a TheoryRef SimSpec stub from recommended theories + calibration."""
    recs = session.recommended_theories + (session.discovered_theories or [])
    ctx  = session.research_context
    param_estimates = (ctx.parameter_estimates or {}) if ctx else {}

    if not recs:
        return "from core.spec import TheoryRef\n\ntheories = []"

    theory_lines = ["from core.spec import TheoryRef", "", "theories = ["]

    for r in recs:
        tid      = r["theory_id"]
        priority = r.get("suggested_priority", r.get("priority", 0))
        features = THEORY_FEATURE_MAP.get(tid, [])

        # Map calibration anchors to this theory's features
        theory_params: dict[str, float] = {}
        for k, v in param_estimates.items():
            k_norm = k.replace("global__", "").replace("_", " ")
            if any(feat in k_norm or k_norm in feat for feat in features):
                theory_params[k] = v

        if theory_params:
            params_str = "\n".join(
                f'            "{k}": {v:.3f},'
                for k, v in theory_params.items()
            )
            theory_lines.append(f'    TheoryRef(')
            theory_lines.append(f'        theory_id="{tid}",')
            theory_lines.append(f'        priority={priority},')
            theory_lines.append(f'        parameters={{')
            theory_lines.append(params_str)
            theory_lines.append(f'        }}')
            theory_lines.append(f'    ),')
        else:
            theory_lines.append(f'    TheoryRef(theory_id="{tid}", priority={priority}),')

    theory_lines.append("]")
    return "\n".join(theory_lines)


# ── Sources section v2 ───────────────────────────────────────────────────────

def _sources_section_v2(ctx: Any) -> str:
    """Organize sources by type: Web/Live Data and Academic."""
    if not ctx or not ctx.results:
        return "*No sources.*"

    web_types     = {"news", "fred", "world_bank", "eia", "rss"}
    academic_types = {"arxiv", "openalex", "semantic_scholar", "ssrn"}

    web_lines      = []
    academic_lines = []
    seen: set[str] = set()

    for r in ctx.results[:30]:
        title = getattr(r, 'title', '') or ''
        url   = getattr(r, 'url', '') or ''
        ok    = getattr(r, 'ok', True)

        if not ok:
            continue
        if not title or 'fetch failed' in title.lower() or 'error' in title.lower():
            continue

        key = title[:60]
        if key in seen:
            continue
        seen.add(key)

        src_type = (getattr(r, 'source_type', '') or '').lower()
        entry    = f"- {title}" + (f" — {url}" if url else "")

        if src_type in web_types:
            web_lines.append(entry)
        elif src_type in academic_types:
            academic_lines.append(entry)
        else:
            web_lines.append(entry)  # default to web

    parts = []
    if web_lines:
        parts.append("### Web / Live Data\n" + "\n".join(web_lines))
    if academic_lines:
        parts.append("### Academic\n" + "\n".join(academic_lines))

    return "\n\n".join(parts) if parts else "*Sources not recorded.*"


# ── Forward signals (kept separate for individual haiku call) ────────────────

def _forward_signals(session: "ForgeSession") -> str:
    """Return forward signals table, using prose_data if available."""
    # Try session._prose_data first (populated by _generate_prose)
    try:
        prose_data = getattr(session, '_prose_data', {})
        signals    = prose_data.get("forward_signals", [])
        if signals:
            rows = ["| Signal | Direction | Confidence | Module |",
                    "|--------|-----------|------------|--------|"]
            for s in signals:
                sig  = s.get("signal", "—")
                dirn = s.get("direction", "→")
                conf = s.get("confidence", "Medium")
                mod  = s.get("module", "—")
                rows.append(f"| {sig} | {dirn} | {conf} | {mod} |")
            return "\n".join(rows)
    except Exception:
        pass

    # Fall back to separate haiku call
    spec = session.simspec
    ctx  = session.research_context
    recs = session.recommended_theories + (session.discovered_theories or [])

    snippets = "\n".join(
        r.to_context_snippet() for r in (ctx.results if ctx else [])[:8] if r.ok
    )[:3000]

    if not snippets:
        return "*Insufficient research data for forward signal extraction.*"

    prompt = f"""You are a simulation analyst. Based on these research findings, identify 3-5 forward signals relevant to this scenario.

Scenario: {spec.name if spec else 'Unknown'}
Domain: {spec.domain if spec else 'unknown'}
Theories: {', '.join(r['theory_id'] for r in recs)}

Research snippets:
{snippets}

Return a markdown table with columns: Signal | Direction | Confidence | Module
- Signal: 1 sentence describing an observable trend or event
- Direction: ↑ (increasing risk/pressure) or ↓ (decreasing) or → (stable/ongoing)
- Confidence: High / Medium / Low
- Module: which theory module this signal feeds into (use theory_id)

Return ONLY the markdown table, no other text. Start with the header row."""

    try:
        client = Anthropic()
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return "| Signal | Direction | Confidence | Module |\n|--------|-----------|------------|--------|\n| Insufficient data for signal extraction | → | Low | — |"


# ── Comparative analysis ────────────────────────────────────────────────────

def _comparative_analysis(session: "ForgeSession", recs: list[dict]) -> str:
    """
    Generate a comparative analysis of the recommended vs custom/discovered
    theory ensembles, describing what each emphasises and how outcomes differ.
    Falls back to a single-ensemble summary if only one option exists.
    """
    spec = session.simspec
    recommended = session.recommended_theories or []
    discovered  = session.discovered_theories or []
    custom      = session.custom_theories or []

    rec_names  = ", ".join(r["display_name"] for r in recommended) or "none"
    disc_names = ", ".join(r["display_name"] for r in discovered) or "none"
    cust_names = ", ".join(t.get("theory_id", "") for t in custom) or "none"

    has_second = bool(discovered or custom)

    outcome = (spec.metadata or {}).get("outcome_focus", "") if spec else ""
    scenario_name = spec.name if spec else "scenario"

    try:
        client = Anthropic()
        if has_second:
            prompt = (
                f"Scenario: {scenario_name}\nOutcome focus: {outcome}\n\n"
                f"Two simulation ensembles are available:\n\n"
                f"**Ensemble A — Library (recommended):** {rec_names}\n"
                f"**Ensemble B — Research-discovered:** {disc_names or cust_names}\n\n"
                f"Write a comparative analysis (3-4 paragraphs) covering:\n"
                f"1. What each ensemble emphasises and why it was selected\n"
                f"2. Where their predicted dynamics will likely diverge\n"
                f"3. Which ensemble is better suited to which analytic question\n"
                f"4. A clear recommendation on which to launch first and why\n\n"
                f"Write as a senior analyst briefing an executive. Be specific and direct."
            )
        else:
            prompt = (
                f"Scenario: {scenario_name}\nOutcome focus: {outcome}\n\n"
                f"Theory ensemble: {rec_names}\n\n"
                f"Write a 2-paragraph analysis covering:\n"
                f"1. Why this ensemble was selected and what dynamics it captures\n"
                f"2. Key assumptions embedded in the model and where it may be most/least reliable\n\n"
                f"Write as a senior analyst briefing an executive."
            )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        if has_second:
            return (
                f"**Ensemble A (Library):** {rec_names}\n\n"
                f"**Ensemble B (Discovered):** {disc_names or cust_names}\n\n"
                f"*Comparative analysis unavailable — run both ensembles to compare outcomes.*"
            )
        return f"**Ensemble:** {rec_names}\n\n*Analysis unavailable.*"


# ── Table builders (kept for backward compatibility and direct use) ──────────

def _actors_table(spec: Any, session: Any = None) -> str:
    """
    Build actor table. Makes one LLM call to generate rich role/description/beliefs
    for each actor using scenario context. Falls back to spec data if LLM fails.
    """
    if not spec or not spec.actors:
        return "*No actors defined.*"

    # Build context for the LLM
    scenario_name = getattr(spec, 'name', 'unknown scenario')
    scenario_desc = getattr(spec, 'description', '')
    outcome = (getattr(spec, 'metadata', {}) or {}).get('outcome_focus', '')
    actor_names = [a.name for a in spec.actors]

    # Collect any existing descriptions from spec
    existing = {}
    for a in spec.actors:
        meta = getattr(a, 'metadata', {}) or {}
        d = getattr(a, 'description', '') or meta.get('description', '') or ''
        r = meta.get('role', '') or ''
        if d or r:
            existing[a.name] = {'role': r, 'description': d}

    try:
        client = Anthropic()
        prompt = (
            f"Scenario: {scenario_name}\n"
            f"{scenario_desc}\n"
            f"Outcome focus: {outcome}\n\n"
            f"Actors: {', '.join(actor_names)}\n\n"
            f"For each actor, write:\n"
            f"  role: 4-6 word phrase capturing their function (e.g. 'Blockade initiator and naval power')\n"
            f"  description: 1-2 sentences on their position, incentives, and constraints in this scenario\n"
            f"  beliefs: 2-3 starting beliefs as key=value pairs (e.g. 'us_will_intervene=0.6, tsmc_offline_duration=0.7')\n\n"
            f"Existing data to incorporate:\n{json.dumps(existing, indent=2)}\n\n"
            f"Return JSON array:\n"
            f'[{{"name": "...", "role": "...", "description": "...", "beliefs": "..."}}]'
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
            raw = raw.rsplit("```", 1)[0].strip()
        enriched = {item['name']: item for item in json.loads(raw)}
    except Exception:
        enriched = {}

    rows = ["| Actor | Role | Description | Starting Beliefs |", "|-------|------|-------------|-----------------|"]
    for a in spec.actors:
        e = enriched.get(a.name, {})
        meta = getattr(a, 'metadata', {}) or {}

        role = e.get('role') or meta.get('role') or '—'
        desc = e.get('description') or getattr(a, 'description', '') or meta.get('description') or '—'
        beliefs_str = e.get('beliefs') or ''

        if not beliefs_str:
            actor_beliefs = getattr(a, 'beliefs', []) or []
            if actor_beliefs:
                beliefs_str = "; ".join(
                    f"{b.name}={b.alpha/(b.alpha+b.beta):.2f}" if hasattr(b, 'alpha') else b.name
                    for b in actor_beliefs[:3]
                )
            else:
                belief_state = meta.get('belief_state') or {}
                beliefs_str = "; ".join(
                    f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                    for k, v in list(belief_state.items())[:3]
                ) or '—'

        rows.append(f"| {a.name} | {role} | {desc} | {beliefs_str} |")
    return "\n".join(rows)


def _env_table(spec: Any) -> str:
    if not spec or not spec.initial_environment:
        return "*No initial conditions set.*"
    rows = ["| Parameter | Value |", "|-----------|-------|"]
    for k, v in list(spec.initial_environment.items())[:20]:
        short = k.replace("global__", "").replace("_", " ")
        rows.append(f"| {short} | {v:.3f} |")
    return "\n".join(rows)


def _theories_table(recs: list[dict]) -> str:
    if not recs:
        return "*No theories selected.*"
    rows = [
        "| # | Theory | Score | Key Mechanism |",
        "|---|--------|-------|---------------|",
    ]
    for i, r in enumerate(recs):
        note = r.get("application_note") or r.get("rationale", "—")
        note = note[:199] + "…" if len(note) >= 200 else note
        src = " *(new)*" if r.get("source") == "discovered" else ""
        rows.append(f"| {i+1} | **{r['display_name']}**{src} | {r['score']:.2f} | {note} |")
    return "\n".join(rows)


def _calibration_table(ctx: Any) -> str:
    if not ctx or not ctx.parameter_estimates:
        return "*No calibration data available from research.*"
    rows = ["| Parameter | Estimate | Source |", "|-----------|----------|--------|"]
    for k, v in ctx.parameter_estimates.items():
        short = k.replace("_", " ")
        # Try to find a source that mentioned this parameter
        source = "Research extraction"
        for r in (ctx.results or []):
            raw = getattr(r, 'raw', '') or ''
            if k.replace('_', ' ') in raw.lower() or k in raw:
                src_title = getattr(r, 'title', '') or ''
                if src_title and 'fetch failed' not in src_title.lower():
                    source = src_title[:50]
                    break
        rows.append(f"| {short} | {v:.3f} | {source} |")
    return "\n".join(rows)


def _sources_section(ctx: Any) -> str:
    if not ctx or not ctx.results:
        return "*No sources.*"
    lines = []
    seen = set()
    for r in ctx.results[:30]:
        title = getattr(r, 'title', '') or ''
        url = getattr(r, 'url', '') or ''
        # Skip failed fetches and duplicates
        if not title or 'fetch failed' in title.lower() or 'error' in title.lower():
            continue
        if not getattr(r, 'ok', True):
            continue
        key = title[:60]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {title}" + (f" — {url}" if url else ""))
    return "\n".join(lines) if lines else "*Sources not recorded.*"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")
