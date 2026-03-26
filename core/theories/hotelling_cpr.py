"""
Hotelling Rule + Common Pool Resource Model

Two complementary theories of resource scarcity, combined into one module:

─── Hotelling (1931) ────────────────────────────────────────────────────────
In competitive equilibrium, the scarcity rent (royalty) on a non-renewable
resource must rise at the rate of interest:

    dP/dt = r · P

Otherwise owners would shift between holding the resource and financial assets.
This produces a rising price path as the resource depletes.

Implementation: scarcity_rent grows at discount_rate per tick, bounded above
by the stock-based depletion signal max(0, 1 - S)^1.5, and capped at 1.0.

─── Ostrom Common Pool Resource (1990) ──────────────────────────────────────
Without governance, rational actors overextract shared resources (tragedy of
the commons). Governance institutions (rules, monitoring, enforcement) can
cap extraction at the sustainable yield.

    effective_extraction = extraction_rate · (1 - governance)
                         + min(extraction_rate, sustainable_yield) · governance

    overharvesting = 1  if effective_extraction > sustainable_yield
                   = 0  otherwise

Stock dynamics:
    S[t+1] = clamp(S[t] - effective_extraction · dt, 0, 1)

Depletion risk:
    Rises linearly from 0 at S = critical_threshold to 1.0 at S = 0.

Cross-theory:
    {resource_id}__extraction_rate        — set by agents per tick
    {resource_id}__governance_effectiveness — set by agents / shocks (default 0.5)

Env keys written:
    {resource_id}__stock                  remaining resource fraction ∈ [0, 1]
    {resource_id}__scarcity_rent          Hotelling price premium ∈ [0, 1]
    {resource_id}__depletion_risk         proximity to critical threshold ∈ [0, 1]
    {resource_id}__overharvesting         1.0 if extracting beyond sustainable yield

Env keys initialized but not written (set by agents / shocks):
    {resource_id}__extraction_rate
    {resource_id}__governance_effectiveness

Use resource_id for multiple simultaneous resources (e.g. "oil", "water", "lithium").

References:
    Hotelling (1931). The economics of exhaustible resources.
    Journal of Political Economy 39(2): 137–175.
    Ostrom (1990). Governing the Commons. Cambridge University Press.
    Dasgupta & Heal (1979). Economic Theory and Exhaustible Resources. Cambridge.
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


@register_theory("hotelling_cpr")
class HotellingCPR(TheoryBase):
    """
    Hotelling (1931) scarcity rent + Ostrom (1990) common pool resource governance.

    Domains: energy, resources, environment, sustainability, water
    Priority: 0 (independent; extraction_rate and governance are external inputs)

    Use resource_id for multiple simultaneous resources in one sim.
    """

    DOMAINS = ["energy", "resources", "environment", "sustainability", "water"]

    class Parameters(BaseModel):
        discount_rate: float = Field(
            default=0.05, ge=0.0, le=0.5,
            description="Rate at which scarcity rent appreciates per tick-unit (Hotelling r)",
        )
        sustainable_yield: float = Field(
            default=0.05, ge=0.0, le=1.0,
            description="Maximum sustainable extraction rate per tick-unit (CPR constraint)",
        )
        critical_threshold: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Stock level below which depletion_risk starts rising sharply",
        )
        initial_extraction_rate: float = Field(
            default=0.05, ge=0.0, le=1.0,
            description="Default extraction rate if agents do not set it",
        )
        tick_unit: str = Field(default="year")
        resource_id: str = Field(
            default="resource",
            description="Env key prefix; e.g. 'oil' → oil__stock",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        r = self.params.resource_id
        return TheoryStateVariables(
            reads=[
                f"{r}__stock",
                f"{r}__scarcity_rent",
                f"{r}__extraction_rate",
                f"{r}__governance_effectiveness",
            ],
            writes=[
                f"{r}__stock",
                f"{r}__scarcity_rent",
                f"{r}__depletion_risk",
                f"{r}__overharvesting",
            ],
            initializes=[
                f"{r}__stock",
                f"{r}__scarcity_rent",
                f"{r}__depletion_risk",
                f"{r}__overharvesting",
                f"{r}__extraction_rate",          # seeded at default; agents override
                f"{r}__governance_effectiveness",  # seeded at 0.5; agents override
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """Seed stock at full (1.0), extraction at default, governance at moderate (0.5)."""
        inits = super().setup(env)
        r = self.params.resource_id
        p = self.params
        if f"{r}__stock" not in env:
            inits[f"{r}__stock"] = 1.0
        if f"{r}__extraction_rate" not in env:
            inits[f"{r}__extraction_rate"] = p.initial_extraction_rate
        if f"{r}__governance_effectiveness" not in env:
            inits[f"{r}__governance_effectiveness"] = 0.5
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Hotelling + CPR step.

        1. Read stock S, extraction_rate, governance.
        2. Compute effective extraction (CPR governance caps toward sustainable yield).
        3. Deplete stock by effective_extraction × dt.
        4. Advance scarcity_rent at discount_rate (Hotelling price path).
        5. Compute depletion_risk and overharvesting flag.

        Args:
            env:    normalized environment (read-only)
            agents: not used (resource dynamics are market/governance driven)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated stock, scarcity_rent, depletion_risk, overharvesting.
        """
        p = self.params
        r = p.resource_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        S              = env.get(f"{r}__stock",                  1.0)
        prev_rent      = env.get(f"{r}__scarcity_rent",          0.0)
        extraction     = env.get(f"{r}__extraction_rate",        p.initial_extraction_rate)
        governance     = env.get(f"{r}__governance_effectiveness", 0.5)

        # CPR governance: blend between uncapped (extraction) and capped (sustainable yield)
        capped_extraction    = min(extraction, p.sustainable_yield)
        effective_extraction = extraction * (1.0 - governance) + capped_extraction * governance
        effective_extraction = max(0.0, effective_extraction)

        # Overharvesting: is extraction beyond sustainable yield?
        overharvesting = 1.0 if effective_extraction > p.sustainable_yield else 0.0

        # Stock depletion
        new_S = max(0.0, min(1.0, S - effective_extraction * dt))

        # Hotelling scarcity rent:
        # Grows at discount_rate per tick; anchored from below by stock depletion signal.
        # stock_signal: convex — gentle when S is high, steep as S → 0
        stock_signal = max(0.0, 1.0 - new_S) ** 1.5
        hotelling_path = min(1.0, prev_rent * (1.0 + p.discount_rate * dt))
        new_rent = min(1.0, max(stock_signal, hotelling_path))

        # Depletion risk: linear from 0 at critical_threshold to 1 at S=0
        if new_S < p.critical_threshold and p.critical_threshold > 0:
            depletion_risk = 1.0 - new_S / p.critical_threshold
        else:
            depletion_risk = 0.0
        depletion_risk = max(0.0, min(1.0, depletion_risk))

        logger.debug(
            "HotellingCPR tick=%d resource=%s: S=%.3f→%.3f extract=%.4f "
            "governance=%.3f rent=%.3f risk=%.3f overharvest=%s",
            tick, r, S, new_S, effective_extraction,
            governance, new_rent, depletion_risk, bool(overharvesting),
        )

        return {
            f"{r}__stock":          new_S,
            f"{r}__scarcity_rent":  new_rent,
            f"{r}__depletion_risk": depletion_risk,
            f"{r}__overharvesting": overharvesting,
        }
