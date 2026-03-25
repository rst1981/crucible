# Crucible — Approach, Deliberations, and Design

**To:** [Boss]
**From:** Development Team
**Date:** March 2026
**Status:** Architecture complete across all five layers. Engineering review passed. Implementation begins Week 1.

---

## 1. Why Agent-Based Simulation

Crucible is built on **agent-based modeling (ABM)** rather than equation-based system dynamics. This was the first major deliberation, and it shapes everything downstream.

Equation-based models — differential equations, econometric regressions, input-output matrices — are the right tool when the system can be expressed in closed form and the relationships between variables are stable and well-understood. They are efficient, interpretable, and well-suited to problems where aggregate behavior is what matters: modeling GDP growth, pricing a financial instrument, forecasting energy demand.

They are the wrong tool for the scenarios our clients bring. A trade war is not a differential equation. It is a set of governments reading signals from each other, forming beliefs, weighing priorities, and choosing responses — subject to what they are actually capable of doing and constrained by the costs already sunk. The dynamics emerge from the interactions between actors, not from a formula specified in advance. When the formula is wrong, you get a confident wrong answer.

**The BDI architecture** — Belief, Desire, Intention — is the design framework we chose for agents. It comes from the intersection of AI planning research and political theory, and it maps naturally onto how analysts already reason about the actors they study:

- **Beliefs** are what an actor thinks is true about the world. In Crucible, beliefs are probability distributions, not point estimates. A government's belief about a rival's military readiness is represented as a Beta distribution (a probability over a probability) or a Gaussian distribution (a continuous estimate with uncertainty). When the actor observes new signals, the belief updates via Bayesian conjugate updates. The Beta distribution has a closed-form posterior for binary events. The Gaussian uses a Kalman-style update for continuous measurements. The choice of prior is made per belief at scenario design time.

- **Desires** are what the actor is trying to achieve. Each desire targets a specific environment variable and has a direction (maximize or minimize) and a salience weight. A government might simultaneously desire to maximize trade revenue (weight 0.9), minimize domestic unemployment (weight 0.8), and minimize military exposure (weight 0.6). These weights can shift as the simulation evolves, modeling changing political conditions.

- **Intentions** are what the actor commits to doing, given beliefs, desires, and capabilities. Capabilities are explicit: each actor has a set of actions they can take, each with a capacity, a cost per use, a recovery rate per tick, and a cooldown period. An actor with a depleted military capability cannot escalate even if their beliefs and desires say they should. This constraint is what separates BDI from a simple utility-maximizer — real actors are bounded by what they can actually do.

The practical benefit: when a client says "what if China recalibrates its tolerance for economic pain," the analyst adjusts a desire weight or a belief prior. The model speaks the language the analyst already uses. The connection from parameter to behavior to outcome is traceable and explainable.

The proof of concept for this architecture is the Hormuz simulation — 18 BDI agents modeling the Strait of Hormuz crisis — which has been running live since early 2026. It is the reference implementation we are generalizing into this platform.

---

## 2. The Theory Library: Deliberate Pluralism

No single theory explains geopolitical crises, market shocks, and organizational change. The deliberation was about how to build a system that is theoretically grounded without being theoretically captured by any one framework.

The answer is **pluggable theory modules**: each a formal model from the academic literature, registered by name, composable with other modules, applicable to specific scenario domains. Multiple theories run simultaneously within one simulation, each updating shared environment variables that others read. The environment is the medium through which theories interact.

Each theory module is now fully specified — not just named. The architecture document contains the actual differential equations, the empirical parameter ranges from the original papers and subsequent empirical work, and the Python implementation stub a developer can code directly against. The deliberation behind each:

**Richardson Arms Race Model (Richardson, 1960).** The original formal model of mutual escalation dynamics. Two differential equations:

> dx/dt = k·y − a·x + g
> dy/dt = l·x − b·y + h

where k and l are defense coefficients (how much each party reacts to the other's arms), a and b are fatigue coefficients (economic and political constraints on spending), and g and h are grievance terms (baseline hostility independent of the opponent). The stability condition is a·b > k·l — if fatigue dominates reactivity, the system reaches an equilibrium; if reactivity dominates, the arms race is unstable and escalates without bound. Cold War empirical estimates place US-USSR defense coefficients at 0.3–0.5 and fatigue coefficients at 0.1–0.2. In Crucible, Richardson governs military readiness variables and is the primary theory for escalation dynamics.

**Fearon Bargaining Model (Fearon, 1995).** The most influential formal treatment of why rational actors fight rather than negotiate. The core insight is that war is inefficient — both parties bear costs, so a negotiated settlement that avoids those costs should always exist. Yet war occurs. Fearon's resolution: **private information** and **commitment problems**. Private information means each party knows things about its own resolve and capability that the other cannot verify; this creates a gap between each side's estimate of who would win, and if the gap exceeds combined war costs, no settlement both sides prefer to fighting exists. Commitment problems mean that even when a settlement range exists, agreements are difficult to enforce when relative power is shifting — the stronger party today has reason to fight rather than sign a deal it cannot enforce tomorrow. In Crucible, Fearon drives the probability of conflict at each tick based on the private information gap and the rate of power shift between actors.

**Wittman-Zartman Settlement / Ripeness Theory (Wittman 1979, Zartman 1985).** The formal conditions under which parties in conflict shift from fighting to negotiating. Wittman's expected utility framework: a party prefers settlement when its share of the negotiated outcome exceeds its expected value from continued conflict (probability of winning times the prize, minus war costs). Zartman adds the concept of a "mutually hurting stalemate" — the empirical observation that settlement is most likely when both parties simultaneously find continued conflict more costly than the status quo, and a "ripe moment" has been reached. In Crucible, Zartman governs the negotiation probability and runs alongside Richardson to model the full arc from escalation through stalemate to settlement. The two theories share environment variables: Richardson's military readiness outputs feed directly into Fearon's and Zartman's conflict probability calculations.

**Keynesian Multiplier / Fiscal Shock Propagation.** The standard framework for propagating a fiscal shock — sanctions, trade disruption, investment withdrawal, stimulus — through a macro economy. The multiplier M = 1 / (1 − MPC·(1−t) + m), where MPC is the marginal propensity to consume, t is the effective tax rate, and m is the marginal propensity to import. For developed economies, typical multipliers run 1.1–2.5; for small open economies with high import leakage, 0.8–1.5. Okun's Law links GDP change to unemployment. In Crucible, Keynesian runs in economic scenarios and in the economic dimension of geopolitical scenarios — sanctions on Iran reduce oil revenues, the multiplier propagates that shock through GDP, unemployment rises, which shifts domestic political pressure on the government, which feeds back into Richardson's grievance term.

**Porter's Five Forces (Porter, 1980).** Competitive dynamics in market structure, modeled as five continuously-valued forces: barriers to entry, supplier power, buyer power, substitute threat, and rivalry intensity. Industry profitability is a weighted function of these forces. In Crucible, Porter runs in corporate and market scenarios and is composable with Keynesian — a macro shock can alter barriers to entry as incumbents lose the capital advantage that kept competitors out.

The theory library is explicitly designed to grow. New theories are added with a Python decorator. The registry maps domain keywords to candidates. The TheoryMapper selects and composes theories deterministically, resolves conflicts between incompatible models (Fearon and Zartman make partially contradictory assumptions and cannot run simultaneously without mediation), and initializes parameters from empirical estimates gathered during the research phase.

---

## 3. Uncertainty as a First-Class Citizen

A single simulation run produces a single trajectory. That is the wrong deliverable for a consulting engagement. The question is never "what will happen" — it is "what is likely to happen, how sensitive is that to what we don't know, and what conditions would change the answer."

Crucible answers this through **Monte Carlo ensemble runs**: 100 parallel simulations of the same scenario, each with controlled variation in starting conditions, producing a distribution of outcomes rather than a single path.

The architecture distinguishes two sources of uncertainty, and this distinction is deliberate:

**Aleatory uncertainty** — genuine irreducible randomness. Agent decision-making has a stochastic component: given the same beliefs, desires, and capabilities, an actor does not always make the same choice. Different random seeds per run capture this.

**Epistemic uncertainty** — uncertainty about what we don't know. The analyst specifies confidence intervals around initial parameter values. Each ensemble run perturbs those values with Gaussian noise proportional to the stated confidence intervals, spanning the plausible parameter space.

The outputs: **percentile bands over time** (p10/p50/p90 fan charts for each metric at each tick), **final-tick distributions** with explicit probability statements ("P(Iranian oil exports fall below critical threshold) = 0.73"), and **threshold probabilities** pre-computed at standard levels. Two ensemble runs — two scenarios, two policy choices, two sets of assumptions — can be compared metric by metric using **Wasserstein distance** (Earth Mover's Distance), a measure of how far one distribution has moved relative to another. This answers the question: if we implement Policy A instead of Policy B, how much does the distribution of outcomes actually change, and on which metrics does it matter most?

The thread-safety of this system required careful attention during engineering review. With eight ensemble runs executing in parallel on a thread pool, a naive implementation using Python's global random state would have silently broken reproducibility — the same scenario with the same seed would produce different results each run, with no error and no signal. This was caught and fixed before implementation: each run uses an isolated `random.Random(seed)` instance, threaded through the simulation engine and every agent.

The key principle: **the width of the uncertainty bands is itself a finding**. A narrow p10-p90 spread means the conclusion holds even if the starting parameters are wrong. A wide spread means the outcome is sensitive to what we don't know — which is worth telling a client explicitly, rather than hiding behind a single-trajectory forecast.

---

## 4. The Calibration Loop: Living Models

Most simulation models are run once, delivered, and become obsolete the moment the world changes. Crucible is designed as a **living model**: the simulation stays calibrated as real-world events evolve.

Every running simulation has a `DataFeedAgent` — a scheduled process checking live data sources every six hours: FRED economic indicators, World Bank data, news feeds, academic preprint servers. It compares the latest readings to current parameter values. When it detects drift above a threshold (5% on the normalized scale by default), it generates a **CalibrationProposal**: a structured recommendation to update a specific parameter, with the data source, old value, proposed new value, a confidence score, and a plain-English rationale ready for consultant review.

The consultant approves or rejects. On approval:

1. A new **version** of the scenario specification is created — a branched copy with the updated parameter.
2. The change is recorded: what changed, why, who authorized it, which data source triggered it.
3. If the simulation is currently running, the update is applied at the next tick boundary.
4. The prior version is preserved in a **version directed acyclic graph** — every fork of every scenario is retained, diffable, and recoverable.

The version DAG means a consultant can compare the current model to where it started in January, diff any two versions field by field, branch a new scenario from any prior version, and understand the full reasoning trail behind every parameter in the current model.

The deliberation on human-in-the-loop was central. Fully automatic recalibration was considered and rejected. Data sources are imperfect. The mapping from a FRED series to a normalized simulation parameter requires domain judgment the system cannot substitute for. Automatic recalibration would produce a model that confidently reflects its data sources, which may or may not reflect the phenomenon being modeled. The consultant is the expert. The system surfaces the evidence and the recommendation. The decision stays with the analyst.

The broader principle: **a model that is known to be drifting is more valuable than a model assumed to be current.** The CalibrationProposal queue is a real-time feed of model divergence from reality. A consultant with three pending proposals knows exactly where their model is diverging. A consultant with no such system is operating on assumptions they cannot see.

---

## 5. The Scoping Agent: Research Before Questions

The intake experience — how a consultant turns a scenario description into a running simulation — is the product. Everything else is infrastructure. The deliberation was about what the intake agent does, in what order, and why.

The naive approach is a form: "Enter your actors. Select your theories. Fill in parameters." This produces shallow scenarios. Consultants fill in what they know and leave blank what they don't. The model inherits the analyst's blind spots.

The chosen approach: **research first, then ask.** When the consultant submits a scenario description, the scoping agent immediately fires parallel research queries before generating a single question — academic preprints, working papers, FRED economic indicators, World Bank data, news feeds. These run in parallel. By the time the first question is ready, the agent has read the literature, found parameter estimates from empirical studies, identified the dominant theoretical frameworks for this type of scenario, and flagged what data is available for calibration.

The conversation follows a state machine with six phases: intake → parallel research → dynamic interview (maximum five questions) → theory mapping → validation → complete. The five-question constraint is deliberate. It forces prioritization. The agent uses a gap detection system that scores what is missing from the scenario specification by priority — actors and their relationships are the highest priority (a simulation with the wrong actors is wrong in a way no parameter adjustment can fix), followed by theory selection, environment parameters, timeframe, metrics, and uncertainty ranges. The five questions target the highest-priority gaps first.

The **TheoryMapper** is deterministic: given domain signals and research context, it applies a rule-based selection process, resolves conflicts between incompatible theories using a priority table, and initializes parameters from empirical estimates in the research context. The theory selection rationale is preserved in the scenario specification and can be reviewed by the analyst before the simulation runs.

The design principle: the scoping agent should feel like a senior analyst who has already done the reading. It knows what the literature says is important for this type of scenario. It knows what data exists. It asks questions a generalist could not ask.

---

## 6. The Client Layer: From Model to Deliverable

The simulation runs for the consultant. The client sees the conclusions.

Crucible has two distinct user layers. The **Forge** layer — internal to the consulting firm — is where consultants interact with the scoping agent, run simulations, manage ensemble runs, inject shocks, take named snapshots, and calibrate parameters. It is a full-featured analytical workspace.

The **Portal** layer is what clients see: a clean, read-only executive interface. No model internals. No raw parameters. No normalized floats. The Portal shows the narrative feed generated by the simulation — plain-English commentary written by the AI narrative agent at significant events — outcome metrics displayed with proper units and labels, named snapshot comparison tables, and a report download button. The consultant controls what the client can access.

This separation required a formal **authorization model**: three roles (admin, consultant, client) with an organizational hierarchy (organization → project → simulation). A client can only see simulations their consultant has explicitly shared. A consultant sees all simulations in their organization. The authorization is enforced at the API layer, not the UI layer — a client who knows a simulation ID cannot retrieve data they were not granted access to.

The display translation layer is where a great deal of care was spent. All values inside the simulation engine are normalized to [0, 1] — necessary for theories written in different units to share a common environment. But a client deliverable cannot show `iranian_sanctions_severity: 0.742`. Every environment key is annotated with a scale factor, a physical unit, and a display name. The engine operates in normalized space; the API translates to display space before serving any output. The value `0.742` on a key annotated with scale `100` and unit `billion USD` becomes `74.2 billion USD` in every report, chart, and narrative entry. The narrative agent — which generates the plain-English commentary — uses display values throughout. A consultant can paste a narrative entry directly into a client deck.

The report export produces three formats: structured JSON for the Portal's chart components, Markdown for consultant review and editing, and PDF for client delivery. Each format is assembled from the same underlying data — the same narrative entries, the same snapshot tables, the same ensemble distributions — with the rendering adapted to the consumer.

---

## 7. What Was Built Before Coding Started

The architecture for this platform was designed, reviewed, and corrected before a single line of implementation code was written. That sequence was deliberate.

The full set of architecture documents:

- **Engine architecture** — SimSpec data contract, BDI agent design, theory plugin system, simulation tick loop
- **Forge architecture** — scoping agent design, research pipeline, theory mapper, gap detection, conversational state machine
- **API architecture** — persistence layer, Monte Carlo ensemble runner, narrative agent, data feed agent, SimSpec versioning, full REST and WebSocket API surface
- **Theory architecture** — the actual mathematics of all five theory modules, with empirical parameter ranges from the source papers and Python implementation stubs a developer can code directly against
- **Portal architecture** — full React component tree, TypeScript data types, Zustand state management, WebSocket connection management, auth model, report download flow

The engineering review of the API architecture before implementation identified **sixteen issues** that would have caused production failures. The most consequential: a thread-safety bug that would have silently broken ensemble reproducibility from day one; a synchronous API client call inside an asynchronous event loop that would have stalled every client-facing interaction during simulation runs; and a second event loop created inside the calibration scheduler that would have crashed on the first real calibration cycle with a runtime error difficult to diagnose without deep asyncio knowledge.

All sixteen were caught on paper and corrected in the architecture documents. The cost of finding a design error in a document is one conversation. The cost of finding it in production is a client relationship.

The deferred items are written down — thirteen of them, with full context, priority, and where-to-start for each. Nothing was forgotten. Nothing was hand-waved. The items that are not being built in the first twelve weeks are explicitly deferred, with the reasoning recorded.

The architecture is now locked. Implementation begins with `core/spec.py` — the SimSpec data contract that every other component in the system depends on.
