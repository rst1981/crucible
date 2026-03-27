"""
api/routers/ensembles.py — Named ensemble CRUD

Ensembles are named lists of theories that can be saved, loaded, and applied
to any simulation. They are stored as JSON files in data/ensembles/.

GET    /api/ensembles                List all ensembles
POST   /api/ensembles                Create a new ensemble
GET    /api/ensembles/{id}           Get a single ensemble
DELETE /api/ensembles/{id}           Delete an ensemble
POST   /api/ensembles/{id}/fork      Fork an ensemble under a new name
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ensembles", tags=["ensembles"])

_ENSEMBLES_DIR = Path("data/ensembles")


def _ensure_dir() -> None:
    _ENSEMBLES_DIR.mkdir(parents=True, exist_ok=True)


def _ensemble_path(ensemble_id: str) -> Path:
    return _ENSEMBLES_DIR / f"{ensemble_id}.json"


def _load(ensemble_id: str) -> dict:
    path = _ensemble_path(ensemble_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Ensemble '{ensemble_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    _ensure_dir()
    path = _ensemble_path(data["ensemble_id"])
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _list_all() -> list[dict]:
    _ensure_dir()
    results = []
    for path in sorted(_ENSEMBLES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(_summary(data))
        except Exception:
            pass
    return results


def _summary(data: dict) -> dict:
    """Return a lightweight summary (no full theory metadata)."""
    return {
        "ensemble_id":   data["ensemble_id"],
        "name":          data["name"],
        "source":        data.get("source", "user"),
        "theory_ids":    [t["theory_id"] for t in data.get("theories", [])],
        "theory_count":  len(data.get("theories", [])),
        "created_at":    data.get("created_at"),
        "forked_from":   data.get("forked_from"),
    }


# ── Request models ─────────────────────────────────────────────────────────────

class TheoryRefIn(BaseModel):
    theory_id: str
    priority: int = 0
    parameters: dict[str, Any] = {}


class CreateEnsembleRequest(BaseModel):
    name: str
    theories: list[TheoryRefIn]
    source: str = "user"          # "user" | "system" | "recommended"


class ForkRequest(BaseModel):
    name: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_ensembles(source: str | None = None) -> dict:
    """List all saved ensembles. Optional ?source=user|system|recommended filter."""
    all_ensembles = _list_all()
    if source:
        all_ensembles = [e for e in all_ensembles if e.get("source") == source]
    return {"count": len(all_ensembles), "ensembles": all_ensembles}


@router.post("", status_code=201)
async def create_ensemble(body: CreateEnsembleRequest) -> dict:
    """
    Create and save a named ensemble.

    All theory_ids must be registered in the library.
    Returns the full ensemble record.
    """
    from core.theories import list_theories
    library = set(list_theories())
    unknown = [t.theory_id for t in body.theories if t.theory_id not in library]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown theory IDs: {unknown}. Available: {sorted(library)}",
        )

    ensemble_id = str(uuid.uuid4())
    data = {
        "ensemble_id": ensemble_id,
        "name":        body.name,
        "source":      body.source,
        "theories":    [
            {
                "theory_id":  t.theory_id,
                "priority":   t.priority,
                "parameters": t.parameters,
            }
            for t in body.theories
        ],
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "forked_from": None,
    }
    _save(data)
    logger.info("Created ensemble %s (%s)", ensemble_id, body.name)
    return data


@router.get("/{ensemble_id}")
async def get_ensemble(ensemble_id: str) -> dict:
    """Get the full record for a saved ensemble."""
    return _load(ensemble_id)


@router.delete("/{ensemble_id}", status_code=204)
async def delete_ensemble(ensemble_id: str) -> None:
    """Delete a saved ensemble."""
    path = _ensemble_path(ensemble_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Ensemble '{ensemble_id}' not found")
    path.unlink()
    logger.info("Deleted ensemble %s", ensemble_id)


@router.post("/{ensemble_id}/fork", status_code=201)
async def fork_ensemble(ensemble_id: str, body: ForkRequest) -> dict:
    """
    Fork an ensemble under a new name.

    Copies all theories and parameters. The forked ensemble has a new ID
    and records forked_from = original ensemble_id.
    """
    original = _load(ensemble_id)

    new_id = str(uuid.uuid4())
    forked = {
        **original,
        "ensemble_id": new_id,
        "name":        body.name,
        "source":      "user",
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "forked_from": ensemble_id,
    }
    _save(forked)
    logger.info("Forked ensemble %s → %s (%s)", ensemble_id, new_id, body.name)
    return forked
