"""
Solow–Swan Neoclassical Growth Model (1956)

The Solow model explains long-run economic growth through capital accumulation,
labor force growth, and exogenous technological progress. The central insight is
conditional convergence: economies with capital below their steady-state level
grow faster than those at or above it.

Steady-state capital per effective worker (k*) satisfies:
    s · f(k*) = (δ + n + g) · k*

For a Cobb-Douglas production function f(k) = k^α:
    k* = [ s / (δ + n + g) ]^(1 / (1-α))

Normalized dynamics. Let κ = k / k* be capital relative to steady state (κ=1
at SS). Per tick-unit:

    dκ/dt = (δ + n + g) · (A · κ^α − κ) · adjustment_speed

where A = 1 + tfp_shock is a TFP multiplier (agents inject tfp_shock ∈ [0,1]).

At the steady state dκ/dt = 0 (when A=1 and κ=1). Below SS (κ < 1) capital
grows; above SS (κ > 1) it contracts. TFP boosts effectively raise the SS.

Output per effective worker (normalized):
    y = min(1, κ^α)

Convergence gap (distance from steady state):
    convergence_gap = |1 − κ|   (clamped to [0, 1])

Cross-theory:
    {economy_id}__tfp_shock — additive TFP shock; set by agents/policy; default 0.0

Env keys written:
    {economy_id}__capital_intensity  κ clamped to [0,1] (1.0 = at or above SS)
    {economy_id}__output_per_worker  y = κ^α ∈ [0,1]
    {economy_id}__convergence_gap    |1 − κ| clamped ∈ [0,1]

References:
    Solow, R. M. (1956). A contribution to the theory of economic growth.
    Quarterly Journal of Economics 70(1): 65–94.

    Swan, T. W. (1956). Economic growth and capital accumulation.
    Economic Record 32(2): 334–361.

    Mankiw, N. G., Romer, D., & Weil, D. N. (1992). A contribution to the
    empirics of economic growth. Quarterly Journal of Economics 107(2): 407–437.
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


@register_theory("solow_growth")
class SolowGrowth(TheoryBase):
    """
    Solow–Swan (1956) neoclassical growth model — normalized κ dynamics.

    Domains: macro, development, growth, long_run, policy
    Priority: 0 (tfp_shock is an external env input set by agents)

    Use economy_id for multiple simultaneous economies in the same sim.
    """

    DOMAINS = ["macro", "development", "growth", "long_run", "policy"]

    class Parameters(BaseModel):
        savings_rate: float = Field(
            default=0.20, ge=0.01, le=0.60,
            description="Fraction of output saved and invested per period",
        )
        depreciation_rate: float = Field(
            default=0.05, ge=0.01, le=0.20,
            description="Fraction of capital stock that depreciates per year",
        )
        labor_growth_rate: float = Field(
            default=0.01, ge=0.0, le=0.10,
            description="Annual growth rate of the labor force (n)",
        )
        tfp_growth_rate: float = Field(
            default=0.02, ge=0.0, le=0.10,
            description="Annual total factor productivity growth rate (g)",
        )
        capital_share: float = Field(
            default=0.33, ge=0.10, le=0.60,
            description="Capital's share of output in Cobb-Douglas production (α)",
        )
        adjustment_speed: float = Field(
            default=1.0, ge=0.1, le=5.0,
            description="Scales the convergence speed (1.0 = textbook rate)",
        )
        tick_unit: str = Field(default="year")
        economy_id: str = Field(
            default="solow",
            description="Env key prefix; e.g. 'usa' → usa__capital_intensity",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        e = self.params.economy_id
        return TheoryStateVariables(
            reads=[
                f"{e}__capital_intensity",
                f"{e}__output_per_worker",
                f"{e}__convergence_gap",
                f"{e}__tfp_shock",
            ],
            writes=[
                f"{e}__capital_intensity",
                f"{e}__output_per_worker",
                f"{e}__convergence_gap",
            ],
            initializes=[
                f"{e}__capital_intensity",
                f"{e}__output_per_worker",
                f"{e}__convergence_gap",
                f"{e}__tfp_shock",   # owned by agents/policy shocks
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed capital below steady state (0.50) so convergence dynamics are visible
        immediately.  Output per worker is the consistent κ^α value.
        """
        inits = super().setup(env)
        e = self.params.economy_id
        p = self.params
        if f"{e}__capital_intensity" not in env:
            inits[f"{e}__capital_intensity"] = 0.50
        if f"{e}__output_per_worker" not in env:
            inits[f"{e}__output_per_worker"] = 0.50 ** p.capital_share
        if f"{e}__tfp_shock" not in env:
            inits[f"{e}__tfp_shock"] = 0.0
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Advance the Solow model by one tick.

        Reads current κ (capital_intensity) and tfp_shock, computes the
        Solow differential equation, steps κ forward, then derives output
        per worker and convergence gap.

        κ is NOT clamped at 1.0 internally — the model allows overshooting
        the steady state (which then self-corrects). Only the value written to
        env (capital_intensity) is clamped to [0, 1].

        Args:
            env:    normalized environment (read-only)
            agents: not used directly (tfp_shock comes from env)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated capital_intensity, output_per_worker,
            convergence_gap.
        """
        p = self.params
        e = p.economy_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        kappa = env.get(f"{e}__capital_intensity", 0.50)
        tfp_shock = env.get(f"{e}__tfp_shock", 0.0)

        eff_rate = p.depreciation_rate + p.labor_growth_rate + p.tfp_growth_rate
        A_factor = 1.0 + tfp_shock

        # Solow equation in normalized form
        dk = eff_rate * (A_factor * (kappa ** p.capital_share) - kappa) * p.adjustment_speed * dt
        new_kappa = max(0.0, kappa + dk)  # allow overshoot above 1.0

        # Output per worker (normalized; clamped at 1.0)
        output_per_worker = min(1.0, new_kappa ** p.capital_share)
        output_per_worker = max(0.0, output_per_worker)

        # Convergence gap = distance from steady state
        convergence_gap = max(0.0, min(1.0, abs(1.0 - new_kappa)))

        # Capital intensity reported to env (clamped for output only)
        capital_intensity = max(0.0, min(1.0, new_kappa))

        logger.debug(
            "SolowGrowth tick=%d economy=%s: kappa=%.4f→%.4f y=%.4f gap=%.4f "
            "(A=%.3f eff_rate=%.4f dt=%.4f)",
            tick, e, kappa, new_kappa, output_per_worker, convergence_gap,
            A_factor, eff_rate, dt,
        )

        return {
            f"{e}__capital_intensity": capital_intensity,
            f"{e}__output_per_worker": output_per_worker,
            f"{e}__convergence_gap":   convergence_gap,
        }
