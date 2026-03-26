"""
Bounded Confidence Opinion Dynamics (Deffuant et al. 2000)

Agents update opinions only toward agents whose opinion is within a confidence
bound ε. Agents outside ε have no influence on each other.

Micro rule (agent pair):
    if |x_i - x_j| < ε:
        x_i += μ · (x_j - x_i)
        x_j += μ · (x_i - x_j)

Emergent macro behavior:
    ε > 0.5  → consensus (all agents eventually agree)
    ε ≈ 0.25 → two clusters (polarization)
    ε < 0.25 → fragmentation (many isolated groups)

Mean-field two-moment approximation (tracks distribution, not individual agents):
    opinion__mean        population-weighted mean opinion ∈ [0, 1]
    opinion__polarization normalized standard deviation ∈ [0, 1]
                         (0 = perfect consensus, 1 = maximum bimodal spread)

    actual std_dev = polarization × 0.5  (max std_dev on [0,1] is 0.5, at bimodal extremes)

Convergence dynamics per tick:
    contact_fraction ≈ min(1, ε / (√2 · σ))   — probability two agents are within ε
    new_σ = σ · (1 − 2μ · contact_fraction · dt)  — convergence step
    new_σ += (noise_sigma + urgency · urgency_polarization_factor) · dt  — noise injection

Mean drift:
    new_mean = mean + media_sensitivity · (media_bias − mean) · dt

    opinion__{domain_id}__media_bias: set by agents or shocks to represent sustained
    media/narrative pressure. Initialized to 0.5 (neutral). Theory reads but does
    not write this key — agents own it.

Cross-theory inputs:
    global__urgency_factor  (from Zartman MHS or agent actions)
                            → injects polarization (crisis creates opinion divergence)

Env keys written:
    {domain_id}__mean          population mean opinion ∈ [0, 1]
    {domain_id}__polarization  normalized std dev ∈ [0, 1]
    {domain_id}__consensus     1 − polarization (bridge variable for other theories)

Env keys initialized but not written (set by agents / shocks):
    {domain_id}__media_bias    exogenous media / narrative pressure ∈ [0, 1]

Multiple simultaneous opinion domains:
    OpinionDynamics({"domain_id": "public"})   → public__mean
    OpinionDynamics({"domain_id": "elite"})    → elite__mean

References:
    Deffuant et al. (2000). Mixing beliefs among interacting agents.
    Advances in Complex Systems 3: 87–98.
    Hegselmann & Krause (2002). Opinion dynamics and bounded confidence.
    JASSS 5(3).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)

_DT_MAP: dict[str, float] = {"month": 1.0 / 12.0, "quarter": 0.25, "year": 1.0}

# sqrt(2) approximation for contact fraction formula
_SQRT2 = 1.41421356


@register_theory("opinion_dynamics")
class OpinionDynamics(TheoryBase):
    """
    Deffuant (2000) bounded confidence opinion dynamics — mean-field approximation.

    Domains: social, political, reputational, media, ESG
    Priority: 0 (reads global__urgency_factor; acceptable one-tick lag from Zartman)

    Use domain_id to model separate opinion populations (public, elites, investors, etc.)
    """

    DOMAINS = ["social", "political", "reputational", "media", "ESG"]

    class Parameters(BaseModel):
        epsilon: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="Confidence bound: max opinion gap for agents to interact",
        )
        mu: float = Field(
            default=0.20, ge=0.0, le=0.5,
            description="Convergence speed per interaction (0.5 = meet halfway each time)",
        )
        noise_sigma: float = Field(
            default=0.01, ge=0.0, le=0.5,
            description="Baseline opinion noise injected per tick (prevents total freeze)",
        )
        urgency_polarization_factor: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="How much global__urgency_factor amplifies polarization noise",
        )
        media_sensitivity: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="Rate at which mean opinion drifts toward media_bias per tick",
        )
        tick_unit: str = Field(
            default="year",
            description="Time step unit: 'month', 'quarter', or 'year'",
        )
        domain_id: str = Field(
            default="opinion",
            description="Env key prefix; e.g. 'public' → public__mean",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        d = self.params.domain_id
        return TheoryStateVariables(
            reads=[
                f"{d}__mean",
                f"{d}__polarization",
                f"{d}__media_bias",
                "global__urgency_factor",
            ],
            writes=[
                f"{d}__mean",
                f"{d}__polarization",
                f"{d}__consensus",
            ],
            initializes=[
                f"{d}__mean",
                f"{d}__polarization",
                f"{d}__consensus",
                f"{d}__media_bias",   # seeded neutral; agents/shocks update this key
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed opinion state:
          mean = 0.5 (neutral)
          polarization = 0.5 (moderate initial spread, σ ≈ 0.25)
          media_bias = 0.5 (neutral)
        """
        inits = super().setup(env)
        d = self.params.domain_id
        if f"{d}__mean" not in env:
            inits[f"{d}__mean"] = 0.5
        if f"{d}__polarization" not in env:
            inits[f"{d}__polarization"] = 0.5
        if f"{d}__media_bias" not in env:
            inits[f"{d}__media_bias"] = 0.5
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Deffuant mean-field step.

        1. Compute contact fraction from current spread and epsilon.
        2. Converge std_dev at rate 2μ × contact_fraction.
        3. Inject noise (baseline + urgency-driven polarization).
        4. Drift mean toward media_bias.

        Args:
            env:    normalized environment (read-only)
            agents: not used (population-level model; extend to read agent beliefs if needed)
            tick:   zero-based tick counter

        Returns:
            delta dict: mean, polarization, consensus.
        """
        p = self.params
        d = p.domain_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        mean        = env.get(f"{d}__mean",        0.5)
        polarization = env.get(f"{d}__polarization", 0.5)

        # Denormalize: actual std_dev ∈ [0, 0.5]
        std_dev = polarization * 0.5

        # Contact fraction: P(two random agents are within epsilon of each other)
        # Mean-field approximation: contact_frac ≈ ε / (√2 · σ), capped at 1
        if std_dev < 1e-9:
            contact_fraction = 1.0
        else:
            contact_fraction = min(1.0, p.epsilon / (_SQRT2 * std_dev))

        # Convergence: opinions shrink toward mean at rate 2μ × contact_frac
        convergence_rate = 2.0 * p.mu * contact_fraction
        new_std_dev = max(0.0, std_dev * (1.0 - convergence_rate * dt))

        # Noise injection: prevents freeze; crisis/urgency amplifies polarization
        urgency = env.get("global__urgency_factor", 0.0)
        noise = (p.noise_sigma + urgency * p.urgency_polarization_factor) * dt
        new_std_dev = min(0.5, new_std_dev + noise)

        # Mean drift toward media bias (sustained narrative pressure)
        media_bias = env.get(f"{d}__media_bias", 0.5)
        mean_drift = p.media_sensitivity * (media_bias - mean) * dt
        new_mean = max(0.0, min(1.0, mean + mean_drift))

        # Renormalize polarization
        new_polarization = min(1.0, new_std_dev / 0.5)
        new_consensus    = 1.0 - new_polarization

        logger.debug(
            "Opinion tick=%d domain=%s: mean=%.3f→%.3f pol=%.3f→%.3f "
            "contact_frac=%.3f urgency=%.3f noise=%.4f",
            tick, d, mean, new_mean, polarization, new_polarization,
            contact_fraction, urgency, noise,
        )

        return {
            f"{d}__mean":         new_mean,
            f"{d}__polarization": new_polarization,
            f"{d}__consensus":    new_consensus,
        }
