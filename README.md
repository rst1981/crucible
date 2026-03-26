# Crucible: Agentic Simulation Platform
### Internal Proposal — March 2026

---

## The Problem

Complex advisory engagements increasingly demand answers to questions that static models cannot answer:

- How will this market respond to a regulatory shock over the next 18 months?
- What are the second- and third-order effects of a competitor's entry?
- How does an escalating conflict affect our client's supply chain under different resolution scenarios?

Current approaches rely on expert judgment, spreadsheet models, or off-the-shelf tools that lack domain depth. They are slow to build, hard to update, and impossible to calibrate against live events.

**We need a better way to model the world.**

---

## The Solution

Crucible is a platform for **agent-based simulation** — the gold standard methodology for modeling complex adaptive systems. It combines:

- **Domain-specific theory** (economics, geopolitics, organizational behavior, market dynamics) to structure each simulation
- **Real-time research ingestion** (academic literature, economic data feeds, news) to calibrate models against the world as it is
- **Agentic scaffolding** — an AI-driven intake process that designs a simulation from a consultant's plain-language description, with minimal manual configuration

The result: a consultant describes a scenario on Monday. By Tuesday, a calibrated, running simulation is delivering insights.

---

## How It Works

### 1. Scenario Intake (The Forge)

A consultant opens the Crucible Forge and describes a scenario in plain language:

> *"Model the competitive dynamics in the US generic pharmaceuticals market following proposed FDA biosimilar approval reforms."*

A research-grounded scoping agent immediately:
- Searches academic literature (arXiv, SSRN) for relevant theory
- Pulls calibration data (FRED, World Bank, industry feeds)
- Asks targeted, informed follow-up questions based on what it finds
- Iterates with the consultant to refine scope, actors, and key uncertainties

The agent builds a **SimSpec** — a structured scenario definition — in the background. When complete, it hands off automatically.

### 2. Model Library & Ensemble Selection

Before the simulation launches, the consultant sees a split panel:

- **Claude recommends** a starting ensemble of 3–5 theories based on the scenario description, with a one-sentence rationale for each
- **The Model Library** lets the consultant browse all 23+ available theories, filter by domain, read parameter details, and swap theories in or out

The resulting theory mix — a named **ensemble** — is saved and attached to the simulation. Clients see which models powered their analysis in the Portal.

### 3. Simulation Build (Automated)

The confirmed ensemble of theoretical models is wired into agent-based actors with Bayesian belief systems, and the simulation runs. No manual parameter entry. No bespoke code per engagement.

### 3. Live Dashboard

Results are delivered through a clean, interactive war-room dashboard:
- Key performance indicators and scenario trajectories
- Named snapshots at critical decision points
- Narrative feed explaining what the simulation is doing and why
- Replay controls to explore alternative paths

### 4. Continuous Calibration

Once running, the simulation stays current. A background data feed agent monitors relevant news and economic indicators, adjusts parameters automatically, and flags significant developments to the consultant team.

---

## Theory Library

Crucible ships with a curated library of validated formal models across five domains. Each theory is implemented as a composable module: it exposes a standard interface (parameters, state variables, update rules) that the Theory Mapper can wire into any simulation without bespoke code.

---

### Domain 1: Geopolitics & Conflict

| Model | Description | Key Parameters |
|-------|-------------|----------------|
| **Richardson Arms Race** | Differential equation model of mutual military buildup driven by threat perception and grievance. Classic dyadic escalation baseline. | Fatigue coefficient, threat sensitivity, grievance load |
| **Wittman-Zartman Negotiation** | Models ripeness for conflict termination — identifies when both parties perceive a mutually hurting stalemate and a negotiated exit becomes rational. | Stalemate threshold, cost tolerance, perceived BATNA |
| **Fearon Bargaining (DIA)** | Explains why rational actors fight. Models private information asymmetries, commitment problems, and issue indivisibility as drivers of conflict onset and duration. | Information gap, credibility discount, issue divisibility |
| **Prospect Theory (Kahneman-Tversky applied to IR)** | Captures loss-aversion in state decision-making — actors in the domain of losses take greater risks than classical expected utility predicts. | Reference point, loss-aversion coefficient |
| **Selectorate Theory (Bueno de Mesquita)** | Models leader survival logic — how the size of the winning coalition shapes foreign policy decisions, war initiation, and concession behavior. | Winning coalition size, selectorate size, loyalty norm |

---

### Domain 2: Market & Competitive Dynamics

| Model | Description | Key Parameters |
|-------|-------------|----------------|
| **Porter's Five Forces** | Structural analysis of industry attractiveness — maps rivalry, substitution, buyer/supplier power, and entry threat as continuous pressure variables. | Entry barrier height, switching costs, concentration ratio |
| **Cournot / Bertrand Competition** | Oligopoly pricing and quantity dynamics. Cournot models quantity competition; Bertrand models price competition to marginal cost. | Number of firms, marginal cost, demand elasticity |
| **Supply/Demand Shock Propagation** | Models how upstream disruptions (supply shocks) or demand collapses ripple through a market system with inventory buffers and price stickiness. | Shock magnitude, buffer depth, price rigidity |
| **Financial Contagion (DebtRank)** | Network-based model of systemic risk propagation across financially linked institutions or markets. | Exposure matrix, leverage ratios, threshold sensitivity |
| **Bass Diffusion Model** | Forecasts adoption curves for new products or technologies — separates innovator-driven early adoption from imitator-driven mass market growth. | Innovation coefficient (p), imitation coefficient (q) |
| **Hotelling Spatial Competition** | Models firm positioning along a product or policy dimension when consumers prefer proximity — explains clustering and differentiation decisions. | Transport cost, consumer distribution, entry cost |

---

### Domain 3: Organizational & Corporate Behavior

| Model | Description | Key Parameters |
|-------|-------------|----------------|
| **Principal-Agent Theory** | Models misaligned incentives between principals (owners, regulators, boards) and agents (managers, employees). Drives hidden action and adverse selection dynamics. | Monitoring cost, agent risk aversion, incentive alignment |
| **Institutional Theory (DiMaggio & Powell)** | Explains organizational isomorphism — why firms in a sector converge on similar structures through coercive, mimetic, and normative pressures. | Regulatory pressure, peer visibility, legitimacy pressure |
| **Diffusion of Innovation (Rogers)** | Models how a practice, technology, or policy spreads through a population segmented into innovators, early adopters, majority, and laggards. | Adoption thresholds per segment, network density |
| **Organizational Resilience (Weick HRO)** | High-Reliability Organization model — captures how organizations maintain function under stress through redundancy, deference to expertise, and sense-making loops. | Redundancy factor, expertise centralization, failure rate |
| **Stakeholder Salience (Mitchell et al.)** | Prioritizes which actors receive organizational attention based on power, legitimacy, and urgency — useful for modeling multi-stakeholder scenarios. | Salience scores, urgency decay, power distribution |

---

### Domain 4: Macroeconomics & Policy

| Model | Description | Key Parameters |
|-------|-------------|----------------|
| **Keynesian Multiplier** | Models the amplified effect of a fiscal stimulus or shock on aggregate demand through successive rounds of spending. | Marginal propensity to consume, leakage rates |
| **Regulatory Shock Propagation** | Captures how a policy change (new regulation, tariff, license requirement) transmits through a sector via compliance cost, market exit, and behavioral adjustment. | Compliance cost distribution, exit threshold, adjustment speed |
| **IS-LM / AS-AD Framework** | Standard macroeconomic equilibrium model linking output, interest rates, and price levels — useful for monetary and fiscal policy scenario analysis. | Investment sensitivity, money demand elasticity, price flexibility |
| **Debt Sustainability (DSA)** | Models sovereign or corporate debt trajectory under different growth, interest rate, and primary balance scenarios — standard IMF/World Bank methodology. | Debt/GDP ratio, interest-growth differential, primary balance |
| **Input-Output (Leontief)** | Sector-level model of economic interdependence — traces how a disruption in one sector propagates through supply chains across the whole economy. | Technical coefficients matrix, final demand vector |

---

### Domain 5: Social & Behavioral Dynamics

| Model | Description | Key Parameters |
|-------|-------------|----------------|
| **Schelling Segregation** | Demonstrates how mild individual preferences produce strong macro-level segregation — applicable to market segmentation, political polarization, and urban dynamics. | Tolerance threshold, population mix |
| **Opinion Dynamics (Deffuant-Weisbuch)** | Models belief convergence and polarization in a population — agents update opinions only when the gap with interacting agents falls below a confidence threshold. | Confidence threshold, convergence rate, network topology |
| **SIR / SEIR Contagion** | Epidemiological spread model adapted for idea diffusion, crisis contagion, financial panic, or social movement propagation. | Transmission rate (β), recovery rate (γ), network structure |
| **Tipping Point / Threshold Models (Granovetter)** | Models cascade phenomena — strikes, protests, bank runs, market crashes — as sequences of agents crossing individual action thresholds. | Threshold distribution, network connectivity |

---

### Composability

Models are not used in isolation. The Theory Mapper composes them into layered simulations:

- A **geopolitical scenario** might layer Richardson (escalation) + Fearon (onset logic) + Prospect Theory (decision bias) + Input-Output (economic damage propagation)
- A **market entry scenario** might layer Porter's Five Forces (structural baseline) + Bass Diffusion (adoption) + Hotelling (positioning) + Principal-Agent (partner dynamics)
- A **regulatory scenario** might layer Regulatory Shock Propagation + Keynesian Multiplier + Institutional Theory (industry response)

---

## Model Library

The Model Library is a browsable, searchable interface to the theory catalog — built into both the Forge (consultant-facing) and the Portal (client-facing).

### What it does

- **Browse** — consultants explore all available theories, filter by domain, read parameter details and academic references
- **Recommend** — when a scenario is described, Claude (claude-haiku) returns a ranked ensemble with one-sentence reasoning per theory and suggested parameter overrides
- **Build** — consultants start from Claude's recommendation and customize: swap theories, adjust the mix, save named ensembles for reuse

### Intake flow

```
Consultant describes scenario
        │
        ▼
Scoping Agent builds SimSpec draft
POST /api/theories/recommend fires in parallel
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  ENSEMBLE SELECTION                                         │
│                                                             │
│  Claude recommends          Model Library browse            │
│  ──────────────────         ─────────────────────────────   │
│  ✓ Richardson (conflict)    Filter: [conflict] [macro]      │
│  ✓ Fearon (bargaining)      □ Bass Diffusion                │
│  ✓ Keynesian (macro)        □ Fearon Bargaining ☑          │
│  [Why these?] [Run as-is]   □ Minsky Instability            │
│                             [Details ↗] [Add]               │
│                                                             │
│  Current ensemble: Fearon + Richardson + Keynesian  [Run ▶] │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
SimRunner executes with confirmed ensemble
```

### Recommendation strategy

The `/api/theories/recommend` endpoint uses a two-stage hybrid approach:

1. **Domain match** (instant) — maps the scenario's domain tag to a pre-computed set of theory IDs
2. **Claude refinement** (async, claude-haiku-4-5) — re-ranks the domain match results, adds reasoning and suggested parameter overrides; falls back to domain match if the Claude call fails

### Ensemble storage

Named ensembles are saved as JSON files (`data/ensembles/{id}.json`) — no database required for MVP. Each ensemble captures the full `TheoryRef[]` list with any parameter overrides, a name, source (`user` | `system` | `hybrid`), and creation timestamp.

### Client portal integration

The Portal shows a "Models powering this analysis" panel on each scenario view — a read-only summary of which theories were active, their domains, and the academic references behind them.

See `ARCHITECTURE-LIBRARY.md` for the full component tree, API endpoints, and Zustand store definitions.

---

- A **geopolitical scenario** might layer Richardson (escalation) + Fearon (onset logic) + Prospect Theory (decision bias) + Input-Output (economic damage propagation)
- A **market entry scenario** might layer Porter's Five Forces (structural baseline) + Bass Diffusion (adoption) + Hotelling (positioning) + Principal-Agent (partner dynamics)
- A **regulatory scenario** might layer Regulatory Shock Propagation + Keynesian Multiplier + Institutional Theory (industry response)

---

## Use Cases

Crucible is sector-agnostic. Initial target domains:

- **Geopolitical risk** — conflict escalation, sanctions, trade disruption
- **Competitive intelligence** — market entry, price wars, M&A dynamics
- **Regulatory scenarios** — policy reform, compliance shocks, market restructuring
- **Supply chain resilience** — disruption modeling, sourcing alternatives
- **Organizational change** — merger integration, restructuring, leadership transition

---

## Platform Architecture

Crucible is a cloud-native platform with five distinct subsystems. Each is independently deployable and communicates through well-defined interfaces.

---

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                          FORGE                              │
│           (Internal consultant-facing interface)            │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  Scoping    │───▶│   Research   │───▶│    Theory     │  │
│  │   Agent     │    │   Pipeline   │    │    Mapper     │  │
│  └─────────────┘    └──────────────┘    └───────┬───────┘  │
│         ▲                                        │          │
│   (chat input)                                   ▼          │
│                                         ┌────────────────┐  │
│                                         │   Sim Factory  │  │
│                                         └───────┬────────┘  │
└─────────────────────────────────────────────────┼───────────┘
                                                  │
                              ┌───────────────────▼───────────────────┐
                              │            SIMULATION ENGINE           │
                              │  BDI Agents + Theory Modules + Clock  │
                              └───────────────────┬───────────────────┘
                                                  │
               ┌──────────────────────────────────┼─────────────────────────────┐
               │                                  │                             │
    ┌──────────▼──────────┐           ┌───────────▼──────────┐     ┌───────────▼──────────┐
    │    FastAPI Backend  │           │   Data Feed Agent    │     │   Snapshot Store     │
    │    (REST + WS)      │           │  (live calibration)  │     │  (named + scheduled) │
    └──────────┬──────────┘           └──────────────────────┘     └──────────────────────┘
               │
    ┌──────────┴──────────────────────────────────┐
    │                  FRONTEND                    │
    │   ForgePage  │  DashboardPage  │  PortalPage │
    └─────────────────────────────────────────────┘
```

---

### Subsystem 1: Scoping Agent

The entry point. A conversational LLM agent (Claude API) that transforms a free-text scenario description into a structured **SimSpec** object.

**Behavior:**
- On first input, fires all research adapters in parallel (background, non-blocking)
- Asks informed questions grounded in what research returns — not a static intake form
- Iteratively refines scope: actors, timeframe, key uncertainties, outcome metrics
- Builds the SimSpec object conversationally, invisible to the user
- Hands off to Theory Mapper when SimSpec is complete

**Key design principles:**
- Research precedes questions — the agent never asks something it could have looked up
- Each conversation turn is context-aware: later questions incorporate earlier answers and new research results
- The consultant sees a natural dialogue; the system is assembling a structured object

---

### Subsystem 2: Research Pipeline

A set of lightweight adapters that fetch, parse, and summarize external data sources on demand. Used by the Scoping Agent at intake and by the Data Feed Agent at runtime.

All adapters implement the same `BaseAdapter` interface — they return normalized `ResearchResult` objects and never raise. Failures are encoded as error results so one bad source never blocks the others.

**Academic & preprint sources:**

| Adapter | Source | Auth | Use |
|---------|--------|------|-----|
| `arxiv.py` | arXiv API | None | Academic papers on relevant theory and domain |
| `ssrn.py` | SSRN search | None | Economics, finance, social science preprints |

**Economic & energy data:**

| Adapter | Source | Auth | Use |
|---------|--------|------|-----|
| `fred.py` | FRED API | `FRED_API_KEY` (free) | Macro time series: GDP, inflation, rates, trade |
| `worldbank.py` | World Bank API | None | Development indicators, country-level data |
| `eia.py` | EIA API / RSS | `EIA_API_KEY` (free, optional) | Energy data: WTI/Brent prices, crude flows, gas; RSS mode works without key |

**Conflict & events:**

| Adapter | Source | Auth | Use |
|---------|--------|------|-----|
| `acled.py` | ACLED | `ACLED_API_KEY` + `ACLED_EMAIL` (free, apply) | Structured conflict events with fatalities + intensity signal mapped to theory calibration |
| `gdelt.py` | GDELT 2.0 | None | Global news tone score [-100, 100]; negative = conflict/crisis signal |
| `un.py` | UN News + Security Council RSS | None | UN resolutions, sanctions, ceasefire votes; SC articles carry higher relevance weight |

**News & media:**

| Adapter | Source | Auth | Use |
|---------|--------|------|-----|
| `news.py` | ~50 curated RSS feeds | None | Parallel feed fetch with keyword relevance scoring; `category=` param restricts to relevant feed subset |
| `guardian.py` | Guardian Open Platform | `GUARDIAN_API_KEY` (free) | High-quality article summaries; section filtering for world/business/politics |
| `newsapi.py` | NewsAPI.org | `NEWSAPI_KEY` (free, 100 req/day) | Single endpoint covering 80,000+ sources; broad keyword coverage |

**Curated RSS feed categories** (`news.py`):

| Category | Example sources |
|----------|----------------|
| `geopolitics` | BBC World, NYT World, Reuters, Al Jazeera, Foreign Policy, Foreign Affairs, Chatham House, CFR, Crisis Group, Carnegie |
| `defense` | Defense News, Breaking Defense, CSIS, RAND, IISS, Belfer Center, War on the Rocks, SIPRI, NATO |
| `economics` | Bloomberg Markets, FT, WSJ Markets, IMF Blog, VoxEU/CEPR, Brookings, Peterson Institute, NBER, World Bank Blog |
| `energy` | OilPrice.com, EIA Today in Energy, IEA, Oil & Gas Journal, Energy Monitor, S&P Global Commodities |
| `corporate` | Bloomberg, FT, WSJ Business, Harvard Business Review, The Economist Finance, Fortune Global |
| `sanctions` | OFAC Recent Actions (Treasury), Reuters, CFR Sanctions Tracker |
| `think_tanks` | Brookings, Carnegie, Chatham House, CSIS, RAND, Institute for Policy Studies, Wilson Center |
| `conflict` | Crisis Group, War on the Rocks, IISS, UN Security Council, UN News, Al Jazeera |

---

### Subsystem 3: SimSpec

The structured output of the Scoping Agent. SimSpec is the contract between intake and simulation — it fully describes a scenario in machine-readable form.

```
SimSpec
├── scenario_id          UUID
├── title                str
├── domain               enum: geopolitics | market | org | macro | social | composite
├── actors[]
│   ├── id               str
│   ├── type             enum: state | firm | regulator | population | coalition
│   ├── beliefs{}        dict: variable → initial probability distribution
│   ├── desires[]        list: goal objects with priority weights
│   └── capabilities{}   dict: action → capacity value
├── environment{}        dict: shared world-state variables
├── theories[]           list: theory module IDs selected by Theory Mapper
├── parameters{}         dict: theory param → value (from research + defaults)
├── timeframe
│   ├── start            date
│   ├── end              date
│   └── tick_unit        enum: day | week | month | quarter
├── uncertainties[]      list: variables with probability distributions
├── outcome_metrics[]    list: KPI definitions for the dashboard
└── research_sources[]   list: ResearchResult references used in construction
```

SimSpec is serialized to JSON and stored — it is the reproducible definition of a simulation. Any simulation can be reconstructed from its SimSpec.

---

### Subsystem 4: Simulation Engine

The core runtime. Domain-agnostic. Executes the scenario defined in a SimSpec.

**Agent Architecture (BDI):**

Each actor in the SimSpec becomes a BDI (Belief-Desire-Intention) agent at runtime:
- **Beliefs** — probability distributions over world-state variables, updated each tick via Bayesian inference
- **Desires** — weighted goal set (e.g., maximize territorial control, minimize economic damage, maintain coalition support)
- **Intentions** — current action plan, selected by a decision function that maximizes expected utility given beliefs and desires
- **Actions** — discrete moves (escalate, negotiate, sanction, invest, exit, etc.) with effects on the shared environment

**Tick Loop:**
```
for each tick:
    1. Environment updated (external shocks, data feed inputs)
    2. Each agent observes environment → updates beliefs (Bayesian)
    3. Each agent evaluates intentions against updated beliefs
    4. Each agent selects and executes action
    5. Actions resolve → environment updated
    6. Theory modules apply update rules (e.g., Richardson equations, multiplier effects)
    7. Outcome metrics recorded
    8. Snapshot trigger evaluated (scheduled or threshold-based)
```

**Theory Module Interface:**

Every theory module exposes:
- `parameters: dict` — configurable inputs
- `state_variables: dict` — variables it reads from and writes to environment
- `update(env, agents, tick) → env` — pure function applied each tick

This makes modules composable without modification.

---

### Subsystem 5: Data Feed Agent

A background agent that runs while a simulation is live. Monitors real-world signals and recalibrates simulation parameters automatically.

**Behavior:**
- Polls news and data adapters on a configurable schedule
- Passes new information to Claude API for relevance assessment and parameter delta estimation
- Applies approved parameter adjustments to the running simulation
- Logs each calibration event with source, reasoning, and delta applied
- Flags high-significance events to the consultant dashboard as alerts

This is the "stays current" capability — a simulation launched on Monday reflects Tuesday's events by Wednesday.

---

### Subsystem 6: API & Data Layer

**FastAPI backend** exposes:
- `POST /simulations` — create simulation from SimSpec
- `GET /simulations/{id}/state` — current simulation state
- `GET /simulations/{id}/metrics` — outcome KPI time series
- `POST /simulations/{id}/snapshots` — name and save a snapshot
- `GET /simulations/{id}/snapshots` — list snapshots
- `WS /simulations/{id}/stream` — real-time tick stream for dashboard
- `POST /forge/intake` — submit scenario text to Scoping Agent
- `GET /forge/intake/{session_id}` — poll scoping session state
- `GET /api/theories` — theory catalog (filterable by domain, keyword)
- `GET /api/theories/{id}` — theory detail (parameters, env keys, reference)
- `POST /api/theories/recommend` — Claude-powered ensemble recommendation
- `GET /api/ensembles` — list saved ensembles
- `POST /api/ensembles` — create named ensemble
- `GET /api/ensembles/{id}` — ensemble detail
- `POST /api/ensembles/{id}/fork` — fork an ensemble under a new name
- `DELETE /api/ensembles/{id}` — delete ensemble

**Data persistence:**
- Simulation state: serialized per-tick to append-only log
- Snapshots: named JSON blobs (SimSpec + state at point-in-time)
- Research cache: TTL-keyed per adapter + query hash

---

### Subsystem 7: Frontend

Three distinct views, unified codebase:

**ForgePage** — Scoping Agent UI
- Chat interface with streaming responses
- Background research status indicators (live as adapters return)
- SimSpec preview panel (builds in real-time as conversation progresses)
- "Launch simulation" CTA when SimSpec is complete

**DashboardPage** — Internal war-room view
- Live KPI panels with tick-by-tick updates (WebSocket)
- Agent belief and intention state viewer
- Timeline with named snapshot markers
- Replay controls — step forward/backward, branch from any snapshot
- Calibration event log (Data Feed Agent activity)
- Theory module parameter viewer

**PortalPage** — Client-facing SaaS view
- Clean, branded layout — no simulation machinery visible
- Key findings panels with narrative explanations
- Snapshot comparison (before/after scenarios)
- Export: PDF report, data CSV, shareable link

---

### Infrastructure

| Component | Technology | Deployment |
|-----------|-----------|------------|
| Backend | Python 3.12 / FastAPI | Railway (Dockerfile) |
| Simulation engine | Pure Python (asyncio) | Co-located with backend |
| Frontend | React 19 / Vite / TypeScript | Vercel |
| Database | PostgreSQL (Railway managed) | Railway |
| Cache | Redis (research results, session state) | Railway |
| AI | Claude API (claude-sonnet-4-6) | Anthropic |
| Scheduling | APScheduler | In-process |

This pattern is proven — it is exactly the architecture of the Hormuz proof of concept, operating in production.

---

## Proof of Concept

An internal proof of concept — the **Hormuz Crisis Simulation** — has already validated the core architecture:

- 18 BDI (Belief-Desire-Intention) agents with Bayesian belief updates
- Richardson escalation dynamics and dual termination theory branches
- OSINT scraping pipeline feeding live parameter adjustments
- Full war-room dashboard with replay, named snapshots, and narrative feed
- Deployed and running on cloud infrastructure

This is not a concept. The engine works. Crucible is the platform that makes it deployable across engagements.

---

*Prepared March 2026*

---

---

# Crucible — Development Plan

> Last updated: March 24, 2026
> Stack: Python 3.12 / FastAPI / React 19 / TypeScript / Railway + Vercel
> Tooling: Claude Code + custom skills (/research-theory, /research-data, /scaffold-sim)

---

## Phases at a Glance

| Phase | Weeks | Theme | Deliverable |
|-------|-------|-------|-------------|
| 1 | 1–3 | Foundation | Core engine running, Hormuz ported |
| 2 | 4–7 | Scoping Agent | Plain-language → running simulation end-to-end |
| 3 | 8–12 | Portal & Pilot | Client-facing SaaS, live engagement |

---

## Phase 1 — Foundation (Weeks 1–3)

Goal: a working simulation engine with the Hormuz scenario running inside the Crucible framework.

### Week 1 — Core Data Model & Theory Stubs

- [x] **`core/spec.py`** — SimSpec + BeliefSpec (decay_rate/process_noise/maps_to_env_key) + ActorSpec (observation_noise_sigma) + EnvKeySpec + SpecDiff (57 tests)
- [x] **`core/agents/base.py`** — BDIAgent + DefaultBDIAgent + AgentHydrationError + tick() coordinator + from_spec() factory (131 tests)
- [x] **`core/theories/base.py`** + **`__init__.py`** — TheoryBase ABC + @register_theory + get_theory/list_theories registry (32 tests)
- [x] **`core/theories/richardson_arms_race.py`** — Full Richardson ODE implementation with dt scaling, stability check, equilibrium() (30 tests)
- [ ] **`core/sim_runner.py`** — Domain-agnostic tick loop (initialize → tick → record → snapshot trigger)
- [x] **Theory implementations** — Fearon bargaining, Wittman-Zartman ripeness, Keynesian multiplier, Porter's Five Forces
- [x] **`requirements.txt`** — pinned deps (fastapi, uvicorn, pydantic, anthropic, apscheduler, sqlalchemy, httpx, redis)

### Week 2 — Research Adapters ✅

- [x] **`forge/researchers/base.py`** — ResearchResult dataclass + BaseAdapter interface (854 tests)
- [x] **`forge/researchers/arxiv.py`** — arXiv API adapter
- [x] **`forge/researchers/fred.py`** — FRED API adapter (series search + fetch, `FRED_API_KEY`)
- [x] **`forge/researchers/worldbank.py`** — World Bank indicators adapter
- [x] **`forge/researchers/ssrn.py`** — SSRN search adapter (HTML scrape + graceful fallback)
- [x] **`forge/researchers/news.py`** — ~50 curated RSS feeds across 8 categories (`FEEDS_BY_CATEGORY`, `category=` param)
- [x] **`forge/researchers/gdelt.py`** — GDELT 2.0 Doc API, tone score for conflict signal (no auth)
- [x] **`forge/researchers/guardian.py`** — Guardian Open Platform (`GUARDIAN_API_KEY`, free)
- [x] **`forge/researchers/newsapi.py`** — NewsAPI.org (`NEWSAPI_KEY`, 80k+ sources, free tier)
- [x] **`forge/researchers/acled.py`** — ACLED conflict events, fatalities + intensity signal (`ACLED_API_KEY` + `ACLED_EMAIL`)
- [x] **`forge/researchers/eia.py`** — EIA energy data, dual-mode RSS/API (`EIA_API_KEY` optional)
- [x] **`forge/researchers/un.py`** — UN News + Security Council RSS, SC bonus scoring (no auth)

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

### Week 5 — Simulation API + Theory Catalog

- [ ] **API route: `POST /simulations`** — Create + start simulation from SimSpec
- [ ] **API route: `GET /simulations/{id}/state`** — Current simulation state
- [ ] **API route: `GET /simulations/{id}/metrics`** — Outcome KPI time series
- [ ] **API route: `WS /simulations/{id}/stream`** — Real-time tick stream (WebSocket)
- [ ] **API route: `POST /simulations/{id}/snapshots`** — Save named snapshot
- [ ] **API route: `GET /simulations/{id}/snapshots`** — List snapshots
- [ ] **`api/services/sim_service.py`** — Async simulation manager (run in thread pool, track active sims)
- [ ] **`api/catalog.py`** — Theory catalog extractor (introspects registry at startup, no DB)
- [ ] **`api/routers/theories.py`** — `GET /api/theories`, `GET /api/theories/{id}`, `POST /api/theories/recommend`
- [ ] **`api/routers/ensembles.py`** — Ensemble CRUD (`data/ensembles/{id}.json` storage)

### Week 6 — Forge UI + Model Library

- [ ] **ForgePage** — Chat interface with streaming agent responses
  - [ ] Research status indicator (live as adapters return)
  - [ ] SimSpec progress panel (builds as conversation progresses)
  - [ ] "Launch simulation" button (appears when SimSpec complete)
- [ ] **DashboardPage** — War-room view (skeleton)
  - [ ] KPI panels (WebSocket-fed)
  - [ ] Snapshot timeline marker
  - [ ] Console/narrative feed
- [ ] **`/library` page** — Theory card grid with domain filter chips + search
  - [ ] `TheoryCard` component (name, domains, short description)
  - [ ] `TheoryDetailModal` (parameters table, env keys, academic reference)
- [ ] **`/ensembles` page** — List saved ensembles with load/fork/delete
- [ ] React project setup: Vite + TypeScript + Zustand stores (`theoryStore`, `ensembleStore`) + Tailwind

### Week 7 — End-to-End Integration + EnsembleBuilder

- [ ] **`EnsembleBuilder`** component on IntakePage — split panel: Claude recommends (left) + library browse (right) + current ensemble footer
- [ ] Full flow test: free-text description → scoping agent → ensemble selection → SimSpec → running sim → dashboard
- [ ] Test with Hormuz scenario: describe it in plain language, verify agent reconstructs a valid SimSpec and recommends the right theories
- [ ] **`api/services/data_feed_agent.py`** — Background calibration agent skeleton (APScheduler, news adapter hook)
- [ ] Error handling: scoping agent timeouts, adapter failures, sim crash recovery
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

### Week 9 — Client Portal

- [ ] **PortalPage** — Client-facing SaaS view
  - [ ] Clean branded layout (no simulation machinery)
  - [ ] Key findings panels with narrative
  - [ ] Snapshot comparison
  - [ ] Export: PDF report generation, data CSV download
  - [ ] "Models powering this analysis" panel (read-only ensemble summary with academic references)
- [ ] Auth layer: consultant login (internal) vs. client login (portal-only)
- [ ] Shareable link generation for portal snapshots

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
