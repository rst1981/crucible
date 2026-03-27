"""
core/theories/discovered/narrative_contagion.py — Competing Narrative Contagion

Based on: Shiller, R.J. (2017). Narrative Economics. American Economic Review, 107(4), 967–1004.
          NBER Working Paper 23075.
Also: Goetzmann, W. & Kim, D. (2022). Crash Narratives. NBER Working Paper 30195.
      Akerlof, G. & Shiller, R. (2015). Phishing for Phools.

Model:
    Economic narratives spread epidemiologically. Two competing narratives — a bull
    narrative (e.g. "AI infrastructure supercycle") and a bear narrative
    (e.g. "compute efficiency destroys GPU moat") — each propagate through a population
    with separate virality and decay rates and cross-inhibit each other.

    Equations (discrete SIR-analog):
        N_bull_t+1 = N_bull + beta_bull * N_bull * (1 - N_bull - N_bear)
                               - gamma_bull * N_bull
                               - inhibition * N_bull * N_bear
        N_bear_t+1 = N_bear + beta_bear * N_bear * (1 - N_bull - N_bear)
                               - gamma_bear * N_bear
                               - inhibition * N_bull * N_bear

    Sentiment proxy written as:
        narrative__sentiment_balance = (N_bull - N_bear + 1) / 2   ∈ [0, 1]
        0.5 = neutral, > 0.5 = bull dominant, < 0.5 = bear dominant

    Calibration (Goetzmann & Kim 2022 crash narrative cycles):
        beta_bull = 0.25, gamma_bull = 0.08
        beta_bear = 0.30, gamma_bear = 0.10 (fear spreads faster, decays faster)
        inhibition = 0.12

Env keys written:
    narrative_contagion__bull_share      ∈ [0, 1]  fraction holding bull narrative
    narrative_contagion__bear_share      ∈ [0, 1]  fraction holding bear narrative
    narrative_contagion__sentiment_balance ∈ [0, 1]  0=full bear, 1=full bull, 0.5=neutral

Reads from env:
    narrative_contagion__bull_share      (prior tick)
    narrative_contagion__bear_share      (prior tick)
    narrative_contagion__bear_trigger    (external shock seeding bear narrative, e.g. 0.0 baseline)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent


@register_theory("narrative_contagion")
class NarrativeContagion(TheoryBase):
    """Shiller (2017) competing narrative epidemiological model."""

    DOMAINS = [
        "behavioral_finance",
        "social",
        "equity",
        "market",
        "contagion",
    ]

    class Parameters(BaseModel):
        beta_bull: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Virality of the bull narrative per tick. "
                        "Calibrated to typical positive sentiment cycles ~0.20–0.30.",
        )
        gamma_bull: float = Field(
            default=0.08,
            ge=0.0,
            le=1.0,
            description="Decay rate of bull narrative per tick. "
                        "Bull narratives tend to be stickier; ~0.05–0.10.",
        )
        beta_bear: float = Field(
            default=0.30,
            ge=0.0,
            le=1.0,
            description="Virality of the bear narrative per tick. "
                        "Fear spreads faster than greed; ~0.25–0.35.",
        )
        gamma_bear: float = Field(
            default=0.10,
            ge=0.0,
            le=1.0,
            description="Decay rate of bear narrative per tick. "
                        "Bear narratives decay faster after recovery; ~0.08–0.15.",
        )
        cross_inhibition: float = Field(
            default=0.12,
            ge=0.0,
            le=1.0,
            description="Rate at which competing narratives suppress each other. "
                        "Calibrated from Goetzmann & Kim (2022): ~0.10–0.15.",
        )
        initial_bull_share: float = Field(
            default=0.60,
            ge=0.0,
            le=1.0,
            description="Bull narrative prevalence at tick 0. "
                        "Pre-DeepSeek AI bull narrative ~0.65.",
        )
        initial_bear_share: float = Field(
            default=0.10,
            ge=0.0,
            le=1.0,
            description="Bear narrative prevalence at tick 0.",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "narrative_contagion__bull_share",
                "narrative_contagion__bear_share",
                "narrative_contagion__bear_trigger",
            ],
            writes=[
                "narrative_contagion__bull_share",
                "narrative_contagion__bear_share",
                "narrative_contagion__sentiment_balance",
            ],
            initializes=[
                "narrative_contagion__bull_share",
                "narrative_contagion__bear_share",
                "narrative_contagion__sentiment_balance",
            ],
        )

    def update(self, env: dict, agents: list, tick: int) -> dict[str, float]:
        p = self.params
        bull = env.get("narrative_contagion__bull_share", p.initial_bull_share)
        bear = env.get("narrative_contagion__bear_share", p.initial_bear_share)
        bear_trigger = env.get("narrative_contagion__bear_trigger", 0.0)

        # Exogenous bear narrative injection (e.g. DeepSeek announcement shock)
        bear = min(1.0, bear + bear_trigger)

        # Susceptible pool (neither narrative held strongly)
        susceptible = max(0.0, 1.0 - bull - bear)

        # Competing narrative dynamics
        d_bull = (
            p.beta_bull * bull * susceptible
            - p.gamma_bull * bull
            - p.cross_inhibition * bull * bear
        )
        d_bear = (
            p.beta_bear * bear * susceptible
            - p.gamma_bear * bear
            - p.cross_inhibition * bull * bear
        )

        new_bull = max(0.0, min(1.0, bull + d_bull))
        new_bear = max(0.0, min(1.0, bear + d_bear))

        # Ensure bull + bear ≤ 1
        total = new_bull + new_bear
        if total > 1.0:
            new_bull /= total
            new_bear /= total

        # Sentiment balance: 0.5 = neutral, >0.5 = bull, <0.5 = bear
        sentiment_balance = max(0.0, min(1.0, (new_bull - new_bear + 1.0) / 2.0))

        return {
            "narrative_contagion__bull_share": new_bull,
            "narrative_contagion__bear_share": new_bear,
            "narrative_contagion__sentiment_balance": sentiment_balance,
        }
