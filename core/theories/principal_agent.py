"""
Principal-Agent Model

A principal (employer, regulator, shareholder, government) delegates a task to
an agent (employee, firm, subsidiary, contractor) but cannot perfectly observe
effort. The agent has private information and acts in their own interest.

Two mechanisms drive misalignment:
  - Moral hazard: agent shirks when monitoring is low and incentives are weak
  - Risk sharing: high-powered incentives (β) elicit effort but impose risk on agent

Agent effort equilibrium (linear contract w = α + β·y, cost c(e) = e²/2):
    e* = β           [from FOC: β = c'(e)]

In practice, effort also depends on intrinsic motivation and risk aversion:
    effort_target = β·(1 - risk_aversion·β) + intrinsic_motivation·(1 - β)

Monitoring effect:
    shirking_discount = (1 - monitoring_intensity)·(1 - β)
    actual_effort = effort_target·(1 - shirking_discount)

    When β=1 (pure commission): monitoring irrelevant — agent already bears outcome.
    When β=0 (flat wage): monitoring is the only disciplining mechanism.

Stock dynamics (inertia — effort adjusts at rate adjustment_speed per tick):
    effort[t+1] = effort[t] + adjustment_speed·(effort_target - effort[t])

Env keys written:
    {agent_id}__effort_level          actual effort ∈ [0, 1]
    {agent_id}__compliance            observable output proxy ∈ [0, 1]
    {agent_id}__shirking_risk         P(shirking this tick) ∈ [0, 1]
    {agent_id}__incentive_alignment   contract quality score ∈ [0, 1]

Env keys initialized but not written (set by principal / shocks):
    {agent_id}__monitoring_intensity  principal's monitoring effort ∈ [0, 1]

Use agent_id for multi-instance (e.g. "subsidiary", "regulator", "contractor").

References:
    Holmström (1979). Moral hazard and observability. Bell Journal of Economics 10(1).
    Jensen & Meckling (1976). Theory of the firm. Journal of Financial Economics 3(4).
    Laffont & Tirole (1993). A Theory of Incentives in Procurement and Regulation. MIT Press.
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


@register_theory("principal_agent")
class PrincipalAgent(TheoryBase):
    """
    Principal-agent incentive alignment dynamics.

    Domains: corporate_governance, regulation, outsourcing, public_sector
    Priority: 0 (independent; monitoring_intensity is an external env input)

    Use agent_id for multiple distinct principal-agent relationships in one sim.
    """

    DOMAINS = ["corporate_governance", "regulation", "outsourcing", "public_sector"]

    class Parameters(BaseModel):
        beta: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="Incentive slope: fraction of output retained by agent "
                        "(0=flat wage, 1=pure commission/residual claimant)",
        )
        intrinsic_motivation: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="Baseline effort independent of incentives (professional norms, mission)",
        )
        risk_aversion: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="Agent risk aversion; dampens effort response to high-powered incentives",
        )
        adjustment_speed: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="Speed at which actual effort converges to target per tick",
        )
        tick_unit: str = Field(default="year")
        agent_id: str = Field(
            default="agent",
            description="Env key prefix; e.g. 'subsidiary' → subsidiary__effort_level",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        a = self.params.agent_id
        return TheoryStateVariables(
            reads=[
                f"{a}__effort_level",
                f"{a}__monitoring_intensity",
            ],
            writes=[
                f"{a}__effort_level",
                f"{a}__compliance",
                f"{a}__shirking_risk",
                f"{a}__incentive_alignment",
            ],
            initializes=[
                f"{a}__effort_level",
                f"{a}__compliance",
                f"{a}__shirking_risk",
                f"{a}__incentive_alignment",
                f"{a}__monitoring_intensity",  # seeded at 0.5; principal/shocks update
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        a = self.params.agent_id
        if f"{a}__monitoring_intensity" not in env:
            inits[f"{a}__monitoring_intensity"] = 0.50
        # Seed effort at the equilibrium given initial params (no inertia at t=0)
        if f"{a}__effort_level" not in env:
            p = self.params
            effort_target = p.beta * (1.0 - p.risk_aversion * p.beta) + \
                            p.intrinsic_motivation * (1.0 - p.beta)
            inits[f"{a}__effort_level"] = max(0.0, min(1.0, effort_target))
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Compute agent effort response to current contract and monitoring.

        1. Compute effort_target from incentive slope, intrinsic motivation, risk aversion.
        2. Apply shirking discount based on monitoring gap.
        3. Adjust effort toward target at adjustment_speed.
        4. Derive compliance, shirking_risk, and incentive_alignment diagnostics.
        """
        p = self.params
        a = p.agent_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        effort_current     = env.get(f"{a}__effort_level",        0.5)
        monitoring         = env.get(f"{a}__monitoring_intensity", 0.5)

        # Effort target: incentive + intrinsic, dampened by risk aversion on β²
        effort_target = (
            p.beta * (1.0 - p.risk_aversion * p.beta)
            + p.intrinsic_motivation * (1.0 - p.beta)
        )
        effort_target = max(0.0, min(1.0, effort_target))

        # Shirking discount: how much below-target effort monitoring failure allows
        # When β=1: agent bears all output risk → monitoring irrelevant
        # When β=0: monitoring is the only disciplining mechanism
        monitoring_gap     = max(0.0, 1.0 - monitoring)
        incentive_coverage = p.beta                          # incentives already align agent
        shirking_discount  = monitoring_gap * (1.0 - incentive_coverage)

        adjusted_target = effort_target * (1.0 - shirking_discount)

        # Inertia: effort adjusts at adjustment_speed per tick
        new_effort = effort_current + p.adjustment_speed * (adjusted_target - effort_current) * dt
        new_effort = max(0.0, min(1.0, new_effort))

        # Compliance: observable output — slightly higher than effort when monitoring is active
        compliance = min(1.0, new_effort * (1.0 + monitoring * 0.15))

        # Shirking risk: probability agent is shirking this tick
        shirking_risk = max(0.0, min(1.0, shirking_discount * (1.0 - p.intrinsic_motivation)))

        # Incentive alignment: composite of β, monitoring, and intrinsic motivation
        incentive_alignment = min(1.0,
            p.beta * 0.4
            + monitoring * 0.3
            + p.intrinsic_motivation * 0.3
        )

        logger.debug(
            "PrincipalAgent tick=%d agent=%s: effort=%.3f→%.3f target=%.3f "
            "monitoring=%.3f shirk_discount=%.3f alignment=%.3f",
            tick, a, effort_current, new_effort, effort_target,
            monitoring, shirking_discount, incentive_alignment,
        )

        return {
            f"{a}__effort_level":        new_effort,
            f"{a}__compliance":          compliance,
            f"{a}__shirking_risk":       shirking_risk,
            f"{a}__incentive_alignment": incentive_alignment,
        }
