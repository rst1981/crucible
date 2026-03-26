"""
Efficiency Wages — Shapiro-Stiglitz (1984) No-Shirking Condition

Firms pay above-market wages to deter shirking when monitoring is imperfect.
The key insight: involuntary unemployment is the equilibrium "discipline device."
Workers who are caught shirking lose their job and face the unemployment pool.

No-Shirking Condition (NSC):
    Workers prefer to work when the expected gain from shirking is eliminated by:
        monitoring_intensity × wage_premium ≥ effort_cost + separation_rate

Unemployment rate consistent with NSC:
    u* = separation_rate / (q × (w/w_m - 1) / e + b)
    where:
        q = monitoring intensity
        w/w_m = wage premium (wage relative to market wage)
        e = effort cost
        b = separation rate

Behavioral predictions:
    - Higher wages → lower unemployment needed to discipline workers
    - Higher monitoring → same effort achieved at lower unemployment cost
    - Higher effort cost → firms must pay more or tolerate more unemployment

Cross-theory:
    {labor_id}__wage_premium  — set by firms/agents; determines incentive discipline
                                (initialized to 1.20; agents/firms override per tick)

Env keys written:
    {labor_id}__effort_level      actual worker effort ∈ [0, 1]
    {labor_id}__shirking_rate     fraction shirking (1 - effort_normalized) ∈ [0, 1]
    {labor_id}__unemployment_rate equilibrium unemployment rate ∈ [0, 1]
    {labor_id}__productivity      effort × (1 - unemployment_rate) ∈ [0, 1]

Env keys initialized but not written (owned by agents/firms):
    {labor_id}__wage_premium      w/w_market ratio (default seed = 1.20)

Use labor_id for multiple simultaneous labor markets (e.g., "skilled", "unskilled").

References:
    Shapiro, C. and Stiglitz, J. E. (1984). Equilibrium unemployment as a
    worker discipline device. The American Economic Review 74(3): 433–444.
    Akerlof, G. A. and Yellen, J. L. (1986). Efficiency wage models of the
    labor market. Cambridge University Press.
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


@register_theory("efficiency_wages")
class EfficiencyWages(TheoryBase):
    """
    Shapiro-Stiglitz (1984) efficiency wages / no-shirking condition model.

    Domains: labor, corporate_governance, incentives, human_resources, policy
    Priority: 0 (reads wage_premium set by firm agents; no circular dependencies)

    Use labor_id for multiple distinct labor market segments in the same sim.
    """

    DOMAINS = ["labor", "corporate_governance", "incentives", "human_resources", "policy"]

    class Parameters(BaseModel):
        monitoring_intensity: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="q: probability of catching a shirking worker per period",
        )
        separation_rate: float = Field(
            default=0.05, ge=0.0, le=0.30,
            description="b: exogenous job loss rate (quits + layoffs unrelated to shirking)",
        )
        effort_cost: float = Field(
            default=0.30, ge=0.01, le=1.0,
            description="e: disutility of effort per period (must be > 0)",
        )
        base_effort: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Minimum effort exerted even at market wage (no wage premium)",
        )
        wage_adjustment_speed: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="Speed at which firms adjust wages toward the NSC equilibrium wage",
        )
        tick_unit: str = Field(default="year")
        labor_id: str = Field(
            default="labor",
            description="Env key prefix; e.g. 'skilled' → skilled__effort_level",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        l = self.params.labor_id
        return TheoryStateVariables(
            reads=[
                f"{l}__wage_premium",
                f"{l}__effort_level",
                f"{l}__unemployment_rate",
            ],
            writes=[
                f"{l}__effort_level",
                f"{l}__shirking_rate",
                f"{l}__unemployment_rate",
                f"{l}__productivity",
            ],
            initializes=[
                f"{l}__effort_level",
                f"{l}__shirking_rate",
                f"{l}__unemployment_rate",
                f"{l}__productivity",
                f"{l}__wage_premium",  # owned by agents/firms; seeded here
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed conservative initial values for all owned keys.

        Sets effort_level to base_effort, unemployment_rate to 5% (typical),
        and wage_premium to 1.20 (20% above market) if not already in env.
        """
        inits = super().setup(env)
        l = self.params.labor_id
        p = self.params
        if f"{l}__effort_level" not in env:
            inits[f"{l}__effort_level"] = p.base_effort
        if f"{l}__unemployment_rate" not in env:
            inits[f"{l}__unemployment_rate"] = 0.05
        if f"{l}__wage_premium" not in env:
            inits[f"{l}__wage_premium"] = 1.20
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Shapiro-Stiglitz efficiency wages step.

        1. Read wage_premium set by firms.
        2. Compute effort level from NSC incentive structure.
        3. Compute equilibrium unemployment required to sustain NSC.
        4. Derive productivity as effort × employed fraction.

        Args:
            env:    normalized environment (read-only)
            agents: not used directly (wage_premium is read from env)
            tick:   zero-based tick counter

        Returns:
            delta dict with effort_level, shirking_rate, unemployment_rate, productivity.
        """
        p = self.params
        l = p.labor_id

        wage_premium = env.get(f"{l}__wage_premium", 1.20)

        # Clamp wage_premium to [1.0, 2.0] for computation
        wp = max(1.0, min(2.0, wage_premium))

        # Effort: workers exert effort when monitoring × wage_premium > effort_cost
        # NSC: q × (wp - 1) ≥ e means full effort; partial effort otherwise
        nsc_incentive = p.monitoring_intensity * (wp - 1.0)
        effort_level = max(
            p.base_effort,
            min(
                1.0,
                p.base_effort
                + (1.0 - p.base_effort) * nsc_incentive / max(p.effort_cost, 1e-9),
            ),
        )

        shirking_rate = max(0.0, min(1.0, 1.0 - effort_level))

        # Unemployment: NSC requires u* = b / (q × excess_wage/e + b)
        # Higher wage premium → lower unemployment needed as discipline device
        excess_wage = max(0.0, wp - 1.0)
        nsc_denominator = (
            p.monitoring_intensity * excess_wage / max(p.effort_cost, 1e-9)
            + p.separation_rate
        )
        unemployment_rate = max(
            0.0,
            min(1.0, p.separation_rate / max(1e-9, nsc_denominator)),
        )

        productivity = max(0.0, min(1.0, effort_level * (1.0 - unemployment_rate)))

        logger.debug(
            "EfficiencyWages tick=%d labor=%s: wage_premium=%.3f effort=%.4f "
            "shirking=%.4f unemployment=%.4f productivity=%.4f",
            tick, l, wage_premium, effort_level, shirking_rate, unemployment_rate, productivity,
        )

        return {
            f"{l}__effort_level": effort_level,
            f"{l}__shirking_rate": shirking_rate,
            f"{l}__unemployment_rate": unemployment_rate,
            f"{l}__productivity": productivity,
        }
