"""
api/routers/simulations.py — Simulation launch, polling, and comparison

Routes:
    POST /simulations                   Launch recommended + custom ensembles for a session
    GET  /simulations/{sim_id}          Poll a single run (status + results when done)
    GET  /simulations/compare/{a}/{b}   Side-by-side comparison of two runs
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["simulations"])


# ── SimulationRun ──────────────────────────────────────────────────────────────

@dataclass
class SimulationRun:
    sim_id:         str
    session_id:     str
    ensemble_type:  str          # "recommended" | "custom"
    theory_ids:     list[str]    # ordered list of theory_id values used
    status:         str          # "pending" | "running" | "complete" | "error"
    started_at:     float        = field(default_factory=time.time)
    completed_at:   float | None = None
    results:        dict | None  = None   # serialized SimRunner output
    error:          str | None   = None

    def to_dict(self, include_results: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "sim_id":        self.sim_id,
            "session_id":    self.session_id,
            "ensemble_type": self.ensemble_type,
            "theory_ids":    self.theory_ids,
            "status":        self.status,
            "started_at":    self.started_at,
            "completed_at":  self.completed_at,
            "error":         self.error,
        }
        if include_results:
            d["results"] = self.results
        return d


# ── In-memory stores ──────────────────────────────────────────────────────────

_runs: dict[str, SimulationRun] = {}


def _get_run(sim_id: str) -> SimulationRun:
    run = _runs.get(sim_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Simulation '{sim_id}' not found")
    return run


# ── Request models ────────────────────────────────────────────────────────────

class LaunchRequest(BaseModel):
    session_id: str
    rng_seed:   int = 42


# ── Background runner ─────────────────────────────────────────────────────────

def _run_simulation_sync(simspec_dict: dict, theory_ids: list, ensemble_type: str) -> dict:
    """
    Blocking simulation work — deterministic pass + 300-run Monte Carlo.
    Intended to be called via run_in_executor so it doesn't block the event loop.
    """
    import random as _random
    from core.spec import SimSpec
    from core.sim_runner import SimRunner
    from forge.scoping_agent import _ensure_metrics_consistent

    # ── Deterministic pass ────────────────────────────────────────────────────
    spec = SimSpec.model_validate(simspec_dict)
    _ensure_metrics_consistent(spec)
    runner = SimRunner(spec, rng_seed=42)
    runner.setup()
    runner.run()

    metric_series: dict[str, list[float]] = {}
    metric_names: dict[str, str] = {}
    for record in runner.metric_history:
        metric_series.setdefault(record.metric_id, []).append(record.value)
        metric_names[record.metric_id] = record.name

    final_env = runner.get_current_env()
    n_ticks = runner.ticks_completed
    metric_ids = list(metric_series.keys())

    # Serialize snapshot env states (every snapshot tick)
    env_snapshots: list[dict] = []
    for snap in runner.snapshots:
        env_snapshots.append({"tick": snap.tick, "label": snap.label, "env": dict(snap.env)})

    # Serialize theory contributions
    theory_contributions = runner.theory_contribution_history  # list of {tick, theory_id, total_delta}

    # ── Monte Carlo (300 runs) ────────────────────────────────────────────────
    # IMPORTANT: use spec.model_dump() (post-_ensure_metrics_consistent) as the base
    # for all MC runs so metric_ids are identical to the deterministic run.
    # Re-using simspec_dict would call _ensure_metrics_consistent again, generating
    # new UUID metric_ids that don't match metric_series keys → empty bands.
    spec_with_metrics = spec.model_dump()

    N_MC = 300
    scenario_weights = {"base": 0.60, "bull": 0.20, "bear": 0.20}
    _rng = _random.Random(42)

    all_mc: dict[str, list[list[float]]] = {mid: [] for mid in metric_ids}
    mc_run_finals: list[dict[str, float]] = []  # lightweight: one dict per MC run

    base_env = dict(spec.initial_environment)

    for mc_i in range(N_MC):
        scenario = _rng.choices(
            list(scenario_weights.keys()),
            weights=list(scenario_weights.values()),
        )[0]

        # Perturb initial environment values (clamp to [0, 1])
        perturbed: dict[str, float] = {}
        for k, v in base_env.items():
            if scenario == "bull":
                delta = _rng.gauss(0.05, 0.02)
            elif scenario == "bear":
                delta = _rng.gauss(-0.05, 0.02)
            else:
                delta = _rng.gauss(0.0, 0.015)
            perturbed[k] = max(0.0, min(1.0, v + delta))

        # Use spec_with_metrics (consistent metric_ids) — only swap initial_environment
        mc_spec = SimSpec.model_validate({**spec_with_metrics, "initial_environment": perturbed})
        mc_runner = SimRunner(mc_spec, rng_seed=mc_i)
        mc_runner.setup()
        mc_runner.run()

        run_series: dict[str, list[float]] = {mid: [] for mid in metric_ids}
        for rec in mc_runner.metric_history:
            if rec.metric_id in run_series:
                run_series[rec.metric_id].append(rec.value)

        for mid in metric_ids:
            all_mc[mid].append(run_series[mid])

        # Record final-tick value per metric for convergence plot
        mc_run_finals.append({
            mid: (run_series[mid][-1] if run_series[mid] else 0.0)
            for mid in metric_ids
        })

    # Compute percentile bands per metric
    bands: dict[str, dict[str, list[float]]] = {}
    for mid in metric_ids:
        runs = all_mc[mid]
        if not runs:
            continue
        # Pad any short runs to n_ticks
        padded = [
            r + [r[-1]] * max(0, n_ticks - len(r)) if r else [0.0] * n_ticks
            for r in runs
        ]
        tick_data = list(zip(*padded))
        if not tick_data:
            continue
        bands[mid] = {
            "p5":  [float(sorted(t)[max(0, int(0.05 * len(t)))]) for t in tick_data],
            "p25": [float(sorted(t)[max(0, int(0.25 * len(t)))]) for t in tick_data],
            "p50": [float(sorted(t)[max(0, int(0.50 * len(t)))]) for t in tick_data],
            "p75": [float(sorted(t)[max(0, int(0.75 * len(t)))]) for t in tick_data],
            "p95": [float(sorted(t)[max(0, int(0.95 * len(t)))]) for t in tick_data],
        }

    return {
        "theory_ids":    theory_ids,
        "ensemble_type": ensemble_type,
        "ticks":         n_ticks,
        "metric_series": metric_series,
        "metric_names":  metric_names,
        "final_env":     final_env,
        "snapshot_count": len(runner.snapshots),
        "monte_carlo": {
            "n_runs":           N_MC,
            "scenario_weights": scenario_weights,
            "bands":            bands,
        },
        "env_snapshots":         env_snapshots,
        "theory_contributions":  theory_contributions,
        "mc_run_finals":         mc_run_finals,
    }


async def _execute_run(run: SimulationRun, simspec_dict: dict) -> None:
    """Run a SimSpec in the background; write results back to the SimulationRun."""
    run.status = "running"
    try:
        run.results = await asyncio.get_event_loop().run_in_executor(
            None,
            _run_simulation_sync,
            simspec_dict,
            run.theory_ids,
            run.ensemble_type,
        )
        run.status = "complete"
        run.completed_at = time.time()
        logger.info("Simulation %s (%s) complete — MC bands computed", run.sim_id, run.ensemble_type)

    except Exception as exc:
        run.status = "error"
        run.error = str(exc)
        run.completed_at = time.time()
        logger.error("Simulation %s failed: %s", run.sim_id, exc)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def launch_simulations(body: LaunchRequest) -> dict:
    """
    Launch simulation runs for a session.

    Always runs the recommended ensemble. If the consultant set a custom
    ensemble (PUT /forge/intake/{id}/theories/custom), that runs too.

    Returns immediately with run IDs. Poll GET /simulations/{sim_id} for results.
    """
    # Import here to avoid circular import with forge router
    from api.routers.forge import _sessions

    session = _sessions.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{body.session_id}' not found")
    if session.simspec is None:
        raise HTTPException(status_code=409, detail="Session has no SimSpec yet")
    if session.state.value not in ("ensemble_review", "complete"):
        raise HTTPException(
            status_code=409,
            detail=f"Session is in state '{session.state.value}' — must be ensemble_review or complete",
        )

    launched: list[dict] = []

    def _make_spec_for(theories: list[dict]) -> dict:
        """Build a SimSpec dict patched with the given theory list."""
        from core.spec import TheoryRef
        spec_dict = session.simspec.model_dump()
        spec_dict["theories"] = [
            {
                "theory_id": t["theory_id"],
                "priority":  t.get("suggested_priority", t.get("priority", 0)),
                "parameters": t.get("parameters", {}),
            }
            for t in theories
        ]
        return spec_dict

    # Always launch recommended
    if session.recommended_theories:
        rec_run = SimulationRun(
            sim_id=str(uuid.uuid4()),
            session_id=body.session_id,
            ensemble_type="recommended",
            theory_ids=[t["theory_id"] for t in session.recommended_theories],
            status="pending",
        )
        _runs[rec_run.sim_id] = rec_run
        asyncio.create_task(_execute_run(rec_run, _make_spec_for(session.recommended_theories)))
        launched.append({"sim_id": rec_run.sim_id, "ensemble_type": "recommended"})

    # Launch custom if the consultant set one
    if session.custom_theories is not None:
        cust_run = SimulationRun(
            sim_id=str(uuid.uuid4()),
            session_id=body.session_id,
            ensemble_type="custom",
            theory_ids=[t["theory_id"] for t in session.custom_theories],
            status="pending",
        )
        _runs[cust_run.sim_id] = cust_run
        asyncio.create_task(_execute_run(cust_run, _make_spec_for(session.custom_theories)))
        launched.append({"sim_id": cust_run.sim_id, "ensemble_type": "custom"})

    if not launched:
        raise HTTPException(status_code=409, detail="No theories configured — nothing to run")

    return {
        "launched": launched,
        "message": (
            f"Launched {len(launched)} simulation run(s). "
            "Poll GET /simulations/{sim_id} for results."
        ),
    }


@router.get("/compare/{sim_id_a}/{sim_id_b}")
async def compare_simulations(sim_id_a: str, sim_id_b: str) -> dict:
    """
    Side-by-side comparison of two simulation runs.

    Returns:
        - ensemble diff: theories only in A, only in B, shared
        - per-metric: final value in A vs B, delta, % change
        - final env: key differences (absolute delta > 0.05)
    """
    run_a = _get_run(sim_id_a)
    run_b = _get_run(sim_id_b)

    for run in (run_a, run_b):
        if run.status != "complete":
            raise HTTPException(
                status_code=409,
                detail=f"Simulation '{run.sim_id}' is not complete (status: {run.status})",
            )

    set_a = set(run_a.theory_ids)
    set_b = set(run_b.theory_ids)

    ensemble_diff = {
        "only_in_a":   sorted(set_a - set_b),
        "only_in_b":   sorted(set_b - set_a),
        "shared":       sorted(set_a & set_b),
        "a_ensemble":  run_a.theory_ids,
        "b_ensemble":  run_b.theory_ids,
    }

    # Metric comparison — final value in each series
    res_a = run_a.results or {}
    res_b = run_b.results or {}
    series_a = res_a.get("metric_series", {})
    series_b = res_b.get("metric_series", {})
    names_a  = res_a.get("metric_names", {})
    names_b  = res_b.get("metric_names", {})
    all_metrics = set(series_a) | set(series_b)

    metric_comparison: list[dict] = []
    for mid in sorted(all_metrics):
        vals_a = series_a.get(mid, [])
        vals_b = series_b.get(mid, [])
        final_a = vals_a[-1] if vals_a else None
        final_b = vals_b[-1] if vals_b else None
        delta = None
        pct   = None
        if final_a is not None and final_b is not None:
            delta = round(final_b - final_a, 4)
            pct   = round((final_b - final_a) / max(abs(final_a), 1e-6) * 100, 2)
        metric_comparison.append({
            "metric_id":   mid,
            "name":        names_a.get(mid) or names_b.get(mid, mid),
            "a_final":     round(final_a, 4) if final_a is not None else None,
            "b_final":     round(final_b, 4) if final_b is not None else None,
            "delta_b_minus_a": delta,
            "pct_change":      pct,
        })

    # Final env diff — keys where |delta| > 0.05
    env_a = res_a.get("final_env", {})
    env_b = res_b.get("final_env", {})
    all_keys = set(env_a) | set(env_b)
    env_diff: list[dict] = []
    for k in sorted(all_keys):
        va = env_a.get(k)
        vb = env_b.get(k)
        if va is None or vb is None:
            continue
        d = vb - va
        if abs(d) > 0.05:
            env_diff.append({"key": k, "a": round(va, 4), "b": round(vb, 4), "delta": round(d, 4)})

    return {
        "sim_id_a":          sim_id_a,
        "sim_id_b":          sim_id_b,
        "ensemble_type_a":   run_a.ensemble_type,
        "ensemble_type_b":   run_b.ensemble_type,
        "ensemble_diff":     ensemble_diff,
        "metric_comparison": metric_comparison,
        "env_diff":          env_diff,
        "summary": {
            "theories_only_in_a": len(ensemble_diff["only_in_a"]),
            "theories_only_in_b": len(ensemble_diff["only_in_b"]),
            "shared_theories":    len(ensemble_diff["shared"]),
            "metrics_with_delta_gt_5pct": sum(
                1 for m in metric_comparison
                if m["pct_change"] is not None and abs(m["pct_change"]) > 5
            ),
            "env_keys_diverged":  len(env_diff),
        },
    }


@router.get("/{sim_id}")
async def get_simulation(sim_id: str, include_results: bool = True) -> dict:
    """Poll a simulation run. Returns status and results when complete."""
    run = _get_run(sim_id)
    return run.to_dict(include_results=include_results)


@router.get("")
async def list_simulations(session_id: str | None = None) -> dict:
    """List all simulation runs, optionally filtered by session."""
    runs = list(_runs.values())
    if session_id:
        runs = [r for r in runs if r.session_id == session_id]
    return {
        "count": len(runs),
        "runs": [r.to_dict(include_results=False) for r in runs],
    }
