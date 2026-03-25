"""
Richardson Arms Race Model (1960)

Lewis Fry Richardson derived a system of two coupled ODEs to describe the
dynamics of mutual armament between two states. It remains the canonical
mathematical foundation for arms race analysis in quantitative IR.

Differential equations:
    dx/dt = k·y - a·x + g      (Country X's rate of arms change)
    dy/dt = l·x - b·y + h      (Country Y's rate of arms change)

  where:
    x, y  = arms level of Country X and Country Y  (normalized [0, 1])
    k, l  = defense coefficients (reactivity to adversary's arms)
    a, b  = fatigue coefficients (economic/political drag on own arms)
    g, h  = grievance terms (baseline arming independent of adversary)

Discretized per tick:
    x[t+1] = clamp(x[t] + dt · (k·y[t] - a·x[t] + g), 0, 1)
    y[t+1] = clamp(y[t] + dt · (l·x[t] - b·y[t] + h), 0, 1)

Stability condition:
    a·b > k·l  →  equilibrium exists at (x*, y*)
    a·b ≤ k·l  →  runaway escalation (unstable arms race)

Equilibrium point (when stable):
    x* = (b·g + k·h) / (a·b - k·l)
    y* = (a·h + l·g) / (a·b - k·l)

Env keys:
    actor_a__military_readiness   — arms level of actor A [0, 1]
    actor_b__military_readiness   — arms level of actor B [0, 1]
    richardson__escalation_index  — (x + y) / 2           [0, 1]
    richardson__stable            — 1.0 if a·b > k·l      {0, 1}

Note: military_readiness keys are actor-namespaced (not theory-namespaced)
so Fearon, Zartman, and other theories can read them without coupling to
Richardson's namespace.

Reference: Richardson, L.F. (1960). Arms and Insecurity. Boxwood Press.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)

# dt scaling by tick unit — theories that implement ODEs use this to convert
# the Richardson equations (formulated in years) to the sim's time step.
_DT_MAP: dict[str, float] = {
    "month":   1.0 / 12.0,
    "quarter": 0.25,
    "year":    1.0,
}


@register_theory("richardson_arms_race")
class RichardsonArmsRace(TheoryBase):
    """
    Lewis Fry Richardson (1960) mutual arms race dynamics.

    Domains: conflict, geopolitics, military
    Priority: 0 — runs before war-onset theories (Fearon, Zartman)
              that read military_readiness to assess conflict probability.

    Data flow:
        env["actor_a__military_readiness"]  ─┐
        env["actor_b__military_readiness"]  ─┤─► ODE step ─► delta dict
        params (k, l, a, b, g, h, tick_unit) ─┘

    Stability check:
        a·b > k·l  →  stable (equilibrium)
        a·b ≤ k·l  →  unstable (runaway escalation until clamp at 1.0)
        Warning logged at construction time if unstable; not an error because
        unstable regimes are physically meaningful for crisis simulations.
    """

    DOMAINS = ["conflict", "geopolitics", "military"]

    class Parameters(BaseModel):
        # ── Defense coefficients ──────────────────────────────────────────────
        k: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="X's reactivity to Y's arms (defense coefficient)",
        )
        l: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description="Y's reactivity to X's arms (defense coefficient)",
        )
        # ── Fatigue coefficients ──────────────────────────────────────────────
        a: float = Field(
            default=0.15, ge=0.0, le=1.0,
            description="X's economic drag on own arms (fatigue coefficient)",
        )
        b: float = Field(
            default=0.15, ge=0.0, le=1.0,
            description="Y's economic drag on own arms (fatigue coefficient)",
        )
        # ── Grievance terms ───────────────────────────────────────────────────
        g: float = Field(
            default=0.05, ge=-0.5, le=0.5,
            description="X's baseline arming motivation (negative = demilitarizing)",
        )
        h: float = Field(
            default=0.05, ge=-0.5, le=0.5,
            description="Y's baseline arming motivation (negative = demilitarizing)",
        )
        # ── Simulation config ─────────────────────────────────────────────────
        tick_unit: str = Field(
            default="year",
            description="Time step unit: 'month', 'quarter', or 'year'",
        )
        actor_a_id: str = Field(
            default="actor_a",
            description="Env key prefix for actor A (e.g. 'iran' → iran__military_readiness)",
        )
        actor_b_id: str = Field(
            default="actor_b",
            description="Env key prefix for actor B",
        )

        @model_validator(mode="after")
        def warn_if_unstable(self) -> "RichardsonArmsRace.Parameters":
            ab = self.a * self.b
            kl = self.k * self.l
            if ab <= kl:
                logger.warning(
                    "Richardson params are in UNSTABLE regime: "
                    "a·b=%.4f ≤ k·l=%.4f. "
                    "Expect runaway escalation (physically valid for crisis sims).",
                    ab,
                    kl,
                )
            return self

    @property
    def state_variables(self) -> TheoryStateVariables:
        p = self.params
        return TheoryStateVariables(
            reads=[
                f"{p.actor_a_id}__military_readiness",
                f"{p.actor_b_id}__military_readiness",
            ],
            writes=[
                f"{p.actor_a_id}__military_readiness",
                f"{p.actor_b_id}__military_readiness",
                "richardson__escalation_index",
                "richardson__stable",
            ],
            initializes=[
                f"{p.actor_a_id}__military_readiness",
                f"{p.actor_b_id}__military_readiness",
                "richardson__escalation_index",
                "richardson__stable",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed missing military_readiness keys with 0.5 (mid-range, not zero).
        escalation_index and stable get 0.0 until the first update() runs.
        """
        p = self.params
        inits = super().setup(env)  # seeds 0.0 for any missing key

        # Override: military_readiness defaults to 0.5, not 0.0
        for key in (
            f"{p.actor_a_id}__military_readiness",
            f"{p.actor_b_id}__military_readiness",
        ):
            if key not in env:
                inits[key] = 0.5
                logger.debug(
                    "Richardson: seeding '%s' = 0.5 (mid-range default)", key
                )

        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one Richardson ODE step.

        Reads x and y from env, computes dx/dt and dy/dt, advances one dt,
        clamps to [0, 1], computes escalation_index and stable diagnostic.

        Args:
            env:    normalized environment (read-only)
            agents: not used by Richardson (pure state-based, no agent intent)
            tick:   zero-based tick counter (unused; Richardson is memoryless)

        Returns:
            delta dict with updated values for all four write keys.
        """
        p = self.params
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        x = env.get(f"{p.actor_a_id}__military_readiness", 0.5)
        y = env.get(f"{p.actor_b_id}__military_readiness", 0.5)

        # dx/dt = k·y - a·x + g
        # dy/dt = l·x - b·y + h
        dx = p.k * y - p.a * x + p.g
        dy = p.l * x - p.b * y + p.h

        new_x = max(0.0, min(1.0, x + dt * dx))
        new_y = max(0.0, min(1.0, y + dt * dy))

        stable = 1.0 if (p.a * p.b > p.k * p.l) else 0.0

        logger.debug(
            "Richardson tick=%d: x=%.4f→%.4f (dx=%.4f) y=%.4f→%.4f (dy=%.4f) "
            "dt=%.4f stable=%s",
            tick, x, new_x, dx, y, new_y, dy, dt, bool(stable),
        )

        return {
            f"{p.actor_a_id}__military_readiness": new_x,
            f"{p.actor_b_id}__military_readiness": new_y,
            "richardson__escalation_index": (new_x + new_y) / 2.0,
            "richardson__stable": stable,
        }

    def equilibrium(self) -> tuple[float, float] | None:
        """
        Compute the theoretical equilibrium point (x*, y*).

        Returns (x*, y*) if stable (a·b > k·l), else None.
        Values may be outside [0, 1] if parameters imply an equilibrium
        beyond physical bounds — clamping in update() handles runtime bounds.
        """
        p = self.params
        denom = p.a * p.b - p.k * p.l
        if denom <= 0:
            return None
        x_star = (p.b * p.g + p.k * p.h) / denom
        y_star = (p.a * p.h + p.l * p.g) / denom
        return x_star, y_star
