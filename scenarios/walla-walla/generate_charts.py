"""
scenarios/walla-walla/generate_charts.py
Generate publication-quality charts for the Walla Walla findings document.
Run: python scenarios/walla-walla/generate_charts.py
"""
import json
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Load data ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent
results = json.loads((ROOT / "results.json").read_text())
det = results["deterministic"]["series"]
mc  = results["monte_carlo"]["bands"]

CHARTS = ROOT / "charts"
CHARTS.mkdir(exist_ok=True)

TICKS = 120
months = list(range(TICKS))

# Year labels for x-axis
year_ticks = list(range(0, TICKS+1, 12))
year_labels = [f"Y{i//12}" for i in year_ticks]

# Shock tick positions
SHOCK_TICKS = {12: "Smoke\n(mild)", 24: "Water\nstress", 36: "Smoke\n(major)",
               48: "Recovery", 60: "Curtail-\nment", 72: "GDD\ncrossing",
               84: "Smoke\n(major)", 96: "Compound", 108: "Replant\nforced"}

PALETTE = {
    "cash":     "#2563EB",
    "revenue":  "#16A34A",
    "debt":     "#DC2626",
    "survival": "#7C3AED",
    "smoke":    "#F97316",
    "water":    "#0891B2",
    "replant":  "#854D0E",
    "quality":  "#BE185D",
    "temp":     "#B45309",
    "band":     "#93C5FD",
}

STYLE = {"dpi": 150, "bbox_inches": "tight"}

def extract_series(key):
    recs = det[key]
    vals = [0.0] * TICKS
    for r in recs:
        if r["tick"] < TICKS:
            vals[r["tick"]] = r["value"]
    return vals

def mc_band(key):
    b = mc[key]
    return b["p5"], b["p25"], b["p50"], b["p75"], b["p95"]

def add_shocks(ax, y_top=1.05, fontsize=6.5):
    for t, label in SHOCK_TICKS.items():
        ax.axvline(t, color="#9CA3AF", lw=0.7, ls="--", alpha=0.6)
        ax.text(t+0.5, y_top, label, fontsize=fontsize, color="#6B7280",
                va="top", ha="left", linespacing=1.2)

def set_year_axis(ax):
    ax.set_xticks(year_ticks)
    ax.set_xticklabels(year_labels)
    ax.set_xlim(0, TICKS - 1)

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

# ── Chart 1: Financial Health Dashboard ──────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
fig.suptitle("Walla Walla Label — Financial Health Dashboard\n120-Month Deterministic Run",
             fontsize=13, fontweight="bold", y=1.01)

panels = [
    ("cash_flow_health",    "Cash Flow Health",    PALETTE["cash"],     axes[0, 0]),
    ("revenue_normalized",  "Revenue (normalized)", PALETTE["revenue"],  axes[0, 1]),
    ("debt_service_stress", "Debt Service Stress",  PALETTE["debt"],     axes[1, 0]),
    ("survival_probability","Survival Probability",  PALETTE["survival"], axes[1, 1]),
]

for key, title, color, ax in panels:
    s = extract_series(key)
    p5, p25, p50, p75, p95 = mc_band(key)
    ax.fill_between(months, p5, p95, alpha=0.15, color=color, label="p5–p95 MC")
    ax.fill_between(months, p25, p75, alpha=0.25, color=color, label="p25–p75 MC")
    ax.plot(months, p50, color=color, lw=1.2, ls="--", alpha=0.8, label="MC p50")
    ax.plot(months, s, color=color, lw=2.0, label="Deterministic")
    add_shocks(ax, y_top=ax.get_ylim()[1] if ax.get_ylim()[1] > 0.5 else 1.0)
    ax.set_title(title, fontsize=10, fontweight="semibold")
    ax.set_ylim(0, 1.05)
    set_year_axis(ax)
    if key == "debt_service_stress":
        ax.axhline(0.70, color="#DC2626", lw=1, ls=":", alpha=0.8)
        ax.text(1, 0.71, "Covenant breach risk", fontsize=7, color="#DC2626")

axes[1, 0].legend(fontsize=7, loc="upper left")
fig.savefig(CHARTS / "fig1_financial_dashboard.png", **STYLE)
plt.close(fig)
print("fig1_financial_dashboard.png")

# ── Chart 2: Shock Cascade — Primary Metrics ─────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 5.5), constrained_layout=True)

cash    = extract_series("cash_flow_health")
revenue = extract_series("revenue_normalized")
debt    = extract_series("debt_service_stress")
surviv  = extract_series("survival_probability")

ax.plot(months, cash,    color=PALETTE["cash"],     lw=2.2, label="Cash Flow Health")
ax.plot(months, revenue, color=PALETTE["revenue"],  lw=2.2, label="Revenue (normalized)")
ax.plot(months, debt,    color=PALETTE["debt"],     lw=2.2, label="Debt Service Stress")
ax.plot(months, surviv,  color=PALETTE["survival"], lw=2.2, label="Survival Probability", ls="--")

# Annotate major shocks
for t, lbl in [(36, "Catastrophic\nsmoke (Y3)"), (60, "Water\ncurtailment (Y5)"), (84, "Second major\nsmoke (Y7)")]:
    ax.axvline(t, color="#E5E7EB", lw=8, alpha=0.5, zorder=0)
    ax.axvline(t, color="#9CA3AF", lw=0.8, ls="--")

ax.text(36, 0.03, "Catastrophic\nSmoke Y3", ha="center", fontsize=8, color="#F97316", fontweight="bold")
ax.text(60, 0.03, "Water\nCurtailment Y5", ha="center", fontsize=8, color="#0891B2", fontweight="bold")
ax.text(84, 0.03, "Second Major\nSmoke Y7", ha="center", fontsize=8, color="#F97316", fontweight="bold")

ax.set_ylim(0, 1.05)
ax.set_ylabel("Normalized [0–1]")
ax.set_title("Shock Cascade — Primary Financial Metrics (Deterministic)", fontsize=12, fontweight="bold")
set_year_axis(ax)
ax.legend(loc="upper right", fontsize=9)
fig.savefig(CHARTS / "fig2_shock_cascade.png", **STYLE)
plt.close(fig)
print("fig2_shock_cascade.png")

# ── Chart 3: MC Fan Chart — Survival Probability ─────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)

p5, p25, p50, p75, p95 = mc_band("survival_probability")
det_s = extract_series("survival_probability")

ax.fill_between(months, p5,  p95, alpha=0.15, color=PALETTE["survival"], label="MC p5–p95 (90% CI)")
ax.fill_between(months, p25, p75, alpha=0.30, color=PALETTE["survival"], label="MC p25–p75 (50% CI)")
ax.plot(months, p50, color=PALETTE["survival"], lw=2.0, ls="--", label="MC p50 (median)")
ax.plot(months, det_s, color=PALETTE["survival"], lw=2.5, label="Deterministic (base)")

ax.axhline(0.50, color="#6B7280", lw=1, ls=":", alpha=0.7)
ax.text(1, 0.51, "50% survival threshold", fontsize=8, color="#6B7280")

# Shade three shock windows
for t_start, t_end, label, col in [(33, 42, "Smoke Y3", "#FED7AA"), (57, 66, "Curtailment Y5", "#BAE6FD"), (81, 90, "Smoke Y7", "#FED7AA")]:
    ax.axvspan(t_start, t_end, alpha=0.2, color=col, zorder=0)

add_shocks(ax, y_top=1.05)
ax.set_ylim(0, 1.1)
ax.set_ylabel("Survival Probability")
ax.set_title("Survival Probability — 300-Run Monte Carlo Fan Chart", fontsize=12, fontweight="bold")
set_year_axis(ax)
ax.legend(loc="lower left", fontsize=9)

# Final tick annotation
ax.annotate(f"p50={p50[-1]:.2f}\np5={p5[-1]:.2f}",
            xy=(119, p50[-1]), xytext=(105, 0.48),
            fontsize=8.5, color=PALETTE["survival"],
            arrowprops=dict(arrowstyle="->", color=PALETTE["survival"], lw=1.2))

fig.savefig(CHARTS / "fig3_mc_survival_fan.png", **STYLE)
plt.close(fig)
print("fig3_mc_survival_fan.png")

# ── Chart 4: Climate & Resource Stress ───────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
fig.suptitle("Climate & Resource Stress Indicators", fontsize=12, fontweight="bold")

# Panel A: Water stock + smoke taint
smoke  = extract_series("smoke_taint_crop_disruption__taint_active")
water  = extract_series("hotelling_cpr__stock")
ax1.fill_between(months, smoke, alpha=0.3, color=PALETTE["smoke"], label="Smoke Taint Active")
ax1.plot(months, smoke, color=PALETTE["smoke"], lw=1.5)
ax1.plot(months, water, color=PALETTE["water"], lw=2.2, label="Water Stock (snowpack proxy)")
ax1.set_ylim(0, 1.05)
ax1.set_title("Smoke Taint Events vs Water Stock", fontsize=10)
ax1.set_ylabel("Normalized [0–1]")
ax1.legend(fontsize=8)
add_shocks(ax1)
set_year_axis(ax1)

# Panel B: GDD quality + temperature + replant signal
quality = extract_series("grapevine_gdd_phenology__quality")
temp    = extract_series("grapevine_gdd_phenology__temperature")
replant = extract_series("real_options_agri_adapt__replant_signal")
ax2.plot(months, quality,  color=PALETTE["quality"], lw=2.2, label="GDD Quality Score")
ax2.plot(months, temp,     color=PALETTE["temp"],    lw=2.0, ls="--", label="Temperature (GDD normalized)")
ax2.fill_between(months, replant, alpha=0.25, color=PALETTE["replant"], label="Replant Signal")
ax2.plot(months, replant,  color=PALETTE["replant"], lw=1.5)
ax2.axhline(0.30, color=PALETTE["replant"], lw=1, ls=":", alpha=0.7)
ax2.text(1, 0.31, "Replant threshold", fontsize=7.5, color=PALETTE["replant"])
ax2.set_ylim(0, 1.05)
ax2.set_title("GDD Quality Trajectory & Replanting Signal", fontsize=10)
ax2.legend(fontsize=8)
add_shocks(ax2)
set_year_axis(ax2)

fig.savefig(CHARTS / "fig4_climate_resource_stress.png", **STYLE)
plt.close(fig)
print("fig4_climate_resource_stress.png")

# ── Chart 5: MC Uncertainty Summary — Final Tick Boxplots ────────────────────
metrics_box = [
    ("cash_flow_health",    "Cash Flow"),
    ("revenue_normalized",  "Revenue"),
    ("survival_probability","Survival\nProb"),
    ("debt_service_stress", "Debt\nStress"),
    ("hotelling_cpr__stock","Water\nStock"),
]
colors_box = [PALETTE["cash"], PALETTE["revenue"], PALETTE["survival"], PALETTE["debt"], PALETTE["water"]]

fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)

positions = list(range(len(metrics_box)))
for i, (key, label) in enumerate(metrics_box):
    p5, p25, p50, p75, p95 = mc_band(key)
    # whisker = p5/p95, box = p25/p75, median = p50, all at final tick
    box_data = {
        "med": p50[-1], "q1": p25[-1], "q3": p75[-1],
        "whislo": p5[-1], "whishi": p95[-1], "fliers": [],
    }
    bp = ax.bxp([box_data], positions=[i], widths=0.45,
                patch_artist=True,
                boxprops=dict(facecolor=colors_box[i], alpha=0.6, linewidth=1.2),
                medianprops=dict(color="white", linewidth=2.5),
                whiskerprops=dict(linewidth=1.2, color=colors_box[i]),
                capprops=dict(linewidth=1.5, color=colors_box[i]),
                flierprops=dict(marker=""))

ax.set_xticks(positions)
ax.set_xticklabels([lbl for _, lbl in metrics_box], fontsize=10)
ax.set_ylabel("Final Value (tick 120)", fontsize=10)
ax.set_ylim(0, 1.05)
ax.set_title("Monte Carlo Distribution at Tick 120 — Key Metrics\n(300 runs; boxes = p25–p75; whiskers = p5–p95)", fontsize=11, fontweight="bold")
ax.axhline(0.50, color="#9CA3AF", lw=1, ls="--", alpha=0.6)
ax.text(4.6, 0.51, "0.50", fontsize=8, color="#9CA3AF")

fig.savefig(CHARTS / "fig5_mc_final_distribution.png", **STYLE)
plt.close(fig)
print("fig5_mc_final_distribution.png")

print(f"\nAll charts written to {CHARTS}")
