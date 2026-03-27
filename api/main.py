"""
api/main.py — Crucible FastAPI application

Run locally:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    POST   /forge/intake                                   Create scoping session
    GET    /forge/intake/{session_id}                      Poll session state
    POST   /forge/intake/{session_id}/message              Stream agent response (SSE)
    DELETE /forge/intake/{session_id}                      Delete session
    GET    /forge/theories/library                         List all registered theories
    GET    /forge/theories/pending                         List pending theories
    GET    /forge/theories/pending/{id}                    Get pending theory detail
    POST   /forge/theories/pending/{id}/approve            Approve + load theory
    POST   /forge/theories/pending/{id}/reject             Reject theory
    GET    /health                                         Health check
    GET    /                                               API info
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import forge as forge_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Crucible",
    description="Theory-grounded multi-agent simulation platform",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (allow all origins in dev; tighten in production) ─────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────

app.include_router(forge_router.router)

# ── System routes ──────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/")
async def root() -> dict:
    return {
        "name":    "Crucible API",
        "version": app.version,
        "docs":    "/docs",
        "routes": {
            "forge_intake":    "POST /forge/intake",
            "forge_session":   "GET  /forge/intake/{session_id}",
            "forge_message":   "POST /forge/intake/{session_id}/message",
        },
    }
