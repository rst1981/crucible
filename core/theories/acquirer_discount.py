"""
Acquirer's Discount / Hubris Hypothesis (Roll 1986; Moeller, Schlingemann & Stulz 2004)

Corporate acquirers systematically overpay for targets due to management hubris
and winner's curse in competitive bidding. The market discounts acquirer stock
on announcement day because investors expect deal synergies to be over-estimated.

Announcement-day abnormal return (AR) mechanics:
    AR = -(deal_premium_fraction × deal_size_ratio × hubris_factor)
         × (1 - synergy_realization_probability × (1 - hubris_factor))

    where deal_premium_fraction = deal_premium - 1.0

    E.g. Roll (1986): mean acquirer AR = -2.5% on announcement.
    Moeller et al. (2004): large acquirers (market cap > $10B) lose ~$12M on
    announcement day on average; acquirers paying top-decile premiums destroy
    ~$165M per deal.

Integration mechanics (post-announcement ticks):
    integration_cost decays over time at integration_completion_rate.
    Each tick, integration_cost contributes a small negative ongoing AR drag
    proportional to integration_complexity.

    dCost/dt = -integration_completion_rate × Cost × dt

Synergy realization window:
    After deal_close_lag ticks the simulation may receive a synergy shock
    (env key {acq_id}__synergy_realized ∈ [0,1]) that shifts CAR upward.

Announcement trigger:
    The simulation sets {acq_id}__deal_announced = 1.0 via scheduled_shock
    on announcement day. The theory fires the AR shock only on ticks where
    this key is 1.0.

Env keys read:
    {acq_id}__deal_announced         1.0 on announcement tick, 0.0 otherwise
    {acq_id}__synergy_realized       [0,1] if synergy materializes later (optional)
    global__market_stress            [0,1] market-wide risk-off (amplifies discount)

Env keys written:
    {acq_id}__abnormal_return        AR this tick, normalized: 0.5 = 0%, <0.5 = negative
    {acq_id}__cumulative_ar          Cumulative AR since tick 0, same normalization
    {acq_id}__integration_cost       Ongoing integration burden [0,1]; peaks at announcement

All return values normalized with 0.5 = 0%, using scale factor of ±40% max.

References:
    Roll (1986). The Hubris Hypothesis of Corporate Takeovers.
        Journal of Business 59(2): 197–216.
    Moeller, Schlingemann & Stulz (2004). Firm size and the gains from acquisitions.
        Journal of Finance 59(4): 1731–1752.
    Jensen (1986). Agency costs of free cash flow, corporate finance, and takeovers.
        American Economic Review 76(2): 323–329.
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

_DT_MAP: dict[str, float] = {
    "day": 1.0 / 365.0,
    "week": 1.0 / 52.0,
    "month": 1.0 / 12.0,
    "quarter": 0.25,
    "year": 1.0,
}

# Normalization scale: maps raw return (e.g. -0.40 to +0.40) → [0, 1]
_RETURN_SCALE = 0.40


def _normalize_return(raw: float) -> float:
    """Map raw decimal return to [0, 1] with 0.5 = 0%."""
    return max(0.0, min(1.0, 0.5 + raw / _RETURN_SCALE))


@register_theory("acquirer_discount")
class AcquirerDiscount(TheoryBase):
    """
    Roll (1986) Acquirer's Discount / Hubris Hypothesis.

    Domains: corporate_finance, mergers_acquisitions, behavioral_finance
    Priority: 2 (reads market_stress from SIR/Keynesian if present)

    Use acquirer_id to run multiple M&A events simultaneously.
    """

    DOMAINS = ["corporate_finance", "mergers_acquisitions", "behavioral_finance", "equity"]

    class Parameters(BaseModel):
        deal_premium: float = Field(
            default=1.30, ge=1.0, le=3.0,
            description=(
                "Acquisition price / target fair value. 1.30 = 30%% premium. "
                "Typical M&A premiums: 20–45%%. EL/Puig ~30%%."
            ),
        )
        deal_size_ratio: float = Field(
            default=0.35, ge=0.0, le=2.0,
            description=(
                "Target market value / acquirer market cap. Scales the AR shock. "
                "EL/Puig: ~$10.2B / $28.7B ≈ 0.355."
            ),
        )
        hubris_factor: float = Field(
            default=0.65, ge=0.0, le=1.0,
            description=(
                "Management overconfidence ∈ [0,1]. 0 = rational; 1 = maximum hubris. "
                "Calibrated from Roll (1986): high-premium deals exhibit hubris ~0.6–0.8."
            ),
        )
        synergy_realization_probability: float = Field(
            default=0.40, ge=0.0, le=1.0,
            description=(
                "Market's prior on synergies actually materializing. "
                "McKinsey research: ~40%% of deals realize synergy targets. "
                "Reduces the announcement-day AR shock."
            ),
        )
        integration_complexity: float = Field(
            default=0.60, ge=0.0, le=1.0,
            description=(
                "Integration difficulty ∈ [0,1]. Drives ongoing drag after announcement. "
                "High cross-border, brand-portfolio complexity → 0.7–0.9."
            ),
        )
        integration_completion_rate: float = Field(
            default=0.25, ge=0.0, le=1.0,
            description=(
                "Annual rate at which integration cost decays (per year). "
                "0.25 = 25%% integration resolved per year; typical M&A: 2–4 year horizon."
            ),
        )
        tick_unit: str = Field(
            default="quarter",
            description="Time step unit: 'day', 'week', 'month', 'quarter', or 'year'",
        )
        acquirer_id: str = Field(
            default="acquirer",
            description="Env key prefix; e.g. 'estee_lauder' → estee_lauder__abnormal_return",
        )

    def __init__(self, parameters: dict | None = None) -> None:
        super().__init__(parameters)
        self._cumulative_ar_raw: float = 0.0   # raw cumulative AR (not normalized)
        self._announcement_fired: bool = False  # fires AR shock only once per instance

    @property
    def state_variables(self) -> TheoryStateVariables:
        a = self.params.acquirer_id
        return TheoryStateVariables(
            reads=[
                f"{a}__deal_announced",
                f"{a}__synergy_realized",
                f"{a}__integration_cost",
                "global__market_stress",
            ],
            writes=[
                f"{a}__abnormal_return",
                f"{a}__cumulative_ar",
                f"{a}__integration_cost",
            ],
            initializes=[
                f"{a}__abnormal_return",
                f"{a}__cumulative_ar",
                f"{a}__integration_cost",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        a = self.params.acquirer_id
        # abnormal_return = 0.5 at start (neutral)
        if f"{a}__abnormal_return" not in env:
            inits[f"{a}__abnormal_return"] = 0.5
        if f"{a}__cumulative_ar" not in env:
            inits[f"{a}__cumulative_ar"] = 0.5
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        One-tick update:
        1. Announcement day: fire AR shock based on Roll (1986) formula.
        2. Every tick: apply ongoing integration cost drag, decay integration cost.
        3. If synergy_realized shock arrives: apply positive AR correction.

        All return env keys in [0, 1] with 0.5 = 0%.
        """
        p = self.params
        a = p.acquirer_id
        dt = _DT_MAP.get(p.tick_unit, 0.25)

        market_stress = env.get("global__market_stress", 0.0)
        deal_announced = env.get(f"{a}__deal_announced", 0.0)
        synergy_realized = env.get(f"{a}__synergy_realized", 0.0)
        integration_cost = env.get(f"{a}__integration_cost", 0.0)

        # --- Announcement-day shock (fires exactly once per instance) ---
        ar_raw = 0.0
        if deal_announced > 0.5 and not self._announcement_fired:
            self._announcement_fired = True
            # Roll (1986) formula: AR = -(premium_fraction × size_ratio × hubris)
            #   × market-skepticism-of-synergies
            premium_fraction = p.deal_premium - 1.0  # e.g. 0.30 for 30% premium
            market_skepticism = 1.0 - p.synergy_realization_probability * (1.0 - p.hubris_factor)
            ar_raw = -(premium_fraction * p.deal_size_ratio * p.hubris_factor * market_skepticism)
            # Market stress amplifies the discount (risk-off → investors penalize uncertainty harder)
            ar_raw *= (1.0 + market_stress * 0.5)
            # Integration cost jumps to integration_complexity on announcement
            integration_cost = p.integration_complexity
            logger.info(
                "AcquirerDiscount[%s]: announcement shock AR=%.4f (premium=%.2f, "
                "size_ratio=%.3f, hubris=%.2f)",
                a, ar_raw, premium_fraction, p.deal_size_ratio, p.hubris_factor,
            )

        # --- Synergy realization (positive correction) ---
        if synergy_realized > 0.1 and deal_announced < 0.5:
            # Partial AR recovery: synergy_realized × max possible synergy gain
            max_synergy_gain = (p.deal_premium - 1.0) * p.deal_size_ratio * p.synergy_realization_probability
            ar_raw += synergy_realized * max_synergy_gain
            logger.info("AcquirerDiscount[%s]: synergy correction AR=+%.4f", a, synergy_realized * max_synergy_gain)

        # --- Ongoing integration drag (every tick, proportional to remaining cost) ---
        ongoing_drag = integration_cost * p.integration_complexity * 0.05 * dt
        ar_raw -= ongoing_drag

        # --- Integration cost decay ---
        new_integration_cost = max(0.0, integration_cost * (1.0 - p.integration_completion_rate * dt))
        # Only reset integration_cost to peak on the exact announcement tick
        if deal_announced > 0.5 and self._announcement_fired and ar_raw != 0.0:
            new_integration_cost = p.integration_complexity

        # --- Accumulate CAR ---
        self._cumulative_ar_raw += ar_raw
        car_raw_clamped = max(-0.90, min(0.90, self._cumulative_ar_raw))

        return {
            f"{a}__abnormal_return":   _normalize_return(ar_raw),
            f"{a}__cumulative_ar":     _normalize_return(car_raw_clamped),
            f"{a}__integration_cost":  max(0.0, min(1.0, new_integration_cost)),
        }
