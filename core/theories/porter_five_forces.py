"""
Porter's Five Forces (1980)

Five force variables [0,1] (higher = stronger force = worse for incumbents):
  barriers_to_entry    0 = easy entry, 1 = very high barriers
  supplier_power       0 = fragmented, 1 = monopoly supplier
  buyer_power          0 = fragmented, 1 = monopsony buyer
  substitute_threat    0 = no substitutes, 1 = perfect substitutes
  rivalry_intensity    0 = cooperative oligopoly, 1 = full price war

Industry profitability:
  P = base_margin + w_barriers*barriers - w_supplier*supplier
                  - w_buyer*buyer - w_substitute*substitute - w_rivalry*rivalry

Force evolution per tick:
  barriers_to_entry: raised by porter__capacity_investment, eroded by entry_erosion_rate
  rivalry_intensity: dampened by above-baseline GDP growth; amplified by trade contraction
  supplier/buyer/substitute: slow mean-reversion toward structural defaults

Env keys written:
    porter__barriers_to_entry
    porter__supplier_power
    porter__buyer_power
    porter__substitute_threat
    porter__rivalry_intensity
    porter__profitability

Env keys read:
    porter__capacity_investment  set by actor actions each tick
    keynesian__gdp_normalized    GDP signal for rivalry dampening
    global__trade_volume         trade disruption increases rivalry

Reference: Porter (1980) Competitive Strategy. Free Press.
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


@register_theory("porter_five_forces")
class PorterFiveForces(TheoryBase):
    """
    Industry competitive structure dynamics.

    Domains: market, corporate_strategy, industry_analysis
    Priority: 0 (runs before supply/demand and contagion theories;
              reads keynesian__gdp_normalized from Keynesian at same priority —
              order within priority-0 bucket should put Keynesian first)
    """

    DOMAINS = ["market", "corporate_strategy", "industry_analysis"]

    class Parameters(BaseModel):
        # Profitability weights (Porter 1980 empirical calibration)
        w_barriers:   float = Field(default=0.25, ge=0.0, le=1.0)
        w_supplier:   float = Field(default=0.20, ge=0.0, le=1.0)
        w_buyer:      float = Field(default=0.20, ge=0.0, le=1.0)
        w_substitute: float = Field(default=0.15, ge=0.0, le=1.0)
        w_rivalry:    float = Field(default=0.20, ge=0.0, le=1.0)
        base_margin:  float = Field(default=0.50, ge=0.0, le=1.0)
        # Force evolution
        entry_erosion_rate: float = Field(
            default=0.02, ge=0.0, le=0.2,
            description="Natural decay of barriers per tick (competitive pressure)",
        )
        rivalry_growth_sensitivity: float = Field(
            default=0.25, ge=0.0, le=1.0,
            description="How much above-baseline GDP growth dampens rivalry",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "porter__barriers_to_entry",
                "porter__supplier_power",
                "porter__buyer_power",
                "porter__substitute_threat",
                "porter__rivalry_intensity",
                "porter__capacity_investment",
                "keynesian__gdp_normalized",
                "global__trade_volume",
            ],
            writes=[
                "porter__barriers_to_entry",
                "porter__supplier_power",
                "porter__buyer_power",
                "porter__substitute_threat",
                "porter__rivalry_intensity",
                "porter__profitability",
            ],
            initializes=[
                "porter__barriers_to_entry",
                "porter__supplier_power",
                "porter__buyer_power",
                "porter__substitute_threat",
                "porter__rivalry_intensity",
                "porter__profitability",
                "porter__capacity_investment",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        # Default: moderately competitive industry
        defaults = {
            "porter__barriers_to_entry":  0.50,
            "porter__supplier_power":     0.40,
            "porter__buyer_power":        0.40,
            "porter__substitute_threat":  0.30,
            "porter__rivalry_intensity":  0.50,
            "porter__capacity_investment": 0.0,
        }
        for k, v in defaults.items():
            if k not in env:
                inits[k] = v
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        p = self.params

        barriers   = env.get("porter__barriers_to_entry", 0.50)
        supplier   = env.get("porter__supplier_power",    0.40)
        buyer      = env.get("porter__buyer_power",       0.40)
        substitute = env.get("porter__substitute_threat", 0.30)
        rivalry    = env.get("porter__rivalry_intensity", 0.50)

        # barriers: raised by capacity investment, eroded by competitive pressure
        capacity_investment = env.get("porter__capacity_investment", 0.0)
        new_barriers = max(0.0, min(1.0,
            barriers + capacity_investment * 0.10 - p.entry_erosion_rate
        ))

        # rivalry: dampened by above-baseline GDP growth, amplified by trade contraction
        gdp = env.get("keynesian__gdp_normalized", 0.5)
        gdp_growth_signal = gdp - 0.5  # positive = growing above baseline
        rivalry_delta = -p.rivalry_growth_sensitivity * gdp_growth_signal
        trade = env.get("global__trade_volume", 0.5)
        if trade < 0.4:
            rivalry_delta += (0.4 - trade) * 0.20
        new_rivalry = max(0.0, min(1.0, rivalry + rivalry_delta * 0.1))

        # supplier, buyer, substitute: slow mean-reversion toward structural defaults
        mr = 0.01
        new_supplier   = max(0.0, min(1.0, supplier   + mr * (0.40 - supplier)))
        new_buyer      = max(0.0, min(1.0, buyer      + mr * (0.40 - buyer)))
        new_substitute = max(0.0, min(1.0, substitute + mr * (0.30 - substitute)))

        # Profitability
        profitability = max(0.0, min(1.0,
            p.base_margin
            + p.w_barriers   * new_barriers
            - p.w_supplier   * new_supplier
            - p.w_buyer      * new_buyer
            - p.w_substitute * new_substitute
            - p.w_rivalry    * new_rivalry
        ))

        logger.debug(
            "Porter tick=%d: barriers=%.3f rivalry=%.3f profit=%.3f",
            tick, new_barriers, new_rivalry, profitability,
        )

        return {
            "porter__barriers_to_entry": new_barriers,
            "porter__supplier_power":    new_supplier,
            "porter__buyer_power":       new_buyer,
            "porter__substitute_threat": new_substitute,
            "porter__rivalry_intensity": new_rivalry,
            "porter__profitability":     profitability,
        }
