"""
core/reporting.py — Simulation output extraction and markdown rendering utilities.

Used by /forge-findings skill and scenario post-run doc generation to pull structured
data from results.json and format it into assessment/findings markdown sections.

Usage:
    from core.reporting import SimResults, fmt_table, fmt_mc_bands

    r = SimResults.load("scenarios/estee-lauder/results.json")
    print(r.sentiment_table(ticks=[0, 7, 28, 30]))
    print(r.mc_summary("investor_sentiment_mean"))
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Data extraction ────────────────────────────────────────────────────────────

@dataclass
class SimResults:
    """
    Parsed view of a results.json file.

    Supports both flat format (legacy: {"series": {...}}) and nested format
    (v2: {"deterministic": {"series": {...}}, "monte_carlo": {"bands": {...}}}).
    """
    series: dict[str, list[dict]]      # {metric_name: [{tick, value}, ...]}
    final_env: dict[str, float]        # env snapshot at last tick
    snapshots: dict[int, dict]         # env snapshots at key ticks
    mc_bands: dict[str, dict]          # {metric: {p5, p25, p50, p75, p95, mean}}
    mc_scenario_counts: dict[str, int] # {base, bull, bear} run counts
    mc_n_runs: int

    @classmethod
    def load(cls, path: str | Path) -> "SimResults":
        with open(path) as f:
            raw = json.load(f)

        if "deterministic" in raw:
            det = raw["deterministic"]
            mc  = raw.get("monte_carlo", {})
        else:
            det = raw
            mc  = {}

        return cls(
            series=det.get("series", {}),
            final_env=det.get("final_env", {}),
            snapshots={int(k): v for k, v in det.get("snapshots", {}).items()},
            mc_bands=mc.get("bands", {}),
            mc_scenario_counts=mc.get("scenario_counts", {}),
            mc_n_runs=mc.get("n_runs", 0),
        )

    # ── Series access ──────────────────────────────────────────────────────────

    def ticks(self, metric: str) -> list[int]:
        return [r["tick"] for r in self.series.get(metric, [])]

    def values(self, metric: str) -> list[float]:
        return [r["value"] for r in self.series.get(metric, [])]

    def at(self, metric: str, tick: int) -> float | None:
        """Return value for a specific tick, or None if not found."""
        for r in self.series.get(metric, []):
            if r["tick"] == tick:
                return r["value"]
        return None

    def series_dict(self, metric: str) -> dict[int, float]:
        """Return {tick: value} dict for easy random access."""
        return {r["tick"]: r["value"] for r in self.series.get(metric, [])}

    # ── MC band access ─────────────────────────────────────────────────────────

    def mc_at(self, metric: str, pct: int, tick: int) -> float | None:
        band = self.mc_bands.get(metric, {}).get(f"p{pct}", [])
        return band[tick] if tick < len(band) else None

    def mc_final(self, metric: str) -> dict[str, float]:
        """Return {p5, p25, p50, p75, p95, mean} at the last tick."""
        bands = self.mc_bands.get(metric, {})
        last = max((len(v) for v in bands.values() if v), default=0) - 1
        if last < 0:
            return {}
        return {k: v[last] for k, v in bands.items() if v and last < len(v)}

    # ── Markdown formatting ────────────────────────────────────────────────────

    def metric_table(
        self,
        metrics: list[tuple[str, str]],  # [(metric_id, display_name), ...]
        ticks: list[int],
        col_label: str = "Day",
        transform: dict[str, Any] | None = None,
    ) -> str:
        """
        Render a markdown table with one column per metric, one row per tick.

        transform: optional dict of {metric_id: callable} for value display.
                   E.g. {"investor_sentiment_mean": lambda v: f"${40+v*81:.0f}"}
        """
        transform = transform or {}
        header = f"| {col_label} | " + " | ".join(name for _, name in metrics) + " |"
        sep    = "|" + "---|" * (len(metrics) + 1)
        rows   = []
        for tick in ticks:
            cells = []
            for metric_id, _ in metrics:
                val = self.at(metric_id, tick)
                if val is None:
                    cells.append("—")
                elif metric_id in transform:
                    cells.append(transform[metric_id](val))
                else:
                    cells.append(f"{val:.4f}")
            rows.append(f"| {tick} | " + " | ".join(cells) + " |")
        return "\n".join([header, sep] + rows)

    def mc_summary_table(self, metrics: list[tuple[str, str]]) -> str:
        """
        Render a markdown table of MC forward distributions (at last tick).
        Columns: metric | p5 | p25 | p50 | p75 | p95
        """
        lines = ["| Metric | p5 | p25 | p50 | p75 | p95 |", "|--------|----|----|----|----|-----|"]
        for metric_id, display_name in metrics:
            f = self.mc_final(metric_id)
            if not f:
                continue
            row = "| {name} | {p5:.3f} | {p25:.3f} | {p50:.3f} | {p75:.3f} | {p95:.3f} |".format(
                name=display_name,
                p5=f.get("p5", 0), p25=f.get("p25", 0), p50=f.get("p50", 0),
                p75=f.get("p75", 0), p95=f.get("p95", 0),
            )
            lines.append(row)
        return "\n".join(lines)


# ── Standalone formatting helpers ─────────────────────────────────────────────

def fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a generic markdown table."""
    header = "| " + " | ".join(headers) + " |"
    sep    = "|" + "---|" * len(headers)
    body   = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join([header, sep] + body)


def fmt_pct(normalized: float, scale: float = 0.40) -> str:
    """Convert normalized [0,1] return env value to display % string."""
    raw = (normalized - 0.5) * scale
    return f"{raw:+.1f}%"


def fmt_price(sentiment: float, lo: float = 40, hi: float = 121) -> str:
    """Convert sentiment [0,1] to stock price estimate string."""
    return f"${lo + sentiment * (hi - lo):.0f}"


def module_results_section(
    r: SimResults,
    module_name: str,
    display_name: str,
    metrics: list[tuple[str, str]],
    ticks: list[int],
    description: str = "",
    transform: dict | None = None,
) -> str:
    """
    Generate a standard '### Module: X' results section for the findings doc.
    """
    lines = [f"### {display_name}"]
    if description:
        lines.append(description)
        lines.append("")
    lines.append(r.metric_table(metrics, ticks, transform=transform))
    return "\n".join(lines)


# ── Document scaffold ──────────────────────────────────────────────────────────

def findings_header(slug: str, n_ticks: int, tick_unit: str, start_date: str, modules: list[str], n_mc: int = 0) -> str:
    mc_note = f" + {n_mc}-run Monte Carlo" if n_mc else ""
    mod_list = ", ".join(f"`{m}`" for m in modules)
    return f"""# {slug.replace('-', ' ').title()} — Simulation Results
**Date:** {start_date} | **Ticks:** {n_ticks} {tick_unit}s{mc_note}
**Modules:** {mod_list}

---"""


def assessment_header(slug: str, date: str, skills_used: list[str]) -> str:
    skills = " + ".join(f"`/{s}`" for s in skills_used)
    return f"""# {slug.replace('-', ' ').title()} — Assessment & Forward Projection
**Date:** {date} | **Skills:** {skills}

---"""
