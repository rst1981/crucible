"""
Regulatory Shock Model

Models the aftermath of a sudden regulatory change: compliance costs imposed on
firms, gradual adaptation as they adjust processes and business models, associated
market-exit risk for marginal players, and competitive advantage accruing to
incumbents who can absorb complexity.

The regulatory event itself is external — it is set by an agent action or shock
that writes to {regulation_id}__shock_magnitude. This theory models the
propagation and adaptation dynamics that follow.

Dynamics per tick:

  1. Compliance cost:
       compliance_cost = shock_magnitude × cost_sensitivity × (1 - adaptation_level)
       As firms adapt, compliance cost converges toward a lower steady state.

  2. Adaptation (stock variable — irreversible learning):
       adaptation grows logistically toward 1.0 at rate adaptation_rate
       GDP below baseline slows adaptation (less slack to invest in compliance)

  3. Market exit risk:
       exit_risk = max(0, compliance_cost - firm_resilience)
       Firms whose compliance burden exceeds their resilience face exit pressure.

  4. Competitive advantage (regulatory moat):
       complex regulation disproportionately burdens smaller/newer entrants
       advantage = compliance_cost × incumbent_advantage_factor
       (Incumbents can amortize fixed compliance costs; entrants cannot)

Cross-theory:
    keynesian__gdp_normalized     — below baseline slows adaptation (capital constraint)
    porter__barriers_to_entry     — read: high existing barriers amplify advantage
    {regulation_id}__shock_magnitude — external event key; initialized 0, set by agents

Env keys written:
    {regulation_id}__compliance_cost       ongoing cost burden ∈ [0, 1]
    {regulation_id}__adaptation_level      cumulative adaptation ∈ [0, 1]
    {regulation_id}__market_exit_risk      P(marginal firm exits) ∈ [0, 1]
    {regulation_id}__competitive_advantage incumbents' moat from complexity ∈ [0, 1]

Env keys initialized but not written (set by agents / shock events):
    {regulation_id}__shock_magnitude       regulation severity ∈ [0, 1]

Example regulation IDs: "carbon_tax", "gdpr", "antitrust", "banking_capital"

References:
    Stigler (1971). The theory of economic regulation. Bell Journal 2(1): 3–21.
    Peltzman (1976). Toward a more general theory of regulation. JLE 19(2): 211–240.
    Viscusi et al. (2005). Economics of Regulation and Antitrust. MIT Press.
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


@register_theory("regulatory_shock")
class RegulatoryShock(TheoryBase):
    """
    Regulatory event propagation and firm adaptation dynamics.

    Domains: regulation, policy, market_structure, compliance
    Priority: 0 (reads Keynesian GDP and Porter barriers if present)

    Use regulation_id for multiple simultaneous regulatory regimes in one sim.
    """

    DOMAINS = ["regulation", "policy", "market_structure", "compliance"]

    class Parameters(BaseModel):
        cost_sensitivity: float = Field(
            default=0.60, ge=0.0, le=1.0,
            description="How much shock_magnitude translates into compliance cost "
                        "(depends on regulatory scope and industry capital intensity)",
        )
        adaptation_rate: float = Field(
            default=0.15, ge=0.0, le=1.0,
            description="Speed of adaptation per tick (process improvement, legal optimization)",
        )
        firm_resilience: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Compliance cost below which no exit risk (margin buffer)",
        )
        incumbent_advantage_factor: float = Field(
            default=0.50, ge=0.0, le=1.0,
            description="Multiplier on compliance_cost → competitive advantage for incumbents "
                        "(fixed compliance costs are a barrier to entry)",
        )
        gdp_adaptation_sensitivity: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="How much below-baseline GDP slows adaptation (capital constraint)",
        )
        tick_unit: str = Field(default="year")
        regulation_id: str = Field(
            default="regulation",
            description="Env key prefix; e.g. 'carbon_tax' → carbon_tax__compliance_cost",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        r = self.params.regulation_id
        return TheoryStateVariables(
            reads=[
                f"{r}__shock_magnitude",
                f"{r}__adaptation_level",
                "keynesian__gdp_normalized",
                "porter__barriers_to_entry",
            ],
            writes=[
                f"{r}__compliance_cost",
                f"{r}__adaptation_level",
                f"{r}__market_exit_risk",
                f"{r}__competitive_advantage",
            ],
            initializes=[
                f"{r}__compliance_cost",
                f"{r}__adaptation_level",
                f"{r}__market_exit_risk",
                f"{r}__competitive_advantage",
                f"{r}__shock_magnitude",  # seeded at 0.0; agents inject the regulatory event
            ],
        )

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Propagate regulatory shock and advance adaptation.

        1. Read current shock magnitude (set externally).
        2. Grow adaptation stock (slowed by GDP below baseline).
        3. Compute compliance cost = shock × cost_sensitivity × (1 - adaptation).
        4. Compute exit risk and competitive advantage.
        """
        p = self.params
        r = p.regulation_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        shock       = env.get(f"{r}__shock_magnitude",  0.0)
        adaptation  = env.get(f"{r}__adaptation_level", 0.0)

        # GDP modulates adaptation speed: recession → less slack to invest in compliance
        gdp = env.get("keynesian__gdp_normalized", 0.5)
        gdp_factor = 1.0 - p.gdp_adaptation_sensitivity * max(0.0, 0.5 - gdp)
        gdp_factor = max(0.0, gdp_factor)

        # Logistic adaptation: fast early, slowing as limits approach
        adaptation_delta = p.adaptation_rate * (1.0 - adaptation) * gdp_factor * dt
        new_adaptation = min(1.0, adaptation + adaptation_delta)

        # Compliance cost: falls as adaptation rises
        compliance_cost = shock * p.cost_sensitivity * (1.0 - new_adaptation)
        compliance_cost = max(0.0, min(1.0, compliance_cost))

        # Market exit risk: firms below resilience threshold face exit pressure
        exit_risk = max(0.0, min(1.0, compliance_cost - p.firm_resilience))

        # Competitive advantage: complex regulation creates incumbents' moat
        # Amplified if Porter barriers are already high (established players benefit more)
        porter_barriers = env.get("porter__barriers_to_entry", 0.5)
        barrier_amplifier = 1.0 + 0.5 * porter_barriers  # high barriers → more advantage
        competitive_advantage = min(1.0,
            compliance_cost * p.incumbent_advantage_factor * barrier_amplifier
        )

        logger.debug(
            "RegShock tick=%d reg=%s: shock=%.3f adapt=%.3f→%.3f "
            "cost=%.3f exit=%.3f advantage=%.3f",
            tick, r, shock, adaptation, new_adaptation,
            compliance_cost, exit_risk, competitive_advantage,
        )

        return {
            f"{r}__compliance_cost":       compliance_cost,
            f"{r}__adaptation_level":      new_adaptation,
            f"{r}__market_exit_risk":      exit_risk,
            f"{r}__competitive_advantage": competitive_advantage,
        }
