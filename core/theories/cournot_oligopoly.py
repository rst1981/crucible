"""
Cournot Oligopoly Model (1838)

Two firms simultaneously choose quantities. Market price is determined by the
inverse demand curve. Each firm best-responds to the rival's previous output.

Inverse demand:
    P = max(0, P_max - demand_slope · (q_A + q_B))

Firm A best-response (FOC of profit maximization):
    q_A* = (P_max - demand_slope·q_B - c_A) / (2·demand_slope)

Symmetric Nash equilibrium (c_A = c_B = c):
    q* = (P_max - c) / (3·demand_slope)
    P* = (P_max + 2c) / 3
    π* = (P_max - c)² / (9·demand_slope)

Adjustment dynamics (Cournot tatônnement — firms best-respond each period):
    q_A[t+1] = q_A[t] + adjustment_speed·(q_A* - q_A[t])

GDP modulation: above-baseline GDP shifts P_max upward (demand expansion).

All quantities normalized to [0, 1] relative to market_capacity.
Prices normalized to [0, 1] relative to P_max.
Profit margins normalized: 1.0 = theoretical monopoly profit ceiling.

Env keys written:
    {market_id}__firm_a_quantity      q_A ∈ [0, 1]
    {market_id}__firm_b_quantity      q_B ∈ [0, 1]
    {market_id}__market_price         P / P_max ∈ [0, 1]
    {market_id}__firm_a_margin        firm A profit / monopoly_profit ∈ [0, 1]
    {market_id}__firm_b_margin        firm B profit / monopoly_profit ∈ [0, 1]
    {market_id}__market_concentration HHI-equivalent ∈ [0, 1] (1.0 = monopoly)

Env keys read:
    keynesian__gdp_normalized          demand expansion above baseline

Reference: Cournot (1838). Recherches sur les Principes Mathématiques de la
           Théorie des Richesses. Hachette.
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


@register_theory("cournot_oligopoly")
class CournotOligopoly(TheoryBase):
    """
    Cournot (1838) quantity-setting duopoly with best-response dynamics.

    Domains: market, competitive_strategy, antitrust, pricing
    Priority: 0 (reads Keynesian GDP if present; independent of conflict theories)

    Use market_id for multiple independent product markets in one sim.
    """

    DOMAINS = ["market", "competitive_strategy", "antitrust", "pricing"]

    class Parameters(BaseModel):
        p_max: float = Field(
            default=1.0, ge=0.0, le=2.0,
            description="Maximum willingness to pay (normalized demand intercept)",
        )
        demand_slope: float = Field(
            default=1.0, ge=0.1, le=5.0,
            description="Slope of inverse demand: P = p_max - demand_slope·(q_A+q_B)",
        )
        cost_a: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Firm A marginal cost (normalized)",
        )
        cost_b: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Firm B marginal cost (normalized)",
        )
        adjustment_speed: float = Field(
            default=0.50, ge=0.0, le=1.0,
            description="Fraction of best-response gap closed each tick (tatônnement speed)",
        )
        gdp_demand_sensitivity: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="How much above-baseline GDP shifts P_max upward",
        )
        tick_unit: str = Field(default="year")
        market_id: str = Field(
            default="cournot",
            description="Env key prefix; e.g. 'telecom' → telecom__market_price",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        m = self.params.market_id
        return TheoryStateVariables(
            reads=[
                f"{m}__firm_a_quantity",
                f"{m}__firm_b_quantity",
                "keynesian__gdp_normalized",
            ],
            writes=[
                f"{m}__firm_a_quantity",
                f"{m}__firm_b_quantity",
                f"{m}__market_price",
                f"{m}__firm_a_margin",
                f"{m}__firm_b_margin",
                f"{m}__market_concentration",
            ],
            initializes=[
                f"{m}__firm_a_quantity",
                f"{m}__firm_b_quantity",
                f"{m}__market_price",
                f"{m}__firm_a_margin",
                f"{m}__firm_b_margin",
                f"{m}__market_concentration",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """Seed quantities at symmetric Nash equilibrium."""
        inits = super().setup(env)
        m = self.params.market_id
        p = self.params
        q_nash = max(0.0, (p.p_max - p.cost_a) / (3.0 * p.demand_slope))
        q_nash = min(1.0, q_nash)
        if f"{m}__firm_a_quantity" not in env:
            inits[f"{m}__firm_a_quantity"] = q_nash
        if f"{m}__firm_b_quantity" not in env:
            inits[f"{m}__firm_b_quantity"] = q_nash
        return inits

    def _monopoly_profit(self, p_max: float) -> float:
        """Theoretical monopoly profit ceiling for margin normalization."""
        p = self.params
        avg_cost = (p.cost_a + p.cost_b) / 2.0
        return max(1e-6, (p_max - avg_cost) ** 2 / (4.0 * p.demand_slope))

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Cournot best-response step.

        1. Adjust P_max for current GDP conditions.
        2. Compute each firm's best-response quantity.
        3. Adjust actual quantities toward best-response at adjustment_speed.
        4. Derive market price, margins, and concentration.
        """
        p = self.params
        m = p.market_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        q_a = env.get(f"{m}__firm_a_quantity", 0.2)
        q_b = env.get(f"{m}__firm_b_quantity", 0.2)

        # GDP shifts demand intercept
        gdp = env.get("keynesian__gdp_normalized", 0.5)
        p_max_eff = p.p_max * (1.0 + p.gdp_demand_sensitivity * (gdp - 0.5))
        p_max_eff = max(0.0, p_max_eff)

        # Best-response quantities
        q_a_star = (p_max_eff - p.demand_slope * q_b - p.cost_a) / (2.0 * p.demand_slope)
        q_b_star = (p_max_eff - p.demand_slope * q_a - p.cost_b) / (2.0 * p.demand_slope)
        q_a_star = max(0.0, min(1.0, q_a_star))
        q_b_star = max(0.0, min(1.0, q_b_star))

        # Tatônnement: partial adjustment toward best-response
        new_q_a = q_a + p.adjustment_speed * (q_a_star - q_a) * dt
        new_q_b = q_b + p.adjustment_speed * (q_b_star - q_b) * dt
        new_q_a = max(0.0, min(1.0, new_q_a))
        new_q_b = max(0.0, min(1.0, new_q_b))

        # Market price
        price = max(0.0, p_max_eff - p.demand_slope * (new_q_a + new_q_b))
        price_norm = min(1.0, price / max(p_max_eff, 1e-9))

        # Profit margins (normalized by monopoly profit ceiling)
        mono_profit = self._monopoly_profit(p_max_eff)
        margin_a = max(0.0, min(1.0, (price - p.cost_a) * new_q_a / mono_profit))
        margin_b = max(0.0, min(1.0, (price - p.cost_b) * new_q_b / mono_profit))

        # Market concentration: HHI-equivalent (sum of squared market shares)
        q_total = new_q_a + new_q_b
        if q_total > 1e-9:
            share_a = new_q_a / q_total
            share_b = new_q_b / q_total
            hhi = share_a ** 2 + share_b ** 2  # ∈ [0.5, 1.0] for duopoly
            concentration = (hhi - 0.5) / 0.5  # normalize: 0=equal split, 1=monopoly
        else:
            concentration = 1.0

        logger.debug(
            "Cournot tick=%d market=%s: q_A=%.3f→%.3f q_B=%.3f→%.3f "
            "P=%.3f margin_A=%.3f conc=%.3f",
            tick, m, q_a, new_q_a, q_b, new_q_b, price, margin_a, concentration,
        )

        return {
            f"{m}__firm_a_quantity":     new_q_a,
            f"{m}__firm_b_quantity":     new_q_b,
            f"{m}__market_price":        price_norm,
            f"{m}__firm_a_margin":       margin_a,
            f"{m}__firm_b_margin":       margin_b,
            f"{m}__market_concentration": concentration,
        }

    def nash_equilibrium(self) -> tuple[float, float, float] | None:
        """
        Compute symmetric Nash equilibrium quantities and price.

        Returns (q_a*, q_b*, P*) at default P_max (no GDP adjustment).
        Returns None if equilibrium implies non-positive output.
        """
        p = self.params
        q_a = (p.p_max - 2 * p.cost_a + p.cost_b) / (3.0 * p.demand_slope)
        q_b = (p.p_max - 2 * p.cost_b + p.cost_a) / (3.0 * p.demand_slope)
        if q_a <= 0 or q_b <= 0:
            return None
        price = p.p_max - p.demand_slope * (q_a + q_b)
        return q_a, q_b, price
