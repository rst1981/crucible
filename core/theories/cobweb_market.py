"""
Cobweb Market — Ezekiel (1938) Cobweb Theorem

Producers base supply decisions on last period's price, but current demand
determines the clearing price. This production lag creates cyclical price
oscillations — the "cobweb" pattern — common in agricultural and housing markets.

Supply (based on lagged price):
    Q_s[t] = supply_intercept + supply_elasticity × P[t-1] − supply_shock

Demand (determines clearing price):
    Q_d[t] = demand_intercept + demand_shock − demand_elasticity × P[t]

Clearing price (equate Q_d = Q_s and solve):
    P[t] = (demand_intercept + demand_shock − Q_s[t]) / demand_elasticity

Stability condition:
    |supply_elasticity / demand_elasticity| < 1 → convergent oscillations
    |supply_elasticity / demand_elasticity| > 1 → divergent oscillations (unstable)

Steady-state price:
    P* = (demand_intercept − supply_intercept) / (demand_elasticity + supply_elasticity)

Cross-theory:
    {market_id}__supply_shock  — additive supply disruption (initialized 0.0; agents override)
    {market_id}__demand_shock  — additive demand shift (initialized 0.0; agents override)

Env keys written:
    {market_id}__price           current market price ∈ [0, 1]
    {market_id}__supply          quantity supplied this period ∈ [0, 1]
    {market_id}__demand          quantity demanded at current price ∈ [0, 1]
    {market_id}__excess_demand   normalized shortage max(0, Q_d−Q_s)/demand_intercept ∈ [0, 1]
    {market_id}__price_volatility tick-over-tick price change |P[t]−P[t-1]| ∈ [0, 1]

Env keys initialized but not written (owned by agents/shocks):
    {market_id}__supply_shock   (default seed = 0.0)
    {market_id}__demand_shock   (default seed = 0.0)

Use market_id for multiple simultaneous commodity markets.

References:
    Ezekiel, M. (1938). The cobweb theorem.
    The Quarterly Journal of Economics 52(2): 255–280.
    Kaldor, N. (1934). A classificatory note on the determinateness of equilibrium.
    The Review of Economic Studies 1(2): 122–136.
    Waugh, F. V. (1964). Cobweb models.
    Journal of Farm Economics 46(4): 732–750.
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


@register_theory("cobweb_market")
class CobwebMarket(TheoryBase):
    """
    Ezekiel (1938) cobweb theorem market dynamics.

    Domains: commodity, agriculture, housing, supply_chain, market_dynamics
    Priority: 0 (supply_shock and demand_shock are external env inputs from agents)

    Use market_id for multiple distinct commodity markets in the same sim.
    """

    DOMAINS = ["commodity", "agriculture", "housing", "supply_chain", "market_dynamics", "ecology", "viticulture", "climate", "land"]

    class Parameters(BaseModel):
        supply_elasticity: float = Field(
            default=0.60, ge=0.0, le=2.0,
            description="b: supply response to lagged price (higher = more responsive producers)",
        )
        demand_elasticity: float = Field(
            default=0.80, ge=0.01, le=2.0,
            description="d: demand price sensitivity; must be > 0 to solve for clearing price",
        )
        supply_intercept: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="a: base supply quantity at zero price",
        )
        demand_intercept: float = Field(
            default=0.80, ge=0.0, le=1.0,
            description="c: demand quantity at zero price",
        )
        price_adjustment_speed: float = Field(
            default=1.0, ge=0.0, le=1.0,
            description="λ: 1.0 = pure cobweb; <1 = partial adjustment (dampened oscillations)",
        )
        tick_unit: str = Field(default="year")
        market_id: str = Field(
            default="cobweb",
            description="Env key prefix; e.g. 'wheat' → wheat__price",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        m = self.params.market_id
        return TheoryStateVariables(
            reads=[
                f"{m}__price",
                f"{m}__supply_shock",
                f"{m}__demand_shock",
            ],
            writes=[
                f"{m}__price",
                f"{m}__supply",
                f"{m}__demand",
                f"{m}__excess_demand",
                f"{m}__price_volatility",
            ],
            initializes=[
                f"{m}__price",
                f"{m}__supply",
                f"{m}__demand",
                f"{m}__excess_demand",
                f"{m}__price_volatility",
                f"{m}__supply_shock",   # owned by agents; seeded here
                f"{m}__demand_shock",   # owned by agents; seeded here
            ],
        )

    def _steady_state_price(self) -> float:
        """Compute P* = (c - a) / (d + b) from current parameters."""
        p = self.params
        return max(
            0.0,
            (p.demand_intercept - p.supply_intercept)
            / max(1e-9, p.demand_elasticity + p.supply_elasticity),
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed price at steady-state P* = (c-a)/(d+b) and shocks at zero.
        """
        inits = super().setup(env)
        m = self.params.market_id
        if f"{m}__price" not in env:
            inits[f"{m}__price"] = self._steady_state_price()
        if f"{m}__supply_shock" not in env:
            inits[f"{m}__supply_shock"] = 0.0
        if f"{m}__demand_shock" not in env:
            inits[f"{m}__demand_shock"] = 0.0
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one cobweb market step.

        1. Read last period's price (the cobweb lag for supply decisions).
        2. Compute supply based on lagged price.
        3. Compute clearing price from demand-side equilibrium.
        4. Apply partial price adjustment toward clearing price.
        5. Compute quantities, volatility, and excess demand.

        Args:
            env:    normalized environment (read-only)
            agents: not used directly (shocks come from env)
            tick:   zero-based tick counter

        Returns:
            delta dict with price, supply, demand, excess_demand, price_volatility.
        """
        p = self.params
        m = p.market_id
        p_star = self._steady_state_price()

        prev_price = env.get(f"{m}__price", p_star)
        supply_shock = env.get(f"{m}__supply_shock", 0.0)
        demand_shock = env.get(f"{m}__demand_shock", 0.0)

        # Supply based on LAST PERIOD price (the cobweb lag)
        Q_s = max(
            0.0,
            min(1.0, p.supply_intercept + p.supply_elasticity * prev_price - supply_shock),
        )

        # Demand at clearing price — solve: Q_d = c + demand_shock - d*P = Q_s
        # P_clearing = (c + demand_shock - Q_s) / d
        P_clearing = max(
            0.0,
            min(
                1.0,
                (p.demand_intercept + demand_shock - Q_s) / max(1e-9, p.demand_elasticity),
            ),
        )

        # Partial price adjustment (λ=1: pure cobweb; λ<1: dampened)
        new_price = max(
            0.0,
            min(
                1.0,
                p.price_adjustment_speed * P_clearing
                + (1.0 - p.price_adjustment_speed) * prev_price,
            ),
        )

        # Quantities at new price
        Q_d = max(
            0.0,
            min(1.0, p.demand_intercept + demand_shock - p.demand_elasticity * new_price),
        )

        price_volatility = max(0.0, min(1.0, abs(new_price - prev_price)))
        excess_demand = max(
            0.0,
            min(1.0, (Q_d - Q_s) / max(1e-9, p.demand_intercept)),
        )

        logger.debug(
            "CobwebMarket tick=%d market=%s: prev_price=%.4f new_price=%.4f "
            "Q_s=%.4f Q_d=%.4f volatility=%.4f excess_demand=%.4f",
            tick, m, prev_price, new_price, Q_s, Q_d, price_volatility, excess_demand,
        )

        return {
            f"{m}__price": new_price,
            f"{m}__supply": Q_s,
            f"{m}__demand": Q_d,
            f"{m}__excess_demand": excess_demand,
            f"{m}__price_volatility": price_volatility,
        }
