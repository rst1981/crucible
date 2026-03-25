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

**Phase:** Week 1 in progress — core engine layer complete. SimRunner next.

**Test coverage: 242 tests, all passing.**

**Implemented (Week 1):**
- `core/spec.py` — SimSpec root contract (Pydantic v2). BeliefSpec with decay_rate/process_noise/maps_to_env_key. ActorSpec with observation_noise_sigma. EnvKeySpec + display_env() (normalized→display translation). SpecDiff + diff_simspecs() + branch_simspec() (version DAG). 57 tests.
- `core/agents/base.py` — BDIAgent ABC with tick() coordinator (decay→observe→update→decide order enforced). BetaBelief (alpha>0 validated, decay(), maps_to_env_key). GaussianBelief (0/0 guard, diffuse(), maps_to_env_key). AgentHydrationError. from_spec() factory (propagates all dynamics; raises on duplicate belief names). DefaultBDIAgent (utility-maximizing concrete class). Thread-safe RNG. 131 tests.
- `core/theories/base.py` + `__init__.py` — TheoryBase ABC (setup/update contract). TheoryStateVariables (reads/writes/initializes). @register_theory decorator (raises on duplicate). get_theory()/list_theories() registry. 32 tests.
- `core/theories/richardson_arms_race.py` — Full Richardson ODE (k/l/a/b/g/h parameters, dt scaling by tick_unit, stability warning at construction, actor-namespaced env keys, equilibrium() method). 30 tests.

**Architecture documents (all current):**
- `ARCHITECTURE.md` — engine: SimSpec, BDIAgent, TheoryBase, SimRunner design
- `ARCHITECTURE-THEORIES.md` — full math for all 5 theory modules with empirical parameter ranges
- `ARCHITECTURE-FORGE.md` — ForgeSession, ScopingAgent, TheoryMapper, GapDetector
- `ARCHITECTURE-API.md` — persistence, EnsembleRunner, NarrativeAgent, full FastAPI surface (incl. 16 pre-impl fixes)
- `ARCHITECTURE-PORTAL.md` — React 19 frontend, Zustand stores, auth model
- `TODOS.md` — 13 deferred items with priority and context
- `Amir.md` — 7-section stakeholder briefing

**Week 1 — remaining:**
1. `core/sim_runner.py` — tick loop, asyncio.to_thread, on_snapshot/on_metric_threshold callbacks
2. Theory stubs — Wittman-Zartman, Fearon, Keynesian Multiplier, Porter's Five Forces
3. `requirements.txt` — pin Python deps

**Reference implementation:**
- Hormuz sim at `d:/dev/hormuz-sim-dashboard` — 18 BDI agents, running live, port as scenario #1 in Week 3

---

## Claude Working Rules

Rules and preferences learned across sessions — apply these without being reminded.

### Environment
- Always `python -m uvicorn` — bare `uvicorn` not on PATH (`AppData\Roaming\Python\Python314\Scripts` missing from PATH)
- NEVER `vercel deploy` or `npx vercel --prod` — creates duplicate projects (had to delete twice). Frontend deploys via `git push` only. If there's a Vercel build issue, fix in the dashboard.

### Session hygiene
- Update `## Current Status` in this file at the end of each session (completed work, updated next steps)
- The Stop hook in `.claude/settings.json` auto-commits and pushes CONTEXT.md when the conversation ends

### Code style preferences
- Thread-safe RNG: always `rng: random.Random` parameter, never global `random` state
- Explicit over clever; minimal diff
- Handle edge cases (0/0 guards, validation on construction) — thoughtfulness > speed
- Tests: prefer too many over too few; integration over mocks where practical

---

## How to Use This File

At the start of any Claude session on any device:

> "Read CONTEXT.md from the Crucible repo and use it as your full project context."

Or paste the contents directly. This file is the single source of truth for where we are and where we're going.
