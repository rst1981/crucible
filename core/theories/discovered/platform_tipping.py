"""
core/theories/discovered/platform_tipping.py — Platform Tipping Dynamics

Based on: Rochet, J.C. & Tirole, J. (2003). Platform Competition in Two-Sided Markets.
Journal of the European Economic Association, 1(4), 990–1029.
Also: Parker, G. & Van Alstyne, M. (2005). Two-Sided Network Effects: A Theory of
Information Product Design. Management Science, 51(10), 1494–1504.

Model:
    Two-sided platforms exhibit tipping when cross-side network effects (alpha) exceed
    a critical threshold relative to switching costs (sigma). Once an incumbent platform
    crosses the tipping threshold, its share grows autocatalytically; below threshold it
    erodes. Relevant for NVIDIA's CUDA ecosystem vs open-weight AI alternatives.

    Share dynamics (discrete-time approximation):
        net_force = alpha * share * (1 - share) - sigma * (share - 0.5)
        share_t+1 = clamp(share_t + lr * net_force, 0, 1)

    Tipping condition: alpha > 2 * sigma
        - alpha >> sigma → market tips to winner-take-all
        - alpha ≈ sigma  → contested multi-homing equilibrium
        - alpha << sigma → incumbent erodes under switching pressure

Env keys written:
    platform_tipping__incumbent_share   ∈ [0, 1]  incumbent platform market share
    platform_tipping__tipping_pressure  ∈ [0, 1]  net force toward winner-take-all
    platform_tipping__moat_intact       ∈ [0, 1]  1.0 = above tipping threshold, 0.0 = below

Reads from env:
    platform_tipping__incumbent_share   (prior tick)
    platform_tipping__disruptive_shock  (external shock reducing incumbent share, e.g. 0.0 baseline)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent


@register_theory("platform_tipping")
class PlatformTipping(TheoryBase):
    """Rochet-Tirole two-sided platform tipping model."""

    DOMAINS = [
        "technology",
        "competitive_dynamics",
        "market",
        "innovation",
        "corporate_strategy",
    ]

    class Parameters(BaseModel):
        cross_side_network_effect: float = Field(
            default=0.30,
            ge=0.0,
            le=2.0,
            description="Alpha: strength of cross-side network externality. "
                        "High (>0.4) → strong tipping tendency.",
        )
        switching_cost: float = Field(
            default=0.15,
            ge=0.0,
            le=1.0,
            description="Sigma: per-period cost for users to switch platforms. "
                        "Tipping occurs when alpha > 2*sigma.",
        )
        initial_incumbent_share: float = Field(
            default=0.80,
            ge=0.0,
            le=1.0,
            description="Incumbent platform market share at tick 0. "
                        "NVIDIA GPU ecosystem ~0.80 in AI training (2024).",
        )
        learning_rate: float = Field(
            default=0.05,
            ge=0.001,
            le=0.5,
            description="Speed of share adjustment per tick.",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=["platform_tipping__incumbent_share", "platform_tipping__disruptive_shock"],
            writes=[
                "platform_tipping__incumbent_share",
                "platform_tipping__tipping_pressure",
                "platform_tipping__moat_intact",
            ],
            initializes=[
                "platform_tipping__incumbent_share",
                "platform_tipping__tipping_pressure",
                "platform_tipping__moat_intact",
            ],
        )

    def update(self, env: dict, agents: list, tick: int) -> dict[str, float]:
        p = self.params
        share = env.get("platform_tipping__incumbent_share", p.initial_incumbent_share)
        shock = env.get("platform_tipping__disruptive_shock", 0.0)

        # Apply any external disruption shock (e.g. open-weight model release)
        share = max(0.0, share - shock)

        # Rochet-Tirole net force
        net_force = (
            p.cross_side_network_effect * share * (1.0 - share)
            - p.switching_cost * (share - 0.5)
        )
        new_share = max(0.0, min(1.0, share + p.learning_rate * net_force))

        # Tipping pressure: normalise net_force to [0,1]
        tipping_pressure = max(0.0, min(1.0, 0.5 + net_force))

        # Moat intact: 1.0 if above tipping threshold (alpha > 2*sigma and share > 0.5)
        tipping_condition_met = p.cross_side_network_effect > 2.0 * p.switching_cost
        moat_intact = 1.0 if (tipping_condition_met and new_share > 0.5) else max(0.0, new_share)

        return {
            "platform_tipping__incumbent_share": new_share,
            "platform_tipping__tipping_pressure": tipping_pressure,
            "platform_tipping__moat_intact": moat_intact,
        }
