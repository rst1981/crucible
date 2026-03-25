# Crucible — Developer Briefing

**To:** Amir
**Date:** March 24, 2026
**Status:** Architecture complete. No code written yet. Week 1 starts now.

---

## What We're Building

Crucible is an agentic simulation platform for a large international consulting firm. Consultants describe scenarios in plain English — trade conflicts, geopolitical flashpoints, regulatory shocks — and the system does the rest: researches theory, calibrates parameters from live data, scaffolds agents, runs simulations, and keeps them updated as the world changes.

The North Star is **"hit go and it goes."** The consultant's job is to describe the problem. Crucible's job is everything after that.

---

## Architecture in Three Layers

```
FREE TEXT INPUT
      ↓
┌─────────────────────────────────────────────────────┐
│  FORGE  (intake layer)                              │
│  ScopingAgent — Claude API tool-use agent           │
│  Fires research first (arXiv, SSRN, FRED,           │
│  World Bank, news), then asks smart questions.      │
│  Builds a SimSpec object conversationally.          │
│  TheoryMapper selects models. SpecBuilder fills     │
│  parameters. GapDetector flags what's missing.      │
└──────────────────────────┬──────────────────────────┘
                           │ SimSpec
┌──────────────────────────▼──────────────────────────┐
│  ENGINE  (simulation layer)                         │
│  SimRunner — async tick loop, BDI agents,           │
│  pluggable theory modules (Richardson, Fearon,      │
│  Wittman-Zartman, Keynesian, Porter's Five Forces)  │
│  EnsembleRunner — 100× parallel runs, Monte Carlo   │
│  NarrativeAgent — Claude API tick commentary        │
└──────────────────────────┬──────────────────────────┘
                           │ results
┌──────────────────────────▼──────────────────────────┐
│  PERSISTENCE + API  (delivery layer)                │
│  SQLite (dev) / Postgres (prod) + Redis             │
│  FastAPI — REST + WebSocket                         │
│  ReportRenderer — Markdown / PDF / JSON             │
│  DataFeedAgent — APScheduler, recalibrates every 6h │
└─────────────────────────────────────────────────────┘
```

**Key data contract:** `SimSpec` (Pydantic v2). Everything — agents, theories, environment, metrics — lives in one versioned object. Fork it, diff it, branch it. The version DAG is in Postgres.

**Key design rule:** All environment values are normalized `[0, 1]` inside the engine. `EnvKeySpec` annotates each key with a scale and unit so the API layer denormalizes for display. Clients never see raw floats.

---

## Bugs We Caught Before Writing a Line of Code

The engineering review of ARCHITECTURE-API.md caught 16 issues. The ones that would have hurt most in production:

**1. Thread-unsafe seeding (would have been silent and maddening)**
`_run_single()` called `random.seed(seed)` — a global call — from 8 concurrent threads. Each thread immediately clobbered the others' seeds. Ensemble reproducibility was broken by design. Fix: `rng = random.Random(seed)`, threaded through `SimRunner` and `BDIAgent` as a parameter.

**2. Async Anthropic client (would have stalled every client demo)**
`NarrativeAgent._generate()` was `async def` but called the *synchronous* `Anthropic()` client. Every Claude API call (1–3 seconds) blocked the entire FastAPI event loop — no WebSocket ticks, no other requests, SimRunner stalled. Fix: `AsyncAnthropic` with `await` everywhere.

**3. DataFeedAgent event loop conflict (would have crashed at first calibration cycle)**
APScheduler runs jobs in threads. The calibration job called `asyncio.run()`, creating a second event loop. Asyncpg connections are bound to the loop that created them — the second loop would hit `RuntimeError: Task attached to a different loop` on first DB write. Fix: capture the main loop at startup, use `asyncio.run_coroutine_threadsafe`.

**4. O(n²) percentile bands (would have surfaced on the first real client scenario)**
`_compute_result` scanned all 36,500 metric records 365 times per metric = 66M iterations for a 100-run, 365-tick, 5-metric ensemble. Estimated 2–10 seconds in Python. Fix: pre-build a `{(metric_id, tick): [values]}` index in one O(n) pass.

**5. Missing wiring layer**
The architecture defined `SimRunner`, `EnsembleRunner`, `NarrativeAgent`, and `SimRepository` as separate units but didn't specify what connects them. Who sets `runner.on_snapshot = agent.on_snapshot`? Who flushes metrics every 10 ticks? Who marks the simulation FAILED if SimRunner throws? Fix: new `SimOrchestrator` class — the only thing the API endpoints call.

**6. Gap 5 regression in reports**
`ReportRenderer.render_markdown()` rendered raw `0.742` floats straight to the client PDF, bypassing the entire `EnvKeySpec` / `display_env()` system we built to solve that exact problem. Fix: pass `SimSpec` to the renderer and call `display_env()` on every snapshot table.

All 16 fixes are documented in the "Engineering Review — Corrections" section at the bottom of `ARCHITECTURE-API.md`.

---

## Dev Timeline

| Week | Deliverable |
|------|-------------|
| **1** | `core/spec.py` (SimSpec, EnvKeySpec, SpecDiff), `core/agents/base.py` (BDIAgent with rng), `core/sim_runner.py` (tick loop), `core/theories/base.py` (registry + @register_theory) |
| **2** | 5 theory stubs (Richardson, Wittman-Zartman, Fearon, Keynesian, Porter's). First working simulation: Hormuz scenario runs end-to-end. |
| **3** | `api/db/schema.py` + `api/db/repository.py` (SQLAlchemy Core, engine injection, no per-method commits). `api/config.py` (pydantic-settings). `api/orchestrator.py` (SimOrchestrator). |
| **4** | `core/ensemble.py` (EnsembleRunner, full corrections applied: rng, caching, index, return_exceptions). `core/narrative.py` (NarrativeAgent, AsyncAnthropic). |
| **5** | Forge layer: `forge/session.py` (ForgeSession.to_dict/from_dict), `forge/scoping.py` (ScopingAgent), `forge/researchers/` (arXiv, SSRN, FRED, World Bank, news). |
| **6** | `forge/theory_mapper.py`, `forge/spec_builder.py`, `forge/gap_detector.py`. End-to-end Forge flow: free text → SimSpec → simulation. |
| **7** | `api/session_store.py` (Redis), `core/calibration.py` (DataFeedAgent with run_coroutine_threadsafe fix), FastAPI routers (simulations, ensembles, narrative, calibration). |
| **8** | `core/versioning.py` (diff_simspecs, branch_simspec), versioning router, WebSocket stream handlers. |
| **9** | `core/reports.py` (ReportRenderer with SimSpec param + display_env fix), reports router, PDF export. |
| **10** | React frontend: Forge chat UI (ScopingAgent), simulation dashboard (live tick stream), ensemble visualization (p10/p50/p90 bands). |
| **11** | Portal layer: client-facing SaaS view, snapshot comparison, report download, authentication. |
| **12** | Hormuz scenario fully ported as reference implementation #1. Staging deployment (Railway + Vercel). Internal QA. |

---

## Where to Start

```
Architecture docs (read in order):
  ARCHITECTURE.md        — engine: SimSpec, BDIAgent, TheoryBase, SimRunner
  ARCHITECTURE-FORGE.md  — intake: ScopingAgent, researchers, TheoryMapper
  ARCHITECTURE-API.md    — persistence, ensemble, narrative, calibration, API
                           └── "Engineering Review — Corrections" section at bottom
                               is mandatory reading before touching any file

Reference implementation:
  d:/dev/hormuz-sim-dashboard   — 18-agent Hormuz sim. Pattern source for
                                   asyncio.to_thread, APScheduler, React store
                                   architecture, Railway/Vercel deployment.

First file to write:
  core/spec.py — SimSpec is the root data contract. Everything else depends on it.
```

Two rules that matter immediately:
- Always `python -m uvicorn` — bare `uvicorn` is not on PATH
- Never `vercel deploy` — push to git only, CLI creates duplicate projects
