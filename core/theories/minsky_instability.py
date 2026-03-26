"""
Minsky Financial Instability Hypothesis (1977 / 1986)

Hyman Minsky argued that stability is destabilizing: prolonged periods of
prosperity induce balance-sheet fragility, moving firms and households along a
spectrum from conservative hedge finance to speculative finance and finally
Ponzi finance. When Ponzi positions dominate, a self-reinforcing crisis becomes
likely.

Three-compartment model (analogous to SIR epidemics):

    Hedge (H)      — cash-flows cover principal + interest
    Speculative (S) — cash-flows cover interest only; roll principal
    Ponzi (P)      — cash-flows cover neither; relies on asset appreciation

Transition dynamics (per tick-unit):

    H → S : erosion_rate × (1 + boom_sensitivity × boom_signal)
    S → P : escalation_rate × (1 + interest_sensitivity × stress_signal)
    P → H : deleveraging_rate  (crisis forces balance-sheet repair)

where:
    boom_signal    = max(0, asset_appreciation - 0.05)
    stress_signal  = max(0, interest_rate - 0.05)

Financial fragility:
    fragility = 0.3·S + 1.0·P   (Ponzi share weighted most heavily)

Crash risk (nonlinear):
    crash_risk = max(0, P - crash_threshold)² / (1 - crash_threshold)²

Cross-theory:
    {cycle_id}__interest_rate      — set by agents/central-bank; default 0.05
    {cycle_id}__asset_appreciation — set by agents/asset markets; default 0.05

Env keys written:
    {cycle_id}__hedge_fraction       fraction of balance sheets in hedge finance
    {cycle_id}__speculative_fraction fraction in speculative finance
    {cycle_id}__ponzi_fraction       fraction in Ponzi finance
    {cycle_id}__financial_fragility  0.3·S + 1.0·P
    {cycle_id}__crash_risk           nonlinear Ponzi-excess signal

References:
    Minsky, H. P. (1977). The financial instability hypothesis: an interpretation
    of Keynes and an alternative to "standard" theory.
    Nebraska Journal of Economics and Business 16(1): 5–16.

    Minsky, H. P. (1986). Stabilizing an Unstable Economy. Yale University Press.

    Keen, S. (1995). Finance and economic breakdown: modeling Minsky's financial
    instability hypothesis. Journal of Post Keynesian Economics 17(4): 607–635.
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


@register_theory("minsky_instability")
class MinskyInstability(TheoryBase):
    """
    Minsky (1977) financial instability hypothesis — three-compartment model.

    Domains: finance, banking, macro, crisis, debt_cycle
    Priority: 0 (reads exogenous interest_rate and asset_appreciation from env)

    Use cycle_id for multiple simultaneous Minsky cycles in the same sim.
    """

    DOMAINS = ["finance", "banking", "macro", "crisis", "debt_cycle"]

    class Parameters(BaseModel):
        erosion_rate: float = Field(
            default=0.10, ge=0.0, le=1.0,
            description="Rate of hedge→speculative transition per tick-unit",
        )
        escalation_rate: float = Field(
            default=0.15, ge=0.0, le=1.0,
            description="Rate of speculative→Ponzi transition per tick-unit",
        )
        deleveraging_rate: float = Field(
            default=0.20, ge=0.0, le=1.0,
            description="Rate of Ponzi→hedge repair (crisis deleveraging) per tick-unit",
        )
        interest_sensitivity: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="Multiplier amplifying the interest-rate stress signal on escalation",
        )
        boom_sensitivity: float = Field(
            default=0.50, ge=0.0, le=2.0,
            description="Multiplier amplifying the asset-appreciation boom signal on erosion",
        )
        crash_threshold: float = Field(
            default=0.30, ge=0.05, le=0.80,
            description="Ponzi fraction above which crash_risk becomes nonlinearly positive",
        )
        tick_unit: str = Field(default="year")
        cycle_id: str = Field(
            default="minsky",
            description="Env key prefix; e.g. 'cycle1' → cycle1__hedge_fraction",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        c = self.params.cycle_id
        return TheoryStateVariables(
            reads=[
                f"{c}__hedge_fraction",
                f"{c}__speculative_fraction",
                f"{c}__ponzi_fraction",
                f"{c}__interest_rate",
                f"{c}__asset_appreciation",
            ],
            writes=[
                f"{c}__hedge_fraction",
                f"{c}__speculative_fraction",
                f"{c}__ponzi_fraction",
                f"{c}__financial_fragility",
                f"{c}__crash_risk",
            ],
            initializes=[
                f"{c}__hedge_fraction",
                f"{c}__speculative_fraction",
                f"{c}__ponzi_fraction",
                f"{c}__financial_fragility",
                f"{c}__crash_risk",
                f"{c}__interest_rate",       # owned by agents/central-bank
                f"{c}__asset_appreciation",  # owned by agents/asset markets
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        """
        Seed compartment fractions and exogenous driving variables.

        H=0.70, S=0.20, P=0.10 reflects a mid-expansion starting point where
        most balance sheets are still sound but speculative finance is present.
        """
        inits = super().setup(env)
        c = self.params.cycle_id
        if f"{c}__hedge_fraction" not in env:
            inits[f"{c}__hedge_fraction"] = 0.70
        if f"{c}__speculative_fraction" not in env:
            inits[f"{c}__speculative_fraction"] = 0.20
        if f"{c}__ponzi_fraction" not in env:
            inits[f"{c}__ponzi_fraction"] = 0.10
        if f"{c}__interest_rate" not in env:
            inits[f"{c}__interest_rate"] = 0.05
        if f"{c}__asset_appreciation" not in env:
            inits[f"{c}__asset_appreciation"] = 0.05
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Advance the Minsky compartmental model by one tick.

        Reads current H/S/P fractions and exogenous drivers from env,
        computes transition flows scaled by dt, renormalizes so H+S+P=1,
        then derives financial_fragility and crash_risk.

        Args:
            env:    normalized environment (read-only)
            agents: not used directly (interest_rate/asset_appreciation in env)
            tick:   zero-based tick counter

        Returns:
            delta dict with updated hedge_fraction, speculative_fraction,
            ponzi_fraction, financial_fragility, crash_risk.
        """
        p = self.params
        c = p.cycle_id
        dt = _DT_MAP.get(p.tick_unit, 1.0)

        H = env.get(f"{c}__hedge_fraction", 0.70)
        S = env.get(f"{c}__speculative_fraction", 0.20)
        P = env.get(f"{c}__ponzi_fraction", 0.10)
        interest_rate = env.get(f"{c}__interest_rate", 0.05)
        asset_appreciation = env.get(f"{c}__asset_appreciation", 0.05)

        # Boom signal: asset appreciation above neutral accelerates H→S erosion
        boom_signal = max(0.0, asset_appreciation - 0.05)
        alpha = p.erosion_rate * (1.0 + p.boom_sensitivity * boom_signal) * dt

        # Stress signal: interest rate above neutral accelerates S→P escalation
        stress_signal = max(0.0, interest_rate - 0.05)
        beta = p.escalation_rate * (1.0 + p.interest_sensitivity * stress_signal) * dt

        # Deleveraging: Ponzi forced to repair balance sheets
        delta_rate = p.deleveraging_rate * dt

        # Compartmental flows — cap at available stock
        hedge_to_spec = min(H, alpha * H)
        spec_to_ponzi = min(S, beta * S)
        ponzi_to_hedge = min(P, delta_rate * P)

        new_H = H - hedge_to_spec + ponzi_to_hedge
        new_S = S + hedge_to_spec - spec_to_ponzi
        new_P = P + spec_to_ponzi - ponzi_to_hedge

        # Renormalize to ensure H + S + P = 1 (SIR-style)
        total = new_H + new_S + new_P
        if total > 1e-9:
            new_H /= total
            new_S /= total
            new_P /= total
        else:
            new_H, new_S, new_P = 1.0, 0.0, 0.0

        # Clamp each fraction to [0, 1]
        new_H = max(0.0, min(1.0, new_H))
        new_S = max(0.0, min(1.0, new_S))
        new_P = max(0.0, min(1.0, new_P))

        financial_fragility = max(0.0, min(1.0, 0.3 * new_S + 1.0 * new_P))

        crash_risk = (
            max(0.0, new_P - p.crash_threshold) ** 2
            / max(1e-9, (1.0 - p.crash_threshold) ** 2)
        )
        crash_risk = max(0.0, min(1.0, crash_risk))

        logger.debug(
            "MinskyInstability tick=%d cycle=%s: H=%.3f S=%.3f P=%.3f "
            "fragility=%.3f crash_risk=%.4f (alpha=%.4f beta=%.4f delta=%.4f)",
            tick, c, new_H, new_S, new_P, financial_fragility, crash_risk,
            alpha, beta, delta_rate,
        )

        return {
            f"{c}__hedge_fraction":       new_H,
            f"{c}__speculative_fraction": new_S,
            f"{c}__ponzi_fraction":       new_P,
            f"{c}__financial_fragility":  financial_fragility,
            f"{c}__crash_risk":           crash_risk,
        }
