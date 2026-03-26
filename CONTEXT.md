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

**Date:** March 26, 2026

**Phase:** Week 2 in progress — theory library expanded.

**Test coverage: 769 tests, all passing.**

**Implemented (Week 1):**
- `core/spec.py` — SimSpec, BeliefSpec, ActorSpec, TheoryRef, EnvKeySpec, SpecDiff, diff_simspecs(), branch_simspec()
- `core/agents/base.py` — BDIAgent ABC, DefaultBDIAgent, BetaBelief, GaussianBelief, tick() coordinator (decay→observe→update→decide), from_spec() factory, thread-safe RNG
- `core/theories/base.py` + `__init__.py` — TheoryBase ABC, TheoryStateVariables, @register_theory decorator, get_theory()/list_theories() registry
- `core/theories/richardson_arms_race.py` — full Richardson ODE (k/l/a/b/g/h, dt scaling, stability warning, equilibrium())
- `core/theories/fearon_bargaining.py` — private info + commitment problem conflict mechanisms
- `core/theories/wittman_zartman.py` — MHS + ripeness + negotiation probability
- `core/theories/keynesian_multiplier.py` — multiplier, signed shock encoding, Okun's Law
- `core/theories/porter_five_forces.py` — five force variables + profitability
- `core/sim_runner.py` — tick engine, snapshots, triggers, thread-safe, asyncio-compatible
- `requirements.txt` — pinned Python deps

**Implemented (Week 2, session 1 — theory library expansion):**
- `core/theories/bass_diffusion.py` — Bass (1969) S-curve adoption. p/q params, GDP→imitation amplification, trade disruption→innovation suppression. `market_id` param for multi-instance. Enables: tech adoption, market entry, disruption, EV/energy transition scenarios.
- `core/theories/sir_contagion.py` — SIR compartmental model. S+I+R=1 renormalized per tick. β amplified by trade disruption. `contagion_id` param for multi-instance (banking, supply chain, cyber, etc.). Enables: financial contagion, supply chain failure, crisis spread scenarios.
- `core/theories/opinion_dynamics.py` — Deffuant (2000) bounded confidence mean-field model. Tracks mean + polarization (normalized std dev). ε controls convergence/fragmentation threshold. Urgency injects polarization; media bias drifts mean. `domain_id` param for multi-instance. Enables: political, reputational, ESG, social license scenarios.

**Implemented (Week 2, session 2 — medium priority theories):**
- `core/theories/principal_agent.py` — Holmström (1979) incentive alignment. β (incentive slope), intrinsic_motivation, risk_aversion, monitoring_intensity (external). Effort adjusts with inertia. Outputs effort_level, compliance, shirking_risk, incentive_alignment. `agent_id` param. Enables: corporate governance, outsourcing, regulation, public sector scenarios.
- `core/theories/cournot_oligopoly.py` — Cournot (1838) quantity-setting duopoly. Best-response tatônnement dynamics. GDP modulates demand. Outputs quantities, price, margins, HHI concentration. `nash_equilibrium()` method. `market_id` param. Enables: competitive strategy, pricing, antitrust scenarios.
- `core/theories/regulatory_shock.py` — Regulatory event propagation. Shock injected externally; theory models compliance cost, logistic adaptation, market exit risk, incumbent competitive advantage. GDP slows adaptation. Porter barriers amplify advantage. `regulation_id` param. Enables: carbon pricing, GDPR, financial regulation, antitrust scenarios.

**Implemented (Week 2, session 3 — lower priority theories):**
- `core/theories/experience_curve.py` — Wright (1936) Learning Curve. `b = -log(lr)/log(2)`; per-tick ratio form `C_new = C_old × (Q_new/Q_old)^(-b)`. Seeded at `_Q_SEED=0.01` to avoid log(0). `curve_id` param for multi-instance (ev_battery, solar_panel, etc.). Enables: tech cost forecasting, energy transition, manufacturing scenarios.
- `core/theories/hotelling_cpr.py` — Hotelling (1931) scarcity rent + Ostrom (1990) CPR governance. CPR blends uncapped extraction with sustainable-yield cap via governance parameter. Hotelling price path: rent grows at discount_rate, anchored by stock depletion signal. `resource_id` param. Enables: energy, water, mining, fisheries, sustainability scenarios.

**Implemented (Week 2, session 4 — 9 additional theories):**
- `core/theories/minsky_instability.py` — Minsky (1986) financial instability. Compartmental model: hedge→speculative→Ponzi phases. Boom/stress signals drive phase transitions. crash_risk nonlinear in Ponzi fraction. `cycle_id` param. Enables: debt cycles, banking crises, bubble scenarios.
- `core/theories/solow_growth.py` — Solow (1956) neoclassical growth. Normalized Cobb-Douglas ODE (κ^α convergence). TFP shock param. `economy_id` param. Enables: development economics, long-run growth, sanctions, post-conflict recovery.
- `core/theories/lotka_volterra.py` — Lotka-Volterra predator-prey. Incumbent (prey) vs challenger (predator) market dynamics. innovation_boost param (external). `ecosystem_id` param. Enables: market disruption, incumbent vs disruptor, ecological/industry competition.
- `core/theories/is_lm.py` — Hicks (1937) IS-LM. Dynamic IS curve (goods market) + LM curve (money market). fiscal_stimulus and money_supply are external inputs. Writes output_gap, interest_rate, investment, is_lm_gap. `market_id` param. Enables: monetary/fiscal policy, central bank scenarios.
- `core/theories/schumpeter_disruption.py` — Schumpeter (1942) creative destruction. Incumbent logistic growth vs innovator S-curve. R&D investment (external) boosts innovator. `creative_destruction` = γ×I×N. `innovation_id` param. Enables: tech disruption, industry transformation, startup scenarios.
- `core/theories/stackelberg_leadership.py` — Stackelberg (1934) leader-follower. Leader commits first (slower), follower best-responds (faster). `stackelberg_equilibrium()` method. `market_id` param. Enables: supply chain power, first-mover advantage, market entry.
- `core/theories/efficiency_wages.py` — Shapiro-Stiglitz (1984) efficiency wages. NSC: monitoring×wage_premium/effort_cost drives effort. Unemployment as discipline device. `wage_premium` is external (set by firms). `labor_id` param. Enables: labor markets, corporate governance, gig economy.
- `core/theories/cobweb_market.py` — Ezekiel (1938) cobweb theorem. Lagged supply response creates price oscillations. Convergent when demand_elasticity > supply_elasticity. `supply_shock`/`demand_shock` external inputs. `market_id` param. Enables: commodity markets, housing, agriculture.
- `core/theories/fisher_pry.py` — Fisher-Pry (1971) technology substitution. Logistic substitution df/dt=α×f×(1-f). Cost reduction (from experience curve) and GDP accelerate substitution. `tech_id` param. Enables: energy transition, format wars, EV adoption, platform displacement.

**Architecture documents (all current):**
- `ARCHITECTURE.md` — engine: SimSpec, BDIAgent, TheoryBase, SimRunner design
- `ARCHITECTURE-THEORIES.md` — full math for all 5 original theory modules with empirical parameter ranges
- `ARCHITECTURE-FORGE.md` — ForgeSession, ScopingAgent, TheoryMapper, GapDetector
- `ARCHITECTURE-API.md` — persistence, EnsembleRunner, NarrativeAgent, full FastAPI surface (incl. 16 pre-impl fixes)
- `ARCHITECTURE-PORTAL.md` — React 19 frontend, Zustand stores, auth model
- `TODOS.md` — 13 deferred items with priority and context
- `Amir.md` — 7-section stakeholder briefing

**Theory library — complete inventory (22 theories):**

| ID | Domain | What it models |
|----|--------|----------------|
| `richardson_arms_race` | conflict/geopolitics | Mutual arms escalation ODE |
| `fearon_bargaining` | conflict/crisis | War onset (private info + commitment problem) |
| `wittman_zartman` | conflict/mediation | War termination, MHS, ripeness |
| `keynesian_multiplier` | macro/sanctions | Fiscal shocks, multiplier, Okun's Law |
| `porter_five_forces` | market/strategy | Industry competitive structure |
| `bass_diffusion` | market/technology | S-curve adoption (innovation + imitation) |
| `sir_contagion` | contagion/risk | S/I/R spread and recovery |
| `opinion_dynamics` | social/political | Bounded confidence polarization |
| `principal_agent` | governance/org | Incentive alignment, effort, shirking |
| `cournot_oligopoly` | market/strategy | Quantity competition, Nash equilibrium |
| `regulatory_shock` | regulation/policy | Compliance cost, adaptation, exit risk |
| `experience_curve` | technology/manufacturing | Wright's Law unit cost learning |
| `hotelling_cpr` | resources/sustainability | Scarcity rent + CPR governance |
| `minsky_instability` | finance/banking | Debt cycle phases (hedge→speculative→Ponzi) |
| `solow_growth` | macro/development | Capital accumulation, TFP, SS convergence |
| `lotka_volterra` | market/disruption | Predator-prey competitive dynamics |
| `is_lm` | macro/monetary | IS-LM output gap + interest rate equilibrium |
| `schumpeter_disruption` | innovation/technology | Creative destruction, incumbent displacement |
| `stackelberg_leadership` | market/game_theory | Leader-follower first-mover advantage |
| `efficiency_wages` | labor/governance | Shapiro-Stiglitz effort + unemployment |
| `cobweb_market` | commodity/agriculture | Lagged supply price oscillations |
| `fisher_pry` | technology/substitution | Logistic tech-for-tech replacement |

**Cross-theory data flow (new additions):**
- Bass reads `keynesian__gdp_normalized` + `global__trade_volume`
- SIR reads `global__trade_volume`
- Opinion reads `global__urgency_factor` (written by Zartman/agents)

**Week 2 — remaining:**
1. Research adapters (arXiv, SSRN, FRED, World Bank, news/RSS)
2. Hormuz scenario port (`scenarios/hormuz/`)
3. Roadmap discussion: path to launchable app

**Reference implementation:**
- Hormuz sim at `d:/dev/hormuz-sim-dashboard` — 18 BDI agents, running live, port as scenario #1 in Week 3

---

## Claude Working Rules

<!-- memory:start -->

### Feedback & Working Preferences

**CONTEXT.md auto-sync on conversation end**  
*User wants CONTEXT.md updated with session progress and auto-committed/pushed to git whenever a conversation ends*

Always keep CONTEXT.md up to date with what happened in the current session. On conversation end, the Stop hook in `.claude/settings.json` will auto-commit and push it.

**Why:** User wants the context doc to serve as a persistent cross-session record, committed to git so it's always current on GitHub. Memory files are also mirrored into CONTEXT.md so the git repo is self-contained.

**How to apply:**
- Before the conversation ends, update `## Current Status` in CONTEXT.md (completed work, updated next steps)
- If new working rules / feedback were learned this session, also update `## Claude Working Rules` in CONTEXT.md
- Commit and push (or let the Stop hook handle it if no manual commit is needed)
- Keep the memory files (`C:\Users\rchtk\.claude\projects\d--dev-crucible\memory\`) and CONTEXT.md `## Claude Working Rules` in sync

**Use python -m uvicorn on this machine**  
*uvicorn CLI not on PATH because user-site Scripts dir missing from PATH; always use python -m uvicorn*

Always use `python -m uvicorn` instead of bare `uvicorn` when starting the API server.

**Why:** uvicorn is installed in user-site packages (`AppData\Roaming\Python\Python314\site-packages`) but the corresponding Scripts directory is not on PATH. The `uvicorn` command is not found in bash.

**How to apply:** Any time you need to start the FastAPI server, use `python -m uvicorn api.main:app ...` instead of `uvicorn api.main:app ...`.

**Never CLI deploy to Vercel**  
*Never run npx vercel or vercel CLI deploy commands — it creates duplicate projects. Only deploy via git push.*

NEVER run `npx vercel --prod` or any Vercel CLI deploy command. It creates duplicate Vercel projects (hormuz-sim-dashboard) that the user has had to delete twice.

**Why:** The CLI auto-creates new projects when run from subdirectories or when linking is ambiguous. The user's correct project is `hormuz-sim` and it deploys via GitHub webhook on git push.

**How to apply:** For frontend deployments, only use `git push`. Never touch Vercel CLI. If there's a Vercel build issue, tell the user to fix it in the Vercel dashboard — don't try to work around it with CLI deploys.

### Project Context

**Crucible — Agentic Simulation Platform**
*Generalized simulation platform for consulting firm — Week 2 in progress, 769 tests green*

Crucible is a proprietary agentic simulation platform enabling the firm to rapidly build, run, and deliver scenario-based models across market sectors for public and private sector clients.

**Why:** Built by one developer (+ Claude) to generalize the Hormuz sim architecture into a reusable consulting platform. Target: 48 hours from client brief to running simulation.

**How to apply:** This is the primary working project. Hormuz sim is reference scenario #1.

---

## Vision

"Hit go and it goes." — Consultant describes a scenario → system researches, scaffolds, runs, and keeps sim calibrated automatically.

### Two Layers
- **Forge** (internal sandbox) — scoping agent → research → scaffold → run
- **Portal** (client SaaS) — clean dashboard, snapshots, exportable reports

---

## Core Loop

```
Free-form text input
        ↓
[Scoping Agent] — fires background research immediately (arXiv, SSRN, FRED, World Bank, news)
  - Research-grounded interview, not a form
  - Asks informed questions based on what research reveals
  - Iterates with user, surfacing domain perspectives
  - Builds SimSpec object conversationally
        ↓
[Theory Mapper] → [Sim Factory] → [Dashboard] → [Data Feed Agent]
```

---

## Research Sources (design-time + runtime)
- arXiv, SSRN, FRED, World Bank, news/OSINT

## Theory Library
- Conflict/geopolitics: Richardson, Wittman-Zartman, Fearon
- Markets: Porter's Five Forces, supply/demand shocks, contagion
- Org/corporate: principal-agent, institutional theory, diffusion of innovation
- Macro/policy: Keynesian multipliers, regulatory shock models

---

## Repo Structure
```
crucible/
├── CONTEXT.md               ← living design doc, commit each session
├── PROPOSAL.md              ← internal pitch document
├── core/                    # generalized sim engine
│   ├── agents/              # BDI agent base classes
│   ├── theories/            # curated theory library
│   ├── sim_runner.py
│   └── spec.py              # SimSpec dataclass
├── forge/                   # scoping agent + research pipeline
│   ├── scoping_agent.py
│   ├── researchers/         # arXiv, SSRN, FRED, World Bank, news adapters
│   └── theory_mapper.py
├── api/                     # FastAPI backend
├── web/                     # React frontend (ForgePage, DashboardPage, PortalPage)
├── scenarios/hormuz/        # reference implementation #1
└── data/
```

---

## Build Plan (12 weeks, 1 developer + Claude)

- **Phase 1 (Weeks 1–3):** Core engine, SimSpec, theory library, research adapters, Hormuz port
- **Phase 2 (Weeks 4–7):** Scoping agent, Forge UI, end-to-end plain-language → running sim
- **Phase 3 (Weeks 8–12):** Client portal, continuous calibration agent, pilot engagement

---

## Open Questions
1. Name trademark check for "Crucible" — not yet done
2. Deployment pattern — likely Railway + Vercel (same as Hormuz)
3. Research skills (custom Claude Code skills) — user is researching gstack-style skill files for /research-theory, /research-data etc.
4. Scenario definition standardization — resolved: SimSpec populated via scoping agent

---

## Status

**Date:** March 26, 2026. **Week 2 in progress.**

### Delivered (769 tests, all green):

**Week 1 — core engine:**
- `core/spec.py`, `core/agents/base.py`, `core/sim_runner.py`
- `core/theories/`: richardson_arms_race, fearon_bargaining, wittman_zartman, keynesian_multiplier, porter_five_forces

**Week 2, session 1 — theory library expansion (high priority):**
- `core/theories/bass_diffusion.py` — S-curve adoption. market_id param.
- `core/theories/sir_contagion.py` — SIR compartmental contagion. contagion_id param.
- `core/theories/opinion_dynamics.py` — Deffuant bounded confidence. domain_id param.

**Week 2, session 2 — theory library expansion (medium priority):**
- `core/theories/principal_agent.py` — Holmström incentive alignment. agent_id param.
- `core/theories/cournot_oligopoly.py` — Cournot duopoly + Nash equilibrium. market_id param.
- `core/theories/regulatory_shock.py` — Regulatory event propagation + adaptation. regulation_id param.

**Week 2, session 3 — theory library expansion (lower priority):**
- `core/theories/experience_curve.py` — Wright's Law learning curve. curve_id param.
- `core/theories/hotelling_cpr.py` — Hotelling scarcity rent + Ostrom CPR governance. resource_id param.

**Week 2, session 4 — 9 additional theories:**
- `minsky_instability`, `solow_growth`, `lotka_volterra` (high priority)
- `is_lm`, `schumpeter_disruption`, `stackelberg_leadership` (medium priority)
- `efficiency_wages`, `cobweb_market`, `fisher_pry` (lower priority)

**22 theories total. All instance-namespaced via ID params (multi-instance per sim).**

### Next: Week 2 remaining
- Research adapters (arXiv, SSRN, FRED, World Bank, news/RSS)
- Hormuz scenario port (`scenarios/hormuz/`)
- Roadmap discussion: path to launchable app

**Hormuz Crisis Simulation — Reference Scenario #1**  
*Proof of concept sim that Crucible generalizes. Deployed and running. Key architecture and operational notes.*

Operation Epic Fury — Strait of Hormuz crisis simulation. War start: Feb 25, 2026.

**Why:** Proof of concept that validated the core architecture. Becomes Crucible reference scenario #1.

**How to apply:** Reference this when designing Crucible's core engine. Port to `scenarios/hormuz/`.

---

## Deployment
- **Local:** `d:/dev/hormuz-sim-dashboard`
- **GitHub:** `rst1981/hormuz-sim` (branch: main)
- **Backend:** Railway at `hormuz-sim-production-9505.up.railway.app` (Dockerfile.api)
- **Frontend:** Vercel at `hormuz-sim.vercel.app` — Root Directory=`web`, Framework=Vite

## Architecture
- 18 BDI agents with Bayesian belief updates
- Richardson escalation + Wittman-Zartman / Fearon DIA termination theory branches
- FastAPI backend + React 19 frontend
- OSINT scraping → Claude API analysis (batched 25/call) → parameter adjustments
- Named baseline snapshots, APScheduler daily saves
- `asyncio.to_thread` for Claude API calls (avoid blocking async loop)

## Key Operational Rules
- Always use `python -m uvicorn` — Scripts not on PATH
- NEVER use Vercel CLI — only `git push` to deploy frontend

<!-- memory:end -->

---

## How to Use This File

At the start of any Claude session on any device:

> "Read CONTEXT.md from the Crucible repo and use it as your full project context."

Or paste the contents directly. This file is the single source of truth for where we are and where we're going.
