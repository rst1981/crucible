# Crucible — Approach, Deliberations, and Design

**To:** [Boss]
**From:** Development Team
**Date:** March 2026
**Status:** Architecture complete and reviewed. Implementation begins Week 1.

---

## 1. Why Agent-Based Simulation

Crucible is built on **agent-based modeling (ABM)** rather than equation-based system dynamics. This was the first major deliberation, and it shapes everything downstream.

Equation-based models — differential equations, econometric regressions, input-output matrices — are the right tool when the system can be expressed in closed form and the relationships between variables are stable and well-understood. They are efficient, interpretable, and well-suited to problems where the aggregate behavior is what matters: modeling GDP growth, pricing a financial instrument, forecasting energy demand.

They are the wrong tool for the scenarios our clients bring. A trade war is not a differential equation. It is a set of governments reading signals from each other, forming beliefs, weighing priorities, and choosing responses — subject to what they are actually capable of doing and constrained by the costs already sunk. The dynamics emerge from the interactions between actors, not from a formula specified in advance. When the formula is wrong, you get a confident wrong answer.

**The BDI architecture** — Belief, Desire, Intention — is the design framework we chose for agents. It comes from the intersection of AI planning research and political theory, and it maps naturally onto how analysts already reason about the actors they study:

- **Beliefs** are what an actor thinks is true about the world. In Crucible, beliefs are not point estimates — they are probability distributions. A government's belief about a rival's military readiness is represented as a Beta distribution (a probability over a probability) or a Gaussian distribution (a continuous estimate with uncertainty). When the actor observes new signals, the belief updates — mathematically, via Bayesian conjugate updates. The Beta distribution has a closed-form posterior when observing binary events. The Gaussian uses a Kalman-style update when absorbing continuous measurements. The choice of prior distribution type is made per belief at scenario design time, not hardcoded.

- **Desires** are what the actor is trying to achieve. Each desire targets a specific environment variable and has a direction (maximize or minimize) and a salience weight. A government might simultaneously desire to maximize trade revenue (weight 0.9), minimize domestic unemployment (weight 0.8), and minimize military exposure (weight 0.6). The weights are not fixed — they can shift as the simulation evolves, modeling changing political conditions.

- **Intentions** are what the actor actually commits to doing, given their beliefs, desires, and capabilities. Capabilities are explicit: each actor has a set of actions they can take, each with a capacity, a cost per use, a recovery rate, and a cooldown. An actor with a depleted military capability cannot escalate even if their beliefs and desires say they should. This constraint is what separates a BDI model from a simple utility-maximizer — real actors are bounded by what they can actually do.

The practical benefit is that when a client says "what if China recalibrates its tolerance for economic pain," the analyst adjusts a desire weight or a belief prior. The model speaks the language the analyst already uses. The connection from parameter to behavior to outcome is traceable and explainable.

The proof of concept for this architecture is the Hormuz simulation — 18 BDI agents modeling the Strait of Hormuz crisis — which has been running live since early 2026 and is the reference implementation we are generalizing into this platform.

---

## 2. The Theory Library: Deliberate Pluralism

No single theory explains geopolitical crises, market shocks, and organizational change. The deliberation was about how to build a system that is theoretically grounded without being theoretically captured by any one framework.

The answer is **pluggable theory modules**: each a formal model from the academic literature, registered by name, composable with other modules, and applicable to specific scenario domains. Multiple theories can run simultaneously within one simulation, each updating shared environment variables that others read. The environment is the medium through which theories interact.

The current library, and the reasoning behind each selection:

**Richardson Arms Race Model (1960).** Lewis Fry Richardson's mathematical treatment of mutual arms race dynamics — the original formal model of how two actors' military spending drives each other upward through perceived threat. It captures a specific feedback loop: when Actor A increases capability, Actor B's threat perception rises, leading B to increase capability, which feeds back into A's perception. The model has well-documented empirical support from Cold War data and remains the foundational framework for escalation dynamics. In Crucible, Richardson runs as a theory module alongside BDI agents: the theory governs the structural dynamics of the escalation spiral, while agents make the individual decisions within it.

**Wittman-Zartman Settlement Theory.** Wittman (1979) and Zartman (1985, "ripeness theory") formalize the conditions under which parties in conflict prefer negotiated settlement to continued fighting. The core insight: parties settle when they share a pessimistic assessment of their own prospects, the costs of continuation are high relative to the expected gains, and a "mutually hurting stalemate" has been reached. Zartman adds the concept of a "ripe moment" — the window during which the conditions for settlement are present but may not persist. In Crucible, this theory governs the conditions under which actors transition from escalation to negotiation, and is typically run alongside Richardson to model the full escalation-to-settlement arc.

**Fearon Bargaining Model (1995).** James Fearon's "Rationalist Explanations for War" is the most influential formal treatment of why rational actors fight rather than negotiate. The core finding: war is inefficient (both parties bear costs), so rational actors should always prefer a negotiated settlement — yet war occurs. Fearon's resolution centers on **private information** (each party knows things about its own capabilities and resolve that the other cannot verify) and **commitment problems** (agreements are hard to enforce, especially when power is shifting). The model produces specific predictions about when war is more or less likely based on the distribution of private information and the severity of commitment problems. In Crucible, Fearon drives the probability that actors choose conflict versus negotiation, and is particularly relevant to scenarios involving shifts in relative power (where commitment problems are most acute).

**Keynesian Multiplier Model.** Fiscal shock propagation — how a policy intervention, supply disruption, or external demand shock ripples through a macro economy. The multiplier is the ratio of final GDP change to initial stimulus; the size depends on the marginal propensity to consume, which varies by sector and economy. In Crucible, this theory governs economic environment variables and is the appropriate framework for sanctions analysis, trade disruption, and investment shock scenarios.

**Porter's Five Forces.** Michael Porter's (1980) framework for analyzing industry competitive dynamics: threat of new entrants, bargaining power of suppliers, bargaining power of buyers, threat of substitutes, and rivalry among existing competitors. In Crucible, this runs as a market structure theory module for corporate and market scenarios — modeling how competitive pressures evolve as actors take actions that shift barriers to entry, concentration, or cost structures.

The theory library is explicitly designed to grow. New theories are registered with a decorator (`@register_theory`) that adds them to a global registry. The registry maps domain keywords to theory candidates. When the scoping agent processes a new scenario, the TheoryMapper selects theories from the registry based on domain signals in the description, resolves conflicts between incompatible theories (some theories make contradictory assumptions and cannot run simultaneously), and initializes parameters from the research context.

The key deliberation in the theory selection process was: **start with the theories that are most empirically grounded and most widely used by the analysts who will use this platform, not the most technically sophisticated.** Parsimony matters. A consultant who can explain why Richardson applies to a scenario is more valuable than one who cannot explain their model at all.

---

## 3. Uncertainty as a First-Class Citizen

A single simulation run produces a single trajectory. That is the wrong deliverable for a consulting engagement. The question is never "what will happen" — it is "what is likely to happen, how sensitive is that to what we don't know, and what conditions would change the answer."

Crucible answers this through **Monte Carlo ensemble runs**: 100 parallel simulations of the same scenario, each with controlled variation in starting conditions, producing a **distribution of outcomes** rather than a single path.

The architecture distinguishes two sources of uncertainty, and this distinction is deliberate:

**Aleatory uncertainty** — genuine randomness. Agent decision-making has a stochastic component: given the same beliefs, desires, and capabilities, an actor does not always make the same choice. Different random seeds per run capture this. This is uncertainty that cannot be reduced by gathering more data — it is irreducible randomness in behavior.

**Epistemic uncertainty** — uncertainty about starting conditions. We do not know the exact values of parameters at scenario initialization. The `UncertaintySpec` in a SimSpec allows the analyst to specify confidence intervals around initial environment values. Each ensemble run perturbs initial values by Gaussian noise proportional to these stated confidence intervals, producing a set of runs that spans the plausible parameter space.

The outputs of an ensemble run are:

- **Percentile bands over time** — for each metric at each tick, the p10, p50, and p90 values across all runs, plus mean and standard deviation. These are the "fan charts" of the simulation.
- **Final-tick distributions** — for each metric, the full distribution of outcomes at the end of the simulation, with explicit probability statements. *P(Iranian oil exports fall below critical threshold) = 0.73 under current parameters.*
- **Threshold probabilities** — pre-computed at common thresholds (0.3, 0.5, 0.7, 0.8, 0.9 on the normalized scale) for each metric.
- **Scenario comparison** — two ensemble runs can be diffed metric by metric using **Wasserstein distance** (Earth Mover's Distance), a measure of how far one distribution has "moved" relative to another. This answers the question: if we implement Policy A instead of Policy B, how much does the distribution of outcomes actually change, and on which metrics?

The deliberation on the ensemble size (100 runs as default) was about balancing statistical stability against computation time. For a 365-tick simulation with 5 metrics and 8 parallel workers, 100 runs completes in the order of minutes on a single server. The p10/p50/p90 estimates stabilize at that sample size for the distributions we are working with. The ceiling (1000 runs) is available for high-stakes scenarios where tighter confidence intervals matter.

The key principle: **the width of the uncertainty bands is itself a finding**. A narrow p10-p90 spread means the outcome is robust — even if we are wrong about the starting conditions, the conclusion holds. A wide spread means the outcome is sensitive to what we do not know — which is worth telling a client explicitly, rather than hiding behind a single-trajectory forecast.

---

## 4. The Calibration Loop: Living Models

Most simulation models are run once, delivered, and become obsolete the moment the world changes. The client receives a snapshot of the world as it was when the analyst ran the model. If conditions shift — sanctions are eased, a government falls, a trade agreement is reached — the model is wrong and no one knows by how much.

Crucible is designed as a **living model**: the simulation stays calibrated as real-world events evolve.

Every running simulation has a `DataFeedAgent` — a scheduled process that runs every six hours and checks the data sources the scenario was initialized with: FRED economic indicators, World Bank development data, news feeds, academic preprint servers. It compares the latest readings to the parameter values currently in the simulation. When it detects drift above a threshold (5% on the normalized scale by default), it generates a **CalibrationProposal**: a structured recommendation to update a specific parameter, with the data source, the old value, the proposed new value, a confidence score, and a plain-English rationale ready for consultant review.

The consultant approves or rejects via the API. On approval:

1. A new **version** of the `SimSpec` is created — a branched copy of the scenario with the updated parameter.
2. The change is recorded: what changed, why, who authorized it, which data source triggered it.
3. If the simulation is currently running, the parameter update is applied at the next tick boundary.
4. The old version is preserved in the version DAG — a directed acyclic graph of all spec versions, linked by parent-child relationships.

The version DAG means every fork of a scenario is preserved. A consultant can compare the current model to where it started, diff any two versions field by field, and branch a new scenario from any prior version. The `diff_simspecs()` function returns a structured list of changes — which environment keys changed, which theories were added or removed, which agent parameters shifted — making the evolution of the model auditable.

The deliberation on the human-in-the-loop design was central. The alternative — fully automatic recalibration — was considered and rejected. Data sources are imperfect. A FRED series that correlates with an environment variable is not the same as that variable. The mapping from raw data to a normalized simulation parameter requires domain judgment that the system cannot substitute for. Automatic recalibration would produce a model that confidently reflects its data sources, which may or may not reflect the phenomenon being modeled. The consultant is the expert. The system's job is to surface the evidence, quantify the drift, and present a reasoned recommendation. The decision stays with the analyst.

The broader design principle behind the calibration loop: **a model that is wrong and known to be wrong is more valuable than a model that is wrong and assumed to be current.** The CalibrationProposal queue is a real-time feed of model drift. A consultant who has three pending proposals knows exactly where their model is diverging from reality. A consultant with no such system is operating on assumptions they cannot see.

---

## 5. The Scoping Agent: Research Before Questions

The intake experience — how a consultant turns a scenario description into a running simulation — is the product. Everything else is infrastructure. The deliberation here was about what the intake agent does, in what order, and why.

The naive approach is a structured form: "Enter your actors. Select your theories. Fill in initial parameters." This is familiar from existing modeling tools and it produces shallow scenarios. Consultants who are domain experts but not modelers will fill in what they know and leave blank what they don't. The model inherits the analyst's blind spots without any mechanism for surfacing what is missing.

The second approach is a generic conversational agent: ask clarifying questions, refine the description, build the scenario. This is better but still shallow. The agent asks questions based on the scenario description alone, with no knowledge of what the academic literature says is important for this type of scenario, what data is available, or what the known unknowns are.

The chosen approach: **research first, then ask.** When the consultant submits a scenario description, the scoping agent immediately fires parallel research queries before generating a single question:

- **arXiv** — academic preprints on the relevant domain
- **SSRN** — social science and economics working papers
- **FRED** — Federal Reserve economic data series relevant to the scenario
- **World Bank** — development and macro indicators
- **News feeds** — recent events and context

These queries run in parallel. By the time the first question is ready, the agent has read the literature, found parameter estimates from empirical studies, identified the dominant theoretical frameworks applied to this type of scenario, and flagged what data is available for calibration. The first question is informed by all of this.

The conversation follows a state machine with six phases:

1. **Intake** — free-text description, initial extraction of actors, domain, and timeframe
2. **Parallel research** — background research fires immediately, results aggregated into a research context
3. **Dynamic interview** — targeted questions, each informed by research findings and current gaps in the SimSpec (maximum 5 questions — the constraint forces prioritization)
4. **Theory mapping** — `TheoryMapper` selects formal models from the library based on domain signals and research context; resolves conflicts between incompatible theories; initializes parameters from empirical estimates in the literature
5. **Validation** — the completed `SimSpec` is reviewed for internal consistency; remaining gaps are flagged with priority scores
6. **Complete** — SimSpec handed to the simulation layer

The **gap detection** system is explicit about what it does not know. Gaps are prioritized: actors and their relationships are the highest priority (a simulation with the wrong actors is wrong in a way no parameter adjustment can fix), followed by the theory selection, then environment parameters, then timeframe, then metrics, then uncertainty ranges. The agent surfaces these gaps in priority order, spending its five questions on what matters most.

The **TheoryMapper** is deterministic: given the domain signals and research context, it applies a rule-based selection process, resolves conflicts using a priority table, and initializes parameters from the research context. This is not a black box. The theory selection rationale is preserved in the SimSpec and can be reviewed by the analyst before the simulation runs. If the analyst disagrees with the automatic theory selection, they can override it.

The design principle: the scoping agent should feel like a senior analyst who has already done the reading. It knows what the literature says is important for this type of scenario. It knows what data exists. It asks questions that a generalist could not ask. The experience of using it should feel like a briefing, not a form.

---

## 6. What the Architecture Is Designed to Protect

Every design decision in this system is in service of a single deliverable: a consultant must be able to describe a scenario and receive an analysis that is **defensible, client-presentable, and auditable** — and stay that way as the world changes.

**Defensible** means the theoretical grounding is traceable. The theories are cited and selected by name from the peer-reviewed literature. The parameters are sourced — the research context records which papers informed which estimates. The probability statements are explicit about what uncertainty they capture (aleatory vs. epistemic) and what they do not. The model does not produce false precision. A consultant who is challenged on the methodology can point to Richardson (1960), Fearon (1995), or Wittman (1979) and explain why that framework applies to this scenario.

**Client-presentable** means the output speaks in the language of the engagement. This required a specific architectural decision: all values inside the simulation engine are normalized to `[0, 1]`. This is necessary for theories written in different units to share a common environment. But it creates a problem — a client deliverable showing `iranian_sanctions_severity: 0.742` is not a deliverable. The `EnvKeySpec` layer annotates every environment key with a scale factor, a physical unit, and a display name. The engine operates in normalized space; the API layer translates to display space before serving any output. A value of `0.742` on a key annotated with scale `100` and unit `"billion USD"` becomes `74.2 billion USD` in every report, dashboard, and narrative entry. The `NarrativeAgent` generates plain-English commentary — "Iranian military readiness reached a critical threshold at week 14 as coalition sanctions reduced oil revenues to 74.2 billion USD, approaching the level at which historical precedent suggests negotiating flexibility increases" — using display values throughout. The consultant pastes this into a client deck.

**Auditable** means the full history of the model is preserved and queryable. Every version of the SimSpec is stored in a version directed acyclic graph. Every calibration decision is logged: who approved it, what data triggered it, what changed. The `diff_simspecs()` function returns a structured diff between any two versions — which parameters moved, by how much, authorized by whom. The scenario as briefed in January and the scenario as it stands in March are both available, and the path between them is explicit.

The engineering review of the architecture before implementation began identified sixteen issues that would have compromised these guarantees in production. The most consequential:

- **Thread-unsafe random seeding** would have made ensemble reproducibility silent and broken from day one — the same scenario with the same seed would produce different results each run, with no error, no warning, and no way to detect it from the output.
- **A synchronous API client inside an asynchronous event loop** would have stalled every client-facing interaction during narrative generation — simulation ticks would pause, WebSocket feeds would freeze, and the behavior would be non-deterministic depending on when threshold events fired.
- **A second event loop inside the calibration scheduler** would have caused the system to crash silently on the first calibration cycle in production, with a runtime error that is difficult to diagnose without understanding Python's asyncio internals.
- **Unbounded memory growth in the ensemble runner** would have caused the server to exhaust memory after a full day of consultant use — each 100-run ensemble holding approximately 36MB of metric records in memory indefinitely.
- **Raw normalized floats in the PDF report renderer** — despite the entire `EnvKeySpec` system being built to solve exactly this problem — meant that the first client deliverable would have shown `0.742` instead of `74.2 billion USD`. The fix was one line; the risk was that it would not have been caught until a report was in front of a client.

These were caught in architecture review before a line of implementation code was written. This is the value of the review process: the cost of finding a design error in a document is one conversation. The cost of finding it in production is a client relationship.

The architecture is now locked. Implementation begins with `core/spec.py` — the `SimSpec` data contract that every other component depends on — and proceeds through the engine, the persistence layer, the scoping agent, and the output layer over twelve weeks. The Hormuz scenario, which has been running in production since early 2026, will be ported as the first reference implementation once the framework exists — validating that the generalization preserves the behavior of the system it was built to generalize.
