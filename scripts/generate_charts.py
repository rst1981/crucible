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
    """2×2 panel: financial metrics with MC bands."""
    metrics = plan["financial_metrics"]
    months  = list(range(n))
    tick_unit = plan["tick_unit"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    fig.suptitle(f"{slug.replace('-', ' ').title()} — Key Metrics Dashboard\n"
                 f"{n}-Tick Deterministic Run + MC Bands",
                 fontsize=13, fontweight="bold", y=1.01)

    for (key, title, color), ax in zip(metrics, axes.flat):
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

    axes[1, 0].legend(fontsize=7, loc="best")
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


# ── Public API ────────────────────────────────────────────────────────────────

def generate(slug: str) -> list[pathlib.Path]:
    """
    Generate all charts for a scenario and return list of written paths.

    Parameters
    ----------
    slug : scenario identifier (must match scenarios/{slug}/results.json)

    Returns
    -------
    list of absolute Path objects for each chart written
    """
    data  = _load(slug)
    det   = data.get("deterministic", data).get("series", {})
    mc    = data.get("monte_carlo", {}).get("bands", {})
    n     = max((r["tick"] for series in det.values() for r in series), default=0) + 1

    plan  = _SCENARIO_PLANS.get(slug) or _auto_plan(det, mc)
    out   = _charts_dir(slug)

    written: list[pathlib.Path] = []
    generators = [
        (_fig1_dashboard, (slug, det, mc, plan, n, out)),
        (_fig2_cascade,   (slug, det,     plan, n, out)),
        (_fig3_mc_fan,    (slug, det, mc, plan, n, out)),
        (_fig4_secondary, (slug, det,     plan, n, out)),
        (_fig5_boxplots,  (slug,      mc, plan, n, out)),
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
