"""
scenarios/walla-walla/run_simulation.py

Walla Walla Premium Label Survival — Smoke Taint & Water Curtailment Shock (Sim 1)
Run: python scenarios/walla-walla/run_simulation.py
"""
from __future__ import annotations

import copy
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from core.spec import (
    ActorSpec, OutcomeMetricSpec, SimSpec, TheoryRef, TimeframeSpec, UncertaintySpec,
)
from core.sim_runner import SimRunner
from params import (
    INITIAL_ENV, METRICS, MC_RUNS, MC_SCENARIOS, SHOCKS, THEORIES, TICKS, TICK_UNIT, START_DATE,
)

OUT_DIR = pathlib.Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_actors() -> list[ActorSpec]:
    specs = [
        ("label_owner",       "Label Owner / Winemaker"),
        ("vineyard_ops",      "Vineyard Operations"),
        ("wine_club_channel", "Wine Club & DTC Channel (60%+ revenue)"),
        ("leonetti_proxy",    "Leonetti Cellar (comparable label)"),
        ("lecole_proxy",      "L'Ecole No. 41 (comparable label)"),
        ("k_vintners_proxy",  "K Vintners (comparable label)"),
        ("water_rights_body", "WA Dept of Ecology / Water Rights"),
        ("wildfire_system",   "Pacific NW Wildfire System"),
        ("bulk_wine_market",  "Bulk / Declassification Market"),
        ("debt_servicer",     "Lender / Debt Service"),
        ("climate_system",    "Regional Climate (GDD Trajectory)"),
    ]
    return [ActorSpec(actor_id=aid, name=name, agent_class="core.agents.base.DefaultBDIAgent") for aid, name in specs]


def _build_theories(params_override: dict | None = None) -> list[TheoryRef]:
    return [TheoryRef(theory_id=tid, priority=int(p * 10)) for tid, p in THEORIES]


def _build_metrics() -> list[OutcomeMetricSpec]:
    return [OutcomeMetricSpec(env_key=m, name=m.replace("_", " ").title()) for m in METRICS]


def build_spec(params_override: dict | None = None) -> SimSpec:
    env = copy.deepcopy(INITIAL_ENV)
    if params_override:
        env.update(params_override)
    return SimSpec(
        name="Walla Walla Premium Label Survival — Smoke Taint & Water Curtailment Shock (Sim 1)",
        description=(
            "Revenue continuity simulation for a lean-operation premium label owner "
            "(40 acres, $1.5M revenue, <6 mo cash reserves, $280K debt service). "
            "Primary failure modes: (1) smoke-taint vintage wipe forcing bulk "
            "declassification at 12 cents on the dollar; (2) junior water rights "
            "curtailment destroying yield. 10-year horizon with 300-run Monte Carlo. "
            "Theories: smoke_taint_crop_disruption, grapevine_gdd_phenology, "
            "hotelling_cpr, real_options_agri_adapt, bordeaux_wine_quality."
        ),
        domain="ecology",
        actors=_build_actors(),
        theories=_build_theories(params_override),
        timeframe=TimeframeSpec(
            total_ticks=TICKS,
            tick_unit=TICK_UNIT,
            start_date=START_DATE,
        ),
        uncertainty=UncertaintySpec(
            observation_noise_sigma=0.02,
            shock_probability=0.0,
            shock_magnitude=0.0,
            scheduled_shocks={k: v for k, v in SHOCKS.items() if k < TICKS},
        ),
        metrics=_build_metrics(),
        initial_environment=env,
    )


def run_deterministic() -> dict:
    spec = build_spec()
    runner = SimRunner(spec, rng_seed=42)
    runner.setup()
    runner.run()

    series: dict[str, list[dict]] = {}
    for rec in runner.metric_history:
        series.setdefault(rec.env_key, []).append({"tick": rec.tick, "value": rec.value})

    return {"series": series, "final_env": dict(runner.env)}


def _perturb(scenario: str) -> dict:
    if scenario == "bull":
        return {
            "hotelling_cpr__stock": 0.82,
            "cash_flow_health": 0.72,
            "survival_probability": 0.90,
        }
    if scenario == "bear":
        return {
            "hotelling_cpr__stock": 0.60,
            "cash_flow_health": 0.52,
            "debt_service_stress": 0.42,
            "survival_probability": 0.76,
        }
    return {k: v + random.gauss(0, 0.015) for k, v in INITIAL_ENV.items()}


def run_monte_carlo() -> dict:
    scenario_keys = list(MC_SCENARIOS.keys())
    scenario_weights = list(MC_SCENARIOS.values())
    all_runs: dict[str, list[list[float]]] = {m: [] for m in METRICS}

    for i in range(MC_RUNS):
        scenario = random.choices(scenario_keys, weights=scenario_weights, k=1)[0]
        spec = build_spec(params_override=_perturb(scenario))
        runner = SimRunner(spec, rng_seed=i)
        runner.setup()
        runner.run()

        run_series: dict[str, list[float]] = {m: [0.0] * TICKS for m in METRICS}
        for rec in runner.metric_history:
            if rec.env_key in run_series and rec.tick < TICKS:
                run_series[rec.env_key][rec.tick] = rec.value
        for m in METRICS:
            all_runs[m].append(run_series[m])

    bands: dict[str, dict[str, list[float]]] = {}
    for m in METRICS:
        tick_data = list(zip(*all_runs[m]))
        bands[m] = {
            "p5":  [float(sorted(t)[int(0.05 * len(t))]) for t in tick_data],
            "p25": [float(sorted(t)[int(0.25 * len(t))]) for t in tick_data],
            "p50": [float(sorted(t)[int(0.50 * len(t))]) for t in tick_data],
            "p75": [float(sorted(t)[int(0.75 * len(t))]) for t in tick_data],
            "p95": [float(sorted(t)[int(0.95 * len(t))]) for t in tick_data],
        }
    return {"n_runs": MC_RUNS, "scenario_weights": MC_SCENARIOS, "bands": bands}


if __name__ == "__main__":
    print("Running deterministic simulation (120 ticks = 10 years)...")
    det = run_deterministic()
    fe = det["final_env"]
    print(f"  cash_flow_health:              {fe.get('cash_flow_health', 0):.3f}")
    print(f"  survival_probability:          {fe.get('survival_probability', 0):.3f}")
    print(f"  debt_service_stress:           {fe.get('debt_service_stress', 0):.3f}")
    print(f"  replant_signal:                {fe.get('real_options_agri_adapt__replant_signal', 0):.3f}")
    print(f"  smoke_taint_active (final):    {fe.get('smoke_taint_crop_disruption__taint_active', 0):.3f}")
    print(f"  water_stock (final):           {fe.get('hotelling_cpr__stock', 0):.3f}")

    print(f"\nRunning Monte Carlo ({MC_RUNS} runs)...")
    mc = run_monte_carlo()
    for metric in ["survival_probability", "cash_flow_health"]:
        b = mc["bands"][metric]
        print(f"  {metric} @ tick 120 — p5: {b['p5'][-1]:.3f}  p50: {b['p50'][-1]:.3f}  p95: {b['p95'][-1]:.3f}")

    results = {"deterministic": det, "monte_carlo": mc}
    out_path = OUT_DIR / "results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults written to {out_path}")
