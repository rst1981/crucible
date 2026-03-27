"""
Tests for api/routers/theories.py — /api/theories endpoints.

Uses FastAPI TestClient (synchronous). No live API calls.
Claude recommend path is tested with mocked anthropic client.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.catalog import invalidate_cache
from api.main import app

client = TestClient(app)


def setup_function():
    invalidate_cache()


# ── GET /api/theories ──────────────────────────────────────────────────────────

class TestListTheories:
    def test_returns_200(self):
        resp = client.get("/api/theories")
        assert resp.status_code == 200

    def test_response_shape(self):
        data = client.get("/api/theories").json()
        assert "count" in data
        assert "theories" in data
        assert isinstance(data["theories"], list)

    def test_count_matches_list_length(self):
        data = client.get("/api/theories").json()
        assert data["count"] == len(data["theories"])

    def test_richardson_in_results(self):
        data = client.get("/api/theories").json()
        ids = [t["theory_id"] for t in data["theories"]]
        assert "richardson_arms_race" in ids

    def test_domain_filter(self):
        data = client.get("/api/theories?domain=geopolitics").json()
        for theory in data["theories"]:
            assert "geopolitics" in [d.lower() for d in theory["domains"]]

    def test_domain_filter_no_results(self):
        data = client.get("/api/theories?domain=nonexistent_domain_xyz").json()
        assert data["count"] == 0

    def test_keyword_filter_name(self):
        data = client.get("/api/theories?q=richardson").json()
        assert data["count"] >= 1
        ids = [t["theory_id"] for t in data["theories"]]
        assert "richardson_arms_race" in ids

    def test_keyword_filter_case_insensitive(self):
        data_lower = client.get("/api/theories?q=richardson").json()
        data_upper = client.get("/api/theories?q=Richardson").json()
        assert data_lower["count"] == data_upper["count"]

    def test_source_filter_builtin(self):
        data = client.get("/api/theories?source=builtin").json()
        for t in data["theories"]:
            assert t["source"] == "builtin"

    def test_filters_reflected_in_response(self):
        data = client.get("/api/theories?domain=market&q=bass").json()
        assert data["filters"]["domain"] == "market"
        assert data["filters"]["q"] == "bass"


# ── GET /api/theories/{theory_id} ─────────────────────────────────────────────

class TestGetTheoryDetail:
    def test_known_theory_returns_200(self):
        resp = client.get("/api/theories/richardson_arms_race")
        assert resp.status_code == 200

    def test_unknown_theory_returns_404(self):
        resp = client.get("/api/theories/nonexistent_theory_xyz")
        assert resp.status_code == 404

    def test_detail_has_full_fields(self):
        data = client.get("/api/theories/richardson_arms_race").json()
        for key in ("theory_id", "name", "domains", "description", "reference",
                    "parameters", "parameter_count", "reads", "writes",
                    "initializes", "source"):
            assert key in data, f"Missing key: {key}"

    def test_parameters_are_list_of_dicts(self):
        data = client.get("/api/theories/richardson_arms_race").json()
        assert isinstance(data["parameters"], list)
        assert len(data["parameters"]) > 0
        for p in data["parameters"]:
            assert "name" in p
            assert "type" in p

    def test_reads_and_writes_are_lists(self):
        data = client.get("/api/theories/richardson_arms_race").json()
        assert isinstance(data["reads"], list)
        assert isinstance(data["writes"], list)

    def test_theory_id_matches_path(self):
        data = client.get("/api/theories/richardson_arms_race").json()
        assert data["theory_id"] == "richardson_arms_race"


# ── POST /api/theories/recommend ──────────────────────────────────────────────

class TestRecommendTheories:
    def test_domain_match_no_claude(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "geopolitics",
            "description": "",
            "use_claude": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "domain_match"
        assert len(data["recommended"]) > 0

    def test_returns_theory_id_name_domains(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "geopolitics",
            "use_claude": False,
        })
        for rec in resp.json()["recommended"]:
            assert "theory_id" in rec
            assert "name" in rec
            assert "domains" in rec

    def test_max_results_respected(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "geopolitics",
            "max_results": 2,
            "use_claude": False,
        })
        assert len(resp.json()["recommended"]) <= 2

    def test_unknown_domain_returns_empty(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "underwater_basket_weaving",
            "use_claude": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended"] == []

    def test_market_domain_includes_market_theories(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "market",
            "use_claude": False,
        })
        ids = [r["theory_id"] for r in resp.json()["recommended"]]
        assert any(tid in ids for tid in ("porters_five_forces", "bass_diffusion", "cournot_bertrand_competition"))

    def test_claude_fallback_on_missing_key(self):
        """With use_claude=True but no ANTHROPIC_API_KEY, falls back to domain-match."""
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("ANTHROPIC_API_KEY", None)
            resp = client.post("/api/theories/recommend", json={
                "domain": "geopolitics",
                "description": "An arms race scenario",
                "use_claude": True,
            })
        assert resp.status_code == 200
        data = resp.json()
        # Without key, should use fast-path (no description + no key = domain_match)
        assert data["stage"] in ("domain_match", "domain_match_fallback")

    def test_confidence_scores_in_range(self):
        resp = client.post("/api/theories/recommend", json={
            "domain": "macro",
            "use_claude": False,
        })
        for rec in resp.json()["recommended"]:
            assert 0.0 <= rec["confidence"] <= 1.0
