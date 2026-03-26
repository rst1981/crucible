"""Generate charts from simulation results.json"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

ROOT = Path(__file__).parent
OUT  = ROOT / "charts"
OUT.mkdir(exist_ok=True)

with open(ROOT / "results.json") as f:
    data = json.load(f)

S = data["series"]

def ticks(name):
    return [r["tick"] for r in S.get(name, [])]

def vals(name):
    return [r["value"] for r in S.get(name, [])]

# ── shared style ─────────────────────────────────────────────────────────────
DARK   = "#111111"
MID    = "#444444"
SOFT   = "#888888"
RULE   = "#dddddd"
ACCENT = "#c0392b"   # red for negative events
BLUE   = "#2471a3"
GREEN  = "#1e8449"
AMBER  = "#d68910"
PURPLE = "#7d3c98"
TEAL   = "#148f77"

EVENTS = {
    1:  ("Iran war onset",       ACCENT),
    3:  ("Petrochem cascade",    AMBER),
    7:  ("Tariff crystallised",  AMBER),
    28: ("Puig announcement",    ACCENT),
    30: ("Today",                BLUE),
}

def add_events(ax, ymin, ymax, label=True):
    for tick, (name, col) in EVENTS.items():
        ax.axvline(tick, color=col, lw=1.0, ls="--", alpha=0.7, zorder=2)
        if label:
            ax.text(tick + 0.4, ymax - (ymax - ymin)*0.04, name,
                    color=col, fontsize=6.5, va="top", rotation=90, alpha=0.85)
    ax.axvspan(30, 44, color="#eaf2ff", alpha=0.45, zorder=0, label="14-day projection")

def style(ax, title, ylabel, xlim=(0, 44)):
    ax.set_title(title, fontsize=9, fontweight="bold", color=DARK, pad=5)
    ax.set_ylabel(ylabel, fontsize=7.5, color=MID)
    ax.set_xlabel("Day (0 = Feb 25, 2026)", fontsize=7.5, color=MID)
    ax.set_xlim(xlim)
    ax.tick_params(labelsize=7, colors=MID)
    ax.spines[["top","right"]].set_visible(False)
    ax.spines[["left","bottom"]].set_color(RULE)
    ax.grid(axis="y", color=RULE, lw=0.6, zorder=0)
    ax.set_facecolor("#fafafa")

# ════════════════════════════════════════════════════════════════════════════
# FIG 1 — Investor Sentiment: Stock Price Proxy
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4.2))
fig.patch.set_facecolor("white")

t  = ticks("investor_sentiment_mean")
v  = vals("investor_sentiment_mean")
vp = vals("investor_sentiment_polarization")

# map sentiment [0,1] to stock price [$40,$121]
lo, hi = 40, 121
stock = [lo + x * (hi - lo) for x in v]

ax2 = ax.twinx()
ax2.fill_between(t, vp, alpha=0.12, color=PURPLE, zorder=1)
ax2.plot(t, vp, color=PURPLE, lw=0.8, ls=":", alpha=0.6, label="Polarisation (vol proxy)")
ax2.set_ylim(0, 2.5)
ax2.set_ylabel("Analyst Polarisation (0=consensus, 1=bimodal)", fontsize=7, color=PURPLE)
ax2.tick_params(labelsize=7, colors=PURPLE)
ax2.spines[["top"]].set_visible(False)

ax.plot(t, stock, color=DARK, lw=2.0, zorder=5, label="Sentiment → price estimate")
ax.fill_between(t, stock, min(stock), alpha=0.08, color=DARK, zorder=3)

# annotate key prices
for tick_day, price, txt in [(0,stock[0],"$104\n(start)"), (28,stock[28],"$71.60\n(Puig day)"), (43,stock[43],"$64\n(proj. end)")]:
    ax.annotate(txt, xy=(tick_day, price), xytext=(tick_day+1.5, price+4),
                fontsize=7, color=DARK,
                arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.8))

add_events(ax, min(stock), max(stock))
style(ax, "Estée Lauder — Investor Sentiment as Stock Price Proxy", "Estimated Stock Price (USD)")
ax.set_ylim(30, 130)

handles = [mpatches.Patch(color="#eaf2ff", alpha=0.8, label="14-day projection"),
           plt.Line2D([0],[0], color=PURPLE, lw=1.5, ls=":", label="Analyst polarisation")]
ax.legend(handles=handles, fontsize=7, loc="upper right", framealpha=0.9)
fig.tight_layout()
fig.savefig(OUT / "fig1_sentiment_stock.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig1 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 2 — 4-panel module dashboard
# ════════════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(12, 8))
fig.patch.set_facecolor("white")
gs = gridspec.GridSpec(2, 2, hspace=0.42, wspace=0.32)

# ── panel A: Contagion SIR ───────────────────────────────────────────────
ax = fig.add_subplot(gs[0, 0])
ax.stackplot(ticks("market_selloff_infected"),
             vals("market_selloff_infected"),
             labels=["Infected (panic)"],
             colors=[ACCENT], alpha=0.7)
ax.plot(ticks("market_selloff_infected"), vals("market_selloff_infected"),
        color=ACCENT, lw=1.5)
add_events(ax, 0, 0.45, label=False)
style(ax, "A. Market Contagion (SIR) — Panic Transmission", "Infected fraction of market actors")
ax.set_ylim(0, 0.46)

# ── panel B: GDP normalized ──────────────────────────────────────────────
ax = fig.add_subplot(gs[0, 1])
ax.plot(ticks("keynesian_gdp"), vals("keynesian_gdp"), color=BLUE, lw=2.0)
ax.fill_between(ticks("keynesian_gdp"), vals("keynesian_gdp"), alpha=0.15, color=BLUE)
add_events(ax, 0, 0.55, label=False)
style(ax, "B. Keynesian GDP (Demand Destruction)", "GDP normalised (0.5 = baseline)")
ax.axhline(0.5, color=GREEN, lw=0.8, ls="--", alpha=0.5)
ax.text(1, 0.51, "baseline", color=GREEN, fontsize=6.5)
ax.set_ylim(-0.05, 0.58)

# ── panel C: Regulation shock stacking ──────────────────────────────────
ax = fig.add_subplot(gs[1, 0])
ax.fill_between(ticks("regulation_shock_magnitude"), vals("regulation_shock_magnitude"),
                alpha=0.25, color=AMBER)
ax.plot(ticks("regulation_shock_magnitude"), vals("regulation_shock_magnitude"),
        color=AMBER, lw=2.0, label="Shock magnitude (tariff + petrochem)")
ax.plot(ticks("regulation_compliance_cost"), vals("regulation_compliance_cost"),
        color=ACCENT, lw=1.5, ls="--", label="Compliance cost (post-adaptation)")
add_events(ax, 0, 0.72, label=False)
style(ax, "C. Regulatory Shock — Tariff + Petrochemical Stack", "Normalised cost level")
ax.legend(fontsize=7, loc="upper right", framealpha=0.9)
ax.set_ylim(0, 0.75)

# ── panel D: Porter profitability + Schumpeter ──────────────────────────
ax = fig.add_subplot(gs[1, 1])
ax.plot(ticks("porter_profitability"), vals("porter_profitability"),
        color=TEAL, lw=2.0, label="Industry profitability (Porter)")
ax2 = ax.twinx()
ax2.plot(ticks("schumpeter_incumbent_share"), vals("schumpeter_incumbent_share"),
         color=PURPLE, lw=1.5, ls="--", label="Incumbent share (Schumpeter)")
ax2.set_ylim(-0.05, 0.85)
ax2.set_ylabel("Incumbent market share", fontsize=7, color=PURPLE)
ax2.tick_params(labelsize=7, colors=PURPLE)
ax2.spines[["top"]].set_visible(False)
add_events(ax, 0, 0.22, label=False)
style(ax, "D. Industry Profitability & Structural Position", "Porter profitability index")
ax.set_ylim(-0.01, 0.22)
h1 = plt.Line2D([0],[0], color=TEAL, lw=2, label="Industry profitability")
h2 = plt.Line2D([0],[0], color=PURPLE, lw=1.5, ls="--", label="Incumbent share")
ax.legend(handles=[h1,h2], fontsize=7, loc="upper right", framealpha=0.9)

fig.suptitle("Estée Lauder Simulation — Module Dashboard (44-Day Cascade)",
             fontsize=11, fontweight="bold", color=DARK, y=1.01)
fig.savefig(OUT / "fig2_module_dashboard.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig2 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 3 — Iran War Channel: Trade & Energy
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
fig.patch.set_facecolor("white")

# trade volume
ax = axes[0]
ax.fill_between(ticks("global_trade_volume"), vals("global_trade_volume"),
                0.5, where=[v < 0.5 for v in vals("global_trade_volume")],
                color=ACCENT, alpha=0.2, label="Disruption below baseline")
ax.plot(ticks("global_trade_volume"), vals("global_trade_volume"),
        color=ACCENT, lw=2.0)
ax.axhline(0.52, color=GREEN, lw=0.8, ls="--", alpha=0.6)
ax.text(1, 0.53, "pre-war baseline (0.52)", color=GREEN, fontsize=6.5)
ax.axhline(0.36, color=ACCENT, lw=0.8, ls=":", alpha=0.6)
ax.text(8, 0.365, "post-disruption floor (0.36 = −31%)", color=ACCENT, fontsize=6.5)
add_events(ax, 0.30, 0.56, label=False)
style(ax, "Iran War — Global Trade Volume\n(Hormuz + Red Sea Disruption)", "Trade volume index")
ax.set_ylim(0.28, 0.58)

# energy cost
ax = axes[1]
ax.fill_between(ticks("global_energy_cost"), vals("global_energy_cost"),
                0.55, where=[v > 0.55 for v in vals("global_energy_cost")],
                color=AMBER, alpha=0.25, label="Energy cost above baseline")
ax.plot(ticks("global_energy_cost"), vals("global_energy_cost"),
        color=AMBER, lw=2.0)
ax.axhline(0.55, color=GREEN, lw=0.8, ls="--", alpha=0.6)
ax.text(1, 0.555, "pre-war baseline", color=GREEN, fontsize=6.5)

# secondary axis: implied oil price
ax2 = ax.twinx()
oil = [55 + v * (120-55) for v in vals("global_energy_cost")]
ax2.plot(ticks("global_energy_cost"), oil, color=AMBER, lw=0, alpha=0)
ax2.set_ylim(55 + 0.28*(120-55), 55 + 0.85*(120-55))
ax2.set_ylabel("Implied WTI (USD/bbl, approx.)", fontsize=7, color=AMBER)
ax2.tick_params(labelsize=7, colors=AMBER)
ax2.spines[["top"]].set_visible(False)

add_events(ax, 0.50, 0.85, label=False)
style(ax, "Iran War — Energy Cost Index\n(Oil Price Proxy)", "Energy cost index")
ax.set_ylim(0.50, 0.86)

fig.suptitle("Iran War Channel: Shipping + Energy Disruption", fontsize=10,
             fontweight="bold", color=DARK, y=1.01)
fig.tight_layout()
fig.savefig(OUT / "fig3_iran_channel.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig3 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 4 — Shock Stacking: cumulative pressure by source
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4))
fig.patch.set_facecolor("white")

T = list(range(44))

# reconstruct approximate contribution of each shock source
# (simplified: each is a stepped profile matching scheduled_shocks)
macro_shock   = [0.12 if t >= 1 else 0.0 for t in T]
petrochem     = [0.18 if t >= 3 else 0.0 for t in T]
tariff        = [0.14 if t >= 7 else 0.0 for t in T]
logistics     = [0.06 if t >= 18 else 0.0 for t in T]
puig_ma       = [0.18 if t >= 28 else 0.0 for t in T]

labels = ["Iran war macro shock", "Petrochemical cascade", "Tariff crystallisation",
          "Wholesale logistics", "Puig M&A uncertainty"]
colors_ = [ACCENT, AMBER, "#e67e22", TEAL, PURPLE]
data_stack = [macro_shock, petrochem, tariff, logistics, puig_ma]

ax.stackplot(T, data_stack, labels=labels, colors=colors_, alpha=0.82)

for tick_day, name, col in [(1,"Iran war",ACCENT),(3,"Petrochem",AMBER),
                             (7,"Tariff",AMBER),(18,"Logistics",TEAL),(28,"Puig",PURPLE)]:
    ax.axvline(tick_day, color=col, lw=0.8, ls="--", alpha=0.5)

ax.axvspan(30, 43, color="#eaf2ff", alpha=0.4, label="14-day projection")
style(ax, "Cumulative Shock Stacking — Pressure on EL Stock", "Cumulative normalised shock magnitude")
ax.legend(fontsize=7.5, loc="upper left", framealpha=0.95)
ax.set_ylim(0, 0.85)

fig.tight_layout()
fig.savefig(OUT / "fig4_shock_stacking.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig4 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 5 — 14-Day Forward Projection scenarios
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4.2))
fig.patch.set_facecolor("white")

t_hist = ticks("investor_sentiment_mean")[:31]
v_hist = vals("investor_sentiment_mean")[:31]
stock_hist = [lo + x * (hi - lo) for x in v_hist]

ax.plot(t_hist, stock_hist, color=DARK, lw=2.2, zorder=5, label="Historical (simulated)")
ax.fill_between(t_hist, stock_hist, min(stock_hist)-2, alpha=0.07, color=DARK)

# projection scenarios from Day 30
t_proj = list(range(30, 45))

# base: sentiment 0.078 → 0.040 → mapped to price
base_sent = [0.078 - (0.078-0.040)*(i/14) for i in range(15)]
base_price = [lo + s*(hi-lo) for s in base_sent]

# bull: Puig collapses → +0.15 sentiment reset, stabilises
bull_sent = [min(0.078 + 0.15*(1 - np.exp(-i/3)), 0.35) for i in range(15)]
bull_price = [lo + s*(hi-lo) for s in bull_sent]

# bear: expensive Puig terms + Iran escalation → further -0.03
bear_sent = [max(0.078 - 0.04*i/14, 0.025) for i in range(15)]
bear_price = [lo + s*(hi-lo) for s in bear_sent]

ax.plot(t_proj, base_price, color=DARK,   lw=1.8, ls="-",  label="Base ($68–$78)")
ax.plot(t_proj, bull_price, color=GREEN,  lw=1.8, ls="--", label="Bull: Puig collapses ($82–$88)")
ax.plot(t_proj, bear_price, color=ACCENT, lw=1.8, ls=":",  label="Bear: Expensive terms + escalation ($60–$65)")

ax.fill_between(t_proj, bear_price, bull_price, alpha=0.08, color=BLUE)
ax.axvline(30, color=BLUE, lw=1.2, ls="-", alpha=0.8)
ax.text(30.4, 115, "Today\nMarch 26", color=BLUE, fontsize=7, va="top")

# consensus PT
ax.axhline(92.52, color=SOFT, lw=0.8, ls=":", alpha=0.7)
ax.text(1, 93.5, "Consensus PT $92.52 (12-month, not 14-day)", color=SOFT, fontsize=6.5)

style(ax, "14-Day Forward Projection — Three Scenarios", "Estimated Stock Price (USD)")
ax.set_ylim(35, 125)
ax.legend(fontsize=8, loc="lower left", framealpha=0.95)
ax.axvspan(30, 44, color="#eaf2ff", alpha=0.35)

fig.tight_layout()
fig.savefig(OUT / "fig5_forward_projection.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig5 done")

print(f"\nAll charts saved to {OUT}")
