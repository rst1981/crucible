"""
api/main.py — Crucible FastAPI application

Run locally:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    POST   /forge/intake                                   Create scoping session
    GET    /forge/intake/{session_id}                      Poll session state
    POST   /forge/intake/{session_id}/message              Stream agent response (SSE)
    DELETE /forge/intake/{session_id}                      Delete session
    GET    /forge/intake/{session_id}/theories             Recommended ensemble + scores
    PUT    /forge/intake/{session_id}/theories/accept      Accept recommended ensemble
    PUT    /forge/intake/{session_id}/theories/custom      Set custom ensemble
    GET    /forge/theories/library                         List all registered theories
    GET    /forge/theories/pending                         List pending theories
    GET    /forge/theories/pending/{id}                    Get pending theory detail
    POST   /forge/theories/pending/{id}/approve            Approve + load theory
    POST   /forge/theories/pending/{id}/reject             Reject theory
    POST   /simulations                                    Launch recommended + custom runs
    GET    /simulations                                    List runs
    GET    /simulations/{sim_id}                           Poll a run
    GET    /simulations/compare/{sim_id_a}/{sim_id_b}      Compare two runs
    GET    /api/theories                                   Theory catalog (filterable)
    GET    /api/theories/{theory_id}                       Theory detail
    POST   /api/theories/recommend                         Recommend theories for a scenario
    GET    /api/ensembles                                  List saved ensembles
    POST   /api/ensembles                                  Create ensemble
    GET    /api/ensembles/{id}                             Get ensemble
    DELETE /api/ensembles/{id}                             Delete ensemble
    POST   /api/ensembles/{id}/fork                        Fork ensemble
    GET    /health                                         Health check
    GET    /                                               API info
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import forge as forge_router
from api.routers import simulations as simulations_router
from api.routers import theories as theories_router
from api.routers import ensembles as ensembles_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Lifespan: init session store on startup ─────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await forge_router._load_sessions()
    yield


# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Crucible",
    lifespan=lifespan,
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
app.include_router(simulations_router.router)
app.include_router(theories_router.router)
app.include_router(ensembles_router.router)

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
            "forge_intake":      "POST /forge/intake",
            "forge_session":     "GET  /forge/intake/{session_id}",
            "forge_message":     "POST /forge/intake/{session_id}/message",
            "forge_theories":    "GET  /forge/intake/{session_id}/theories",
            "sim_launch":        "POST /simulations",
            "sim_poll":          "GET  /simulations/{sim_id}",
            "sim_compare":       "GET  /simulations/compare/{sim_id_a}/{sim_id_b}",
            "theory_catalog":    "GET  /api/theories",
            "theory_detail":     "GET  /api/theories/{theory_id}",
            "theory_recommend":  "POST /api/theories/recommend",
            "ensemble_list":     "GET  /api/ensembles",
            "ensemble_create":   "POST /api/ensembles",
            "ensemble_fork":     "POST /api/ensembles/{id}/fork",
        },
    }
