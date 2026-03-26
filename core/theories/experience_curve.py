"""
Experience Curve / Wright's Law (1936)

Unit costs decline by a constant percentage for every doubling of cumulative
production. The learning exponent b is derived from the learning rate:

    C(Q) = C₀ · (Q / Q₀)^(-b)
    b = -log(learning_rate) / log(2)

Per-tick update (Wright's Law in ratio form):
    C[t+1] = C[t] · (Q[t+1] / Q[t])^(-b)

where Q[t+1] = Q[t] + production_rate · dt (cumulative production grows each tick)

Characteristic values:
    learning_rate = 0.80 → 20% cost reduction per doubling (semiconductors, solar PV)
    learning_rate = 0.85 → 15% cost reduction per doubling (aircraft, chemicals)
    learning_rate = 0.90 → 10% cost reduction per doubling (mature industries)

Cross-theory:
    {curve_id}__production_rate  — set by agents; determines speed of learning
                                   (initialized to default; agents override per tick)

Env keys written:
    {curve_id}__unit_cost              current normalized unit cost ∈ [0, 1]
    {curve_id}__cumulative_production  cumulative output to date ∈ [0, 1]
    {curve_id}__cost_reduction_pct     (initial_cost - unit_cost) / initial_cost ∈ [0, 1]

Env keys initialized but not written (set by agents / shocks):
    {curve_id}__production_rate        current period output rate ∈ [0, 1]

Use curve_id for multiple simultaneous cost curves (e.g. "ev_battery", "solar_panel").

References:
    Wright (1936). Factors affecting the cost of airplanes.
    Journal of the Aeronautical Sciences 3(4): 122–128.
    Yelle (1979). The learning curve: Historical review and comprehensive survey.
    Decision Sciences 10(2): 302–328.
    Way et al. (2022). Empirically grounded technology forecasts and the energy transition.
    Joule 6(9): 2057–2082.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)

_DT_MAP: dict[str, float] = {"month": 1.0 / 12.0, "quarter": 0.25, "year": 1.0}

# Minimum cumulative production seed — avoids log(0) at initialization
_Q_SEED = 0.01


@register_theory("experience_curve")
class ExperienceCurve(TheoryBase):
    """
    Wright (1936) experience / learning curve.

    Domains: operations, manufacturing, technology, cost_modeling, energy_transition
    Priority: 0 (independent; production_rate is an external env input)

    Use curve_id for multiple distinct cost curves in the same sim.
    """

    DOMAINS = ["operations", "manufacturing", "technology", "cost_modeling", "energy_transition"]

    class Parameters(BaseModel):
        learning_rate: float = Field(
            default=0.80, ge=0.50, le=1.0,
            description="Fraction of cost retained per doubling of cumulative production "
                        "(0.80 = 80% curve = 20% cost reduction per doubling)",
        )
        initial_cost: float = Field(
            default=1.0, ge=0.01, le=1.0,
            description="Normalized unit cost at simulation start (1.0 = full initial cost)",
        )
        min_cost: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="Physical / material cost floor below which learning cannot reduce cost",
        )
        default_production_rate: float = Field(
            default=0.05, ge=0.0, le=1.0,
            description="Default production rate per tick-unit if agents do not set it "
                        "(fraction of normalized market capacity)",
        )
        tick_unit: str = Field(default="year")
        curve_id: str = Field(
            default="experience",
            description="Env key prefix; e.g. 'ev_battery' → ev_battery__unit_cost",
        )

        @model_validator(mode="after")
        def min_cost_below_initial(self) -> "ExperienceCurve.Parameters":
            if self.min_cost >= self.initial_cost:
                raise ValueError(
                    f"min_cost ({self.min_cost}) must be less than initial_cost ({self.initial_cost})"
                )
            return self

    @property
    def state_variables(self) -> TheoryStateVariables:
        c = self.params.curve_id
        return TheoryStateVariables(
            reads=[
                f"{c}__cumulative_production",
                f"{c}__unit_cost",
                f"{c}__production_rate",
            ],
            writes=[
                f"{c}__unit_cost",
                f"{c}__cumulative_production",
                f"{c}__cost_reduction_pct",
            ],
            initializes=[
                f"{c}__unit_cost",
                f"{c}__cumulative_production",
                f"{c}__cost_reduction_pct",
                f"{c}__production_rate",   # seeded at default; agents override
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed unit_cost at initial_cost, cumulative_production at seed value,
        and production_rate at default.
        """
        inits = super().setup(env)
        c = self.params.curve_id
        p = self.params
        if f"{c}__unit_cost" not in env:
            inits[f"{c}__unit_cost"] = p.initial_cost
        if f"{c}__cumulative_production" not in env:
            inits[f"{c}__cumulative_production"] = _Q_SEED
        if f"{c}__production_rate" not in env:
            inits[f"{c}__production_rate"] = p.default_production_rate
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Wright's Law step.

        1. Read current cumulative production Q and production_rate.
        2. Advance Q by production_rate × dt.
        3. Apply Wright's Law: C_new = C_old × (Q_new / Q_old)^(-b).
        4. Clamp cost to [min_cost, initial_cost].
        5. Compute cost_reduction_pct.

        Args:
            env:    normalized environment (read-only)
            agents: not used (cost dynamics are determined by production volume)
            tick:   zero-based tick counter (unused; Wright's Law is cumulative-volume based)

        Returns:
            delta dict with updated unit_cost, cumulative_production, cost_reduction_pct.
        """
        p = self.params
        c = p.curve_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        Q    = env.get(f"{c}__cumulative_production", _Q_SEED)
        cost = env.get(f"{c}__unit_cost",             p.initial_cost)
        prod_rate = env.get(f"{c}__production_rate",  p.default_production_rate)

        # Learning exponent: b = -log(lr) / log(2)
        # For lr=0.80: b ≈ 0.322 (each doubling reduces cost by 20%)
        b = -math.log(p.learning_rate) / math.log(2.0)

        # Advance cumulative production
        dQ    = max(0.0, prod_rate * dt)
        new_Q = min(1.0, Q + dQ)

        # Wright's Law: cost decreases proportionally to production growth
        if Q > 1e-9 and new_Q > Q:
            cost_multiplier = (new_Q / Q) ** (-b)
            new_cost = max(p.min_cost, min(p.initial_cost, cost * cost_multiplier))
        else:
            new_cost = cost  # no production → no learning

        cost_reduction_pct = max(0.0, min(1.0,
            (p.initial_cost - new_cost) / p.initial_cost
        ))

        logger.debug(
            "ExperienceCurve tick=%d curve=%s: Q=%.4f→%.4f cost=%.4f→%.4f "
            "reduction=%.1f%% b=%.3f",
            tick, c, Q, new_Q, cost, new_cost, cost_reduction_pct * 100, b,
        )

        return {
            f"{c}__unit_cost":             new_cost,
            f"{c}__cumulative_production": new_Q,
            f"{c}__cost_reduction_pct":    cost_reduction_pct,
        }
