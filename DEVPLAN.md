# Crucible — Development Plan

> Last updated: March 25, 2026
> Stack: Python 3.12 / FastAPI / React 19 / TypeScript / Railway + Vercel
> Tooling: Claude Code + custom skills (/research-theory, /research-data, /scaffold-sim)

---

## Phases at a Glance

| Phase | Weeks | Theme | Deliverable |
|-------|-------|-------|-------------|
| 1 | 1–3 | Foundation | Core engine running, Hormuz ported |
| 2 | 4–7 | Scoping Agent + Model Library | Plain-language → running simulation, theory catalog + ensemble builder |
| 3 | 8–12 | Portal & Pilot | Client-facing SaaS, live engagement, ensemble management |

---

## Phase 1 — Foundation (Weeks 1–3)

Goal: a working simulation engine with the Hormuz scenario running inside the Crucible framework.

### Week 1 — Core Data Model & Theory Stubs

- [ ] **`core/spec.py`** — SimSpec dataclass (full schema: actors, theories, parameters, timeframe, metrics, uncertainties)
- [ ] **`core/agents/base.py`** — BDIAgent base class (beliefs dict, desires list, capabilities dict, `update_beliefs()`, `decide()`, `act()` interface)
- [ ] **`core/sim_runner.py`** — Domain-agnostic tick loop (initialize → tick → record → snapshot trigger)
- [ ] **`core/theories/base.py`** — Theory module base class (parameters, state_variables, `update(env, agents, tick)` interface)
- [ ] **Theory stubs × 5** — Richardson, Wittman-Zartman, Fearon, Keynesian Multiplier, Porter's Five Forces (interface only, logic TODO)
- [ ] **`requirements.txt`** — pin Python deps (fastapi, uvicorn, pydantic, apscheduler, anthropic, httpx)

### Week 2 — Research Adapters

- [ ] **`forge/researchers/base.py`** — ResearchResult dataclass + BaseAdapter interface
- [ ] **`forge/researchers/fred.py`** — FRED API adapter (series search + fetch, returns ResearchResult)
- [ ] **`forge/researchers/arxiv.py`** — arXiv API adapter (search by keyword, abstract parse)
- [ ] **`forge/researchers/worldbank.py`** — World Bank indicators adapter
- [ ] **`forge/researchers/ssrn.py`** — SSRN search adapter (scrape or API)
- [ ] **`forge/researchers/news.py`** — RSS/OSINT news adapter (configurable feeds)
- [ ] Adapter integration test: each adapter returns valid ResearchResult for a known query

### Week 3 — Hormuz Port + End-to-End Smoke Test

- [ ] **`forge/theory_mapper.py`** — Maps SimSpec domain + research results → selected theory module IDs
- [ ] **`scenarios/hormuz/`** — Full port from `d:/dev/hormuz-sim-dashboard`:
  - [ ] `params.py` — all 18 agent configs + Richardson parameters
  - [ ] `agents/` — 18 BDI agents (Iran, US, Saudi, shipping actors, etc.)
  - [ ] `theories.py` — Richardson + Wittman-Zartman + Fearon wired
  - [ ] `run.py` — entry point
- [ ] **Smoke test**: `python scenarios/hormuz/run.py` runs 10 ticks without error
- [ ] **`core/snapshot.py`** — named snapshot save/load (JSON, APScheduler daily trigger)

---

## Phase 2 — Scoping Agent & Forge UI (Weeks 4–7)

Goal: a consultant types a scenario description and gets a running simulation.

### Week 4 — Scoping Agent (Backend)

- [ ] **`forge/scoping_agent.py`** — Conversational intake agent (Claude API, streaming)
  - Background research firing on first message
  - SimSpec builder (populates spec incrementally)
  - Handoff to theory mapper when spec is complete
- [ ] **`forge/session.py`** — Scoping session state (conversation history, partial SimSpec, research cache)
- [ ] **API route: `POST /forge/intake`** — Start scoping session
- [ ] **API route: `GET /forge/intake/{session_id}`** — Poll session state + SimSpec progress
- [ ] **API route: `POST /forge/intake/{session_id}/message`** — Send user message, get agent response (streaming)

### Week 5 — Simulation API + Theory Catalog API

- [ ] **API route: `POST /simulations`** — Create + start simulation from SimSpec
- [ ] **API route: `GET /simulations/{id}/state`** — Current simulation state
- [ ] **API route: `GET /simulations/{id}/metrics`** — Outcome KPI time series
- [ ] **API route: `WS /simulations/{id}/stream`** — Real-time tick stream (WebSocket)
- [ ] **API route: `POST /simulations/{id}/snapshots`** — Save named snapshot
- [ ] **API route: `GET /simulations/{id}/snapshots`** — List snapshots
- [ ] **`api/services/sim_service.py`** — Async simulation manager (run in thread pool, track active sims)
- [ ] **`api/catalog.py`** — TheoryCatalogEntry: introspects registry, extracts DOMAINS, Parameters fields, state_variables, docstring, academic reference
- [ ] **API route: `GET /api/theories`** — Full catalog list (filterable by domain + keyword search)
- [ ] **API route: `GET /api/theories/{id}`** — Theory detail (parameters, reads/writes, full description)
- [ ] **API route: `POST /api/theories/recommend`** — Hybrid recommendation: domain-match fast path + Claude refinement (claude-haiku)
- [ ] **API route: `GET/POST/DELETE /api/ensembles`** — Named ensemble CRUD (stored as JSON in `data/ensembles/`)
- [ ] **API route: `POST /api/ensembles/{id}/fork`** — Fork an ensemble under a new name

### Week 6 — Forge UI + Model Library UI

- [ ] React project setup: Vite + TypeScript + Zustand stores + Tailwind
- [ ] **ForgePage** — Chat interface with streaming agent responses
  - [ ] Research status indicator (live as adapters return)
  - [ ] SimSpec progress panel (builds as conversation progresses)
  - [ ] "Launch simulation" button (appears when SimSpec complete)
- [ ] **DashboardPage** — War-room view (skeleton)
  - [ ] KPI panels (WebSocket-fed)
  - [ ] Snapshot timeline marker
  - [ ] Console/narrative feed
- [ ] **`/library` — Model Library page**
  - [ ] Domain filter chips (macro, market, conflict, ecology, corporate, technology)
  - [ ] Keyword search across theory names + descriptions
  - [ ] TheoryCard grid: name, domains, short description, parameter count
  - [ ] TheoryDetailModal: full description, parameters table, env keys (reads/writes), academic reference
  - [ ] `theoryStore` (Zustand): catalog fetch, filter, selected theory
- [ ] **`/ensembles` — Saved Ensembles page**
  - [ ] List: name, source (user/system), theory count, created date
  - [ ] Fork, delete, load into intake actions
- [ ] **`/library/pending` — Discovered Theory Review queue**
  - [ ] List: theory name, source paper, domains, smoke test status (pass/fail), created date
  - [ ] PendingTheoryDetailModal: generated code viewer, abstract snippet, citation, smoke test output
  - [ ] Approve button → `POST /forge/theories/pending/{id}/approve` (hot-loads immediately)
  - [ ] Reject button → `POST /forge/theories/pending/{id}/reject`
  - [ ] Badge on `/library` nav item showing pending count

### Week 7 — Ensemble Builder + End-to-End Integration

- [ ] **EnsembleBuilder component** — split-panel in intake flow (fires after SimSpec draft is ready)
  - [ ] Left panel: Claude's recommended theories (from `POST /api/theories/recommend`), each with one-sentence reasoning and confidence
  - [ ] Right panel: inline Model Library browser (domain filter + search + TheoryCard with Add toggle)
  - [ ] Footer: current ensemble chip list (removable), Save button, Run button
  - [ ] `ensembleStore` (Zustand): active ensemble, recommendations, add/remove/save/load
- [ ] **IntakePage updated** — scoping agent chat fires recommendation call in parallel; ensemble step appears when SimSpec domain is known
- [ ] Full flow test: free-text description → scoping agent → SimSpec + recommendations → ensemble selection → running sim → dashboard
- [ ] Test with Hormuz scenario: describe in plain language, verify agent reconstructs a valid SimSpec and recommends Richardson + Fearon + Wittman
- [ ] **`api/services/data_feed_agent.py`** — Background calibration agent skeleton (APScheduler, news adapter hook)
- [ ] Error handling: scoping agent timeouts, adapter failures, sim crash recovery, recommendation fallback (domain-match if Claude fails)
- [ ] **Local dev setup doc** — README with `uvicorn` run instructions, env vars

---

## Phase 3 — Client Portal & Pilot Engagement (Weeks 8–12)

Goal: a live client engagement delivered through Crucible.

### Week 8 — Dashboard Completion

- [ ] DashboardPage — full feature set:
  - [ ] Agent belief/intention state viewer
  - [ ] Replay controls (step forward/back, branch from snapshot)
  - [ ] Theory parameter viewer
  - [ ] Calibration event log
- [ ] Snapshot comparison view (before/after two snapshots)

### Week 9 — Client Portal + Ensemble Comparison

- [ ] **PortalPage** — Client-facing SaaS view
  - [ ] Clean branded layout (no simulation machinery)
  - [ ] Key findings panels with narrative
  - [ ] Snapshot comparison
  - [ ] Export: PDF report generation, data CSV download
  - [ ] "Models powering this analysis" panel — read-only theory cards showing which ensemble was used, with plain-language descriptions
- [ ] Auth layer: consultant login (internal) vs. client login (portal-only)
- [ ] Shareable link generation for portal snapshots
- [ ] **Ensemble comparison view** in Dashboard — run two saved ensembles against same SimSpec, overlay metrics on single chart

### Week 10 — Continuous Calibration Agent

- [ ] **`api/services/data_feed_agent.py`** — Full implementation
  - [ ] Polls news + FRED on configurable schedule
  - [ ] Claude API call to assess relevance + estimate parameter delta
  - [ ] Applies approved adjustments to running simulation
  - [ ] Pushes calibration events to dashboard alert feed
- [ ] Calibration event log UI in DashboardPage
- [ ] Alert threshold config per simulation

### Week 11 — Pilot Preparation

- [ ] **Second scenario** built from pilot engagement brief (using `/research-theory`, `/research-data`, `/scaffold-sim`)
- [ ] Full scoping agent run: consultant describes scenario → SimSpec → running sim (target: < 2 hours)
- [ ] Performance testing: 10-tick sim latency, WebSocket stability, snapshot write speed
- [ ] Railway deployment: backend + PostgreSQL + Redis
- [ ] Vercel deployment: frontend (root dir = `web`, framework = Vite)

### Week 12 — Pilot Delivery

- [ ] Live engagement delivery: client-facing portal live
- [ ] Continuous calibration agent running against live news feeds
- [ ] Post-pilot retro: what theory/data gaps appeared? Add to library backlog.
- [ ] Update CONTEXT.md with lessons learned + new open questions

---

## Model Library — Key Design Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Catalog source of truth | Theory module classes (no separate DB) | DOMAINS, Parameters, docstring already exist; single source of truth |
| Catalog storage | In-memory singleton, built at startup | 23 theories, fast to build; no write path needed |
| Ensemble persistence | JSON files (`data/ensembles/`) | No DB dependency for MVP; migrate to PostgreSQL in Phase 3 if multi-user |
| Recommendation fast path | Domain-match map (hardcoded) | Deterministic, instant, no API cost |
| Recommendation refined path | Claude (claude-haiku) | Cheap, fast, understands nuance; domain-match result if Claude fails |
| Ensemble format | `list[TheoryRef]` (same as SimSpec.theories) | No new types; ensemble IS the theory list, drops directly into SimSpec |
| User-defined vs. system ensembles | Both stored as EnsembleSummary with `source` field | No distinction in storage; UI labels them differently |

---

## Architecture Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend | FastAPI + Python 3.12 | Proven in Hormuz; async-native; Claude API SDK |
| Agent model | BDI with Bayesian belief updates | Proven in Hormuz; composable |
| Theory modules | Functional (pure `update()` fn) | Stateless, composable, testable |
| Frontend | React 19 + Vite + TypeScript | Proven in Hormuz |
| State (frontend) | Zustand | Lightweight, works well with WebSocket streams |
| Deployment | Railway (backend) + Vercel (frontend) | Proven in Hormuz |
| AI | Claude API (claude-sonnet-4-6) | Scoping agent + calibration agent |
| SimSpec format | Pydantic dataclass → JSON | Validated, serializable, reproducible |

---

## Key Rules (carry forward from Hormuz)

- Always `python -m uvicorn` — bare `uvicorn` not on PATH
- NEVER `vercel deploy` CLI — only `git push` to deploy frontend
- Claude API calls: batch 25/call, wrap in `asyncio.to_thread` to avoid blocking
- Snapshots: APScheduler daily + named manual saves

---

## Open Questions

1. Trademark check on "Crucible" — not yet done
2. PostgreSQL schema design — defer to Week 5 (when API routes are being built)
3. Auth strategy — simple JWT for now, revisit for client portal (Week 9)
4. Second pilot scenario — TBD, depends on which engagement is identified
5. Theory module: when does a stub get promoted to full implementation? (suggested: when first used in a real scenario)
