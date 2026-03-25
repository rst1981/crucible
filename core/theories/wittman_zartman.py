"""
Wittman (1979) / Zartman (1985) Ripeness Theory

War termination expected utility:
  EU_war(A) = p * V - c_A     (V normalized to 1.0)
  EU_war(B) = (1-p) * V - c_B

Mutually Hurting Stalemate (MHS):
  Both EU_war(A) < payoff_floor AND EU_war(B) < payoff_floor
  AND no path to decisive victory.

Ripe moment:
  ripe = MHS AND stalemate_duration >= min_stalemate_ticks
         AND (mediator_present OR urgency_factor > urgency_threshold)

Negotiation probability per tick:
  base_rate * ripe_multiplier * (1 + urgency)  if ripe
  base_rate                                     otherwise

Env keys written:
    zartman__eu_war_a               A's expected utility of continued fighting
    zartman__eu_war_b               B's expected utility
    zartman__mhs                    1.0 = Mutually Hurting Stalemate active
    zartman__ripe_moment            1.0 = all ripeness conditions met
    zartman__negotiation_probability per-tick P(negotiation begins)
    zartman__stalemate_duration     normalized stalemate length (0-48 ticks)

Env keys read (set externally):
    zartman__mediator_present       1.0 = active mediator (set by shock or agent)
    global__urgency_factor          cross-theory urgency signal

Note: _stalemate_ticks is instance state, not in env (known limitation).

References:
  Wittman (1979) Journal of Conflict Resolution 23(4): 743-763
  Zartman (1985) Ripe for Resolution
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

_MAX_STALEMATE_HORIZON = 48  # ticks (e.g. 48 months = 4 years)


@register_theory("wittman_zartman")
class WittmanZartman(TheoryBase):
    """
    War termination and ripeness theory.

    Domains: conflict, geopolitics, mediation
    Priority: 1 (reads Richardson military readiness + Fearon win_prob at priority 0)
    Note: conflicts with fearon_bargaining — use one or the other per simulation.
    """

    DOMAINS = ["conflict", "geopolitics", "mediation"]

    class Parameters(BaseModel):
        base_negotiation_rate: float = Field(
            default=0.02, ge=0.0, le=1.0,
            description="P(negotiate) per tick in non-ripe conditions",
        )
        ripe_multiplier: float = Field(
            default=5.0, ge=1.0, le=20.0,
            description="Multiplier on negotiation probability when ripe",
        )
        min_stalemate_ticks: int = Field(
            default=4, ge=1,
            description="Minimum stalemate duration before ripe condition",
        )
        payoff_floor: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description="EU_war below this threshold triggers MHS for that party",
        )
        transaction_costs: float = Field(
            default=0.05, ge=0.0, le=0.5,
            description="Overhead cost of the negotiation process itself",
        )
        urgency_threshold: float = Field(
            default=0.65, ge=0.0, le=1.0,
            description="Urgency level that substitutes for mediator presence",
        )
        actor_a_id: str = Field(default="actor_a")
        actor_b_id: str = Field(default="actor_b")

    def __init__(self, parameters: dict | None = None) -> None:
        super().__init__(parameters)
        self._stalemate_ticks: int = 0

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "fearon__win_prob_a",
                "fearon__war_cost_a",
                "fearon__war_cost_b",
                "zartman__mediator_present",
                "global__urgency_factor",
            ],
            writes=[
                "zartman__eu_war_a",
                "zartman__eu_war_b",
                "zartman__mhs",
                "zartman__ripe_moment",
                "zartman__negotiation_probability",
                "zartman__stalemate_duration",
            ],
            initializes=[
                "zartman__eu_war_a",
                "zartman__eu_war_b",
                "zartman__mhs",
                "zartman__ripe_moment",
                "zartman__negotiation_probability",
                "zartman__stalemate_duration",
                "zartman__mediator_present",
                "global__urgency_factor",
            ],
        )

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        p = self.params

        win_prob_a = env.get("fearon__win_prob_a", 0.5)
        c_A = env.get("fearon__war_cost_a", 0.10)
        c_B = env.get("fearon__war_cost_b", 0.10)

        # EU_war(A) = p*V - c_A;  EU_war(B) = (1-p)*V - c_B  (V = 1.0)
        eu_war_a = max(0.0, min(1.0, win_prob_a - c_A))
        eu_war_b = max(0.0, min(1.0, (1.0 - win_prob_a) - c_B))

        # MHS: both parties below payoff floor
        mhs_a = eu_war_a < p.payoff_floor
        mhs_b = eu_war_b < p.payoff_floor
        mhs = 1.0 if (mhs_a and mhs_b) else 0.0

        # Stalemate counter
        if mhs_a and mhs_b:
            self._stalemate_ticks += 1
        else:
            self._stalemate_ticks = 0
        stalemate_duration_norm = min(1.0, self._stalemate_ticks / _MAX_STALEMATE_HORIZON)

        # Ripeness conditions
        mediator_present = env.get("zartman__mediator_present", 0.0) > 0.5
        urgency = env.get("global__urgency_factor", 0.0)
        urgency_high = urgency > p.urgency_threshold
        duration_met = self._stalemate_ticks >= p.min_stalemate_ticks

        ripe = mhs_a and mhs_b and duration_met and (mediator_present or urgency_high)
        ripe_val = 1.0 if ripe else 0.0

        # Negotiation probability
        if ripe:
            negotiation_prob = min(1.0,
                p.base_negotiation_rate * p.ripe_multiplier * (1.0 + urgency)
            )
        else:
            negotiation_prob = p.base_negotiation_rate

        logger.debug(
            "Zartman tick=%d: eu_a=%.3f eu_b=%.3f mhs=%s stalemate_ticks=%d "
            "ripe=%s P(negotiate)=%.3f",
            tick, eu_war_a, eu_war_b, bool(mhs), self._stalemate_ticks,
            bool(ripe), negotiation_prob,
        )

        return {
            "zartman__eu_war_a":               eu_war_a,
            "zartman__eu_war_b":               eu_war_b,
            "zartman__mhs":                    mhs,
            "zartman__ripe_moment":            ripe_val,
            "zartman__negotiation_probability": negotiation_prob,
            "zartman__stalemate_duration":     stalemate_duration_norm,
        }
