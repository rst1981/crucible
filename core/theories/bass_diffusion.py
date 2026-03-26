"""
Bass Diffusion Model (1969)

S-curve of technology / product adoption driven by two forces:
  - Innovation (p): adopters independent of existing adopters (advertising, external influence)
  - Imitation (q): adopters influenced by the existing installed base (word-of-mouth)

Differential equation:
    dN/dt = (p + q·N) · (1 - N)

    where N ∈ [0, 1] = cumulative adoption fraction of the total addressable market

Discretized per tick:
    N[t+1] = clamp(N[t] + dt · (p + q·N[t]) · (1 - N[t]), 0, 1)

Peak adoption rate (inflection point) occurs at:
    N* = (q - p) / (2·q)   [when q > p; otherwise monotone growth]

Characteristic shapes:
    p >> q : fast initial adoption, gentle S-curve (e.g. fax machines)
    p << q : slow start, steep middle, fast saturation (e.g. VCRs, smartphones)

Cross-theory modulation:
    keynesian__gdp_normalized:  above-baseline GDP amplifies q (more discretionary income
                                → faster word-of-mouth spread and willingness to adopt)
    global__trade_volume:       below-baseline trade suppresses p (supply disruption
                                reduces product availability / distribution reach)

Env keys written:
    {market_id}__adoption_fraction   cumulative N ∈ [0, 1]
    {market_id}__adoption_rate       instantaneous dN/dt ∈ [0, 1]
    {market_id}__innovator_rate      p_eff · (1 - N) component
    {market_id}__imitator_rate       q_eff · N · (1 - N) component

Empirical defaults (Bass 1969 consumer durables average):
    p = 0.03,  q = 0.38

Reference: Bass (1969). A new product growth model for consumer durables.
           Management Science 15(5): 215–227.
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


@register_theory("bass_diffusion")
class BassDiffusion(TheoryBase):
    """
    Bass (1969) S-curve adoption model.

    Domains: market, technology, adoption, disruption
    Priority: 0 (independent; reads Keynesian GDP and global trade volume if present)

    Multiple instances can coexist using distinct market_id values, e.g.:
        BassDiffusion({"market_id": "ev"})        → ev__adoption_fraction
        BassDiffusion({"market_id": "heatpump"})  → heatpump__adoption_fraction
    """

    DOMAINS = ["market", "technology", "adoption", "disruption"]

    class Parameters(BaseModel):
        p: float = Field(
            default=0.03, ge=0.0, le=1.0,
            description="Coefficient of innovation (external influence / advertising)",
        )
        q: float = Field(
            default=0.38, ge=0.0, le=1.0,
            description="Coefficient of imitation (word-of-mouth / social influence)",
        )
        gdp_sensitivity: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="How much above-baseline GDP amplifies q (0 = no effect)",
        )
        supply_sensitivity: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="How much below-baseline trade suppresses p (0 = no effect)",
        )
        tick_unit: str = Field(
            default="year",
            description="Time step unit: 'month', 'quarter', or 'year'",
        )
        market_id: str = Field(
            default="bass",
            description="Env key prefix; e.g. 'ev' → ev__adoption_fraction",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        m = self.params.market_id
        return TheoryStateVariables(
            reads=[
                f"{m}__adoption_fraction",
                "keynesian__gdp_normalized",
                "global__trade_volume",
            ],
            writes=[
                f"{m}__adoption_fraction",
                f"{m}__adoption_rate",
                f"{m}__innovator_rate",
                f"{m}__imitator_rate",
            ],
            initializes=[
                f"{m}__adoption_fraction",
                f"{m}__adoption_rate",
                f"{m}__innovator_rate",
                f"{m}__imitator_rate",
            ],
        )

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Bass ODE step.

        Reads N from env, applies GDP and trade modulation to p and q,
        computes dN/dt and advances one dt.

        Args:
            env:    normalized environment (read-only)
            agents: not used by Bass (pure state-based, no agent intent)
            tick:   zero-based tick counter (unused; Bass is memoryless)

        Returns:
            delta dict with updated values for all four write keys.
        """
        p = self.params
        m = p.market_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        N = env.get(f"{m}__adoption_fraction", 0.0)

        # GDP modulates imitation: higher income → faster social spread
        gdp = env.get("keynesian__gdp_normalized", 0.5)
        gdp_effect = 1.0 + p.gdp_sensitivity * (gdp - 0.5)
        q_eff = max(0.0, p.q * gdp_effect)

        # Trade disruption suppresses innovation: less product available to discover
        trade = env.get("global__trade_volume", 0.5)
        supply_factor = max(0.0, 1.0 - p.supply_sensitivity * max(0.0, 0.5 - trade))
        p_eff = p.p * supply_factor

        remaining = 1.0 - N
        innovator_rate = p_eff * remaining
        imitator_rate = q_eff * N * remaining
        adoption_rate = innovator_rate + imitator_rate

        new_N = max(0.0, min(1.0, N + dt * adoption_rate))

        logger.debug(
            "Bass tick=%d market=%s: N=%.3f→%.3f rate=%.4f "
            "(innov=%.4f imit=%.4f) q_eff=%.3f p_eff=%.4f",
            tick, m, N, new_N, adoption_rate, innovator_rate, imitator_rate,
            q_eff, p_eff,
        )

        return {
            f"{m}__adoption_fraction": new_N,
            f"{m}__adoption_rate":     max(0.0, min(1.0, adoption_rate)),
            f"{m}__innovator_rate":    max(0.0, min(1.0, innovator_rate)),
            f"{m}__imitator_rate":     max(0.0, min(1.0, imitator_rate)),
        }
