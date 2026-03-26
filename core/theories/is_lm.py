"""
IS-LM Model (Hicks, 1937)

The IS-LM model characterizes macroeconomic equilibrium by combining two
curves: the IS curve (goods market equilibrium: investment = savings) and the
LM curve (money market equilibrium: money demand = money supply). Together
they determine output gap Y and interest rate r.

IS curve — goods market equilibrium:
    Y_IS = (autonomous_spending - investment_sensitivity × r) / (1 - mpc)

    where autonomous_spending = 0.25 + G (baseline consumption + fiscal shock G)
    and mpc is the marginal propensity to consume.

LM curve — money market equilibrium:
    r_LM = (income_money_demand × Y - money_supply) / rate_money_demand

Dynamic version: Y and r adjust toward IS-LM equilibrium with inertia:
    Y[t+1] = Y[t] + adjustment_speed × (Y_IS - Y[t]) × dt
    r[t+1] = r[t] + adjustment_speed × (r_LM - r[t]) × dt

Fiscal policy (G shock) shifts the IS curve rightward → higher Y, higher r.
Monetary policy (M supply) shifts the LM curve rightward → lower r, higher Y.

Characteristic values:
    mpc = 0.75 → Keynesian multiplier of 4 (standard)
    investment_sensitivity = 0.30 → moderate interest-rate sensitivity of investment
    adjustment_speed = 0.50 → 50% gap closed per year (moderate inertia)

Env keys written:
    {market_id}__output_gap       Y ∈ [0,1]: 0=recession, 0.5=neutral, 1=boom
    {market_id}__interest_rate    r ∈ [0,1]: normalized interest rate
    {market_id}__investment       I ∈ [0,1]: investment demand
    {market_id}__is_lm_gap        ∈ [0,1]: distance from full IS-LM equilibrium

Env keys initialized but not written (set by agents / shocks):
    {market_id}__fiscal_stimulus   G ∈ [0,1]: government spending shock
    {market_id}__money_supply      M ∈ [0,1]: real money supply (M/P)

Use market_id for multiple simultaneous macro environments in one simulation.

References:
    Hicks (1937). Mr. Keynes and the "Classics"; A Suggested Interpretation.
    Econometrica 5(2): 147–159.
    Blanchard & Fischer (1989). Lectures on Macroeconomics. MIT Press.
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


@register_theory("is_lm")
class ISLM(TheoryBase):
    """
    Hicks (1937) IS-LM macroeconomic equilibrium model.

    Domains: macro, monetary_policy, fiscal_policy, interest_rates, output
    Priority: 0 (reads fiscal_stimulus and money_supply as external env inputs)

    Use market_id for multiple independent macro environments in one sim.
    """

    DOMAINS = ["macro", "monetary_policy", "fiscal_policy", "interest_rates", "output"]

    class Parameters(BaseModel):
        mpc: float = Field(
            default=0.75, ge=0.0, lt=1.0,
            description="Marginal propensity to consume; determines Keynesian multiplier "
                        "(must be < 1 to ensure finite multiplier)",
        )
        investment_sensitivity: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="b: sensitivity of investment to interest rate; "
                        "higher b → steeper IS curve slope",
        )
        income_money_demand: float = Field(
            default=0.50, ge=0.0, le=1.0,
            description="k: income elasticity of money demand; "
                        "higher k → steeper LM curve",
        )
        rate_money_demand: float = Field(
            default=0.40, ge=0.01, le=1.0,
            description="h: interest rate semi-elasticity of money demand (>0 to avoid "
                        "division by zero); higher h → flatter LM curve (liquidity trap limit)",
        )
        adjustment_speed: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="Speed at which Y and r adjust toward IS-LM equilibrium per year; "
                        "1.0 = full adjustment in one year",
        )
        tick_unit: str = Field(default="year")
        market_id: str = Field(
            default="islm",
            description="Env key prefix; e.g. 'us_macro' → us_macro__output_gap",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        m = self.params.market_id
        return TheoryStateVariables(
            reads=[
                f"{m}__output_gap",
                f"{m}__interest_rate",
                f"{m}__fiscal_stimulus",
                f"{m}__money_supply",
            ],
            writes=[
                f"{m}__output_gap",
                f"{m}__interest_rate",
                f"{m}__investment",
                f"{m}__is_lm_gap",
            ],
            initializes=[
                f"{m}__output_gap",
                f"{m}__interest_rate",
                f"{m}__investment",
                f"{m}__is_lm_gap",
                f"{m}__fiscal_stimulus",   # seeded at 0.0; agents/shocks override
                f"{m}__money_supply",      # seeded at 0.50; agents/shocks override
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed output_gap at 0.50 (neutral), interest_rate at 0.05,
        fiscal_stimulus at 0.0 (no shock), money_supply at 0.50 (baseline).
        """
        inits = super().setup(env)
        m = self.params.market_id
        if f"{m}__output_gap" not in env:
            inits[f"{m}__output_gap"] = 0.50
        if f"{m}__interest_rate" not in env:
            inits[f"{m}__interest_rate"] = 0.05
        if f"{m}__fiscal_stimulus" not in env:
            inits[f"{m}__fiscal_stimulus"] = 0.0
        if f"{m}__money_supply" not in env:
            inits[f"{m}__money_supply"] = 0.50
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one IS-LM dynamic adjustment step.

        1. Read current Y, r, fiscal stimulus G, and money supply M.
        2. Compute IS equilibrium output (Y_IS) and LM equilibrium rate (r_LM).
        3. Partially adjust Y and r toward their respective equilibria.
        4. Derive investment demand and IS-LM gap.

        Args:
            env:    normalized environment (read-only)
            agents: not used (IS-LM is driven by macro aggregates, not individual agents)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated output_gap, interest_rate, investment, is_lm_gap.
        """
        p = self.params
        m = p.market_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        Y = env.get(f"{m}__output_gap", 0.50)
        r = env.get(f"{m}__interest_rate", 0.05)
        G = env.get(f"{m}__fiscal_stimulus", 0.0)
        M = env.get(f"{m}__money_supply", 0.50)

        # Autonomous spending (normalized): baseline consumption 0.25 + fiscal shock G
        autonomous = 0.25 + G

        # IS equilibrium output: Y_IS = (autonomous - b*r) / (1 - mpc)
        Y_IS = max(0.0, min(1.0,
            (autonomous - p.investment_sensitivity * r) / max(0.01, 1.0 - p.mpc)
        ))

        # LM equilibrium rate: r_LM = (k*Y - M) / h
        r_LM = max(0.0, min(1.0,
            (p.income_money_demand * Y - M) / p.rate_money_demand
        ))

        # Dynamic adjustment (partial adjustment toward IS-LM equilibrium)
        new_Y = max(0.0, min(1.0, Y + p.adjustment_speed * (Y_IS - Y) * dt))
        new_r = max(0.0, min(1.0, r + p.adjustment_speed * (r_LM - r) * dt))

        # Investment demand: I = autonomous - b*r (clamped)
        investment = max(0.0, min(1.0, autonomous - p.investment_sensitivity * new_r))

        # IS-LM gap: distance from equilibrium (sum of absolute deviations)
        is_lm_gap = max(0.0, min(1.0, abs(Y_IS - new_Y) + abs(r_LM - new_r)))

        logger.debug(
            "ISLM tick=%d market=%s: Y=%.3f→%.3f r=%.3f→%.3f "
            "Y_IS=%.3f r_LM=%.3f inv=%.3f gap=%.3f",
            tick, m, Y, new_Y, r, new_r, Y_IS, r_LM, investment, is_lm_gap,
        )

        return {
            f"{m}__output_gap":    new_Y,
            f"{m}__interest_rate": new_r,
            f"{m}__investment":    investment,
            f"{m}__is_lm_gap":     is_lm_gap,
        }
