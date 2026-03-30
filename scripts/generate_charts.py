"""
scripts/generate_charts.py — Reusable chart generator for Crucible findings documents.

Reads a scenario's results.json and produces a standard chart set in
scenarios/{slug}/charts/.  Called automatically by /forge-findings after
the simulation runs.

Usage:
    python scripts/generate_charts.py <slug>
    python scripts/generate_charts.py walla-walla
    python scripts/generate_charts.py deepseek

Returns:
    Prints the path of each chart written.  Exit 0 on success.

From Python:
    from scripts.generate_charts import generate
    paths = generate("walla-walla")   # list[Path]
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Repo layout ───────────────────────────────────────────────────────────────
_REPO = pathlib.Path(__file__).parent.parent


# ── Colour palette (shared across all scenarios) ──────────────────────────────
PALETTE = [
    "#2563EB",  # blue
    "#16A34A",  # green
    "#DC2626",  # red
    "#7C3AED",  # purple
    "#F97316",  # orange
    "#0891B2",  # cyan
    "#854D0E",  # brown
    "#BE185D",  # pink
    "#B45309",  # amber
    "#4B5563",  # grey
]

STYLE = {"dpi": 150, "bbox_inches": "tight"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(slug: str) -> dict[str, Any]:
    path = _REPO / "scenarios" / slug / "results.json"
    if not path.exists():
        raise FileNotFoundError(f"results.json not found: {path}")
    return json.loads(path.read_text())


def _charts_dir(slug: str) -> pathlib.Path:
    d = _REPO / "scenarios" / slug / "charts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_series(det_series: dict, key: str, n_ticks: int) -> list[float]:
    vals = [0.0] * n_ticks
    for r in det_series.get(key, []):
        t = r["tick"]
        if t < n_ticks:
            vals[t] = r["value"]
    return vals


def _set_year_axis(ax: plt.Axes, n_ticks: int, tick_unit: str = "month") -> None:
    if tick_unit == "month":
        step = 12
        label_fn = lambda t: f"Y{t // 12}"
    elif tick_unit == "quarter":
        step = 4
        label_fn = lambda t: f"Y{t // 4}"
    else:
        step = max(1, n_ticks // 10)
        label_fn = lambda t: str(t)
    xticks = list(range(0, n_ticks + 1, step))
    ax.set_xticks(xticks)
    ax.set_xticklabels([label_fn(t) for t in xticks])
    ax.set_xlim(0, n_ticks - 1)


def _add_shocks(ax: plt.Axes, shocks: dict[int, str], y_top: float = 1.05,
                fontsize: float = 6.5) -> None:
    for t, label in sorted(shocks.items()):
        ax.axvline(t, color="#9CA3AF", lw=0.7, ls="--", alpha=0.6)
        ax.text(t + 0.5, y_top, label, fontsize=fontsize, color="#6B7280",
                va="top", ha="left", linespacing=1.2)


# ── Per-scenario chart plans ──────────────────────────────────────────────────
# Each entry defines which charts to produce and how to label them.
# Keys must match env keys in results.json.

_SCENARIO_PLANS: dict[str, dict] = {
    "walla-walla": {
        "tick_unit": "month",
        "shocks": {
            12: "Smoke\n(mild)", 24: "Water\nstress", 36: "Smoke\n(major)",
            48: "Recovery", 60: "Curtail-\nment", 72: "GDD\ncrossing",
            84: "Smoke\n(major)", 96: "Compound", 108: "Replant\nforced",
        },
        "financial_metrics": [
            ("cash_flow_health",     "Cash Flow Health",     PALETTE[0]),
            ("revenue_normalized",   "Revenue (normalized)", PALETTE[1]),
            ("debt_service_stress",  "Debt Service Stress",  PALETTE[2]),
            ("survival_probability", "Survival Probability", PALETTE[3]),
        ],
        "cascade_metrics": [
            ("cash_flow_health",     "Cash Flow Health",     PALETTE[0]),
            ("revenue_normalized",   "Revenue (normalized)", PALETTE[1]),
            ("debt_service_stress",  "Debt Service Stress",  PALETTE[2]),
            ("survival_probability", "Survival Probability", PALETTE[3]),
        ],
        "cascade_annotations": [
            (36,  "Catastrophic\nSmoke Y3",  "#F97316"),
            (60,  "Water\nCurtailment Y5",   "#0891B2"),
            (84,  "Second Major\nSmoke Y7",  "#F97316"),
        ],
        "climate_left": [
            ("smoke_taint_crop_disruption__taint_active", "Smoke Taint Active", PALETTE[4], "fill"),
            ("hotelling_cpr__stock",                      "Water Stock",        PALETTE[5], "line"),
        ],
        "climate_right": [
            ("grapevine_gdd_phenology__quality",          "GDD Quality Score",  PALETTE[7], "line"),
            ("grapevine_gdd_phenology__temperature",      "Temperature (GDD)",  PALETTE[8], "dashed"),
            ("real_options_agri_adapt__replant_signal",   "Replant Signal",     PALETTE[6], "fill"),
        ],
        "replant_threshold": 0.30,
        "covenant_threshold": 0.70,
        "boxplot_metrics": [
            ("cash_flow_health",     "Cash Flow"),
            ("revenue_normalized",   "Revenue"),
            ("survival_probability", "Survival\nProb"),
            ("debt_service_stress",  "Debt\nStress"),
            ("hotelling_cpr__stock", "Water\nStock"),
        ],
        "mc_fan_metric": "survival_probability",
        "mc_fan_label":  "Survival Probability",
        "mc_fan_threshold": (0.50, "50% survival threshold"),
    },
    "deepseek": {
        "tick_unit": "month",
        "shocks": {
            0:  "DeepSeek\nshock",
            6:  "Earnings\nrevision",
            12: "CUDA\nresponse",
        },
        "financial_metrics": [
            ("event__cumulative_ar",               "Cumulative AR (NVIDIA)",   PALETTE[2]),
            ("narrative_contagion__sentiment_balance", "Sentiment Balance",    PALETTE[0]),
            ("platform_tipping__incumbent_share",  "GPU Market Share",         PALETTE[4]),
            ("compute_efficiency__incumbent_moat", "Compute Moat",             PALETTE[3]),
        ],
        "cascade_metrics": [
            ("event__cumulative_ar",               "Cumulative AR",            PALETTE[2]),
            ("narrative_contagion__sentiment_balance", "Sentiment",            PALETTE[0]),
            ("platform_tipping__incumbent_share",  "Market Share",             PALETTE[4]),
            ("fisher__new_tech_share",             "Open-weight Share",        PALETTE[1]),
        ],
        "cascade_annotations": [
            (0,  "DeepSeek\nR1 release",  "#DC2626"),
        ],
        "climate_left": [
            ("narrative_contagion__bull_share",  "Bull Narrative",  PALETTE[0], "fill"),
            ("narrative_contagion__bear_share",  "Bear Narrative",  PALETTE[2], "fill"),
        ],
        "climate_right": [
            ("fisher__new_tech_share",          "Open-weight Share",  PALETTE[1], "line"),
            ("compute_efficiency__incumbent_moat", "Compute Moat",    PALETTE[3], "dashed"),
            ("schumpeter__innovator_share",     "Innovator Share",    PALETTE[4], "line"),
        ],
        "replant_threshold": None,
        "covenant_threshold": None,
        "boxplot_metrics": [
            ("event__cumulative_ar",               "Cum AR"),
            ("narrative_contagion__sentiment_balance", "Sentiment"),
            ("platform_tipping__incumbent_share",  "Market\nShare"),
            ("compute_efficiency__incumbent_moat", "Compute\nMoat"),
        ],
        "mc_fan_metric": "event__cumulative_ar",
        "mc_fan_label":  "Cumulative Abnormal Return",
        "mc_fan_threshold": (0.0, "Zero return baseline"),
    },
}

_DEFAULT_PLAN = {
    "tick_unit": "month",
    "shocks": {},
    "financial_metrics": None,   # auto-detect top 4 metrics
    "cascade_metrics": None,
    "cascade_annotations": [],
    "climate_left": None,
    "climate_right": None,
    "replant_threshold": None,
    "covenant_threshold": None,
    "boxplot_metrics": None,
    "mc_fan_metric": None,
    "mc_fan_label": "Primary Metric",
    "mc_fan_threshold": None,
}


def _auto_plan(det_series: dict, mc_bands: dict) -> dict:
    """Build a minimal plan from whatever metrics exist in results.json."""
    all_keys = list(det_series.keys())
    plan = dict(_DEFAULT_PLAN)
    top4 = [(k, k.replace("_", " ").title(), PALETTE[i % len(PALETTE)])
            for i, k in enumerate(all_keys[:4])]
    plan["financial_metrics"]  = top4
    plan["cascade_metrics"]    = top4
    plan["boxplot_metrics"]    = [(k, k.split("__")[-1].replace("_", " ").title()[:12])
                                   for k in all_keys[:5]]
    plan["mc_fan_metric"]      = all_keys[0] if all_keys else None
    plan["mc_fan_label"]       = all_keys[0].replace("_", " ").title() if all_keys else ""
    mid = len(all_keys) // 2
    plan["climate_left"]  = [(k, k.split("__")[-1].replace("_", " ").title(),
                               PALETTE[i % len(PALETTE)], "line")
                              for i, k in enumerate(all_keys[mid:mid+2])]
    plan["climate_right"] = [(k, k.split("__")[-1].replace("_", " ").title(),
                               PALETTE[(i+2) % len(PALETTE)], "line")
                              for i, k in enumerate(all_keys[mid+2:mid+5])]
    return plan


# ── Chart generators ──────────────────────────────────────────────────────────

def _fig1_dashboard(slug: str, det: dict, mc: dict, plan: dict,
                    n: int, out: pathlib.Path) -> pathlib.Path:
    """Adaptive panel layout: 1–4 metrics with MC bands. Never leaves empty panels."""
    metrics = plan["financial_metrics"] or []
    if not metrics:
        return None
    months    = list(range(n))
    tick_unit = plan["tick_unit"]
    m         = len(metrics)

    # Choose grid: 1→(1,1), 2→(1,2), 3→(1,3), 4→(2,2)
    if m == 1:
        nrows, ncols = 1, 1
    elif m == 2:
        nrows, ncols = 1, 2
    elif m == 3:
        nrows, ncols = 1, 3
    else:
        nrows, ncols = 2, 2

    fig_w = max(7, ncols * 6)
    fig_h = max(4, nrows * 4)
    fig, axes_obj = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), constrained_layout=True)
    # Normalise axes to a flat list regardless of shape
    import numpy as np
    axes_flat = np.array(axes_obj).flatten().tolist()

    fig.suptitle(f"{slug.replace('-', ' ').title()} — Key Metrics Dashboard\n"
                 f"{n}-Tick Deterministic Run + MC Bands",
                 fontsize=13, fontweight="bold", y=1.01)

    for (key, title, color), ax in zip(metrics, axes_flat):
        s = _extract_series(det, key, n)
        if key in mc:
            b = mc[key]
            p5, p25, p50, p75, p95 = b["p5"], b["p25"], b["p50"], b["p75"], b["p95"]
            ax.fill_between(months, p5,  p95,  alpha=0.15, color=color, label="p5–p95 MC")
            ax.fill_between(months, p25, p75,  alpha=0.25, color=color, label="p25–p75 MC")
            ax.plot(months, p50, color=color, lw=1.2, ls="--", alpha=0.8, label="MC p50")
        ax.plot(months, s, color=color, lw=2.0, label="Deterministic")
        _add_shocks(ax, plan["shocks"])
        ax.set_title(title, fontsize=10, fontweight="semibold")
        ax.set_ylim(auto=True)
        _set_year_axis(ax, n, tick_unit)
        if plan.get("covenant_threshold") and "stress" in key:
            ax.axhline(plan["covenant_threshold"], color=PALETTE[2], lw=1, ls=":", alpha=0.7)
            ax.text(1, plan["covenant_threshold"] + 0.01, "Covenant risk",
                    fontsize=7, color=PALETTE[2])

    axes_flat[0].legend(fontsize=7, loc="best")
    path = out / "fig1_metrics_dashboard.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig2_cascade(slug: str, det: dict, plan: dict,
                  n: int, out: pathlib.Path) -> pathlib.Path:
    """All primary metrics on one timeline with shock annotations."""
    months = list(range(n))
    fig, ax = plt.subplots(figsize=(13, 5.5), constrained_layout=True)

    for key, label, color in plan["cascade_metrics"]:
        s = _extract_series(det, key, n)
        ax.plot(months, s, color=color, lw=2.2, label=label)

    for t, label, color in plan.get("cascade_annotations", []):
        ax.axvspan(max(0, t - 3), min(n - 1, t + 6), alpha=0.12, color=color, zorder=0)
        ax.axvline(t, color="#9CA3AF", lw=0.8, ls="--")
        ax.text(t, ax.get_ylim()[0] + 0.02 if ax.get_ylim()[0] > -0.5 else ax.get_ylim()[0] + 0.02,
                label, ha="center", fontsize=8, color=color, fontweight="bold")

    ax.set_ylabel("Normalized value")
    ax.set_title(f"{slug.replace('-', ' ').title()} — Shock Cascade (Deterministic)",
                 fontsize=12, fontweight="bold")
    _set_year_axis(ax, n, plan["tick_unit"])
    ax.legend(loc="best", fontsize=9)

    path = out / "fig2_shock_cascade.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig3_mc_fan(slug: str, det: dict, mc: dict, plan: dict,
                 n: int, out: pathlib.Path) -> pathlib.Path:
    """MC fan chart for the primary metric."""
    metric = plan["mc_fan_metric"]
    if not metric or metric not in mc:
        return None
    months = list(range(n))
    b = mc[metric]
    p5, p25, p50, p75, p95 = b["p5"], b["p25"], b["p50"], b["p75"], b["p95"]
    det_s = _extract_series(det, metric, n)
    color = PALETTE[3]

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    ax.fill_between(months, p5,  p95,  alpha=0.15, color=color, label="MC p5–p95 (90% CI)")
    ax.fill_between(months, p25, p75,  alpha=0.30, color=color, label="MC p25–p75 (50% CI)")
    ax.plot(months, p50,  color=color, lw=2.0, ls="--", label="MC p50 (median)")
    ax.plot(months, det_s, color=color, lw=2.5, label="Deterministic (base)")

    if plan.get("mc_fan_threshold"):
        thr, label = plan["mc_fan_threshold"]
        ax.axhline(thr, color="#6B7280", lw=1, ls=":", alpha=0.7)
        ax.text(1, thr + 0.01, label, fontsize=8, color="#6B7280")

    _add_shocks(ax, plan["shocks"])
    ax.set_ylabel(plan["mc_fan_label"])
    ax.set_title(f"{plan['mc_fan_label']} — 300-Run Monte Carlo Fan Chart",
                 fontsize=12, fontweight="bold")
    _set_year_axis(ax, n, plan["tick_unit"])
    ax.legend(loc="best", fontsize=9)

    # Annotate final tick
    ax.annotate(f"p50={p50[-1]:.2f}\np5={p5[-1]:.2f}",
                xy=(n - 1, p50[-1]),
                xytext=(max(0, n - 18), (p50[-1] + p5[-1]) / 2),
                fontsize=8.5, color=color,
                arrowprops=dict(arrowstyle="->", color=color, lw=1.2))

    path = out / "fig3_mc_fan.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig4_secondary(slug: str, det: dict, plan: dict,
                    n: int, out: pathlib.Path) -> pathlib.Path:
    """Two-panel secondary metrics chart (climate/resource/narrative)."""
    left  = plan.get("climate_left")  or []
    right = plan.get("climate_right") or []
    if not left and not right:
        return None

    months = list(range(n))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    fig.suptitle("Secondary Indicators", fontsize=12, fontweight="bold")

    def _plot_panel(ax, series_list, title):
        for key, label, color, style in series_list:
            s = _extract_series(det, key, n)
            if style == "fill":
                ax.fill_between(months, s, alpha=0.3, color=color, label=label)
                ax.plot(months, s, color=color, lw=1.5)
            elif style == "dashed":
                ax.plot(months, s, color=color, lw=2.0, ls="--", label=label)
            else:
                ax.plot(months, s, color=color, lw=2.2, label=label)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("Normalized [0–1]")
        ax.legend(fontsize=8)
        _add_shocks(ax, plan["shocks"])
        _set_year_axis(ax, n, plan["tick_unit"])

    left_keys  = [l[1] for l in left]
    right_keys = [r[1] for r in right]
    _plot_panel(ax1, left,  " / ".join(left_keys[:2]))
    _plot_panel(ax2, right, " / ".join(right_keys[:2]))

    # Optional threshold lines
    if plan.get("replant_threshold"):
        ax2.axhline(plan["replant_threshold"], color=PALETTE[6], lw=1, ls=":", alpha=0.7)
        ax2.text(1, plan["replant_threshold"] + 0.01, "Exercise threshold",
                 fontsize=7.5, color=PALETTE[6])

    path = out / "fig4_secondary_indicators.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig5_boxplots(slug: str, mc: dict, plan: dict,
                   n: int, out: pathlib.Path) -> pathlib.Path:
    """Boxplots of MC distribution at final tick for key metrics."""
    box_metrics = [(k, l) for k, l in plan.get("boxplot_metrics", []) if k in mc]
    if not box_metrics:
        return None

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for i, (key, label) in enumerate(box_metrics):
        b = mc[key]
        box_data = {
            "med":    b["p50"][-1],
            "q1":     b["p25"][-1],
            "q3":     b["p75"][-1],
            "whislo": b["p5"][-1],
            "whishi": b["p95"][-1],
            "fliers": [],
        }
        ax.bxp([box_data], positions=[i], widths=0.45,
               patch_artist=True,
               boxprops=dict(facecolor=PALETTE[i % len(PALETTE)], alpha=0.6, linewidth=1.2),
               medianprops=dict(color="white", linewidth=2.5),
               whiskerprops=dict(linewidth=1.2, color=PALETTE[i % len(PALETTE)]),
               capprops=dict(linewidth=1.5,  color=PALETTE[i % len(PALETTE)]),
               flierprops=dict(marker=""))

    ax.set_xticks(list(range(len(box_metrics))))
    ax.set_xticklabels([l for _, l in box_metrics], fontsize=10)
    ax.set_ylabel("Final Value (tick 120)", fontsize=10)
    ax.set_title(
        f"Monte Carlo Distribution at Final Tick — Key Metrics\n"
        f"(300 runs; boxes = p25–p75; whiskers = p5–p95)",
        fontsize=11, fontweight="bold")
    ax.axhline(0.50, color="#9CA3AF", lw=1, ls="--", alpha=0.6)

    path = out / "fig5_mc_final_distribution.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig6_env_heatmap(slug: str, det: dict, plan: dict, n: int, out: pathlib.Path) -> pathlib.Path:
    """
    Heat map of all tracked metrics across all ticks.
    Rows = metrics (sorted by final value), columns = ticks.
    Color = normalized value [0-1]. Reveals emergence: correlated rows show cascade coupling.
    """
    import numpy as np
    keys = list(det.keys())
    if not keys:
        return None

    # Build matrix: rows=metrics, cols=ticks
    matrix = np.zeros((len(keys), n))
    for i, key in enumerate(keys):
        vals = _extract_series(det, key, n)
        matrix[i, :] = vals

    # Sort rows by final column value descending
    sort_idx = np.argsort(matrix[:, -1])[::-1]
    matrix = matrix[sort_idx]
    sorted_keys = [keys[i] for i in sort_idx]
    labels = [k.split("__")[-1].replace("_", " ")[:18] for k in sorted_keys]

    fig_h = max(4, len(keys) * 0.35)
    fig, ax = plt.subplots(figsize=(13, fig_h), constrained_layout=True)
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1,
                   interpolation="nearest")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=max(6, min(9, 120 // len(labels))))
    ax.set_xlabel("Tick", fontsize=10)
    ax.set_title("Environment State Heatmap — All Metrics × All Ticks\n"
                 "(green=high, red=low; correlated rows = cascade coupling)",
                 fontsize=11, fontweight="bold")

    # Add shock lines
    for t in plan.get("shocks", {}):
        ax.axvline(t, color="white", lw=0.8, alpha=0.5, ls="--")

    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="Normalized value [0–1]")

    # Year labels on x-axis
    tick_unit = plan.get("tick_unit", "month")
    step = 12 if tick_unit == "month" else (4 if tick_unit == "quarter" else max(1, n // 10))
    xticks = list(range(0, n, step))
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"Y{t // step}" for t in xticks], fontsize=8)

    path = out / "fig6_env_heatmap.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig7_theory_contributions(slug: str, theory_contribs: list[dict], n: int,
                                out: pathlib.Path) -> pathlib.Path:
    """
    Stacked area chart of per-theory total delta magnitude per tick.
    Shows which theories dominate during each phase — ABM attribution chart.
    """
    if not theory_contribs:
        return None

    import numpy as np
    from collections import defaultdict

    # Aggregate total_delta per tick per theory_id
    by_theory: dict[str, list[float]] = defaultdict(lambda: [0.0] * n)
    theory_ids: set[str] = set()
    for rec in theory_contribs:
        tick = rec.get("tick", 0)
        tid  = rec.get("theory_id", "unknown")
        delta = rec.get("total_delta", 0.0)
        if tick < n:
            by_theory[tid][tick] += delta
            theory_ids.add(tid)

    if not theory_ids:
        return None

    # Sort theories by total contribution descending
    tids = sorted(theory_ids, key=lambda t: sum(by_theory[t]), reverse=True)[:8]
    ticks = list(range(n))

    fig, ax = plt.subplots(figsize=(12, 5), constrained_layout=True)
    bottom = np.zeros(n)
    for i, tid in enumerate(tids):
        vals = np.array(by_theory[tid])
        label = tid.replace("_", " ").title()[:28]
        ax.fill_between(ticks, bottom, bottom + vals,
                        color=PALETTE[i % len(PALETTE)], alpha=0.75, label=label)
        bottom += vals

    ax.set_ylabel("Total Theory Write Magnitude (Σ|Δenv|)", fontsize=10)
    ax.set_xlabel("Tick", fontsize=10)
    ax.set_title("Theory Contribution per Tick — Mechanism Attribution\n"
                 "(stacked: which theory drove most state change each tick)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=7, ncol=2)

    path = out / "fig7_theory_contributions.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig8_phase_space(slug: str, det: dict, mc: dict, plan: dict,
                      n: int, out: pathlib.Path) -> pathlib.Path:
    """
    2D phase space: top-2 metrics against each other, colored by tick.
    MC cloud (final-tick p25–p75 ellipse) overlaid on deterministic path.
    Reveals attractor dynamics, phase transitions, regime shifts.
    """
    import numpy as np

    metrics = plan.get("financial_metrics", [])
    if len(metrics) < 2:
        return None

    key_x, lbl_x, _ = metrics[0]
    key_y, lbl_y, _ = metrics[1]

    sx = _extract_series(det, key_x, n)
    sy = _extract_series(det, key_y, n)

    fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)

    # Plot trajectory colored by time
    cmap = plt.get_cmap("plasma")
    for t in range(n - 1):
        color = cmap(t / max(n - 1, 1))
        ax.plot([sx[t], sx[t+1]], [sy[t], sy[t+1]], color=color, lw=1.5, alpha=0.8)

    # MC uncertainty cloud at final tick
    if key_x in mc and key_y in mc:
        bx = mc[key_x]
        by = mc[key_y]
        # Draw a box from p25-p75 at final tick
        x25, x75 = bx["p25"][-1], bx["p75"][-1]
        y25, y75 = by["p25"][-1], by["p75"][-1]
        from matplotlib.patches import FancyBboxPatch
        rect = FancyBboxPatch((x25, y25), x75 - x25, y75 - y25,
                              boxstyle="round,pad=0.01",
                              linewidth=1.5, edgecolor="#7C3AED",
                              facecolor="#7C3AED", alpha=0.12)
        ax.add_patch(rect)
        ax.annotate("MC p25–p75\nat final tick", xy=(x75, y75),
                    fontsize=8, color="#7C3AED", ha="left")

    # Mark start and end
    ax.plot(sx[0], sy[0], "o", color="#16A34A", ms=10, zorder=5, label="Start (tick 0)")
    ax.plot(sx[-1], sy[-1], "s", color="#DC2626", ms=10, zorder=5,
            label=f"End (tick {n-1})")

    # Colorbar for time
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=n-1))
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.04, pad=0.04, label="Tick")

    ax.set_xlabel(lbl_x, fontsize=11)
    ax.set_ylabel(lbl_y, fontsize=11)
    ax.set_title(f"Phase Space Trajectory: {lbl_x} vs {lbl_y}\n"
                 f"(path colored by time; purple box = MC uncertainty at final tick)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)

    path = out / "fig8_phase_space.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig9_uncertainty_decomp(slug: str, mc: dict, n: int, out: pathlib.Path) -> pathlib.Path:
    """
    Horizontal bar chart: p95-p5 spread per metric at final tick, sorted descending.
    Shows which state variables have the most emergent uncertainty — key for
    identifying the model's most sensitive dimensions.
    """
    bands = mc if isinstance(mc, dict) else {}
    if not bands:
        return None

    items: list[tuple[float, str]] = []
    for mid, band in bands.items():
        p5  = band.get("p5",  [None])
        p95 = band.get("p95", [None])
        if p5 and p95 and p5[-1] is not None and p95[-1] is not None:
            spread = float(p95[-1]) - float(p5[-1])
            label  = mid.split("__")[-1].replace("_", " ").title()[:30]
            items.append((spread, label))

    if not items:
        return None

    items.sort(reverse=True)
    items = items[:15]  # top 15

    spreads = [s for s, _ in items]
    labels  = [l for _, l in items]
    colors  = [PALETTE[i % len(PALETTE)] for i in range(len(items))]

    fig, ax = plt.subplots(figsize=(9, max(4, len(items) * 0.45)), constrained_layout=True)
    bars = ax.barh(labels, spreads, color=colors, alpha=0.8)
    ax.set_xlabel("p95 – p5 spread at final tick", fontsize=10)
    ax.set_title("MC Uncertainty Decomposition — Sensitivity by State Variable\n"
                 "(width = 90% confidence interval; wider = more uncertain outcome)",
                 fontsize=11, fontweight="bold")
    ax.set_xlim(0, max(spreads) * 1.15)
    for bar, val in zip(bars, spreads):
        ax.text(val + max(spreads) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=8)

    path = out / "fig9_uncertainty_decomp.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig10_mc_convergence(slug: str, mc_run_finals: list[dict],
                           mc_fan_metric: str | None,
                           out: pathlib.Path) -> pathlib.Path:
    """
    Running p50 estimate as N_runs increases (sub-sampled every 10 runs).
    Flat line = 300 runs was sufficient. Shows simulation sample efficiency.
    """
    if not mc_run_finals or not mc_fan_metric:
        return None

    vals = [r.get(mc_fan_metric) for r in mc_run_finals if r.get(mc_fan_metric) is not None]
    if len(vals) < 20:
        return None

    import numpy as np
    checkpoints = list(range(10, len(vals) + 1, 10))
    running_p50 = [float(np.median(vals[:k])) for k in checkpoints]
    running_p5  = [float(np.percentile(vals[:k],  5)) for k in checkpoints]
    running_p95 = [float(np.percentile(vals[:k], 95)) for k in checkpoints]

    label = mc_fan_metric.split("__")[-1].replace("_", " ").title()[:40]

    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax.fill_between(checkpoints, running_p5, running_p95,
                    alpha=0.2, color=PALETTE[3], label="p5–p95 running CI")
    ax.plot(checkpoints, running_p50, color=PALETTE[3], lw=2.2, label="Running p50")
    ax.axhline(running_p50[-1], color="#9CA3AF", lw=1, ls="--", alpha=0.7)
    ax.set_xlabel("MC Runs Completed", fontsize=10)
    ax.set_ylabel(label, fontsize=10)
    ax.set_title(f"Monte Carlo Convergence — {label}\n"
                 f"(flatness confirms 300-run sample size is sufficient)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="best", fontsize=9)

    path = out / "fig10_mc_convergence.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


def _fig11_agent_beliefs(slug: str, env_snapshots: list[dict],
                          plan: dict, out: pathlib.Path) -> pathlib.Path:
    """
    Multi-panel chart of full environment state at each snapshot tick.
    Each snapshot is a horizontal bar showing all env keys — reveals
    how the global state vector shifts over the simulation lifetime.
    Approximates agent belief convergence (agents observe this env).
    """
    if not env_snapshots or len(env_snapshots) < 2:
        return None

    import numpy as np

    # Use up to 6 evenly spaced snapshots
    snaps = env_snapshots
    if len(snaps) > 6:
        idx = [int(i * (len(snaps) - 1) / 5) for i in range(6)]
        snaps = [snaps[i] for i in idx]

    # Collect all env keys from all snapshots
    all_keys: list[str] = []
    seen: set[str] = set()
    for snap in snaps:
        for k in (snap.get("env") or {}).keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    if not all_keys:
        return None

    # Sort keys by range across snapshots
    key_ranges = []
    for k in all_keys:
        vals = [snap["env"].get(k, 0.0) for snap in snaps]
        key_ranges.append((max(vals) - min(vals), k))
    key_ranges.sort(reverse=True)
    top_keys = [k for _, k in key_ranges[:20]]
    labels = [k.split("__")[-1].replace("_", " ")[:18] for k in top_keys]

    n_snaps = len(snaps)
    n_keys  = len(top_keys)
    matrix  = np.zeros((n_keys, n_snaps))
    for j, snap in enumerate(snaps):
        env = snap.get("env") or {}
        for i, k in enumerate(top_keys):
            matrix[i, j] = env.get(k, 0.0)

    fig, ax = plt.subplots(figsize=(max(8, n_snaps * 1.5), max(4, n_keys * 0.45)),
                           constrained_layout=True)
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1,
                   interpolation="nearest")
    ax.set_yticks(range(n_keys))
    ax.set_yticklabels(labels, fontsize=max(7, min(10, 180 // n_keys)))
    tick_labels = [f"T{snap['tick']}" for snap in snaps]
    ax.set_xticks(range(n_snaps))
    ax.set_xticklabels(tick_labels, fontsize=9)
    ax.set_title("Agent Observable State — Environment Snapshots\n"
                 "(each column = full env state agents observed at that tick; "
                 "green=high, red=low)",
                 fontsize=11, fontweight="bold")
    plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="Value [0–1]")

    path = out / "fig11_agent_state_snapshots.png"
    fig.savefig(path, **STYLE)
    plt.close(fig)
    return path


# ── Public API ────────────────────────────────────────────────────────────────

def generate(slug: str, plan: dict | None = None,
             theory_contributions: list | None = None,
             env_snapshots: list | None = None,
             mc_run_finals: list | None = None) -> list[pathlib.Path]:
    """
    Generate the standard 5-chart set for a scenario and return list of written paths.

    Charts produced:
      fig1 — Key metrics dashboard (4 panels with MC bands)
      fig2 — Shock cascade (all primary metrics + shock annotations)
      fig3 — MC fan chart (primary metric with p5/p25/p50/p75/p95 bands)
      fig4 — Secondary indicators (domain-specific: climate, resource, narrative)
      fig5 — MC final distribution (boxplots at last tick)

    Parameters
    ----------
    slug : scenario identifier (must match scenarios/{slug}/results.json)
    plan : optional pre-built chart plan (skips _SCENARIO_PLANS lookup if provided)

    Returns
    -------
    list of absolute Path objects for each chart written
    """
    data  = _load(slug)
    det   = data.get("deterministic", data).get("series", {})
    mc    = data.get("monte_carlo", {}).get("bands", {})
    n     = max((r["tick"] for series in det.values() for r in series), default=0) + 1

    if plan is None:
        plan = _SCENARIO_PLANS.get(slug) or _auto_plan(det, mc)
    out   = _charts_dir(slug)

    written: list[pathlib.Path] = []
    generators = [
        (_fig1_dashboard,  (slug, det, mc, plan, n, out)),
        (_fig2_cascade,    (slug, det,     plan, n, out)),
        (_fig3_mc_fan,     (slug, det, mc, plan, n, out)),
        (_fig4_secondary,  (slug, det,     plan, n, out)),
        (_fig5_boxplots,   (slug,      mc, plan, n, out)),
    ]
    for fn, args in generators:
        try:
            path = fn(*args)
            if path:
                written.append(path)
                print(f"  [chart] {path.name}")
        except Exception as exc:
            print(f"  [chart] WARNING: {fn.__name__} failed — {exc}", file=sys.stderr)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_charts.py <slug>")
        sys.exit(1)
    slug = sys.argv[1]
    paths = generate(slug)
    print(f"\n{len(paths)} charts written to scenarios/{slug}/charts/")
