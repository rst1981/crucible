# Crucible — Approach and Deliberations

**To:** [Boss]
**From:** Development Team
**Date:** March 2026

---

## Why Agent-Based Simulation

Crucible is built on **agent-based modeling (ABM)**, not equation-based system dynamics. This was a deliberate choice, and the reasoning matters.

Equation-based models — differential equations, econometric regressions, input-output matrices — are powerful when you can specify the system in closed form. They are the right tool when the relationships between variables are well-understood and stable. But most of the scenarios our clients care about involve **actors making decisions under uncertainty**, reacting to each other, updating their beliefs, constrained by what they are actually capable of doing. A trade war isn't a differential equation. It's a set of governments reading signals from each other and choosing responses.

ABM treats the simulation as a collection of **agents**, each with:
- **Beliefs** about the world (represented as probability distributions — not point estimates, because real actors are uncertain)
- **Desires** — goals they are trying to achieve, weighted by how much they want them
- **Intentions** — what they plan to do, constrained by their actual capabilities

This is the BDI architecture, drawn from AI planning and political theory. It maps naturally onto how analysts already reason about adversaries, governments, and firms. The Richardson arms race model, for example, is not just a formula — it is an expression of how two actors update their threat perceptions and respond with action. In Crucible, that logic lives inside the agent's `decide()` function, not in a spreadsheet.

The practical benefit: when a client says "what if Iran's leadership changes risk calculus," the analyst changes a belief parameter, not a regression coefficient. The model speaks the language of the analysis.

---

## The Theory Library: Deliberate Pluralism

No single theory explains geopolitical crises, market shocks, or organizational change. Crucible is designed around **pluggable theory modules** — each a formal model from the academic literature, each applicable to specific domains, each composable with others.

The current library draws from:

- **Richardson (1960)** — arms race dynamics; mutual threat perception driving spending spirals
- **Wittman-Zartman** — negotiated settlement theory; when parties prefer agreement to continued conflict based on expected costs and outcome uncertainty
- **Fearon (1995)** — bargaining model of war; the conditions under which rational actors fight rather than agree, centering on private information and commitment problems
- **Keynesian multipliers** — fiscal shock propagation through an economy
- **Porter's Five Forces** — competitive dynamics in market structure

These are not arbitrary choices. They represent the dominant formal frameworks in each domain, with peer-reviewed empirical foundations. The deliberation in selecting them was: **what is the smallest set of theories that covers the widest range of scenarios our clients will bring?**

The architecture allows multiple theories to run simultaneously within one scenario. A geopolitical scenario might run Richardson (for military escalation), Fearon (for negotiation timing), and a macro shock model (for economic spillover) in the same simulation — each updating shared environment variables that others read.

The composability is intentional: real situations are not clean enough to fit one theory.

---

## Uncertainty as a First-Class Citizen

A single simulation run produces a single trajectory. That is the wrong answer for a consulting engagement. The right answer is a **distribution of outcomes** — and a clear statement of what drives the spread.

Crucible runs **Monte Carlo ensembles**: 100 parallel simulations of the same scenario, each with small perturbations to initial parameters drawn from the stated uncertainty ranges. The output is not "the answer" but a **probability distribution over outcomes** — p10, p50, p90 bands over time, with explicit probability statements ("P(conflict escalation above critical threshold) = 0.73 under current parameters").

The deliberation here was about what uncertainty to model. We settled on two sources:

1. **Aleatory uncertainty** — genuine randomness in agent behavior (different random seeds per run). Some decisions have a stochastic component; this captures it.
2. **Epistemic uncertainty** — we don't know the exact starting parameters (perturb initial environment values with Gaussian noise proportional to stated confidence intervals).

This distinction matters for clients. When the p10-p90 spread is narrow, the scenario is robust to parameter uncertainty — the conclusion holds even if we're wrong about the starting conditions. When the spread is wide, the outcome is sensitive to what we don't know — which is itself a finding worth delivering.

---

## The Calibration Loop: Living Models, Not Snapshots

Most simulation models are run once, delivered, and become outdated the moment the world changes. Crucible is designed to **stay calibrated** as events evolve.

Every running simulation has a `DataFeedAgent` that checks live data sources every six hours — FRED economic indicators, World Bank data, news feeds — and compares current readings to the parameters the model was initialized with. When it detects drift above a threshold, it generates a **CalibrationProposal**: a structured suggestion to update a parameter, with a rationale in plain English, ready for consultant review.

The consultant approves or rejects. On approval, the system creates a new **version** of the SimSpec — a branched snapshot of the scenario with the updated parameter, linked to the prior version in a version DAG. Every fork is preserved. You can always compare the current model to where it started.

The deliberation was: **should recalibration be automatic or human-in-the-loop?** We chose human-in-the-loop. The data sources are imperfect. The mapping from a FRED series to a normalized simulation parameter requires judgment. Automation would produce confident wrong answers. The consultant is the expert; the system surfaces the evidence and the recommendation, and the consultant decides.

---

## The Scoping Agent: Research Before Questions

The intake experience for a consultant is a conversation with an AI agent. The deliberation was about **what the agent does before the first question**.

The naive approach: ask the consultant to fill in a form, or ask generic clarifying questions. This produces shallow scenarios. A consultant who types "EU carbon tariff impact on China manufacturing" gets asked "what are your actors?" — a question that reveals no understanding of the domain.

The chosen approach: **research first, then ask**. When the consultant submits their scenario description, the scoping agent immediately fires parallel research queries — academic papers on carbon border adjustment mechanisms, FRED trade data, relevant news — before generating a single question. The first question is informed by what the literature says matters for this type of scenario, what data is available, and what is genuinely uncertain.

This is the difference between a junior analyst who asks "what should I look for?" and a senior analyst who arrives having already done the reading. The agent should feel like the latter.

---

## What the Architecture Is Designed to Protect

Every design decision was made in service of one outcome: **a consultant can describe a scenario and receive a defensible, client-presentable analysis**, with a clear audit trail from theoretical grounding through to probability statements.

"Defensible" means the theories are cited. The parameters are sourced. The uncertainty is quantified and honest about what it is and is not capturing. The model does not produce false precision.

"Client-presentable" means the output speaks in the language of the engagement — not normalized floats, not model internals, but named actors, display units, executive prose generated by the narrative layer.

"Audit trail" means every version of the scenario is preserved, every calibration decision is logged, and the diff between what we modeled in January and what we are modeling in March is one query away.

The technology serves these goals. The theoretical choices are the product.
