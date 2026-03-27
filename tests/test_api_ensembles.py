"""
Tests for api/routers/ensembles.py — /api/ensembles endpoints.

Uses FastAPI TestClient. Each test class isolates its ensemble files
via a tmp_path-patched ENSEMBLES_DIR.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ── Fixture: redirect ensemble storage to a temp dir ──────────────────────────

@pytest.fixture(autouse=True)
def _tmp_ensembles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect all ensemble file I/O to a fresh temp directory."""
    ensembles_dir = tmp_path / "ensembles"
    ensembles_dir.mkdir()
    monkeypatch.setattr("api.routers.ensembles._ENSEMBLES_DIR", ensembles_dir)
    yield ensembles_dir


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_ensemble(name: str = "Test Ensemble", theories: list[dict] | None = None) -> dict:
    if theories is None:
        theories = [{"theory_id": "richardson_arms_race", "priority": 0, "parameters": {}}]
    resp = client.post("/api/ensembles", json={"name": name, "theories": theories})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── GET /api/ensembles ─────────────────────────────────────────────────────────

class TestListEnsembles:
    def test_empty_list(self):
        resp = client.get("/api/ensembles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["ensembles"] == []

    def test_lists_created_ensembles(self):
        _create_ensemble("Ensemble A")
        _create_ensemble("Ensemble B")
        data = client.get("/api/ensembles").json()
        assert data["count"] == 2

    def test_source_filter(self):
        _create_ensemble("User ensemble")
        client.post("/api/ensembles", json={
            "name": "System ensemble",
            "theories": [{"theory_id": "richardson_arms_race"}],
            "source": "system",
        })
        user_data = client.get("/api/ensembles?source=user").json()
        system_data = client.get("/api/ensembles?source=system").json()
        assert user_data["count"] == 1
        assert system_data["count"] == 1

    def test_summary_shape(self):
        _create_ensemble()
        data = client.get("/api/ensembles").json()
        entry = data["ensembles"][0]
        for key in ("ensemble_id", "name", "source", "theory_ids", "theory_count", "created_at"):
            assert key in entry


# ── POST /api/ensembles ────────────────────────────────────────────────────────

class TestCreateEnsemble:
    def test_creates_and_returns_201(self):
        resp = client.post("/api/ensembles", json={
            "name": "My Ensemble",
            "theories": [{"theory_id": "richardson_arms_race"}],
        })
        assert resp.status_code == 201

    def test_returned_data_shape(self):
        data = _create_ensemble()
        for key in ("ensemble_id", "name", "source", "theories", "created_at", "forked_from"):
            assert key in data

    def test_theories_stored(self):
        data = _create_ensemble(theories=[
            {"theory_id": "richardson_arms_race", "priority": 0},
            {"theory_id": "fearon_bargaining", "priority": 1},
        ])
        assert len(data["theories"]) == 2
        ids = [t["theory_id"] for t in data["theories"]]
        assert "richardson_arms_race" in ids
        assert "fearon_bargaining" in ids

    def test_default_source_is_user(self):
        data = _create_ensemble()
        assert data["source"] == "user"

    def test_custom_source(self):
        resp = client.post("/api/ensembles", json={
            "name": "Sys",
            "theories": [{"theory_id": "richardson_arms_race"}],
            "source": "system",
        })
        assert resp.json()["source"] == "system"

    def test_unknown_theory_id_returns_422(self):
        resp = client.post("/api/ensembles", json={
            "name": "Bad",
            "theories": [{"theory_id": "not_a_real_theory_xyz"}],
        })
        assert resp.status_code == 422

    def test_ensemble_id_is_uuid(self):
        import uuid
        data = _create_ensemble()
        uuid.UUID(data["ensemble_id"])  # raises if not valid UUID

    def test_forked_from_is_null_on_create(self):
        data = _create_ensemble()
        assert data["forked_from"] is None


# ── GET /api/ensembles/{id} ────────────────────────────────────────────────────

class TestGetEnsemble:
    def test_get_existing(self):
        created = _create_ensemble("My Ensemble")
        resp = client.get(f"/api/ensembles/{created['ensemble_id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Ensemble"

    def test_get_missing_returns_404(self):
        resp = client.get("/api/ensembles/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_full_record_returned(self):
        created = _create_ensemble()
        data = client.get(f"/api/ensembles/{created['ensemble_id']}").json()
        assert "theories" in data
        assert isinstance(data["theories"], list)


# ── DELETE /api/ensembles/{id} ────────────────────────────────────────────────

class TestDeleteEnsemble:
    def test_delete_returns_204(self):
        created = _create_ensemble()
        resp = client.delete(f"/api/ensembles/{created['ensemble_id']}")
        assert resp.status_code == 204

    def test_deleted_ensemble_not_found(self):
        created = _create_ensemble()
        eid = created["ensemble_id"]
        client.delete(f"/api/ensembles/{eid}")
        resp = client.get(f"/api/ensembles/{eid}")
        assert resp.status_code == 404

    def test_delete_missing_returns_404(self):
        resp = client.delete("/api/ensembles/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_delete_removes_from_list(self):
        a = _create_ensemble("A")
        _create_ensemble("B")
        client.delete(f"/api/ensembles/{a['ensemble_id']}")
        data = client.get("/api/ensembles").json()
        assert data["count"] == 1
        assert data["ensembles"][0]["name"] == "B"


# ── POST /api/ensembles/{id}/fork ──────────────────────────────────────────────

class TestForkEnsemble:
    def test_fork_returns_201(self):
        original = _create_ensemble("Original")
        resp = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        )
        assert resp.status_code == 201

    def test_fork_has_new_id(self):
        original = _create_ensemble("Original")
        forked = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        ).json()
        assert forked["ensemble_id"] != original["ensemble_id"]

    def test_fork_records_forked_from(self):
        original = _create_ensemble("Original")
        forked = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        ).json()
        assert forked["forked_from"] == original["ensemble_id"]

    def test_fork_copies_theories(self):
        original = _create_ensemble(theories=[
            {"theory_id": "richardson_arms_race"},
            {"theory_id": "fearon_bargaining"},
        ])
        forked = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        ).json()
        orig_ids = {t["theory_id"] for t in original["theories"]}
        fork_ids = {t["theory_id"] for t in forked["theories"]}
        assert orig_ids == fork_ids

    def test_fork_uses_new_name(self):
        original = _create_ensemble("Original")
        forked = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "My Fork"},
        ).json()
        assert forked["name"] == "My Fork"

    def test_fork_source_is_user(self):
        original = _create_ensemble()
        forked = client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        ).json()
        assert forked["source"] == "user"

    def test_fork_missing_ensemble_returns_404(self):
        resp = client.post(
            "/api/ensembles/00000000-0000-0000-0000-000000000000/fork",
            json={"name": "Forked"},
        )
        assert resp.status_code == 404

    def test_both_original_and_fork_in_list(self):
        original = _create_ensemble("Original")
        client.post(
            f"/api/ensembles/{original['ensemble_id']}/fork",
            json={"name": "Forked"},
        )
        data = client.get("/api/ensembles").json()
        assert data["count"] == 2
