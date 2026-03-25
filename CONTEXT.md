# Crucible — Project Context

> This file is the canonical context document for the Crucible project.
> It is updated at the end of each working session and committed to git.
> Paste the contents into any Claude session (VSCode, Claude.ai, mobile) to restore full context.

---

## What Is Crucible?

Crucible is a generalized, agentic simulation modeling platform built for a large international consulting firm. It enables consultants to rapidly build, run, and deliver scenario simulations across market sectors for public and private sector clients.

It is a **clean-slate project** — not a fork of Hormuz. The Hormuz sim (Operation Epic Fury / Strait of Hormuz crisis) will become **reference implementation scenario #1** once the framework exists.

---

## Origin

Built by the same developer who built the Hormuz Crisis Simulation Dashboard (`d:/dev/hormuz-sim-dashboard`, GitHub: `rst1981/hormuz-sim`). Crucible generalizes that architecture into a reusable platform.

The Hormuz sim established:
- 18 BDI agents with Bayesian belief updates
- Richardson escalation model
- Wittman-Zartman and Fearon/DIA termination theory branches
- FastAPI backend + React 19 frontend
- OSINT scraping → Claude API analysis → parameter adjustment pipeline
- Named baseline snapshots with APScheduler daily saves
- Deployed on Railway (backend) + Vercel (frontend)

---

## Vision

**"Hit go and it goes."**

A consultant describes a scenario. The system researches relevant theory, pulls calibration data, scaffolds agents and parameters, runs the simulation, and keeps it calibrated as the real world evolves — automatically.

### Two Layers

| Layer | Users | Purpose |
|-------|-------|---------|
| **Forge** (sandbox) | Internal consultants | Scoping agent → research → scaffold → run |
| **Portal** (SaaS) | Clients | Clean dashboard, snapshots, exportable reports |

---

## The Core Loop

```
Consultant inputs scenario (free-form text)
        ↓
[Scoping Agent] — LLM-driven conversational intake
  - Fires background research immediately (arXiv, SSRN, FRED, World Bank, news)
  - Asks dynamic, research-informed questions
  - Iterates with user, surfacing domain perspectives from live research
  - Builds a SimSpec object conversationally (invisible to user)
        ↓
[Theory Mapper] — selects models, configures agents & params from SimSpec
        ↓
[Sim Factory] — scaffolds and runs the simulation
        ↓
[Dashboard] — live results, named snapshots, export
        ↓
[Data Feed Agent] — recalibrates parameters as real-world data evolves
```

The scoping agent is a **research-grounded interview** — it already did homework before asking the first question.

---

## Research Sources

Used at both design-time (by Claude/scoping agent) and runtime (by the platform):

- **arXiv** — academic papers, preprints
- **SSRN** — social science / economics research
- **FRED** — Federal Reserve Economic Data
- **World Bank** — development and macro data
- **News/OSINT feeds** — live event tracking (pattern from Hormuz scraper)

---

## Theory Library (curated)

| Domain | Theories / Models |
|--------|-------------------|
| Conflict / geopolitics | Richardson arms race, Wittman-Zartman, Fearon bargaining |
| Markets | Porter's Five Forces, supply/demand shocks, contagion models |
| Org / corporate | Principal-agent, institutional theory, diffusion of innovation |
| Macro / policy | Keynesian multipliers, regulatory shock models |

---

## Proposed Repo Structure

```
crucible/
├── CONTEXT.md               ← this file — update and commit each session
├── core/                    # Python package — generalized sim engine
│   ├── agents/              # BDI agent base classes
│   ├── theories/            # Curated theory library
│   ├── sim_runner.py        # Domain-agnostic simulation runtime
│   └── spec.py              # SimSpec — the structured scenario object
│
├── forge/                   # Scoping agent + research pipeline
│   ├── scoping_agent.py     # Conversational intake + SimSpec builder
│   ├── researchers/         # arXiv, SSRN, FRED, World Bank, news adapters
│   └── theory_mapper.py     # Maps domain + research → theory selection
│
├── api/                     # FastAPI backend
│   ├── routers/
│   └── services/
│
├── web/                     # React frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ForgePage/   # Scoping agent chat UI
│   │   │   ├── DashboardPage/
│   │   │   └── PortalPage/  # Client-facing SaaS view
│   │   └── stores/
│
├── scenarios/               # Reference implementations
│   └── hormuz/              # Hormuz sim ported as scenario #1
│
└── data/                    # Snapshots, outputs
```

---

## Open Questions (pinned)

1. **Name trademark check** — "Crucible" not yet verified. User paused that search.
2. **GitHub account** — likely `rst1981` (same as Hormuz), confirm before first push.
3. **Scenario definition standardization** — resolved via SimSpec + scoping agent (conversational, not a form).
4. **Research skills** — user is researching custom Claude Code skills (e.g. `/research-theory`, `/research-data`) to augment Claude's toolset. Pattern: gstack-style markdown skill files.
5. **Deployment** — TBD. Likely same pattern as Hormuz: Railway (backend) + Vercel (frontend).

---

## Hormuz Sim Reference (for porting as scenario #1)

- **Local:** `d:/dev/hormuz-sim-dashboard`
- **GitHub:** `rst1981/hormuz-sim` (branch: main)
- **Backend:** Railway at `hormuz-sim-production-9505.up.railway.app`
- **Frontend:** Vercel at `hormuz-sim.vercel.app`
- **War start date:** Feb 25, 2026. Day 18 = March 15, 2026.

### Key operational notes from Hormuz:
- Always use `python -m uvicorn` (not bare `uvicorn`) — Scripts not on PATH
- **NEVER** use Vercel CLI deploy — only `git push`. CLI creates duplicate projects.
- Analyzer batches Claude API calls in groups of 25 to avoid token truncation
- Use `asyncio.to_thread` for Claude API calls to avoid blocking async event loop

---

## Custom Skills (Claude Code)

Located in `.claude/skills/` — invoke with `/skill-name`:

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/research-theory` | Before designing a sim | arXiv + SSRN search → theory brief + SimSpec update |
| `/research-data` | Before launching a sim | FRED + World Bank → parameter values + data brief |
| `/scaffold-sim` | Ready to build a scenario | SimSpec → full scenario directory scaffold |

---

## Current Status

**Date:** March 25, 2026

**Phase:** Architecture complete and reviewed. No code written yet. Week 1 begins now.

**Architecture documents (all committed, all reviewed):**
- `ARCHITECTURE.md` — engine: SimSpec (Pydantic v2), BDIAgent (BetaBelief/GaussianBelief), TheoryBase (@register_theory), SimRunner (asyncio.to_thread tick loop)
- `ARCHITECTURE-FORGE.md` — intake: ForgeSession (6-state machine), ScopingAgent (Claude API tool-use, research-first), TheoryMapper, SpecBuilder, GapDetector
- `ARCHITECTURE-API.md` — persistence (SQLAlchemy Core + Redis), EnsembleRunner (Monte Carlo), NarrativeAgent (AsyncAnthropic), ReportRenderer, DataFeedAgent, SimSpec versioning, full FastAPI surface. Includes "Engineering Review — Corrections" section with 16 pre-implementation fixes.
- `ARCHITECTURE-THEORIES.md` — full math for all 5 theory modules: Richardson, Fearon, Wittman-Zartman, Keynesian, Porter's. Parameter tables with empirical ranges. Python stubs.
- `ARCHITECTURE-PORTAL.md` — React 19 + TypeScript frontend: Forge UI (scoping agent chat, sim dashboard), Portal UI (client-facing, read-only), Zustand stores, WebSocket management, auth model (ADMIN/CONSULTANT/CLIENT), multi-tenancy.
- `TODOS.md` — 13 deferred items with full context, priority, and where-to-start for each.
- `Amir.md` — 6-page theory briefing for stakeholders: BDI rationale, theory library deliberations, uncertainty design, calibration loop, scoping agent philosophy.

**Key engineering review findings (all resolved before coding):**
- `random.seed()` thread-safety bug in EnsembleRunner → `rng: random.Random` param threaded through SimRunner/BDIAgent
- Sync Anthropic client in async context → AsyncAnthropic everywhere
- `asyncio.run()` in APScheduler thread → `run_coroutine_threadsafe` with captured main loop
- O(n²) percentile band computation → pre-built `{(metric_id, tick): [values]}` index
- Missing SimOrchestrator wiring layer → new `api/orchestrator.py`
- ForgeSession serialization stubs → `to_dict()/from_dict()` fully specified
- Gap 5 regression in ReportRenderer → `SimSpec` param + `display_env()` call
- Transaction atomicity (per-method `commit()`) → caller-controlled via `async with engine.begin()`

**Week 1 — start now:**
1. `core/spec.py` — SimSpec + EnvKeySpec + SpecDiff (root data contract, everything depends on this)
2. `core/agents/base.py` — BDIAgent with `rng: random.Random` param, BetaBelief, GaussianBelief
3. `core/sim_runner.py` — tick loop, `asyncio.to_thread`, on_snapshot/on_metric_threshold callbacks
4. `core/theories/base.py` — TheoryBase ABC, @register_theory decorator, registry
5. Theory stubs × 5 — Richardson, Wittman-Zartman, Fearon, Keynesian, Porter's (see ARCHITECTURE-THEORIES.md for full math)

**Reference implementation:**
- Hormuz sim at `d:/dev/hormuz-sim-dashboard` — 18 BDI agents, running live, port as scenario #1 in Week 12

---

## How to Use This File

At the start of any Claude session on any device:

> "Read CONTEXT.md from the Crucible repo and use it as your full project context."

Or paste the contents directly. This file is the single source of truth for where we are and where we're going.
