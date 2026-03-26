"""
SIR Contagion Model

Compartmental model for the spread of contagion through a population.
Applies equally to: financial crises, supply chain failures, disease, information cascades,
reputational damage, cyber incidents, or any phenomenon with transmission and recovery dynamics.

Compartments (all normalized, S + I + R = 1):
    S = Susceptible  — not yet exposed
    I = Infected     — currently affected / actively spreading
    R = Recovered    — resolved, immune, or removed from spread

Differential equations:
    dS/dt = -β · S · I
    dI/dt =  β · S · I - γ · I
    dR/dt =  γ · I

Key metrics:
    R₀ = β / γ         basic reproduction number (R₀ > 1 → epidemic grows)
    R_eff = R₀ · S      effective reproduction number (declines as S is depleted)
    Herd immunity threshold: S_herd = 1 - 1/R₀

Discretized per tick with renormalization (prevents float drift from S+I+R=1):
    new_S = S - dt · β_eff · S · I
    new_I = I + dt · (β_eff · S · I - γ · I)
    new_R = R + dt · γ · I
    then: S, I, R = (new_S, new_I, new_R) / (new_S + new_I + new_R)

Cross-theory modulation:
    global__trade_volume < 0.5: trade disruption amplifies β (more systemic exposure,
                                denser contact networks under stress)

Env keys written:
    {contagion_id}__susceptible        S ∈ [0, 1]
    {contagion_id}__infected           I ∈ [0, 1]
    {contagion_id}__recovered          R ∈ [0, 1]
    {contagion_id}__r_effective        R_eff normalized to [0, 1] (÷ 10; 1.0 = R_eff ≥ 10)
    {contagion_id}__active_contagion   1.0 if I > active_threshold, else 0.0

Multiple simultaneous contagion processes:
    SIRContagion({"contagion_id": "banking"})       → banking__infected
    SIRContagion({"contagion_id": "supply_chain"})  → supply_chain__infected

References:
    Kermack & McKendrick (1927). Contribution to the mathematical theory of epidemics.
    Allen & Gale (2000). Financial contagion. Journal of Political Economy 108(1): 1–33.
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


@register_theory("sir_contagion")
class SIRContagion(TheoryBase):
    """
    SIR compartmental contagion model.

    Domains: contagion, financial_risk, supply_chain, epidemiology, cyber
    Priority: 0 (independent; reads global trade volume if present)

    Use contagion_id to run multiple independent contagion processes in
    the same simulation.
    """

    DOMAINS = ["contagion", "financial_risk", "supply_chain", "epidemiology", "cyber"]

    class Parameters(BaseModel):
        beta: float = Field(
            default=0.30, ge=0.0, le=5.0,
            description="Transmission rate per tick-unit (contact rate × transmission probability)",
        )
        gamma: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="Recovery rate per tick-unit (1/gamma = mean duration of infection)",
        )
        initial_infected: float = Field(
            default=0.01, ge=0.0, le=1.0,
            description="Seed fraction of infected population at setup",
        )
        active_threshold: float = Field(
            default=0.01, ge=0.0, le=1.0,
            description="I above this fraction triggers active_contagion = 1.0",
        )
        trade_amplification: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="Trade disruption → β amplification factor (0 = no coupling)",
        )
        tick_unit: str = Field(
            default="year",
            description="Time step unit: 'month', 'quarter', or 'year'",
        )
        contagion_id: str = Field(
            default="sir",
            description="Env key prefix; e.g. 'banking' → banking__infected",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        c = self.params.contagion_id
        return TheoryStateVariables(
            reads=[
                f"{c}__susceptible",
                f"{c}__infected",
                f"{c}__recovered",
                "global__trade_volume",
            ],
            writes=[
                f"{c}__susceptible",
                f"{c}__infected",
                f"{c}__recovered",
                f"{c}__r_effective",
                f"{c}__active_contagion",
            ],
            initializes=[
                f"{c}__susceptible",
                f"{c}__infected",
                f"{c}__recovered",
                f"{c}__r_effective",
                f"{c}__active_contagion",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed S, I, R from initial_infected parameter.
        S = 1 - initial_infected, I = initial_infected, R = 0.
        """
        inits = super().setup(env)
        c = self.params.contagion_id
        i0 = self.params.initial_infected
        if f"{c}__infected" not in env:
            inits[f"{c}__infected"] = i0
        if f"{c}__susceptible" not in env:
            inits[f"{c}__susceptible"] = 1.0 - i0
        if f"{c}__recovered" not in env:
            inits[f"{c}__recovered"] = 0.0
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one SIR ODE step with S+I+R=1 renormalization.

        Args:
            env:    normalized environment (read-only)
            agents: not used by SIR (population-level model)
            tick:   zero-based tick counter (unused; SIR is memoryless)

        Returns:
            delta dict with updated S, I, R, r_effective, active_contagion.
        """
        p = self.params
        c = p.contagion_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        S = env.get(f"{c}__susceptible", 1.0 - p.initial_infected)
        I = env.get(f"{c}__infected",    p.initial_infected)
        R = env.get(f"{c}__recovered",   0.0)

        # Trade disruption amplifies β: stressed networks have denser exposure
        trade = env.get("global__trade_volume", 0.5)
        if trade < 0.5:
            beta_eff = p.beta * (1.0 + p.trade_amplification * (0.5 - trade) / 0.5)
        else:
            beta_eff = p.beta

        # ODE step
        new_infections = beta_eff * S * I
        recoveries     = p.gamma * I

        new_S = S + dt * (-new_infections)
        new_I = I + dt * (new_infections - recoveries)
        new_R = R + dt * recoveries

        # Clamp negatives then renormalize to maintain S+I+R=1
        new_S = max(0.0, new_S)
        new_I = max(0.0, new_I)
        new_R = max(0.0, new_R)
        total = new_S + new_I + new_R
        if total > 1e-9:
            new_S /= total
            new_I /= total
            new_R /= total
        else:
            new_S, new_I, new_R = 0.0, 0.0, 1.0

        # R_effective = R₀ · S = (β/γ) · S, normalized ÷ 10 (1.0 = R_eff ≥ 10)
        r_eff = (beta_eff / max(p.gamma, 1e-9)) * new_S
        r_effective_norm = min(1.0, r_eff / 10.0)

        active_contagion = 1.0 if new_I > p.active_threshold else 0.0

        logger.debug(
            "SIR tick=%d contagion=%s: S=%.3f I=%.3f R=%.3f "
            "beta_eff=%.3f R_eff=%.2f active=%s",
            tick, c, new_S, new_I, new_R, beta_eff, r_eff, bool(active_contagion),
        )

        return {
            f"{c}__susceptible":      new_S,
            f"{c}__infected":         new_I,
            f"{c}__recovered":        new_R,
            f"{c}__r_effective":      r_effective_norm,
            f"{c}__active_contagion": active_contagion,
        }
