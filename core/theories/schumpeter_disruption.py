"""
Schumpeter Creative Destruction Model (Schumpeter, 1942)

Schumpeter's theory of creative destruction: innovation displaces incumbents,
renewing market structure through waves of technological change. R&D investment
drives innovator capability growth (logistic S-curve). Incumbents resist through
scale economies, IP portfolios, and network effects, but face structural
obsolescence as technology matures.

Incumbent dynamics (market share / profit position):
    dI/dt = σ·I·(1-I) - γ·I·N - ω·I

    where σ = incumbent inertia (lock-in growth), γ = disruption coefficient,
    ω = obsolescence rate (natural technology aging)

Innovator dynamics (capability / momentum):
    dN/dt = ρ·(1 + rd)·N·(1-N) - δ·I²·N

    where ρ = innovator S-curve growth rate, rd = R&D investment,
    δ = incumbent defense (grows with I² — dominant incumbents defend hardest)

The I² term captures the empirical observation that near-monopolist incumbents
defend far more aggressively than incumbents with partial market share.

Market constraint: I + N ≤ 1 (residual = "other" players / latent demand)

Characteristic regimes:
    - Incumbent dominance (I→1): slow innovation, high defense → N stays low
    - Disruption phase (N rising): incumbent loses share rapidly
    - Post-disruption (N→1): new incumbent, cycle restarts

Env keys written:
    {innovation_id}__incumbent_share         I ∈ [0,1]: incumbent position
    {innovation_id}__innovator_share         N ∈ [0,1]: innovator momentum
    {innovation_id}__creative_destruction    γ·I·N ∈ [0,1]: disruption intensity
    {innovation_id}__market_renewal          N/(I+N) ∈ [0,1]: innovator relative position

Env keys initialized but not written (set by agents / shocks):
    {innovation_id}__rd_investment   R&D spending ∈ [0,1]: boosts innovator growth

Use innovation_id for multiple simultaneous technology disruption waves.

References:
    Schumpeter (1942). Capitalism, Socialism and Democracy. Harper & Brothers.
    Aghion & Howitt (1992). A Model of Growth Through Creative Destruction.
    Econometrica 60(2): 323–351.
    Foster & Kaplan (2001). Creative Destruction. Currency/Doubleday.
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

_DT_MAP: dict[str, float] = {"day": 1.0 / 365.0, "week": 1.0 / 52.0, "month": 1.0 / 12.0, "quarter": 0.25, "year": 1.0}


@register_theory("schumpeter_disruption")
class SchumpeterDisruption(TheoryBase):
    """
    Schumpeter (1942) creative destruction with logistic innovator dynamics.

    Domains: innovation, technology, disruption, market_structure, entrepreneurship
    Priority: 0 (reads rd_investment as an external env input from agents)

    Use innovation_id for multiple simultaneous disruption waves in one sim.
    """

    DOMAINS = ["innovation", "technology", "disruption", "market_structure", "entrepreneurship"]

    class Parameters(BaseModel):
        incumbent_inertia: float = Field(
            default=0.05, ge=0.0, le=0.50,
            description="σ: incumbent organic growth rate from network effects and scale; "
                        "higher σ → incumbents resist displacement longer",
        )
        disruption_coefficient: float = Field(
            default=0.25, ge=0.0, le=1.0,
            description="γ: rate at which innovator displaces incumbent per unit interaction; "
                        "higher γ → faster creative destruction",
        )
        innovator_growth_rate: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="ρ: base S-curve growth rate of innovator capability/momentum; "
                        "modulated upward by R&D investment",
        )
        incumbent_defense: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="δ: incumbent ability to resist innovator (IP, scale, switching costs); "
                        "defense grows as I² — dominant incumbents resist most",
        )
        obsolescence_rate: float = Field(
            default=0.03, ge=0.0, le=0.20,
            description="ω: natural technology aging rate even without competition; "
                        "products become obsolete regardless of innovator presence",
        )
        innovation_id: str = Field(
            default="schumpeter",
            description="Env key prefix; e.g. 'ev_auto' → ev_auto__incumbent_share",
        )
        tick_unit: str = Field(default="year")

    @property
    def state_variables(self) -> TheoryStateVariables:
        n = self.params.innovation_id
        return TheoryStateVariables(
            reads=[
                f"{n}__incumbent_share",
                f"{n}__innovator_share",
                f"{n}__rd_investment",
            ],
            writes=[
                f"{n}__incumbent_share",
                f"{n}__innovator_share",
                f"{n}__creative_destruction",
                f"{n}__market_renewal",
            ],
            initializes=[
                f"{n}__incumbent_share",
                f"{n}__innovator_share",
                f"{n}__creative_destruction",
                f"{n}__market_renewal",
                f"{n}__rd_investment",   # seeded at 0.10; agents override
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed incumbent_share at 0.80 (dominant incumbent), innovator_share at 0.05
        (nascent challenger), and rd_investment at 0.10 (baseline R&D spend).
        """
        inits = super().setup(env)
        n = self.params.innovation_id
        if f"{n}__incumbent_share" not in env:
            inits[f"{n}__incumbent_share"] = 0.80
        if f"{n}__innovator_share" not in env:
            inits[f"{n}__innovator_share"] = 0.05
        if f"{n}__rd_investment" not in env:
            inits[f"{n}__rd_investment"] = 0.10
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Schumpeterian disruption step.

        1. Read current incumbent share I, innovator share N, and R&D investment.
        2. Compute logistic growth / decay differentials for I and N.
        3. Enforce I + N ≤ 1 constraint (rest of market is "other").
        4. Derive creative destruction intensity and market renewal ratio.

        Args:
            env:    normalized environment (read-only)
            agents: not used (dynamics driven by macro innovation parameters)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated incumbent_share, innovator_share,
            creative_destruction, and market_renewal.
        """
        p = self.params
        n = p.innovation_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        I = env.get(f"{n}__incumbent_share", 0.80)
        N = env.get(f"{n}__innovator_share", 0.05)
        rd = env.get(f"{n}__rd_investment", 0.10)

        # Incumbent dynamics: logistic lock-in growth minus disruption minus obsolescence
        dI = (
            p.incumbent_inertia * I * (1.0 - I)
            - p.disruption_coefficient * I * N
            - p.obsolescence_rate * I
        ) * dt

        # Innovator dynamics: S-curve growth boosted by R&D, resisted by I² incumbent defense
        dN = (
            p.innovator_growth_rate * (1.0 + rd) * N * (1.0 - N)
            - p.incumbent_defense * I * I * N
        ) * dt

        new_I = max(0.0, min(1.0, I + dI))
        new_N = max(0.0, min(1.0, N + dN))

        # Enforce I + N ≤ 1 (rest of market is "other" players)
        if new_I + new_N > 1.0:
            total = new_I + new_N
            new_I /= total
            new_N /= total

        # Creative destruction intensity: γ × I × N (peak during disruption transition)
        creative_destruction = max(0.0, min(1.0,
            p.disruption_coefficient * new_I * new_N
        ))

        # Market renewal: innovator's relative position within I+N space
        market_renewal = new_N / max(1e-9, new_I + new_N)
        market_renewal = max(0.0, min(1.0, market_renewal))

        logger.debug(
            "SchumpeterDisruption tick=%d id=%s: I=%.3f→%.3f N=%.3f→%.3f "
            "cd=%.3f renewal=%.3f rd=%.3f",
            tick, n, I, new_I, N, new_N, creative_destruction, market_renewal, rd,
        )

        return {
            f"{n}__incumbent_share":      new_I,
            f"{n}__innovator_share":      new_N,
            f"{n}__creative_destruction": creative_destruction,
            f"{n}__market_renewal":       market_renewal,
        }
