"""
forge/findings_generator.py — Simulation Findings Document Generator

Structure matches the canonical walla-walla findings format:
  Executive Summary (Baseline / Causes / Final State / Projection)
  Executive Findings (phase narrative)
  1. Simulation Design (architecture cascade + shock table)
  2. Results by Module (per-theory data tables)
  3. Cascade Interaction (numbered cascade steps)
  4. Monte Carlo Distribution (full percentile table)
  5. Model Limitations (table with status)
  6. Parameters Appendix

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


def _fmt(v) -> str:
    """Format a float to 3 decimal places, or return str as-is."""
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return str(v)


_PALETTE = [
    "#2563EB", "#16A34A", "#DC2626", "#7C3AED",
    "#F97316", "#0891B2", "#854D0E", "#BE185D",
    "#B45309", "#4B5563",
]


def _build_chart_plan(
    spec,
    metric_series: dict,
    metric_names: dict,
    monte_carlo: dict,
    tick_unit: str,
    final_env: dict | None = None,
) -> dict:
    """
    Build a scenario-specific chart plan by ranking metrics by variance
    (max-min range) so the most dynamic metrics get the prominent panels.
    Falls back to final_env deviation when all tracked metrics are flat.
    """
    # Skip clearly static keys: "baseline_*" prefixes and zero-variance series
    _SKIP_PREFIXES = ("baseline_", "initial_", "param_", "config_")

    ranked: list[tuple[float, str]] = []
    flat: list[tuple[float, str]] = []   # kept as last-resort fallback
    for mid, vals in metric_series.items():
        if not vals:
            continue
        if any(mid.lower().startswith(p) for p in _SKIP_PREFIXES):
            continue
        try:
            floats = [float(v) for v in vals]
            lo, hi = min(floats), max(floats)
            rng = hi - lo
            if rng > 1e-4:
                ranked.append((rng, mid))
            else:
                flat.append((rng, mid))
        except (TypeError, ValueError):
            pass
    ranked.sort(reverse=True)

    # If no dynamic metrics found in metric_series, try final_env deviation from 0.5
    if not ranked and final_env:
        env_ranked = []
        for k, v in final_env.items():
            if any(k.lower().startswith(p) for p in _SKIP_PREFIXES):
                continue
            try:
                env_ranked.append((abs(float(v) - 0.5), k))
            except (TypeError, ValueError):
                pass
        env_ranked.sort(reverse=True)
        # Can't chart final_env as time series, so fall back to flat metrics
        # but reorder them by their final value deviation
        env_keys = {k for _, k in env_ranked[:10]}
        ranked = [(r, m) for r, m in flat if m in env_keys] + \
                 [(r, m) for r, m in flat if m not in env_keys]
    elif not ranked:
        ranked = flat  # last resort: show something

    top_ids = [mid for _, mid in ranked]

    def _label(mid: str) -> str:
        return metric_names.get(mid, mid.replace("_", " ").replace("__", ": ").title())

    def _short(mid: str) -> str:
        """Short label for boxplot axis."""
        lbl = _label(mid)
        return lbl[:14] if len(lbl) > 14 else lbl

    # Top 4 go into dashboard + cascade panels
    fin_metrics = [
        (mid, _label(mid), _PALETTE[i % len(_PALETTE)])
        for i, mid in enumerate(top_ids[:4])
    ]

    # Next 4 go into secondary-indicators panel (split left/right)
    secondary = top_ids[4:8] if len(top_ids) > 4 else top_ids[:4]
    mid_split = len(secondary) // 2
    climate_left = [
        (mid, _label(mid), _PALETTE[(i + 4) % len(_PALETTE)], "line")
        for i, mid in enumerate(secondary[:mid_split or 1])
    ]
    climate_right = [
        (mid, _label(mid), _PALETTE[(i + 6) % len(_PALETTE)], "dashed")
        for i, mid in enumerate(secondary[mid_split or 1:])
    ]

    # MC fan: pick the metric with largest p95-p5 spread at final tick
    mc_fan_metric = top_ids[0] if top_ids else None
    mc_fan_label = _label(mc_fan_metric) if mc_fan_metric else "Primary Metric"
    bands = monte_carlo.get("bands", {})
    if bands:
        best_spread, best_mid = 0.0, None
        for mid, band in bands.items():
            p5 = band.get("p5", [None])
            p95 = band.get("p95", [None])
            if p5 and p95 and p5[-1] is not None and p95[-1] is not None:
                spread = float(p95[-1]) - float(p5[-1])
                if spread > best_spread:
                    best_spread, best_mid = spread, mid
        if best_mid:
            mc_fan_metric = best_mid
            mc_fan_label = _label(best_mid)

    # Shock annotations from simspec (scheduled_shocks: {tick: {env_key: delta}})
    shocks_dict: dict[int, str] = {}
    scheduled = getattr(spec, "scheduled_shocks", None) or {}
    for tick, vars_dict in scheduled.items():
        label = ", ".join(vars_dict.keys())
        words = label.split()
        shocks_dict[int(tick)] = "\n".join(
            " ".join(words[i:i+2]) for i in range(0, min(len(words), 4), 2)
        )

    return {
        "tick_unit": tick_unit,
        "shocks": shocks_dict,
        "financial_metrics": fin_metrics,
        "cascade_metrics": fin_metrics,
        "cascade_annotations": [],
        "climate_left": climate_left,
        "climate_right": climate_right,
        "replant_threshold": None,
        "covenant_threshold": None,
        "boxplot_metrics": [
            (mid, _short(mid)) for mid in top_ids[:5]
        ],
        "mc_fan_metric": mc_fan_metric,
        "mc_fan_label": mc_fan_label,
        "mc_fan_threshold": None,
    }


def _generate_comparison_chart(
    slug: str,
    metric_series_a: dict,
    metric_series_b: dict,
    metric_names: dict,
    tick_unit: str,
) -> Path | None:
    """
    Generate an overlay chart comparing top-4 metrics from Model A (solid)
    and Model B (dashed). Saves to scenarios/{slug}/fig_comparison.png.
    Returns the Path or None on failure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Pick top 4 metrics by variance in model A
    ranked: list[tuple[float, str]] = []
    for mid, vals in metric_series_a.items():
        if not vals:
            continue
        try:
            floats = [float(v) for v in vals]
            rng = max(floats) - min(floats)
            ranked.append((rng, mid))
        except (TypeError, ValueError):
            pass
    ranked.sort(reverse=True)
    top4 = [mid for _, mid in ranked[:4]]

    if not top4:
        return None

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()

    colors = [_PALETTE[0], _PALETTE[2], _PALETTE[3], _PALETTE[4]]

    for ax, mid, color in zip(axes, top4, colors):
        label = metric_names.get(mid, mid.replace("_", " ").replace("__", ": ").title())
        vals_a = metric_series_a.get(mid, [])
        vals_b = metric_series_b.get(mid, [])
        if vals_a:
            ax.plot(range(len(vals_a)), [float(v) for v in vals_a],
                    color=color, linewidth=2, linestyle="-", label="Model A (Recommended)")
        if vals_b:
            ax.plot(range(len(vals_b)), [float(v) for v in vals_b],
                    color=color, linewidth=2, linestyle="--", label="Model B (Custom)", alpha=0.8)
        ax.set_title(label, fontsize=9, fontweight="bold")
        ax.set_xlabel(tick_unit.capitalize(), fontsize=8)
        ax.legend(fontsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(True, alpha=0.25, linestyle="--")

    fig.suptitle("Model Comparison — Recommended vs Custom Ensemble", fontweight="bold", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_dir = Path(__file__).parent.parent / "scenarios" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fig_comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path.resolve()


def _build_trajectory_table(metric_series: dict, metric_names: dict) -> str:
    """Build a | Metric | T=0 | ... | Final | Change | trajectory table."""
    trajectory_rows = []
    for mid, series in metric_series.items():
        if not series:
            continue
        name = metric_names.get(mid, mid.replace("_", " ").replace("__", ": ").title())
        n = len(series)
        vals = {
            "t0":   series[0],
            "t25":  series[n // 4],
            "t50":  series[n // 2],
            "t75":  series[3 * n // 4],
            "tfin": series[-1],
        }
        delta = vals["tfin"] - vals["t0"]
        arrow = "▲" if delta > 0.01 else ("▼" if delta < -0.01 else "→")
        trajectory_rows.append(
            f"| {name} | {_fmt(vals['t0'])} | {_fmt(vals['t25'])} | "
            f"{_fmt(vals['t50'])} | {_fmt(vals['t75'])} | {_fmt(vals['tfin'])} | "
            f"{arrow} {abs(delta):.3f} |"
        )
    return (
        "| Metric | T=0 | T=25% | T=50% | T=75% | Final | Change |\n"
        "|--------|-----|-------|-------|-------|-------|--------|\n"
        + "\n".join(trajectory_rows)
    ) if trajectory_rows else "_No outcome metrics tracked._"


def _build_comparison_table(
    metric_series_a: dict,
    metric_series_b: dict,
    metric_names_a: dict,
    metric_names_b: dict,
) -> str:
    """Build a side-by-side comparison table of final values for both models."""
    all_metrics = sorted(
        set(metric_series_a.keys()) | set(metric_series_b.keys())
    )
    rows = [
        "| Metric | Model A Final | Model B Final | Delta (B-A) | More Severe |",
        "|--------|--------------|--------------|-------------|-------------|",
    ]
    for mid in all_metrics:
        series_a = metric_series_a.get(mid, [])
        series_b = metric_series_b.get(mid, [])
        val_a = series_a[-1] if series_a else None
        val_b = series_b[-1] if series_b else None
        name = (metric_names_a or metric_names_b).get(
            mid, mid.replace("_", " ").replace("__", ": ").title()
        )
        if val_a is None and val_b is None:
            continue
        fa = _fmt(val_a) if val_a is not None else "—"
        fb = _fmt(val_b) if val_b is not None else "—"
        if val_a is not None and val_b is not None:
            try:
                delta = float(val_b) - float(val_a)
                delta_str = f"{delta:+.3f}"
                # "More severe" is whichever has larger absolute deviation from 0.5
                # (lower is worse for stability metrics, higher for risk metrics —
                # we use absolute deviation as a proxy)
                more = "Model B" if abs(float(val_b) - 0.5) > abs(float(val_a) - 0.5) else "Model A"
            except (TypeError, ValueError):
                delta_str = "—"
                more = "—"
        else:
            delta_str = "—"
            more = "—"
        rows.append(f"| {name} | {fa} | {fb} | {delta_str} | {more} |")
    return "\n".join(rows)


def generate_findings(
    session: "ForgeSession",
    sim_results: dict,
    sim_results_b: dict | None = None,
) -> tuple[Path, Path]:
    """
    Generate a findings document from a completed simulation run.

    Args:
        session:       The ForgeSession with full SimSpec and research context.
        sim_results:   The results dict from _execute_run (Model A / Recommended).
        sim_results_b: Optional results for a second ensemble (Model B / Custom).

    Returns:
        (md_path, pdf_path)
    """
    client = Anthropic()
    spec = session.simspec

    slug = _slug(spec.name or session.session_id)
    md_path  = _RESEARCH_DIR / f"{slug}-findings.md"
    pdf_path = md_path.with_suffix(".pdf")

    # ── Extract simulation data ──────────────────────────────────────────────

    ticks         = sim_results.get("ticks", 0)
    metric_series = sim_results.get("metric_series", {})
    metric_names  = sim_results.get("metric_names", {})
    final_env     = sim_results.get("final_env", {})
    theory_ids    = sim_results.get("theory_ids", [])

    tick_unit  = spec.timeframe.tick_unit if spec.timeframe else "tick"
    start_date = (spec.metadata or {}).get("start_date", "")
    end_date   = (spec.metadata or {}).get("end_date", "")

    # Full metric trajectory: tick 0, 25%, 50%, 75%, final
    trajectory_table = _build_trajectory_table(metric_series, metric_names)

    # Model B data (if present)
    _dual = sim_results_b is not None
    if _dual:
        metric_series_b = sim_results_b.get("metric_series", {})
        metric_names_b  = sim_results_b.get("metric_names", {})
        theory_ids_b    = sim_results_b.get("theory_ids", [])
        trajectory_table_b = _build_trajectory_table(metric_series_b, metric_names_b)
        comparison_table   = _build_comparison_table(
            metric_series, metric_series_b, metric_names, metric_names_b
        )
    else:
        metric_series_b = {}
        metric_names_b  = {}
        theory_ids_b    = []
        trajectory_table_b = ""
        comparison_table   = ""

    # Final environment — top 40 keys alphabetically
    env_table = "| Key | Final Value |\n|-----|-------------|\n" + "\n".join(
        f"| `{k}` | {_fmt(v)} |"
        for k, v in sorted(final_env.items())[:40]
    )

    # ── Dual-model trajectory block for prompt ───────────────────────────────
    if _dual:
        dual_trajectory_block = (
            f"\n### Model A (Recommended Ensemble) — Metric Trajectories\n"
            f"{trajectory_table}\n\n"
            f"### Model B (Custom Ensemble) — Metric Trajectories\n"
            f"{trajectory_table_b}\n\n"
            f"### Model Comparison — Final Values\n"
            f"{comparison_table}\n"
        )
    else:
        dual_trajectory_block = ""

    # Shock schedule from simspec (scheduled_shocks: {tick: {env_key: delta}})
    shocks_text = ""
    _scheduled = getattr(spec, "scheduled_shocks", None) or {}
    if _scheduled:
        shock_rows = []
        for tick, vars_dict in sorted(_scheduled.items(), key=lambda x: int(x[0])):
            vars_str = ", ".join(
                f"{k} {'+' if v >= 0 else ''}{float(v):.2f}"
                for k, v in vars_dict.items()
            )
            shock_rows.append(f"| {tick} | | {vars_str} |")
        shocks_text = (
            "| Tick | Event | Key Variables Shocked |\n"
            "|------|-------|----------------------|\n"
            + "\n".join(shock_rows)
        )

    # Theory cascade for architecture block
    theories_in_spec = spec.theories if spec.theories else []
    cascade_lines = []
    for t in sorted(theories_in_spec, key=lambda x: -(x.priority or 0)):
        cascade_lines.append(f"{t.theory_id} (priority {t.priority})")
    cascade_text = "\n".join(cascade_lines) or "(no theories)"

    # MC data if present — bands or summary
    mc_text = ""
    if "monte_carlo" in sim_results:
        mc = sim_results["monte_carlo"]
        bands = mc.get("bands", {})
        if bands:
            mc_rows = []
            for metric, band in list(bands.items())[:8]:
                name = metric_names.get(metric, metric)
                p5   = _fmt(band.get("p5",  [None])[-1])
                p25  = _fmt(band.get("p25", [None])[-1])
                p50  = _fmt(band.get("p50", [None])[-1])
                p75  = _fmt(band.get("p75", [None])[-1])
                p95  = _fmt(band.get("p95", [None])[-1])
                mc_rows.append(f"| {name} | {p5} | {p25} | {p50} | {p75} | {p95} |")
            mc_text = (
                "| Metric | p5 | p25 | p50 | p75 | p95 |\n"
                "|--------|----|----|-----|-----|-----|\n"
                + "\n".join(mc_rows)
            )

    # Research grounding
    research_summary = ""
    if session.research_context and session.research_context.results:
        ok = [r for r in session.research_context.results if r.ok][:8]
        research_summary = "\n".join(
            f"- {r.title}: {r.summary[:120]}..." if r.summary else f"- {r.title}"
            for r in ok if r.title
        )

    outcome_focus = (spec.metadata or {}).get("outcome_focus", "")
    client_type   = (spec.metadata or {}).get("client_type", "the client")

    # ── LLM call ────────────────────────────────────────────────────────────

    system = (
        "You are a senior quantitative analyst writing a simulation findings document. "
        "Write in a professional, analytical style. Be specific: every number you cite "
        "must come from the simulation data provided. Do not invent values. "
        "Use markdown tables and headers exactly as specified in the structure. "
        "Every section must contain real insights tied to actual simulation outputs."
    )

    # Dual-model theory diff for prompt
    if _dual:
        ids_a = set(theory_ids)
        ids_b = set(theory_ids_b)
        shared   = sorted(ids_a & ids_b)
        only_a   = sorted(ids_a - ids_b)
        only_b   = sorted(ids_b - ids_a)
        theory_diff_block = (
            f"\n### Theory Ensemble Difference\n"
            f"| Category | Theories |\n"
            f"|----------|---------|\n"
            f"| Shared | {', '.join(shared) or '—'} |\n"
            f"| Only in Model A (Recommended) | {', '.join(only_a) or '—'} |\n"
            f"| Only in Model B (Custom) | {', '.join(only_b) or '—'} |\n"
        )
        model_comparison_section = f"""
## 7. Model Comparison

### Theory Ensemble Difference
| Theory | Model A | Model B |
|--------|---------|---------|
{"".join(f"| {t} | ✓ | ✓ |" + chr(10) for t in shared)}{"".join(f"| {t} | ✓ |  |" + chr(10) for t in only_a)}{"".join(f"| {t} |  | ✓ |" + chr(10) for t in only_b)}

### Outcome Divergence
{comparison_table}

### Key Finding
{{Which ensemble produces worse stress? Why do they diverge? What does the difference tell the client?}}
"""
        model_comparison_instruction = f"""
---

{model_comparison_section}
"""
        dual_exec_summary_addon = f"""
### Model Comparison Summary
| Outcome | Model A (Recommended) | Model B (Custom) | More Conservative |
|---------|----------------------|-----------------|-------------------|
{{3–5 rows using real final values from the comparison table above}}
"""
    else:
        theory_diff_block = ""
        model_comparison_instruction = ""
        dual_exec_summary_addon = ""

    prompt = f"""Write a complete simulation findings document. Follow the EXACT structure below.
All numbers must come from the simulation data. Do not use placeholder text.

---

## SIMULATION DATA

**Scenario:** {spec.name}
**Domain:** {spec.domain}
**Description:** {spec.description or session.intake_text[:400]}
**Timeframe:** {ticks} {tick_unit}s | Start: {start_date} | End: {end_date}
**Outcome Focus:** {outcome_focus}
**Client type:** {client_type}
**Model A (Recommended) theories:** {', '.join(theory_ids) or 'none'}
{f'**Model B (Custom) theories:** {chr(44).join(theory_ids_b) or "none"}' if _dual else ''}
**Actors:** {', '.join(a.name for a in spec.actors[:8])}

### Metric Trajectories (T=0, 25%, 50%, 75%, Final)
{trajectory_table if not _dual else dual_trajectory_block}

### Final Environment State
{env_table}

### Shock Schedule
{shocks_text or '(no scheduled shocks)'}

### Theory Cascade (by priority)
```
{cascade_text}
```

### Monte Carlo (if present)
{mc_text or '(no MC data)'}

### Research Grounding
{research_summary or 'No external research available.'}
{theory_diff_block}

---

## REQUIRED DOCUMENT STRUCTURE

Write the document using EXACTLY these sections, in this order:

---

# {{Scenario Name}} — Simulation Results & Analysis
**Date:** {time.strftime('%Y-%m-%d')} | **Ticks:** {ticks} {tick_unit}s ({start_date} – {end_date}) | **Version:** 1 — {len(theory_ids)} theory modules | **Focus:** {{1-line outcome focus}}

---

## Executive Summary

### Baseline Position (Tick 0 — {{start date}})
{{2–3 sentences describing the entity's starting position from the simulation data.}}

| Indicator | Tick 0 | Value |
|-----------|--------|-------|
{{5–7 rows using real tick-0 values from the trajectory table above}}

### Causes of the {{N}}-{{unit}} {{Change/Decline/Rise}}
{{For each major cause (3–5), numbered:}}
**N. {{Event Name}} (Tick X / {{timeframe label}})** — {{Short Label}} *({{theory_id}}, {{key_var}}: {{value}})*
{{2–3 sentences with specific numbers from the simulation data.}}

### Final State (Tick {{N}} — {{end date}})
| Indicator | Final Value | Change from Tick 0 | Status |
|-----------|-------------|-------------------|--------|
{{6–8 rows; Status = CRITICAL / DISTRESSED / SEVERE DECLINE / TRIGGERED / COVENANT BREACH / STABLE / etc.}}

**Primary active threats:**
- {{bullet per major threat, tied to specific metric values}}

### {{N}}-{{unit}} Projection
| Scenario | {{Primary metric}} range | Trigger | Probability |
|----------|------------------------|---------|-------------|
| Base ({{N}}%) | ... | ... | ... |
| Bull ({{N}}%) | ... | ... | ... |
| Bear ({{N}}%) | ... | ... | ... |

**Key finding:** {{1–2 sentences on the most important MC or scenario finding.}}
{dual_exec_summary_addon}

---

## Executive Findings

{{4–5 paragraphs. Label phases if the scenario has distinct phases (Phase 1, Phase 2, etc.). Each paragraph should cover a distinct dynamic from the simulation — not just summarise, but interpret. End with a paragraph on Monte Carlo convergence or uncertainty.}}

---

## 1. Simulation Design

### Architecture ({len(theory_ids)} Modules)
```
{cascade_text}
```

### Timeframe and Shocks

| Variable | Value |
|----------|-------|
| Tick unit | {tick_unit} |
| Total ticks | {ticks} |
| Tick 0 | {start_date} — Baseline |
| Tick {ticks - 1} | {end_date} — End of projection |

{shocks_text or '*(No scheduled shocks.)*'}

---

## 2. Results by Module

{{One subsection per theory. For each:}}
### 2.N {{Module Display Name}} {{(NEW — Citation if applicable)}}
{{1–2 sentences: what this module modeled in this scenario.}}

| Tick | {{unit}} | {{metric 1}} | {{metric 2}} | Event |
|------|---------|-------------|-------------|-------|
{{4–6 rows at key ticks using real values from the simulation data}}

{{2–3 sentence interpretation of what the numbers show.}}

---

## 3. Cascade Interaction

{{Numbered list of how module outputs fed into each other — the specific sequence that produced the key outcome. Be precise about which variables were passed between modules.}}

{{Bold concluding sentence stating the core cascade finding.}}

---

## 4. Monte Carlo Distribution

{{If MC data is present:}}
**{{N}} runs.** Scenarios: {{base N%}} / {{bull N%}} / {{bear N%}}.

{mc_text or '*(No Monte Carlo data in this run.)*'}

{{3 short paragraphs interpreting the MC table: convergence/divergence, which metrics are certain vs uncertain, what drives the spread.}}

---

## 5. Model Limitations

| Limitation | Impact | Status |
|-----------|--------|--------|
{{5–7 rows. Status = OPEN / RESOLVED / BY DESIGN}}

---

## 6. Parameters Appendix

| Module | Key Parameters Used | Calibration Source |
|--------|--------------------|--------------------|
{{One row per theory with the key parameter values actually used}}
{model_comparison_instruction}"""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )

    md_content = resp.content[0].text.strip()

    # ── Generate charts ──────────────────────────────────────────────────────
    # Convert metric_series flat lists → records format expected by generate_charts.py
    # and wrap in {"deterministic": {"series": ...}, "monte_carlo": ...}
    import json
    chart_paths: dict[str, Path] = {}
    try:
        det_series: dict = {}
        for mid, vals in metric_series.items():
            det_series[mid] = [{"tick": i, "value": float(v)} for i, v in enumerate(vals)]

        results_for_charts = {
            "deterministic": {"series": det_series, "final_env": final_env},
            "monte_carlo": sim_results.get("monte_carlo", {}),
            # keep original flat fields for other consumers
            "ticks": ticks,
            "metric_series": metric_series,
            "metric_names": metric_names,
            "final_env": final_env,
        }

        # Include Model B series in results.json under "comparison" key
        if _dual:
            det_series_b: dict = {}
            for mid, vals in metric_series_b.items():
                det_series_b[mid] = [{"tick": i, "value": float(v)} for i, v in enumerate(vals)]
            results_for_charts["comparison"] = {
                "det_series_a": det_series,
                "det_series_b": det_series_b,
                "theory_ids_a": theory_ids,
                "theory_ids_b": theory_ids_b,
            }

        scenarios_dir = Path(__file__).parent.parent / "scenarios" / slug
        scenarios_dir.mkdir(parents=True, exist_ok=True)
        results_json = scenarios_dir / "results.json"
        results_json.write_text(json.dumps(results_for_charts, default=str), encoding="utf-8")

        chart_plan = _build_chart_plan(spec, metric_series, metric_names,
                                       sim_results.get("monte_carlo", {}), tick_unit,
                                       final_env=final_env)

        from scripts.generate_charts import generate as _gen_charts
        generated = _gen_charts(slug, plan=chart_plan)
        for p in generated:
            chart_paths[p.stem] = p.resolve()
        logger.info("Generated %d charts for %s", len(generated), slug)

        # ── Comparison chart (dual-model overlay) ────────────────────────────
        if _dual:
            try:
                _comparison_chart_path = _generate_comparison_chart(
                    slug, metric_series, metric_series_b, metric_names, tick_unit
                )
                if _comparison_chart_path:
                    chart_paths["fig_comparison"] = _comparison_chart_path
            except Exception as cmp_exc:
                logger.warning("Comparison chart generation failed: %s", cmp_exc)

    except Exception as exc:
        logger.warning("Chart generation failed (findings will have no images): %s", exc)

    # ── Inject chart references into markdown ────────────────────────────────
    # Insert charts at specific section boundaries using absolute paths.
    # xhtml2pdf embeds images as base64 so absolute paths are required.
    def _img(stem: str, caption: str) -> str:
        p = chart_paths.get(stem)
        if not p or not p.exists():
            return ""
        return f'\n\n![{caption}]({p})\n\n*{caption}*\n'

    # Injection points (insert AFTER these section headers):
    domain_label = (spec.domain or "Scenario").title()
    injections = [
        # After Executive Findings → shock cascade + MC fan
        ("## 1. Simulation Design",
         _img("fig2_shock_cascade", f"Shock Cascade — {domain_label} Primary Metrics") +
         _img("fig3_mc_fan", f"Monte Carlo Fan Chart — {ticks} {tick_unit}s, 300 Runs")),
        # After Section 1 shock table → key metrics dashboard
        ("## 2. Results by Module",
         _img("fig1_metrics_dashboard", f"{domain_label} Metrics Dashboard")),
        # After Section 2 module results → secondary indicators
        ("## 3. Cascade Interaction",
         _img("fig4_secondary_indicators", f"Secondary Indicators — {domain_label}")),
        # After Section 4 MC distribution → boxplot
        ("## 5. Model Limitations",
         _img("fig5_mc_final_distribution", "Monte Carlo Final Distribution — Key Metrics")),
    ]

    # Dual-model: inject comparison chart after "## 7. Model Comparison"
    if _dual:
        injections.append((
            "### Key Finding",
            _img("fig_comparison", "Model Comparison — Recommended vs Custom Ensemble"),
        ))

    for marker, img_block in injections:
        if img_block and marker in md_content:
            md_content = md_content.replace(marker, img_block + marker, 1)

    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Findings MD written: %s", md_path)

    # ── Convert to PDF ───────────────────────────────────────────────────────
    try:
        from scripts.md_to_pdf import convert
        pdf_path = convert(md_path, quiet=True)
        logger.info("Findings PDF written: %s", pdf_path)
    except Exception as exc:
        logger.warning("Findings PDF conversion failed: %s", exc)
        pdf_path = md_path.with_suffix(".pdf")

    return md_path, pdf_path
