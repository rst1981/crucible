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

**Force ask_user after update_simspec**  
*How to prevent the scoping agent from looping on update_simspec instead of asking the user*

After the first `update_simspec` call in `_agent_turn`, do NOT trust the LLM to call `ask_user` next — it will loop on `update_simspec` indefinitely.

The fix: intercept programmatically and call `_force_ask_user`, which makes a separate constrained Claude call with ONLY the `ask_user` tool available (`tool_choice: {"type": "any"}`). The model cannot call `update_simspec` because it's not in the tool list.

**Why:** Prompt-based instructions ("you MUST call ask_user next", SYSTEM REMINDER injections) are ignored when the model has already built up a long tool-use context. The only reliable fix is architectural — remove the unwanted tool from the available set.

**How to apply:** Any time a tool-use agent loops on a specific tool instead of progressing, the fix is a constrained follow-up call with reduced tool set, not stronger prompt instructions.

**Interview should be 2-3 questions max**  
*Interview sweet spot is 2 questions; 3 is the ceiling. Outcome focus + theories are the right human-input questions. Everything else is model-derived.*

The interview should ask 2 questions (sweet spot), maximum 3. Asking 1 is too few — client needs agency over both their decision focus and theoretical framing.

**Rule — ask these three:**
1. `outcome_focus` — "What decision does this simulation inform?" — always ask (human knows their decision)
2. `timeframe` — "How long should the scenario run, and from what start date?" — always ask (user specifies horizon)
3. `theories` — "Specific framework or let model decide?" — always ask, always offer "let model decide empirically" as default option

**Hard limits — never ask:**
- Metrics → model derives from outcome focus
- Actors → model derives from intake
- Initial conditions → model derives from research

**Why:** User noted (2026-03-28) that asking too many questions "overspecifies the model." But 1 question was too few — theories question gives client agency over framing without being prescriptive, especially with the empirical option. "2 is best, 3 max."

**How to apply:** `gap_detector.py` should flag `outcome_focus` (priority 0.99) and `theories` (priority 0.50) only. Theories gap should be suppressed if research has already surfaced a clear recommendation. All other gaps (metrics, actors, timeframe, initial_environment) should be auto-filled by the agent from research context.

**Theory selection — always offer empirical option**  
*The theories interview question must always include a "let the model decide empirically" option — no prescribed framework*

"Let the model decide empirically — no prescribed theoretical framework" must always be offered as a selectable option when the scoping agent asks about theories/theoretical framework.

**Why:** User explicitly asked for it during live testing (2026-03-28). When we build dashboard features, this option becomes critical — the empirical path lets the model select theories based on research rather than user prescription.

**How to apply:** In `_force_ask_user` when asking about `theories` gap, the suggested options should always include an explicit "empirical / let the model decide based on research" choice. Also applies to the ensemble review UI — add an "Accept model recommendation" default button.

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
*Generalized simulation platform for consulting firm — Week 6 complete, 1039 tests green, full Forge UI live*

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
[Scoping Agent] — fires background research immediately (arXiv, SSRN, FRED, World Bank, ~50 RSS feeds)
  - Research-grounded interview, not a form
  - Asks informed questions based on what research reveals
  - Outcome-focus deep-dive after consultant defines simulation goal
  - Builds SimSpec object conversationally
        ↓
[Theory Mapper] → [Sim Factory] → [Dashboard] → [Data Feed Agent]
```

---

## Research Sources
- arXiv, SSRN, FRED, World Bank — structured adapters
- ~50 curated RSS feeds: geopolitics, defense, economics, energy, corporate, think tanks
- GDELT, Guardian, NewsAPI, ACLED, EIA, UN adapters (Week 2 expansion)

## Theory Library
- Conflict/geopolitics: Richardson, Wittman-Zartman, Fearon
- Markets: Porter's Five Forces, supply/demand shocks, contagion, Cournot oligopoly
- Org/corporate: principal-agent, institutional theory, diffusion of innovation
- Macro/policy: Keynesian multipliers, regulatory shock models
- Discovered theories: auto-built from arXiv/SSRN papers via TheoryBuilder (smoke-tested, auto-approved or queued for review)

---

## Repo Structure
```
crucible/
├── CONTEXT.md               ← living design doc, commit each session
├── core/                    # generalized sim engine
│   ├── agents/              # BDI agent base classes
│   ├── theories/            # curated + discovered theory library
│   ├── sim_runner.py
│   └── spec.py              # SimSpec dataclass
├── forge/                   # scoping agent + research pipeline
│   ├── scoping_agent.py     # ScopingAgent + _force_ask_user + _run_outcome_deepdive
│   ├── gap_detector.py      # mandatory outcome_focus gap
│   ├── spec_builder.py
│   ├── session.py           # ForgeSession state machine
│   ├── theory_builder.py    # auto-builds theories from papers
│   ├── theory_mapper.py
│   └── researchers/         # arXiv, SSRN, FRED, World Bank, news + 6 new adapters
├── api/                     # FastAPI backend (port 8000)
│   └── routers/             # forge, theories, ensembles, simulations
├── web/                     # React/Vite/TS frontend (port 5173)
│   └── src/pages/           # ForgePage, LibraryPage, EnsemblesPage, DashboardPage
├── scenarios/hormuz/        # reference implementation #1
├── data/theories/pending/   # discovered theories awaiting review
└── restart.ps1              # kills ports 8000/5173, relaunches both
```

---

## Build Plan Status (as of 2026-03-27)

- ✅ **Week 1:** Core engine, SimSpec, theory library, BDI agents (268 tests)
- ✅ **Week 2:** Research adapters — arXiv, SSRN, FRED, World Bank, news + 6 new adapters (GDELT, Guardian, NewsAPI, ACLED, EIA, UN), ~50 curated RSS feeds
- ✅ **Week 3:** Hormuz scenario port, sim runner, snapshots
- ✅ **Week 4:** Scoping Agent + Forge API
- ✅ **Week 5:** Theory catalog API, ensemble CRUD, 77 new tests (1039 total)
- ✅ **Week 6:** React/Vite frontend — Forge, Library, Ensembles, Dashboard pages
- **Phase 3 (Weeks 8–12):** Client portal, continuous calibration agent, pilot engagement

---

## Key Bugs Fixed (recent)
- `_force_ask_user`: after first `update_simspec`, loop hands off to a constrained Claude call with ONLY `ask_user` available — prevents the agent looping on `update_simspec` indefinitely
- `outcome_focus` gap: mandatory gap (priority 0.99) that research cannot fill — forces agent to always ask the consultant
- `charmap` codec: theory_builder writes generated Python with `encoding="utf-8"`
- `_run_outcome_deepdive`: after `outcome_focus` is filled, runs targeted arXiv search + haiku summary of relevant theory frameworks; prepended to next interview turn
- Markdown rendering in ForgePage chat (react-markdown + remark-gfm)

---

## Open Questions
1. Name trademark check for "Crucible" — not yet done
2. Deployment pattern — likely Railway + Vercel
3. Agent model design review — flagged in Week 2, not yet revisited (BDI architecture, belief updates, theory interaction)

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

**Research pipeline fix list**  
*Running list of known research adapter issues and UX fixes identified during live testing (2026-03-28)*

# Research Pipeline Fix List

## Source errors (dead feeds / blocked)

### 404s — wrong URLs, need correct ones
- `cfr.org/rss/world` → 404 (tried `/rss/all` then `/rss/world`, both dead — find current CFR feed)
- `nato.int/cps/en/natohq/news.rss` → 404 (updated from old URL, still wrong)
- `sipri.org/rss.xml` → removed, need working replacement
- `cepr.org/vox/rss.xml` → removed, need working replacement (VoxEU)

### 403s — permanently blocked, already removed
- SSRN, Bloomberg markets feed, WSJ (feeds.a.dj.com), S&P Global, Breaking Defense

## Academic sources status (live test 2026-03-28)

| Source | Status | Notes |
|--------|--------|-------|
| OpenAlex | ✅ Working | Clean query formatter fixed zero-results issue |
| Semantic Scholar | ❓ Silent — no log entry | Likely timeout; needs investigation |
| arXiv | ⚠ 429 → retry → 200 | Retry works but adds 27s; IP gets blocked across session |
| FRED direct series | ✅ Working | DCOILWTICO, CPIAUCSL, UNRATE all 200 |
| FRED agent tool call | ❌ "no series found" | Agent passes space-separated IDs → hits search endpoint, not direct fetch |
| World Bank | ✅ Working | |
| News feeds | ✅ Mostly working | CFR/NATO still 404 |

## UX fixes needed

1. **"Research complete. Generating first question..." fires too early** — message comes after `_run_research` but agent does 2-3 more tool-call rounds before asking. Move message to after `_force_ask_user` fires.

2. **No streaming updates during agent interview loops** — user sees nothing for 2+ minutes while agent runs rounds 0, 1, 2. Need to yield per-round status chunks: `"Researching: oil price shock macroeconomic impact (round 2)...\n"`

3. **Semantic Scholar silent timeout** — needs error logging to surface in UI warnings.

4. **FRED agent tool** — agent calls `search_fred` with space-separated series IDs (e.g. "DCOILWTICO GASREGCOVW GDPC1") which routes to text search, not direct fetch. Fix: detect space-separated uppercase IDs in FRED adapter and split + fetch individually.

**Why:** User noticed 2+ minute silence with "Generating first question" message already shown. Critical for consulting UX — client must see research is still running.

**revisit_agent_model**  
*User wants to revisit the agent model design in the next session*

Revisit the agent model design — still open as of Week 6.

**Why:** User flagged this after the Week 2 research adapter sprint. Now in Week 6+ with a working Forge UI and scoping agent. A design review of the BDI architecture (belief update mechanisms, how agents interact with theory modules) is needed before Phase 3 work.

**How to apply:** Surface when planning Week 7-8 work or when the user asks about simulation agent design.

**Two-tier theory ensemble design**  
*Product vision for generic library ensemble + researched custom ensemble, presented side-by-side in ensemble review*

The theory ensemble review should offer two tiers:

**Tier 1 — Library ensemble** (always ready)
Domain-matched theories from the existing library. Fast, reliable fallback. Works even when academic sources are rate-limited.

**Tier 2 — Discovered ensemble** (research-driven)
Scenario-specific theories extracted fresh from academic papers during the intake run. Iran gets Hormuz closure economics + IRGC proxy dynamics. A banking crisis gets contagion diffusion. A supply chain scenario gets bullwhip dynamics.

**Ensemble review panel shows both side-by-side:**
- "Accept library recommendation"
- "Use researched ensemble"
- "Merge both" (combine unique theories from each)

**Why:** Current flow only offers the library ensemble. Discovered theories exist but aren't surfaced as a distinct option. The custom ensemble is what makes Crucible scenario-specific rather than generic — each simulation should have a different theory stack depending on the unique dynamics of the case.

**How to apply:** When building the ensemble review UI and backend:
- Run TheoryMapper against library → Tier 1
- Run TheoryBuilder against research results → Tier 2 (may be empty if sources rate-limited)
- Present both in ensemble review panel with merge option
- As discovered theories accumulate, they graduate into the library — shrinking the gap between tiers over time

<!-- memory:end -->

---

## How to Use This File

At the start of any Claude session on any device:

> "Read CONTEXT.md from the Crucible repo and use it as your full project context."

Or paste the contents directly. This file is the single source of truth for where we are and where we're going.
