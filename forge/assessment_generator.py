"""
forge/assessment_generator.py — Assessment document generator

Given a ForgeSession (post-ensemble-review), generates:
  - forge/research/{slug}-assessment.md   (Markdown)
  - forge/research/charts/{slug}/         (pre-run charts: same style as generate_charts.py)
  - forge/research/{slug}-assessment.pdf  (PDF via pandoc + weasyprint)

Called via POST /forge/intake/{session_id}/assessment.
Uses claude-haiku for prose sections, matplotlib for charts.
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

    # 1. Generate pre-run charts
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


# ── Chart generation (same palette/style as generate_charts.py) ────────────

PALETTE = [
    "#2563EB", "#16A34A", "#DC2626", "#7C3AED", "#F97316",
    "#0891B2", "#854D0E", "#BE185D", "#B45309", "#4B5563",
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


def _apply_rcparams():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })
    return plt


def _generate_charts(session: "ForgeSession", charts_dir: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []

    try:
        plt = _apply_rcparams()

        # Chart 1: Theory ensemble scores
        recs = session.recommended_theories
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

        # Chart 2: Initial environment parameters
        env = session.simspec.initial_environment if session.simspec else {}
        if env:
            fig, ax = plt.subplots(figsize=(8, max(3, len(env) * 0.5)))
            keys = list(env.keys())[:16]  # cap at 16
            vals = [env[k] for k in keys]
            short_keys = [k.replace("global__", "").replace("_", " ") for k in keys]
            colors = [PALETTE[2] if v > 0.7 else PALETTE[0] if v < 0.3 else PALETTE[1]
                      for v in vals]
            ax.barh(short_keys, vals, color=colors)
            ax.set_xlabel("Normalized Value [0–1]")
            ax.set_title("Initial Conditions — Parameter Calibration", fontweight="bold", pad=12)
            ax.set_xlim(0, 1)
            ax.axvline(0.5, color="grey", linestyle=":", alpha=0.5, linewidth=1)
            fig.tight_layout()
            p = charts_dir / "fig2_initial_conditions.png"
            fig.savefig(p, **STYLE)
            plt.close(fig)
            paths.append(p)

        # Chart 3: Actor roles donut
        actors = session.simspec.actors if session.simspec else []
        if actors:
            from collections import Counter
            role_counts = Counter(
                (getattr(a, 'role', None) or (getattr(a, 'metadata', None) or {}).get('role') or 'unknown')
                for a in actors
            )
            fig, ax = plt.subplots(figsize=(5, 5))
            wedges, texts, autotexts = ax.pie(
                list(role_counts.values()),
                labels=list(role_counts.keys()),
                colors=PALETTE[:len(role_counts)],
                autopct="%1.0f%%",
                pctdistance=0.8,
                wedgeprops={"width": 0.5},
            )
            ax.set_title("Actor Composition by Role", fontweight="bold", pad=12)
            fig.tight_layout()
            p = charts_dir / "fig3_actor_roles.png"
            fig.savefig(p, **STYLE)
            plt.close(fig)
            paths.append(p)

        # Chart 4: Theory-feature matrix heatmap
        if recs:
            theory_ids   = [r["theory_id"]    for r in recs]
            theory_names = [r["display_name"] for r in recs]

            # Collect features in consistent order
            all_features = []
            seen = set()
            for tid in theory_ids:
                for f in THEORY_FEATURE_MAP.get(tid, []):
                    if f not in seen:
                        all_features.append(f)
                        seen.add(f)
            all_features = all_features[:14]  # cap columns

            n_t = len(theory_ids)
            n_f = len(all_features)
            if n_t > 0 and n_f > 0:
                cell_w, cell_h = 1.4, 0.55
                fig_w = max(10, n_f * cell_w + 3)
                fig_h = max(3,  n_t * cell_h + 2)
                fig, ax = plt.subplots(figsize=(fig_w, fig_h))
                ax.set_xlim(-0.5, n_f - 0.5)
                ax.set_ylim(-0.5, n_t - 0.5)
                ax.axis("off")
                fig.patch.set_facecolor("white")

                # Draw cells
                for ti, tid in enumerate(theory_ids):
                    color = PALETTE[ti % len(PALETTE)]
                    mapped = set(THEORY_FEATURE_MAP.get(tid, []))
                    for fi, feat in enumerate(all_features):
                        if feat in mapped:
                            rect = plt.Rectangle((fi - 0.45, ti - 0.40), 0.90, 0.80,
                                                 color=color, alpha=0.75, zorder=2)
                            ax.add_patch(rect)
                            # Checkmark inside
                            ax.text(fi, ti, "✓", ha="center", va="center",
                                    fontsize=9, color="white", fontweight="bold", zorder=3)
                        else:
                            rect = plt.Rectangle((fi - 0.45, ti - 0.40), 0.90, 0.80,
                                                 color="#F3F4F6", zorder=1)
                            ax.add_patch(rect)

                # Theory labels (y-axis, left)
                for ti, name in enumerate(theory_names):
                    ax.text(-0.6, ti, name, ha="right", va="center",
                            fontsize=9, fontweight="bold", color=PALETTE[ti % len(PALETTE)])

                # Feature labels (x-axis, top — rotated)
                for fi, feat in enumerate(all_features):
                    ax.text(fi, n_t - 0.3, feat.replace(" ", "\n"),
                            ha="center", va="bottom", fontsize=7.5, color="#374151", linespacing=1.2)

                # Grid lines
                for fi in range(-1, n_f):
                    ax.axvline(fi + 0.5, color="#E5E7EB", linewidth=0.5, zorder=0)
                for ti in range(-1, n_t):
                    ax.axhline(ti + 0.5, color="#E5E7EB", linewidth=0.5, zorder=0)

                ax.set_title("Theory Ensemble — Simulation Feature Coverage",
                             fontweight="bold", pad=16, fontsize=12, loc="left")

                fig.tight_layout(rect=[0.15, 0, 1, 0.88])
                p = charts_dir / "fig4_theory_feature_map.png"
                fig.savefig(p, **STYLE)
                plt.close(fig)
                paths.append(p)

    except Exception as exc:
        logger.warning("Chart generation failed: %s", exc)

    return paths


# ── Markdown builder ────────────────────────────────────────────────────────

def _theory_cascade(recs: list[dict]) -> str:
    if not recs:
        return "*No theories selected.*"
    if len(recs) == 1:
        return f"Single module: **{recs[0]['display_name']}** drives all state updates each tick."

    names = [f"**{r['display_name']}**" for r in recs]
    chain = " → ".join(names)
    return (
        f"Theories execute in priority order each tick: {chain}. "
        f"Each module reads environment state set by prior modules, ensuring consistent "
        f"causal ordering from {recs[0]['display_name']} (primary driver) through to "
        f"{recs[-1]['display_name']} (downstream effects)."
    )


def _forward_signals(session: "ForgeSession") -> str:
    spec = session.simspec
    ctx  = session.research_context
    recs = session.recommended_theories

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


def _build_markdown(
    session: "ForgeSession",
    slug: str,
    chart_paths: list[pathlib.Path],
) -> str:
    spec = session.simspec
    ctx  = session.research_context
    recs = session.recommended_theories

    today = date.today().strftime("%B %d, %Y")
    name  = spec.name if spec else "Unnamed Scenario"
    domain = spec.domain if spec else "—"
    raw_focus = (spec.metadata or {}).get("outcome_focus", "—") if spec else "—"
    # Strip markdown headers, bold, strip leading/trailing whitespace
    outcome_focus = re.sub(r'^#{1,6}\s*', '', raw_focus, flags=re.MULTILINE)
    outcome_focus = re.sub(r'\*+', '', outcome_focus).strip()
    # If it's the agent's empirical selection message, replace with clean text
    if "empirically" in outcome_focus.lower() and len(outcome_focus) < 120:
        outcome_focus = "Model-driven — theoretical framework selected empirically from research"
    ticks = spec.timeframe.total_ticks if spec else 0
    tick_unit = spec.timeframe.tick_unit if spec else "month"
    start_date = spec.timeframe.start_date if spec else "—"

    # Prose sections via haiku
    exec_summary, data_gaps = _generate_prose(session)

    # Actors table
    actors_md = _actors_table(spec)

    # Initial conditions table
    env_md = _env_table(spec)

    # Theory ensemble table
    theories_md = _theories_table(recs)

    # Calibration anchors
    calib_md = _calibration_table(ctx)

    # Sources
    sources_md = _sources_section(ctx)

    # Theory cascade text
    cascade_text = _theory_cascade(recs)

    # Forward signals table
    signals_md = _forward_signals(session)

    # Chart embeds split by section (relative paths from MD file location)
    chart_embeds_env = ""
    for fname, caption in [
        ("fig2_initial_conditions.png", "Figure 2: Initial condition calibration"),
        ("fig3_actor_roles.png",        "Figure 3: Actor composition by role"),
    ]:
        p = next((cp for cp in chart_paths if cp.name == fname), None)
        if p:
            rel = f"charts/{slug}/{fname}"
            chart_embeds_env += f"\n![{caption}]({rel})\n*{caption}*\n"

    chart_embeds_theory = ""
    for fname, caption in [
        ("fig1_theory_scores.png",      "Figure 1: Theory ensemble relevance scores"),
        ("fig4_theory_feature_map.png", "Figure 4: Theory ensemble — simulation feature coverage"),
    ]:
        p = next((cp for cp in chart_paths if cp.name == fname), None)
        if p:
            rel = f"charts/{slug}/{fname}"
            chart_embeds_theory += f"\n![{caption}]({rel})\n*{caption}*\n"

    # Monte Carlo guidance
    domain_mc = {
        "market":      "300–500 runs; perturb price_sensitivity ±20%, churn_rate ±15%",
        "geopolitics": "200–400 runs; perturb escalation_prob ±25%, resolve_threshold ±20%",
        "conflict":    "200–400 runs; perturb escalation_prob ±25%, resolve_threshold ±20%",
        "macro":       "200–300 runs; perturb gdp_growth ±15%, inflation ±10%",
        "corporate":   "200–400 runs; perturb market_share ±15%, cost_pressure ±20%",
        "ecology":     "300–500 runs; perturb climate_stress ±20%, resource_availability ±25%",
    }.get(domain, "200–400 runs; perturb key parameters ±15–25%")

    top_params = list((ctx.parameter_estimates or {}).keys())[:4]
    sensitivity_params = ", ".join(top_params) if top_params else "key initial environment parameters"

    custom_note = ""
    if session.custom_theories:
        custom_note = (
            f"\n**Custom ensemble** ({len(session.custom_theories)} modules) also configured "
            f"— both will run in parallel for comparison.\n"
        )

    doc = f"""# {name} — Scenario Assessment

**Date:** {today} | **Domain:** {domain} | **Ensemble:** {len(recs)}-module | **Horizon:** {ticks} {tick_unit}s | **Generated by:** Crucible Forge

---

## Executive Summary

{exec_summary}

---

## Scenario

**Simulation Horizon:** {ticks} {tick_unit}s (starting {start_date})
**Outcome Focus:** {outcome_focus}

### Actors

{actors_md}

### Initial Conditions

{chart_embeds_env}

{env_md}

---

## Recommended Theory Stack

{theories_md}

### Module Cascade

{cascade_text}

{chart_embeds_theory}

---

## Calibration Anchors

{calib_md}

---

## Forward Signals

{signals_md}

---

## Simulation Settings

**Recommended configuration:**

- **Monte Carlo:** {domain_mc}
- **Sensitivity parameters:** {sensitivity_params}
- **Horizon:** {ticks} {tick_unit}s — {"sufficient for short-run dynamics" if ticks <= 12 else "allows full cycle to emerge"}
- **Deterministic baseline:** Run 1 deterministic pass first to validate cascade, then launch Monte Carlo
{custom_note}

---

## Data Gaps & Uncertainty

{data_gaps}

---

## Sources

{sources_md}
"""
    return doc.strip()


# ── Prose generation (haiku) ────────────────────────────────────────────────

def _generate_prose(session: "ForgeSession") -> tuple[str, str]:
    """Generate executive summary and data gaps sections via haiku."""
    spec = session.simspec
    ctx  = session.research_context

    context = f"""
Scenario name: {spec.name if spec else 'Unnamed'}
Domain: {spec.domain if spec else 'unknown'}
Outcome focus: {(spec.metadata or {}).get('outcome_focus', 'not specified') if spec else 'not specified'}
Actors: {', '.join(a.name for a in spec.actors) if spec and spec.actors else 'none'}
Timeframe: {spec.timeframe.total_ticks if spec else 0} {spec.timeframe.tick_unit if spec else 'months'}
Theory candidates from research: {', '.join(ctx.theory_candidates) if ctx.theory_candidates else 'none'}
Recommended theories: {', '.join(r['theory_id'] for r in session.recommended_theories)}
Parameter estimates: {json.dumps(ctx.parameter_estimates, indent=2) if ctx.parameter_estimates else 'none'}
Research results count: {len(ctx.results)} sources
Library additions: {', '.join(ctx.library_additions) if ctx.library_additions else 'none'}
"""

    prompt = f"""You are a simulation analyst writing a pre-run assessment document.

Scenario data:
{context}

Write two sections (return as JSON with keys "exec_summary" and "data_gaps"):

1. "exec_summary": 2–3 paragraphs (plain text, no markdown headers). Cover:
   - What entity/situation is being assessed and why it matters
   - The 3–5 key drivers identified in research
   - What the simulation will answer and for whom
   Do NOT include conclusions or results predictions.

2. "data_gaps": 3–5 bullet points (use "- " prefix) covering:
   - Parameters that could not be empirically grounded
   - Sources that were inaccessible (403, 404)
   - What would reduce uncertainty most if obtained
   - Monte Carlo guidance given the gaps

Write in a direct, analytical consulting voice. No fluff."""

    try:
        client = Anthropic()
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        exec_summary = data.get("exec_summary", "")
        data_gaps_raw = data.get("data_gaps", "")
        # Haiku sometimes returns data_gaps as a JSON array instead of string
        if isinstance(data_gaps_raw, list):
            data_gaps = "\n".join(
                item if str(item).startswith("-") else f"- {item}"
                for item in data_gaps_raw
            )
        else:
            data_gaps = data_gaps_raw
        return exec_summary, data_gaps
    except Exception as exc:
        logger.warning("Prose generation failed: %s", exc)
        spec_name = spec.name if spec else "this scenario"
        return (
            f"This assessment covers {spec_name}. "
            f"Research identified {len(session.recommended_theories)} relevant theory modules."
        ), "- Parameter estimates require empirical validation before launch."


# ── Table builders ──────────────────────────────────────────────────────────

def _actors_table(spec: Any) -> str:
    if not spec or not spec.actors:
        return "*No actors defined.*"
    rows = ["| Actor | Role | Description | Starting Beliefs |", "|-------|------|-------------|-----------------|"]
    for a in spec.actors:
        meta = getattr(a, 'metadata', {}) or {}
        role = meta.get('role', '—')
        desc = meta.get('description', '—') or '—'
        belief_state = meta.get('belief_state') or {}
        beliefs = "; ".join(
            f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
            for k, v in list(belief_state.items())[:3]
        ) or '—'
        rows.append(f"| {a.name} | {role} | {desc} | {beliefs} |")
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


# ── Helpers ─────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")
