"""
core/theories/discovered/compute_efficiency.py — AI Compute Efficiency Dynamics

Based on: Lu, C.P. (2025). The Race to Efficiency: A New Perspective on AI Scaling Laws.
          arXiv:2501.02156.
Also: Erdil, E. & Besiroglu, T. (2023). Increased Compute Efficiency and the Diffusion
      of AI Capabilities. arXiv:2311.15377.
      Hobbhahn et al. (2022). Trends in ML Hardware. Epoch AI.
      "Densing Law of LLMs" — Nature Machine Intelligence, 2025. (capability density
      doubles ~every 3.5 months)

Model:
    Algorithmic efficiency improvements reduce the compute cost required to achieve
    a fixed AI performance level. This creates a time-dependent "efficiency gain"
    that erodes the cost advantage of capital-intensive incumbents (e.g. NVIDIA GPU
    buyers) and lowers barriers to entry for cost-efficient newcomers (e.g. DeepSeek).

    Core equation (Lu 2025 relative-loss):
        efficiency_gain_t = 2^(tick / T_eff) - 1
        cost_t = base_cost / (1 + efficiency_gain_t)
        incumbent_moat = max(0, (actor_cost - cost_t) / actor_cost)

    Where:
        T_eff = efficiency_doubling_period (ticks; default 12 for monthly ticks)
        base_cost = normalized cost at tick 0 (1.0)
        actor_cost = normalized cost of incumbent's hardware investment (typically 1.0)

    Derived outputs:
        compute_efficiency__efficiency_gain   ∈ [0, 1]  normalised efficiency advantage
        compute_efficiency__incumbent_moat    ∈ [0, 1]  cost moat of GPU incumbent
        compute_efficiency__entry_barrier     ∈ [0, 1]  barrier to entry for new models
                                                         (inversely related to efficiency_gain)

Calibration:
    - Algorithmic efficiency doubles ~every 9–16 months (Epoch AI, 2022).
    - Densing Law: capability density doubles every 3.5 months (Nature MI, 2025).
    - DeepSeek R1 (Jan 2025): achieved GPT-4 parity at ~1/30th training cost → represents
      ~5x efficiency gain vs expectation, compressing ~50 months of linear progress into 1 event.

Env keys written:
    compute_efficiency__efficiency_gain  ∈ [0, 1]
    compute_efficiency__incumbent_moat   ∈ [0, 1]
    compute_efficiency__entry_barrier    ∈ [0, 1]

Reads from env:
    compute_efficiency__efficiency_shock  (discrete shock to efficiency, e.g. 0.0 baseline;
                                           set to 0.5 at tick of DeepSeek announcement)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent


@register_theory("compute_efficiency")
class ComputeEfficiency(TheoryBase):
    """Lu (2025) AI compute efficiency erosion model."""

    DOMAINS = [
        "technology",
        "innovation",
        "competitive_dynamics",
        "market",
        "corporate_strategy",
    ]

    class Parameters(BaseModel):
        efficiency_doubling_period: float = Field(
            default=12.0,
            ge=1.0,
            le=120.0,
            description="Ticks for compute efficiency to double (T_eff). "
                        "Epoch AI estimate: 9–16 months for monthly ticks. Default 12.",
        )
        initial_incumbent_moat: float = Field(
            default=0.80,
            ge=0.0,
            le=1.0,
            description="Normalized cost advantage of incumbent at tick 0. "
                        "NVIDIA CUDA ecosystem advantage pre-DeepSeek ~0.80.",
        )
        moat_erosion_sensitivity: float = Field(
            default=1.0,
            ge=0.1,
            le=5.0,
            description="Multiplier on efficiency gain for moat erosion. "
                        ">1.0 = moat erodes faster than raw efficiency gains (regime shift).",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=["compute_efficiency__efficiency_shock"],
            writes=[
                "compute_efficiency__efficiency_gain",
                "compute_efficiency__incumbent_moat",
                "compute_efficiency__entry_barrier",
            ],
            initializes=[
                "compute_efficiency__efficiency_gain",
                "compute_efficiency__incumbent_moat",
                "compute_efficiency__entry_barrier",
            ],
        )

    def update(self, env: dict, agents: list, tick: int) -> dict[str, float]:
        p = self.params

        # Continuous efficiency gain from algorithmic improvement (Lu 2025)
        continuous_gain = 2.0 ** (tick / p.efficiency_doubling_period) - 1.0

        # Discrete shock (e.g. DeepSeek announcement — set env key to 0.5 at event tick)
        shock = env.get("compute_efficiency__efficiency_shock", 0.0)

        total_gain = continuous_gain + shock

        # Normalise to [0, 1]: full gain at ~3x doubling periods
        efficiency_gain = min(1.0, total_gain / (2.0 ** 3 - 1.0))

        # Incumbent moat erodes as efficiency enables new entrants at lower cost
        moat_erosion = min(1.0, efficiency_gain * p.moat_erosion_sensitivity)
        incumbent_moat = max(0.0, p.initial_incumbent_moat * (1.0 - moat_erosion))

        # Entry barrier falls as efficiency gain rises (inverse relationship)
        entry_barrier = max(0.0, 1.0 - efficiency_gain)

        return {
            "compute_efficiency__efficiency_gain": efficiency_gain,
            "compute_efficiency__incumbent_moat": incumbent_moat,
            "compute_efficiency__entry_barrier": entry_barrier,
        }
