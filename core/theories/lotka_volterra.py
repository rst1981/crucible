"""
Lotka–Volterra Competitive Market Dynamics (1925 / 1926)

Originally formulated to model predator–prey population dynamics, the
Lotka–Volterra equations have been widely applied to competitive market
dynamics where an incumbent firm (prey) is challenged by a disruptor
(predator). Incumbents grow logistically within their carrying capacity;
challengers grow only when exploiting incumbents' market share.

Model interpretation:
    X  (incumbent_share) — established player(s) with organic growth
    Y  (challenger_share) — new entrant(s) eroding incumbent share

Dynamics (modified Lotka–Volterra with logistic incumbent growth):

    dX/dt = r·X·(1 - X/K) - a·X·Y
    dY/dt = b·a·X·Y - d·Y + innovation_boost·Y·(1 - Y)

where:
    r  = prey_growth_rate       incumbent organic market-share growth
    a  = predator_efficiency    competitive interaction (market share captured)
    b  = conversion_efficiency  fraction of captured share converted to challenger growth
    d  = predator_mortality     challenger base fade / burn rate
    K  = carrying_capacity      market saturation ceiling for incumbent
    innovation_boost            exogenous challenger-growth accelerator (set by agents)

Outputs:
    total_market   = X + Y  (total occupied market share)
    dominance_ratio = X / (X + Y)  (incumbent fraction of total occupied share)

Cross-theory:
    {ecosystem_id}__innovation_boost — exogenous challenger-growth boost;
                                        set by agents/R&D events; default 0.0

Env keys written:
    {ecosystem_id}__incumbent_share   X ∈ [0,1]
    {ecosystem_id}__challenger_share  Y ∈ [0,1]
    {ecosystem_id}__total_market      X + Y (clamped) ∈ [0,1]
    {ecosystem_id}__dominance_ratio   X / (X + Y) ∈ [0,1]

References:
    Lotka, A. J. (1925). Elements of Physical Biology. Williams & Wilkins.

    Volterra, V. (1926). Fluctuations in the abundance of a species considered
    mathematically. Nature 118: 558–560.

    Barnett, W. P. & Hansen, M. T. (1996). The red queen in organizational
    evolution. Strategic Management Journal 17(S1): 139–157.

    Farmer, J. D. & Hepburn, C. (2019). Less precision, more truth: uncertainty
    in climate economics and macroprudential policy.
    In: Rethinking Economics (eds. Coyle et al.). Agenda Publishing.
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


@register_theory("lotka_volterra")
class LotkaVolterra(TheoryBase):
    """
    Lotka–Volterra (1925/1926) predator–prey dynamics applied to market competition.

    Domains: market, competitive_dynamics, ecology, disruption, strategy
    Priority: 0 (innovation_boost is an external env input set by agents)

    Use ecosystem_id for multiple simultaneous competitive dynamics in the same sim.
    """

    DOMAINS = ["market", "competitive_dynamics", "ecology", "disruption", "strategy"]

    class Parameters(BaseModel):
        prey_growth_rate: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="r: incumbent organic market-share growth rate per tick-unit",
        )
        predator_efficiency: float = Field(
            default=0.30, ge=0.0, le=2.0,
            description="a: competitive interaction coefficient (share captured per unit contact)",
        )
        predator_mortality: float = Field(
            default=0.05, ge=0.0, le=1.0,
            description="d: challenger base fade / burn rate per tick-unit",
        )
        conversion_efficiency: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="b: fraction of captured incumbent share that converts to challenger growth",
        )
        carrying_capacity: float = Field(
            default=1.0, ge=0.1, le=1.0,
            description="K: market saturation ceiling for incumbent logistic growth",
        )
        tick_unit: str = Field(default="year")
        ecosystem_id: str = Field(
            default="ecosystem",
            description="Env key prefix; e.g. 'ev_market' → ev_market__incumbent_share",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        e = self.params.ecosystem_id
        return TheoryStateVariables(
            reads=[
                f"{e}__incumbent_share",
                f"{e}__challenger_share",
                f"{e}__innovation_boost",
            ],
            writes=[
                f"{e}__incumbent_share",
                f"{e}__challenger_share",
                f"{e}__total_market",
                f"{e}__dominance_ratio",
            ],
            initializes=[
                f"{e}__incumbent_share",
                f"{e}__challenger_share",
                f"{e}__total_market",
                f"{e}__dominance_ratio",
                f"{e}__innovation_boost",  # owned by agents/R&D events
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed incumbent at dominant share (0.80) and challenger at early entry (0.05).

        A small but nonzero challenger share is required for Lotka–Volterra
        predation dynamics to activate.
        """
        inits = super().setup(env)
        e = self.params.ecosystem_id
        if f"{e}__incumbent_share" not in env:
            inits[f"{e}__incumbent_share"] = 0.80
        if f"{e}__challenger_share" not in env:
            inits[f"{e}__challenger_share"] = 0.05
        if f"{e}__innovation_boost" not in env:
            inits[f"{e}__innovation_boost"] = 0.0
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Advance the Lotka–Volterra market competition model by one tick.

        Reads current X (incumbent) and Y (challenger) from env, integrates
        the modified Lotka–Volterra ODEs with Euler step dt, then enforces
        X + Y ≤ 1 and computes derived outputs.

        Args:
            env:    normalized environment (read-only)
            agents: not used directly (innovation_boost comes from env)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated incumbent_share, challenger_share,
            total_market, dominance_ratio.
        """
        p = self.params
        e = p.ecosystem_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        X = env.get(f"{e}__incumbent_share", 0.80)
        Y = env.get(f"{e}__challenger_share", 0.05)
        innovation_boost = env.get(f"{e}__innovation_boost", 0.0)

        # Lotka–Volterra ODEs (modified with logistic incumbent growth)
        dX = (
            p.prey_growth_rate * X * (1.0 - X / p.carrying_capacity)
            - p.predator_efficiency * X * Y
        ) * dt

        dY = (
            p.conversion_efficiency * p.predator_efficiency * X * Y
            - p.predator_mortality * Y
            + innovation_boost * Y * (1.0 - Y)
        ) * dt

        new_X = max(0.0, min(1.0, X + dX))
        new_Y = max(0.0, min(1.0, Y + dY))

        # Ensure X + Y ≤ 1 (market share cannot exceed total market)
        if new_X + new_Y > 1.0:
            total_sum = new_X + new_Y
            new_X /= total_sum
            new_Y /= total_sum

        total_market = max(0.0, min(1.0, new_X + new_Y))
        dominance_ratio = new_X / max(1e-9, new_X + new_Y)
        dominance_ratio = max(0.0, min(1.0, dominance_ratio))

        logger.debug(
            "LotkaVolterra tick=%d ecosystem=%s: X=%.4f→%.4f Y=%.4f→%.4f "
            "total=%.4f dominance=%.4f (innovation_boost=%.3f)",
            tick, e, X, new_X, Y, new_Y, total_market, dominance_ratio, innovation_boost,
        )

        return {
            f"{e}__incumbent_share":  new_X,
            f"{e}__challenger_share": new_Y,
            f"{e}__total_market":     total_market,
            f"{e}__dominance_ratio":  dominance_ratio,
        }
