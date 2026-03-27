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

async def _execute_run(run: SimulationRun, simspec_dict: dict) -> None:
    """Run a SimSpec in the background; write results back to the SimulationRun."""
    import asyncio
    from core.spec import SimSpec, TheoryRef
    from core.sim_runner import SimRunner

    run.status = "running"
    try:
        spec = SimSpec.model_validate(simspec_dict)
        runner = SimRunner(spec, rng_seed=42)
        await asyncio.get_event_loop().run_in_executor(None, runner.run)

        # Serialize results
        metric_series: dict[str, list[float]] = {}
        for record in runner.metric_history:
            metric_series.setdefault(record.metric_id, []).append(record.value)

        final_env = runner.get_current_env()

        run.results = {
            "theory_ids":     run.theory_ids,
            "ensemble_type":  run.ensemble_type,
            "ticks":          len(set(r.tick for r in runner.metric_history)),
            "metric_series":  metric_series,
            "metric_names":   {
                r.metric_id: r.name
                for r in runner.metric_history
            },
            "final_env":      final_env,
            "snapshot_count": len(runner.snapshots),
        }
        run.status = "complete"
        run.completed_at = time.time()
        logger.info("Simulation %s (%s) complete", run.sim_id, run.ensemble_type)

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
