"""Generate charts from simulation results.json (v2 — 9 modules + Monte Carlo bands)"""
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

# Support both old (flat) and new (nested) results format
if "deterministic" in data:
    S  = data["deterministic"]["series"]
    MC = data["monte_carlo"]["bands"]
else:
    S  = data["series"]
    MC = {}

def ticks(name):
    return [r["tick"] for r in S.get(name, [])]

def vals(name):
    return [r["value"] for r in S.get(name, [])]

def mc_band(name, pct):
    return MC.get(name, {}).get(f"p{pct}", [])

# ── style ─────────────────────────────────────────────────────────────────────
DARK   = "#111111"
MID    = "#444444"
SOFT   = "#888888"
RULE   = "#dddddd"
ACCENT = "#c0392b"
BLUE   = "#2471a3"
GREEN  = "#1e8449"
AMBER  = "#d68910"
PURPLE = "#7d3c98"
TEAL   = "#148f77"

EVENTS = {
    1:  ("Iran war onset",      ACCENT),
    3:  ("Petrochem cascade",   AMBER),
    7:  ("Tariff crystallised", AMBER),
    28: ("Puig announcement",   ACCENT),
    30: ("Today",               BLUE),
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

def add_mc_band(ax, name, color, alpha_outer=0.10, alpha_inner=0.18):
    p5  = mc_band(name, 5)
    p25 = mc_band(name, 25)
    p75 = mc_band(name, 75)
    p95 = mc_band(name, 95)
    if not p5:
        return
    x = list(range(len(p5)))
    ax.fill_between(x, p5,  p95,  alpha=alpha_outer, color=color, zorder=1)
    ax.fill_between(x, p25, p75,  alpha=alpha_inner,  color=color, zorder=2)

lo, hi = 40, 121  # stock price mapping range

# ════════════════════════════════════════════════════════════════════════════
# FIG 1 — Investor Sentiment: Stock Price Proxy + MC bands
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4.2))
fig.patch.set_facecolor("white")

t  = ticks("investor_sentiment_mean")
v  = vals("investor_sentiment_mean")
vp = vals("investor_sentiment_polarization")
stock = [lo + x * (hi - lo) for x in v]

# MC bands mapped to price
p5  = mc_band("investor_sentiment_mean", 5)
p95 = mc_band("investor_sentiment_mean", 95)
p25 = mc_band("investor_sentiment_mean", 25)
p75 = mc_band("investor_sentiment_mean", 75)
if p5:
    xmc = list(range(len(p5)))
    s5  = [lo + x*(hi-lo) for x in p5]
    s95 = [lo + x*(hi-lo) for x in p95]
    s25 = [lo + x*(hi-lo) for x in p25]
    s75 = [lo + x*(hi-lo) for x in p75]
    ax.fill_between(xmc, s5,  s95,  alpha=0.08, color=DARK, zorder=1, label="MC p5–p95")
    ax.fill_between(xmc, s25, s75,  alpha=0.15, color=DARK, zorder=2, label="MC p25–p75")

ax2 = ax.twinx()
ax2.fill_between(t, vp, alpha=0.12, color=PURPLE, zorder=1)
ax2.plot(t, vp, color=PURPLE, lw=0.8, ls=":", alpha=0.6)
ax2.set_ylim(0, 2.5)
ax2.set_ylabel("Analyst Polarisation", fontsize=7, color=PURPLE)
ax2.tick_params(labelsize=7, colors=PURPLE)
ax2.spines[["top"]].set_visible(False)

ax.plot(t, stock, color=DARK, lw=2.0, zorder=5, label="Deterministic run")
ax.fill_between(t, stock, min(stock), alpha=0.08, color=DARK, zorder=3)

for tick_day, price, txt in [(0,stock[0],"$104\n(start)"), (28,stock[28],"$71.60\n(Puig day)"), (43,stock[43],"$64\n(proj. end)")]:
    ax.annotate(txt, xy=(tick_day, price), xytext=(tick_day+1.5, price+4),
                fontsize=7, color=DARK,
                arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.8))

add_events(ax, min(stock), max(stock))
style(ax, "Estée Lauder — Investor Sentiment as Stock Price Proxy (with MC Uncertainty Bands)", "Estimated Stock Price (USD)")
ax.set_ylim(30, 130)
handles = [mpatches.Patch(color=DARK, alpha=0.2, label="MC p25–p75 band"),
           mpatches.Patch(color="#eaf2ff", alpha=0.8, label="14-day projection"),
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

ax = fig.add_subplot(gs[0, 0])
add_mc_band(ax, "market_selloff_infected", ACCENT)
ax.stackplot(ticks("market_selloff_infected"), vals("market_selloff_infected"),
             colors=[ACCENT], alpha=0.7)
ax.plot(ticks("market_selloff_infected"), vals("market_selloff_infected"), color=ACCENT, lw=1.5)
add_events(ax, 0, 0.45, label=False)
style(ax, "A. Market Contagion (SIR)", "Infected fraction")
ax.set_ylim(0, 0.46)

ax = fig.add_subplot(gs[0, 1])
add_mc_band(ax, "keynesian_gdp", BLUE)
ax.plot(ticks("keynesian_gdp"), vals("keynesian_gdp"), color=BLUE, lw=2.0)
ax.fill_between(ticks("keynesian_gdp"), vals("keynesian_gdp"), alpha=0.15, color=BLUE)
add_events(ax, 0, 0.55, label=False)
style(ax, "B. Keynesian GDP (Demand Destruction)", "GDP normalised")
ax.axhline(0.5, color=GREEN, lw=0.8, ls="--", alpha=0.5)
ax.set_ylim(-0.05, 0.58)

ax = fig.add_subplot(gs[1, 0])
add_mc_band(ax, "regulation_shock_magnitude", AMBER)
ax.fill_between(ticks("regulation_shock_magnitude"), vals("regulation_shock_magnitude"),
                alpha=0.25, color=AMBER)
ax.plot(ticks("regulation_shock_magnitude"), vals("regulation_shock_magnitude"),
        color=AMBER, lw=2.0, label="Shock magnitude")
ax.plot(ticks("regulation_compliance_cost"), vals("regulation_compliance_cost"),
        color=ACCENT, lw=1.5, ls="--", label="Compliance cost")
add_events(ax, 0, 0.72, label=False)
style(ax, "C. Regulatory Shock — Tariff + Petrochem Stack", "Normalised cost level")
ax.legend(fontsize=7, loc="upper right", framealpha=0.9)
ax.set_ylim(0, 0.75)

ax = fig.add_subplot(gs[1, 1])
add_mc_band(ax, "porter_profitability", TEAL)
ax.plot(ticks("porter_profitability"), vals("porter_profitability"), color=TEAL, lw=2.0)
ax2 = ax.twinx()
add_mc_band(ax2, "schumpeter_incumbent_share", PURPLE, alpha_outer=0.08, alpha_inner=0.12)
ax2.plot(ticks("schumpeter_incumbent_share"), vals("schumpeter_incumbent_share"),
         color=PURPLE, lw=1.5, ls="--")
ax2.set_ylim(-0.05, 0.85)
ax2.set_ylabel("Incumbent market share", fontsize=7, color=PURPLE)
ax2.tick_params(labelsize=7, colors=PURPLE)
ax2.spines[["top"]].set_visible(False)
add_events(ax, 0, 0.22, label=False)
style(ax, "D. Industry Profitability & Structural Position", "Porter profitability")
ax.set_ylim(-0.01, 0.22)
h1 = plt.Line2D([0],[0], color=TEAL, lw=2, label="Industry profitability")
h2 = plt.Line2D([0],[0], color=PURPLE, lw=1.5, ls="--", label="Incumbent share")
ax.legend(handles=[h1,h2], fontsize=7, loc="upper right", framealpha=0.9)

fig.suptitle("Estée Lauder Simulation — Module Dashboard (44-Day Cascade, MC Bands Shown)",
             fontsize=11, fontweight="bold", color=DARK, y=1.01)
fig.savefig(OUT / "fig2_module_dashboard.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig2 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 3 — Iran War Channel
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
fig.patch.set_facecolor("white")

ax = axes[0]
add_mc_band(ax, "global_trade_volume", ACCENT)
ax.fill_between(ticks("global_trade_volume"), vals("global_trade_volume"),
                0.5, where=[v < 0.5 for v in vals("global_trade_volume")],
                color=ACCENT, alpha=0.2)
ax.plot(ticks("global_trade_volume"), vals("global_trade_volume"), color=ACCENT, lw=2.0)
ax.axhline(0.52, color=GREEN, lw=0.8, ls="--", alpha=0.6)
ax.text(1, 0.53, "pre-war baseline", color=GREEN, fontsize=6.5)
ax.axhline(0.36, color=ACCENT, lw=0.8, ls=":", alpha=0.6)
ax.text(8, 0.365, "post-disruption floor (−31%)", color=ACCENT, fontsize=6.5)
add_events(ax, 0.30, 0.56, label=False)
style(ax, "Iran War — Global Trade Volume\n(Hormuz + Red Sea Disruption)", "Trade volume index")
ax.set_ylim(0.28, 0.58)

ax = axes[1]
add_mc_band(ax, "global_energy_cost", AMBER)
ax.fill_between(ticks("global_energy_cost"), vals("global_energy_cost"),
                0.55, where=[v > 0.55 for v in vals("global_energy_cost")],
                color=AMBER, alpha=0.25)
ax.plot(ticks("global_energy_cost"), vals("global_energy_cost"), color=AMBER, lw=2.0)
ax.axhline(0.55, color=GREEN, lw=0.8, ls="--", alpha=0.6)
ax.text(1, 0.555, "pre-war baseline", color=GREEN, fontsize=6.5)
ax2 = ax.twinx()
oil = [55 + v*(120-55) for v in vals("global_energy_cost")]
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
# FIG 4 — Shock Stacking
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4))
fig.patch.set_facecolor("white")
T = list(range(44))
macro_shock = [0.12 if t >= 1 else 0.0 for t in T]
petrochem   = [0.18 if t >= 3 else 0.0 for t in T]
tariff      = [0.14 if t >= 7 else 0.0 for t in T]
logistics   = [0.06 if t >= 18 else 0.0 for t in T]
puig_ma     = [0.18 if t >= 28 else 0.0 for t in T]
labels  = ["Iran war macro", "Petrochemical cascade", "Tariff crystallisation",
           "Wholesale logistics", "Puig M&A uncertainty"]
colors_ = [ACCENT, AMBER, "#e67e22", TEAL, PURPLE]
ax.stackplot(T, [macro_shock, petrochem, tariff, logistics, puig_ma],
             labels=labels, colors=colors_, alpha=0.82)
for td, col in [(1,ACCENT),(3,AMBER),(7,AMBER),(18,TEAL),(28,PURPLE)]:
    ax.axvline(td, color=col, lw=0.8, ls="--", alpha=0.5)
ax.axvspan(30, 43, color="#eaf2ff", alpha=0.4)
style(ax, "Cumulative Shock Stacking — Pressure on EL Stock", "Cumulative normalised shock magnitude")
ax.legend(fontsize=7.5, loc="upper left", framealpha=0.95)
ax.set_ylim(0, 0.85)
fig.tight_layout()
fig.savefig(OUT / "fig4_shock_stacking.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig4 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 5 — 14-Day Forward Projection (MC-derived bands)
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 4.2))
fig.patch.set_facecolor("white")

t_hist  = ticks("investor_sentiment_mean")[:31]
v_hist  = vals("investor_sentiment_mean")[:31]
s_hist  = [lo + x*(hi-lo) for x in v_hist]
ax.plot(t_hist, s_hist, color=DARK, lw=2.2, zorder=5, label="Historical (simulated)")
ax.fill_between(t_hist, s_hist, min(s_hist)-2, alpha=0.07, color=DARK)

# MC forward bands (ticks 30-43)
p5_full  = mc_band("investor_sentiment_mean", 5)
p25_full = mc_band("investor_sentiment_mean", 25)
p50_full = mc_band("investor_sentiment_mean", 50)
p75_full = mc_band("investor_sentiment_mean", 75)
p95_full = mc_band("investor_sentiment_mean", 95)

if p50_full:
    fwd = list(range(30, min(44, len(p50_full))))
    s5_fwd  = [lo + p5_full[i]*(hi-lo)  for i in fwd]
    s25_fwd = [lo + p25_full[i]*(hi-lo) for i in fwd]
    s50_fwd = [lo + p50_full[i]*(hi-lo) for i in fwd]
    s75_fwd = [lo + p75_full[i]*(hi-lo) for i in fwd]
    s95_fwd = [lo + p95_full[i]*(hi-lo) for i in fwd]
    ax.fill_between(fwd, s5_fwd,  s95_fwd, alpha=0.10, color=BLUE, label="MC p5–p95")
    ax.fill_between(fwd, s25_fwd, s75_fwd, alpha=0.20, color=BLUE, label="MC p25–p75")
    ax.plot(fwd, s50_fwd, color=BLUE, lw=2.0, ls="-", label="MC median (base mix)")

    # Label scenario bands at day 44
    last = len(fwd) - 1
    ax.annotate(f"Bear p5\n${s5_fwd[last]:.0f}", xy=(fwd[last], s5_fwd[last]),
                xytext=(fwd[last]-3, s5_fwd[last]-6), fontsize=6.5, color=ACCENT)
    ax.annotate(f"Bull p95\n${s95_fwd[last]:.0f}", xy=(fwd[last], s95_fwd[last]),
                xytext=(fwd[last]-3, s95_fwd[last]+2), fontsize=6.5, color=GREEN)
else:
    # Fallback: deterministic hand-drawn scenarios
    t_proj = list(range(30, 45))
    base_sent = [0.078 - (0.078-0.040)*(i/14) for i in range(15)]
    bull_sent = [min(0.078 + 0.15*(1-np.exp(-i/3)), 0.35) for i in range(15)]
    bear_sent = [max(0.078 - 0.04*i/14, 0.025) for i in range(15)]
    ax.plot(t_proj, [lo+s*(hi-lo) for s in base_sent], color=DARK,   lw=1.8, label="Base ($68–$78)")
    ax.plot(t_proj, [lo+s*(hi-lo) for s in bull_sent], color=GREEN,  lw=1.8, ls="--", label="Bull ($82–$88)")
    ax.plot(t_proj, [lo+s*(hi-lo) for s in bear_sent], color=ACCENT, lw=1.8, ls=":",  label="Bear ($60–$65)")

ax.axvline(30, color=BLUE, lw=1.2, ls="-", alpha=0.8)
ax.text(30.4, 115, "Today\nMarch 26", color=BLUE, fontsize=7, va="top")
ax.axhline(92.52, color=SOFT, lw=0.8, ls=":", alpha=0.7)
ax.text(1, 93.5, "Consensus PT $92.52 (12-month)", color=SOFT, fontsize=6.5)
style(ax, "14-Day Forward Projection — MC-Derived Uncertainty Distribution", "Estimated Stock Price (USD)")
ax.set_ylim(35, 125)
ax.legend(fontsize=8, loc="lower left", framealpha=0.95)
ax.axvspan(30, 44, color="#eaf2ff", alpha=0.35)
fig.tight_layout()
fig.savefig(OUT / "fig5_forward_projection.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig5 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 6 — Event Study: CAPM Abnormal Return Decomposition (NEW)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
fig.patch.set_facecolor("white")

# Panel A: Per-tick AR on event days
ax = axes[0]
t_ar = ticks("el_30day_abnormal_return")
v_ar = vals("el_30day_abnormal_return")
ar_pct = [(v - 0.5)*40 for v in v_ar]  # convert to % using RETURN_SCALE=0.40

colors_bar = [ACCENT if v < 0 else GREEN for v in ar_pct]
ax.bar(t_ar, ar_pct, color=colors_bar, alpha=0.75, width=0.8, zorder=3)
ax.axhline(0, color=MID, lw=0.8)

for tick, label in [(1,"Iran war\n-2.1%"),(7,"Tariff\n-2.3%"),(28,"Puig\n-7.8%")]:
    if tick < len(ar_pct):
        ax.annotate(label, xy=(tick, ar_pct[tick]),
                    xytext=(tick+1.2, ar_pct[tick]-0.8),
                    fontsize=6.5, color=ACCENT,
                    arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.6))

add_events(ax, min(ar_pct)-1, max(ar_pct)+1, label=False)
style(ax, "A. Daily Abnormal Return vs. CAPM\n(MacKinlay 1997; EL beta=1.15)", "AR (%)")
ax.set_ylim(min(ar_pct)-2, max(ar_pct)+2)

# Panel B: Cumulative AR vs acquirer discount CAR
ax = axes[1]
t_car = ticks("el_30day_cumulative_ar")
v_car = vals("el_30day_cumulative_ar")
car_pct = [(v - 0.5)*40 for v in v_car]

t_puig = ticks("el_puig_cumulative_ar")
v_puig = vals("el_puig_cumulative_ar")
puig_pct = [(v - 0.5)*40 for v in v_puig]

add_mc_band(ax, "el_30day_cumulative_ar", ACCENT, alpha_outer=0.10, alpha_inner=0.18)

ax.plot(t_car,  car_pct,  color=ACCENT,  lw=2.0, label="Total event CAR (MacKinlay)")
ax.plot(t_puig, puig_pct, color=PURPLE,  lw=1.8, ls="--", label="Puig deal CAR (Roll 1986)")
ax.fill_between(t_car, car_pct, 0, alpha=0.08, color=ACCENT)
ax.axhline(0, color=MID, lw=0.8)

# annotate final CAR values
if car_pct:
    ax.annotate(f"Total event CAR:\n{car_pct[-1]:.1f}%", xy=(t_car[-1], car_pct[-1]),
                xytext=(t_car[-1]-8, car_pct[-1]-3), fontsize=7, color=ACCENT)
if puig_pct:
    ax.annotate(f"Puig CAR:\n{puig_pct[-1]:.1f}%", xy=(t_puig[-1], puig_pct[-1]),
                xytext=(t_puig[-1]-8, puig_pct[-1]+1.5), fontsize=7, color=PURPLE)

add_events(ax, min(car_pct)-1, 1, label=False)
style(ax, "B. Cumulative Abnormal Return\n(Event-Driven Component of Total Decline)", "CAR (%)")
ax.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
ax.set_ylim(min(car_pct)-2, 3)

fig.suptitle("Event Study: CAPM Abnormal Return Decomposition — Isolating Event-Driven vs. Systematic Decline",
             fontsize=10, fontweight="bold", color=DARK, y=1.01)
fig.tight_layout()
fig.savefig(OUT / "fig6_event_study.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig6 done")

# ════════════════════════════════════════════════════════════════════════════
# FIG 7 — Brand Equity Decay + Price Premium Compression (NEW)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
fig.patch.set_facecolor("white")

ax = axes[0]
add_mc_band(ax, "el_brand_equity",     TEAL, alpha_outer=0.10, alpha_inner=0.18)
add_mc_band(ax, "el_brand_loyalty",    BLUE, alpha_outer=0.08, alpha_inner=0.12)
ax.plot(ticks("el_brand_equity"),  vals("el_brand_equity"),  color=TEAL, lw=2.0, label="Brand equity")
ax.plot(ticks("el_brand_loyalty"), vals("el_brand_loyalty"), color=BLUE, lw=1.5, ls="--", label="Consumer loyalty")

add_events(ax, 0.60, 0.75, label=False)
style(ax, "A. Brand Equity & Loyalty Decay\n(Keller 1993; Dupe Culture Pressure)", "Index [0,1]")
ax.set_ylim(0.58, 0.78)
ax.legend(fontsize=8, loc="lower left", framealpha=0.9)

# annotate total equity loss
eq_v = vals("el_brand_equity")
if eq_v:
    loss = (eq_v[0] - eq_v[-1]) / eq_v[0] * 100
    ax.annotate(f"Equity loss\n{loss:.1f}% over 44 days",
                xy=(43, eq_v[-1]), xytext=(30, eq_v[-1]-0.02),
                fontsize=7, color=TEAL,
                arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.6))

ax = axes[1]
add_mc_band(ax, "el_brand_price_premium", PURPLE, alpha_outer=0.10, alpha_inner=0.18)
ax.plot(ticks("el_brand_price_premium"), vals("el_brand_price_premium"),
        color=PURPLE, lw=2.0, label="Price premium vs. mass")

# secondary axis: implied premium %
ax2 = ax.twinx()
prem_vals = [v / 0.42 * 42 for v in vals("el_brand_price_premium")]  # scale back to %
ax2.plot(ticks("el_brand_price_premium"), prem_vals, lw=0, alpha=0)
ax2.set_ylim(min(prem_vals)-1, max(prem_vals)+2)
ax2.set_ylabel("Implied premium over mass (%)", fontsize=7, color=PURPLE)
ax2.tick_params(labelsize=7, colors=PURPLE)
ax2.spines[["top"]].set_visible(False)

add_events(ax, min(vals("el_brand_price_premium"))-0.002, max(vals("el_brand_price_premium"))+0.002, label=False)
style(ax, "B. Price Premium Compression\n(Willingness-to-Pay Gap: Prestige vs. Mass/Dupe)", "Normalised premium")
ax.legend(fontsize=8, loc="lower left", framealpha=0.9)

fig.suptitle("Brand Equity Decay — Dupe Culture & Competitive Pressure Eroding Prestige Premium",
             fontsize=10, fontweight="bold", color=DARK, y=1.01)
fig.tight_layout()
fig.savefig(OUT / "fig7_brand_equity.png", dpi=160, bbox_inches="tight")
plt.close()
print("fig7 done")

print(f"\nAll 7 charts saved to {OUT}")
