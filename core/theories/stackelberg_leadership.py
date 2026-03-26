"""
Stackelberg Leadership Model (Stackelberg, 1934)

In Stackelberg competition the leader firm commits to a quantity first; the
follower firm observes that commitment and immediately best-responds.  The
leader anticipates the follower's best response and optimises accordingly,
earning a first-mover advantage over the symmetric Cournot equilibrium.

Inverse demand:
    P = max(0, p_max - demand_slope × (q_l + q_f))

Follower best response (given q_l):
    q_f*(q_l) = max(0, (p_max - demand_slope × q_l - c_f) / (2 × demand_slope))

Leader optimal quantity (by backward induction, substituting follower BR):
    q_l* = (p_max + c_f - 2 × c_l) / (2 × demand_slope)

Analytical equilibrium:
    q_l* = (p_max + c_f - 2*c_l) / (2*slope)   [leader produces ~2× Cournot share]
    q_f* = (p_max - slope*q_l* - c_f) / (2*slope)
    P*   = p_max - slope*(q_l* + q_f*)

First-mover advantage: leader earns higher margin than follower when c_l ≤ c_f
because the leader exploits follower's best-response passivity.

Dynamic version — quantities adjust toward Stackelberg optimum with inertia:
    q_l[t+1] = q_l[t] + leader_speed × (q_l* - q_l[t]) × dt
    q_f[t+1] = q_f[t] + follower_speed × (q_f*(q_l[t]) - q_f[t]) × dt

The follower's convergence speed is typically higher (best-responds immediately).
GDP modulation: above-baseline GDP shifts p_max upward (demand expansion).

Env keys written:
    {market_id}__leader_quantity      q_l ∈ [0,1]
    {market_id}__follower_quantity    q_f ∈ [0,1]
    {market_id}__market_price         P ∈ [0,1]  normalized by p_max
    {market_id}__leader_margin        (P-c_l)×q_l / p_max² ∈ [0,1]
    {market_id}__follower_margin      (P-c_f)×q_f / p_max² ∈ [0,1]
    {market_id}__leadership_advantage leader_margin - follower_margin ∈ [0,1]

Env keys read (optional cross-theory):
    keynesian__gdp_normalized          demand expansion above 0.50 baseline

Use market_id for multiple independent leader–follower markets in one simulation.

References:
    Stackelberg, H. von (1934). Marktform und Gleichgewicht. Springer.
    Tirole, J. (1988). The Theory of Industrial Organization. MIT Press.
    Fudenberg, D. & Tirole, J. (1991). Game Theory. MIT Press.
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


@register_theory("stackelberg_leadership")
class StackelbergLeadership(TheoryBase):
    """
    Stackelberg (1934) leader-follower quantity competition.

    Domains: market, competitive_strategy, game_theory, first_mover, supply_chain
    Priority: 0 (reads Keynesian GDP if present; independent of conflict theories)

    Use market_id for multiple independent leader–follower markets in one sim.
    """

    DOMAINS = ["market", "competitive_strategy", "game_theory", "first_mover", "supply_chain"]

    class Parameters(BaseModel):
        p_max: float = Field(
            default=1.0, ge=0.0, le=2.0,
            description="Maximum willingness to pay (normalized demand intercept)",
        )
        demand_slope: float = Field(
            default=1.0, ge=0.1, le=5.0,
            description="b: slope of inverse demand P = p_max - b·(q_l + q_f)",
        )
        cost_leader: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Marginal cost of the leader (typically lower, enabling first-mover)",
        )
        cost_follower: float = Field(
            default=0.25, ge=0.0, le=1.0,
            description="Marginal cost of the follower (typically higher than leader)",
        )
        leader_speed: float = Field(
            default=0.60, ge=0.0, le=1.0,
            description="Leader convergence speed toward Stackelberg optimum per tick-unit; "
                        "slower reflects strategic commitment delay",
        )
        follower_speed: float = Field(
            default=0.90, ge=0.0, le=1.0,
            description="Follower convergence speed toward best-response per tick-unit; "
                        "higher than leader — follower best-responds quickly",
        )
        gdp_demand_sensitivity: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="How much above-baseline GDP shifts p_max upward (demand boom effect)",
        )
        tick_unit: str = Field(default="year")
        market_id: str = Field(
            default="stackelberg",
            description="Env key prefix; e.g. 'aviation' → aviation__leader_quantity",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        m = self.params.market_id
        return TheoryStateVariables(
            reads=[
                f"{m}__leader_quantity",
                f"{m}__follower_quantity",
                "keynesian__gdp_normalized",
            ],
            writes=[
                f"{m}__leader_quantity",
                f"{m}__follower_quantity",
                f"{m}__market_price",
                f"{m}__leader_margin",
                f"{m}__follower_margin",
                f"{m}__leadership_advantage",
            ],
            initializes=[
                f"{m}__leader_quantity",
                f"{m}__follower_quantity",
                f"{m}__market_price",
                f"{m}__leader_margin",
                f"{m}__follower_margin",
                f"{m}__leadership_advantage",
            ],
        )

    def stackelberg_equilibrium(self) -> tuple[float, float, float] | None:
        """
        Compute the analytical Stackelberg equilibrium quantities and price.

        Returns (q_l*, q_f*, P*) at default p_max (no GDP adjustment).
        Returns None if the leader's optimal quantity is non-positive (no
        profitable production — e.g., when costs exceed p_max).
        """
        p = self.params
        q_l_star = (p.p_max + p.cost_follower - 2.0 * p.cost_leader) / (2.0 * p.demand_slope)
        if q_l_star <= 0:
            return None
        q_f_star = max(0.0, (p.p_max - p.demand_slope * q_l_star - p.cost_follower) /
                       (2.0 * p.demand_slope))
        price = max(0.0, p.p_max - p.demand_slope * (q_l_star + q_f_star))
        return (q_l_star, q_f_star, price)

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """Seed leader and follower quantities at Stackelberg equilibrium values."""
        inits = super().setup(env)
        m = self.params.market_id
        eq = self.stackelberg_equilibrium()
        if eq:
            q_l_star, q_f_star, _ = eq
            if f"{m}__leader_quantity" not in env:
                inits[f"{m}__leader_quantity"] = min(1.0, max(0.0, q_l_star))
            if f"{m}__follower_quantity" not in env:
                inits[f"{m}__follower_quantity"] = min(1.0, max(0.0, q_f_star))
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Stackelberg adjustment step.

        1. Adjust p_max for current GDP conditions.
        2. Compute the leader's Stackelberg optimum quantity.
        3. Compute the follower's best-response to current q_l.
        4. Partially adjust both quantities toward their targets.
        5. Derive market price, margins, and leadership advantage.

        Args:
            env:    normalized environment (read-only)
            agents: not used
            tick:   zero-based tick counter

        Returns:
            delta dict with 6 updated keys.
        """
        p = self.params
        m = p.market_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        q_l = env.get(f"{m}__leader_quantity", 0.33)
        q_f = env.get(f"{m}__follower_quantity", 0.17)
        gdp = env.get("keynesian__gdp_normalized", 0.50)

        # GDP-adjusted demand intercept
        p_max_eff = max(0.0, min(2.0,
            p.p_max + p.gdp_demand_sensitivity * (gdp - 0.50)
        ))

        # Stackelberg leader optimal quantity (backward induction)
        q_l_star = max(0.0, min(1.0,
            (p_max_eff + p.cost_follower - 2.0 * p.cost_leader) / (2.0 * p.demand_slope)
        ))

        # Follower best-responds to leader's *current* (not optimal) quantity
        q_f_star = max(0.0, min(1.0,
            (p_max_eff - p.demand_slope * q_l - p.cost_follower) / (2.0 * p.demand_slope)
        ))

        # Partial adjustment toward targets (leader slower, follower faster)
        new_q_l = max(0.0, min(1.0, q_l + p.leader_speed * (q_l_star - q_l) * dt))
        new_q_f = max(0.0, min(1.0, q_f + p.follower_speed * (q_f_star - q_f) * dt))

        # Market price
        price = max(0.0, min(1.0, p_max_eff - p.demand_slope * (new_q_l + new_q_f)))

        # Margins normalized by p_max_eff² to keep in [0,1]
        norm = max(1e-9, p_max_eff ** 2)
        leader_margin = max(0.0, min(1.0, (price - p.cost_leader) * new_q_l / norm))
        follower_margin = max(0.0, min(1.0, (price - p.cost_follower) * new_q_f / norm))
        leadership_advantage = max(0.0, min(1.0, leader_margin - follower_margin))

        logger.debug(
            "StackelbergLeadership tick=%d market=%s: q_l=%.3f→%.3f q_f=%.3f→%.3f "
            "P=%.3f lm=%.3f fm=%.3f adv=%.3f",
            tick, m, q_l, new_q_l, q_f, new_q_f, price, leader_margin, follower_margin,
            leadership_advantage,
        )

        return {
            f"{m}__leader_quantity":     new_q_l,
            f"{m}__follower_quantity":   new_q_f,
            f"{m}__market_price":        price,
            f"{m}__leader_margin":       leader_margin,
            f"{m}__follower_margin":     follower_margin,
            f"{m}__leadership_advantage": leadership_advantage,
        }
