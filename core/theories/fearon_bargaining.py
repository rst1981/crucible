"""
Fearon Bargaining Model of War (1995)

War occurs when:
  (a) private information gap > joint war costs:
        |p - p̂_B| > c_A + c_B
  (b) power shift rate exceeds commitment threshold:
        |p[t] - p[t-1]| / dt > commit_threshold

Conflict probability is a smooth [0,1] output derived from both mechanisms.

Env keys written:
    fearon__win_prob_a              A's true win probability (from military balance)
    fearon__win_prob_b_estimate     B's lagged belief about A's capability
    fearon__war_cost_a              A's cost of war as fraction of prize
    fearon__war_cost_b              B's cost of war
    fearon__conflict_probability    per-tick P(war onset)
    fearon__settlement_range_width  c_A + c_B (negotiating zone width)

Cross-theory: fearon__win_prob_a is the primary bridge variable read by
wittman_zartman and (informally) by Richardson via military_readiness.

Reference: Fearon (1995), International Organization 49(3): 379-414
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


@register_theory("fearon_bargaining")
class FearonBargaining(TheoryBase):
    """
    Rationalist bargaining theory of war onset.

    Domains: conflict, geopolitics, crisis management
    Priority: 1 (reads military readiness set by Richardson at priority 0)
    Note: conflicts with wittman_zartman — use one or the other per simulation.
    """

    DOMAINS = ["conflict", "geopolitics", "crisis_management"]

    class Parameters(BaseModel):
        c_A: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="A's war cost as fraction of contested prize",
        )
        c_B: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="B's war cost as fraction of contested prize",
        )
        private_info_sigma: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Std dev of B's estimation error re: A's win probability",
        )
        commitment_threshold: float = Field(
            default=0.05, ge=0.0, le=1.0,
            description="Power shift rate above which commitment problem activates",
        )
        tick_unit: str = Field(default="year")
        actor_a_id: str = Field(default="actor_a")
        actor_b_id: str = Field(default="actor_b")

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "fearon__win_prob_a",
                "fearon__win_prob_b_estimate",
                "fearon__war_cost_a",
                "fearon__war_cost_b",
                f"{self.params.actor_a_id}__military_readiness",
                f"{self.params.actor_b_id}__military_readiness",
            ],
            writes=[
                "fearon__win_prob_a",
                "fearon__win_prob_b_estimate",
                "fearon__war_cost_a",
                "fearon__war_cost_b",
                "fearon__conflict_probability",
                "fearon__settlement_range_width",
            ],
            initializes=[
                "fearon__win_prob_a",
                "fearon__win_prob_b_estimate",
                "fearon__war_cost_a",
                "fearon__war_cost_b",
                "fearon__conflict_probability",
                "fearon__settlement_range_width",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        p = self.params
        if "fearon__win_prob_a" not in env:
            inits["fearon__win_prob_a"] = 0.5
        if "fearon__win_prob_b_estimate" not in env:
            inits["fearon__win_prob_b_estimate"] = 0.5
        if "fearon__war_cost_a" not in env:
            inits["fearon__war_cost_a"] = p.c_A
        if "fearon__war_cost_b" not in env:
            inits["fearon__war_cost_b"] = p.c_B
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        p = self.params
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        # Win probability: Lanchester capability ratio from military readiness
        mil_a = env.get(f"{p.actor_a_id}__military_readiness", 0.5)
        mil_b = env.get(f"{p.actor_b_id}__military_readiness", 0.5)
        denom = mil_a + mil_b
        win_prob_a = (mil_a / denom) if denom > 1e-6 else 0.5

        # B's estimate converges toward true value at 10% per tick (slow belief update)
        prev_estimate = env.get("fearon__win_prob_b_estimate", 0.5)
        win_prob_b_estimate = prev_estimate + 0.10 * (win_prob_a - prev_estimate)

        # War costs: read from env (agents/shocks may update), fall back to params
        war_cost_a = env.get("fearon__war_cost_a", p.c_A)
        war_cost_b = env.get("fearon__war_cost_b", p.c_B)
        settlement_range_width = war_cost_a + war_cost_b

        # Private information mechanism: war if |p - p̂_B| > c_A + c_B
        info_gap = abs(win_prob_a - win_prob_b_estimate)
        excess_info_gap = max(0.0, info_gap - settlement_range_width)
        remaining_range = max(1e-6, 1.0 - settlement_range_width)
        info_conflict_term = excess_info_gap / remaining_range

        # Commitment problem: war if power shift rate > threshold
        prev_win_prob = env.get("fearon__win_prob_a", 0.5)
        power_shift_rate = abs(win_prob_a - prev_win_prob) / max(dt, 1e-6)
        excess_shift = max(0.0, power_shift_rate - p.commitment_threshold)
        remaining_shift = max(1e-6, 1.0 - p.commitment_threshold)
        commit_conflict_term = min(1.0, excess_shift / remaining_shift)

        conflict_probability = max(0.0, min(1.0,
            max(info_conflict_term, commit_conflict_term)
        ))

        logger.debug(
            "Fearon tick=%d: win_prob_a=%.3f estimate=%.3f info_gap=%.3f "
            "commit_shift=%.4f P(conflict)=%.3f",
            tick, win_prob_a, win_prob_b_estimate, info_gap,
            power_shift_rate, conflict_probability,
        )

        return {
            "fearon__win_prob_a":            win_prob_a,
            "fearon__win_prob_b_estimate":   win_prob_b_estimate,
            "fearon__war_cost_a":            war_cost_a,
            "fearon__war_cost_b":            war_cost_b,
            "fearon__conflict_probability":  conflict_probability,
            "fearon__settlement_range_width": settlement_range_width,
        }
