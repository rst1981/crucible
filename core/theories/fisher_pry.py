"""
Fisher-Pry Technology Substitution Model (1971)

New technology replaces incumbent technology via logistic (S-curve) market share growth.
Unlike Bass diffusion (which models first-time adoption), Fisher-Pry models SUBSTITUTION
between two competing technologies sharing an existing market.

Core equation:
    df/dt = α_eff × f × (1 - f)

where:
    f     = new technology market share ∈ (0, 1)
    α_eff = effective substitution rate (base rate × cost and GDP multipliers)

The logistic shape arises because:
  - Growth is slow when f ≈ 0 (few adopters to spread word / few units driving costs down)
  - Growth is maximal at f = 0.5 (equal market split — maximum competition)
  - Growth slows again at f ≈ 1 (market saturation)

Effective substitution rate:
    α_eff = α × (1 + cost_sensitivity × cost_reduction) × (1 + gdp_sensitivity × (GDP - 0.5))

Cost reductions (from experience curve learning) and GDP booms both accelerate substitution.

Takeoff index:
    TI = 4 × f × (1 - f)    peaks at 1.0 when f = 0.5 (inflection point of S-curve)

Cross-theory integration:
    {tech_id}__cost_reduction     — from experience_curve theory; reduces new tech cost
    keynesian__gdp_normalized     — from Keynesian macro theory; GDP boom effect

Env keys written:
    {tech_id}__new_tech_share      f: new technology market fraction ∈ [0, 1]
    {tech_id}__old_tech_share      1 - f: incumbent fraction ∈ [0, 1]
    {tech_id}__substitution_flow   df/dt × dt: share transferred this tick ∈ [0, 1]
    {tech_id}__takeoff_index       4 × f × (1-f): S-curve progress indicator ∈ [0, 1]

Env keys initialized but not written (owned by other theories/agents):
    {tech_id}__cost_reduction      (default seed = 0.0; set by experience_curve)

Use tech_id for multiple simultaneous technology substitutions (e.g., "ev", "solar_pv").

References:
    Fisher, J. C. and Pry, R. H. (1971). A simple substitution model of technological change.
    Technological Forecasting and Social Change 3: 75–88.
    Marchetti, C. and Nakicenovic, N. (1979). The dynamics of energy systems and the logistic
    substitution model. International Institute for Applied Systems Analysis RR-79-13.
    Grübler, A., Nakicenovic, N. and Victor, D. G. (1999). Dynamics of energy technologies and
    global change. Energy Policy 27(5): 247–280.
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


@register_theory("fisher_pry")
class FisherPry(TheoryBase):
    """
    Fisher-Pry (1971) logistic technology substitution model.

    Domains: technology, energy_transition, substitution, innovation, market
    Priority: 1 (reads cost_reduction from experience_curve theory; run after it)

    Use tech_id for multiple distinct technology substitution races in the same sim.
    """

    DOMAINS = ["technology", "energy_transition", "substitution", "innovation", "market"]

    class Parameters(BaseModel):
        substitution_rate: float = Field(
            default=0.30, ge=0.01, le=2.0,
            description="α: base substitution rate per tick-unit "
                        "(ln(2)/t_half where t_half is years to reach 50% share from entry)",
        )
        cost_sensitivity: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="How much cost reduction (from experience curve) accelerates substitution",
        )
        gdp_sensitivity: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="GDP boom effect on substitution rate (GDP above 0.5 accelerates)",
        )
        tick_unit: str = Field(default="year")
        tech_id: str = Field(
            default="fisher",
            description="Env key prefix; e.g. 'ev' → ev__new_tech_share",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        t = self.params.tech_id
        return TheoryStateVariables(
            reads=[
                f"{t}__new_tech_share",
                f"{t}__cost_reduction",
                "keynesian__gdp_normalized",
            ],
            writes=[
                f"{t}__new_tech_share",
                f"{t}__old_tech_share",
                f"{t}__substitution_flow",
                f"{t}__takeoff_index",
            ],
            initializes=[
                f"{t}__new_tech_share",
                f"{t}__old_tech_share",
                f"{t}__substitution_flow",
                f"{t}__takeoff_index",
                f"{t}__cost_reduction",   # owned by experience_curve or agents; seeded here
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed new technology at just-entered-market level (1%).
        Seeds cost_reduction at 0.0 (no learning advantage yet).
        """
        inits = super().setup(env)
        t = self.params.tech_id
        if f"{t}__new_tech_share" not in env:
            inits[f"{t}__new_tech_share"] = 0.01
        if f"{t}__cost_reduction" not in env:
            inits[f"{t}__cost_reduction"] = 0.0
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Fisher-Pry logistic substitution step.

        1. Read current new tech share, cost reduction, and GDP.
        2. Compute effective substitution rate (α_eff).
        3. Apply logistic equation: df = α_eff × f × (1-f) × dt.
        4. Compute all output variables and clamp to [0, 1].

        Args:
            env:    normalized environment (read-only)
            agents: not used directly
            tick:   zero-based tick counter

        Returns:
            delta dict with new_tech_share, old_tech_share, substitution_flow, takeoff_index.
        """
        p = self.params
        t = p.tech_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        f = env.get(f"{t}__new_tech_share", 0.01)
        cost_reduction = env.get(f"{t}__cost_reduction", 0.0)
        gdp = env.get("keynesian__gdp_normalized", 0.50)

        # Effective substitution rate: base × cost multiplier × GDP multiplier
        alpha_eff = max(
            0.0,
            p.substitution_rate
            * (1.0 + p.cost_sensitivity * cost_reduction)
            * (1.0 + p.gdp_sensitivity * (gdp - 0.50)),
        )

        # Fisher-Pry logistic substitution
        df = alpha_eff * f * (1.0 - f) * dt
        new_f = max(0.0, min(1.0, f + df))

        old_share = max(0.0, min(1.0, 1.0 - new_f))
        substitution_flow = max(0.0, min(1.0, abs(new_f - f)))

        # Takeoff index: peaks at 1.0 when f = 0.5 (S-curve inflection)
        takeoff_index = max(0.0, min(1.0, 4.0 * new_f * (1.0 - new_f)))

        logger.debug(
            "FisherPry tick=%d tech=%s: f=%.4f→%.4f alpha_eff=%.4f "
            "flow=%.4f takeoff=%.4f gdp=%.3f cost_reduction=%.3f",
            tick, t, f, new_f, alpha_eff, substitution_flow, takeoff_index,
            gdp, cost_reduction,
        )

        return {
            f"{t}__new_tech_share": new_f,
            f"{t}__old_tech_share": old_share,
            f"{t}__substitution_flow": substitution_flow,
            f"{t}__takeoff_index": takeoff_index,
        }
