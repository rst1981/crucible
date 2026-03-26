"""
Customer-Based Brand Equity Decay (Keller 1993; Fornell et al. 2006)

Brand equity is a stock of consumer associations — awareness, perceived quality,
and loyalty — that command a price premium over functional alternatives. This model
treats brand equity as a depletable resource that decays under competitive pressure
and media erosion, and that is rebuilt through marketing investment.

Brand equity dynamics:
    dE/dt = -decay_coeff × E × (1 + competitive_pressure × sensitivity
                                    + media_erosion_rate × media_negative)
            + marketing_investment × (1 - E)          ← logistic ceiling

    where E = brand equity ∈ [0, 1]

Price premium transmission:
    price_premium = E × max_price_premium_fraction     (normalized to [0, 1])

    This maps brand equity → willingness-to-pay premium over mass alternatives.
    As equity decays under dupe culture pressure, the premium compresses:
    consumers become indifferent between prestige and mass products.

Awareness and Loyalty sub-models:
    Awareness decays more slowly than equity (less price-sensitive, more reach-driven):
        dA/dt = -0.4 × decay_coeff × A × (1 + competitive_pressure × sensitivity * 0.5)

    Loyalty is more persistent than awareness (switching costs, habit):
        dL/dt = -0.3 × decay_coeff × L × (1 + competitive_pressure × 0.3)

Fornell et al. (2006) link: customer satisfaction → brand loyalty → abnormal returns.
    This model operationalizes that link: brand equity (including loyalty) directly
    reduces customer churn, supporting revenue stability.

Env keys read:
    global__competitive_pressure     [0,1] from porter_five_forces or external shock
    {brand_id}__marketing_investment [0,1] marketing spend intensity (set by shocks/agents)
    {brand_id}__media_negative       [0,1] fraction of media coverage that is negative

Env keys written:
    {brand_id}__brand_equity         E ∈ [0,1]: current brand equity stock
    {brand_id}__price_premium        [0,1]: willingness-to-pay premium (E × max_premium)
    {brand_id}__awareness            [0,1]: consumer brand awareness
    {brand_id}__loyalty              [0,1]: consumer loyalty / repeat purchase rate

Use brand_id to track multiple brands simultaneously in competitive scenarios.

References:
    Keller (1993). Conceptualizing, Measuring, and Managing Customer-Based Brand Equity.
        Journal of Marketing 57(1): 1–22.
    Fornell, Mithas, Morgeson & Krishnan (2006). Customer Satisfaction and Stock Prices:
        High Returns, Low Risk. Journal of Marketing 70(1): 3–14.
    Keller & Lehmann (2006). Brands and Branding: Research Findings and Future Priorities.
        Marketing Science 25(6): 740–759.
    Davcik & Sharma (2015). Impact of product differentiation, marketing investments and
        brand equity on pricing strategies. European Journal of Marketing 49(5/6).
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


@register_theory("brand_equity_decay")
class BrandEquityDecay(TheoryBase):
    """
    Keller (1993) Customer-Based Brand Equity Decay model.

    Domains: brand_management, marketing, corporate_finance, consumer_behavior
    Priority: 3 (reads competitive_pressure from porter_five_forces)

    Use brand_id to simulate multiple brands in the same scenario.
    """

    DOMAINS = ["brand_management", "marketing", "corporate_finance", "consumer_behavior"]

    class Parameters(BaseModel):
        initial_brand_equity: float = Field(
            default=0.75, ge=0.0, le=1.0,
            description=(
                "Starting brand equity ∈ [0,1]. Prestige heritage brands: 0.70–0.85. "
                "Challenger brands: 0.40–0.60. EL brands (Clinique, MAC, ESTEE): ~0.72."
            ),
        )
        initial_awareness: float = Field(
            default=0.85, ge=0.0, le=1.0,
            description=(
                "Starting consumer awareness ∈ [0,1]. EL masterbrand global awareness ~0.85. "
                "Decays more slowly than equity."
            ),
        )
        initial_loyalty: float = Field(
            default=0.65, ge=0.0, le=1.0,
            description=(
                "Starting loyalty / repeat-purchase rate ∈ [0,1]. "
                "Prestige beauty typical retention: 60–70%%."
            ),
        )
        decay_coefficient: float = Field(
            default=0.08, ge=0.0, le=1.0,
            description=(
                "Annual brand equity decay rate absent marketing reinvestment. "
                "0.08 = 8%% annual equity erosion under moderate pressure. "
                "Dupe/mass pressure can push this to 0.15–0.20 annually."
            ),
        )
        competitive_pressure_sensitivity: float = Field(
            default=0.60, ge=0.0, le=2.0,
            description=(
                "How much competitive_pressure amplifies decay. "
                "0.6 = moderate sensitivity. High-substitution categories → 1.0–1.5."
            ),
        )
        media_erosion_rate: float = Field(
            default=0.30, ge=0.0, le=1.0,
            description=(
                "Fraction of media negativity that transmits to equity decay. "
                "Social media amplifies: negative viral content → 0.4–0.6."
            ),
        )
        max_price_premium_fraction: float = Field(
            default=0.45, ge=0.0, le=1.0,
            description=(
                "Maximum price premium prestige commands over mass at full equity (=1.0). "
                "Prestige beauty typically 30–60%% above mass. Normalized: 0.45 = 45%% premium."
            ),
        )
        marketing_investment_sensitivity: float = Field(
            default=0.50, ge=0.0, le=1.0,
            description=(
                "Rate at which marketing investment rebuilds equity. "
                "0.5 = 50%% of investment flows to equity per year."
            ),
        )
        tick_unit: str = Field(
            default="quarter",
            description="Time step unit: 'day', 'week', 'month', 'quarter', or 'year'",
        )
        brand_id: str = Field(
            default="brand",
            description="Env key prefix; e.g. 'estee_lauder' → estee_lauder__brand_equity",
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        p = self.params
        b = p.brand_id
        if f"{b}__brand_equity" not in env:
            inits[f"{b}__brand_equity"] = p.initial_brand_equity
        if f"{b}__awareness" not in env:
            inits[f"{b}__awareness"] = p.initial_awareness
        if f"{b}__loyalty" not in env:
            inits[f"{b}__loyalty"] = p.initial_loyalty
        if f"{b}__price_premium" not in env:
            inits[f"{b}__price_premium"] = p.initial_brand_equity * p.max_price_premium_fraction
        return inits

    @property
    def state_variables(self) -> TheoryStateVariables:
        b = self.params.brand_id
        return TheoryStateVariables(
            reads=[
                "global__competitive_pressure",
                f"{b}__brand_equity",
                f"{b}__awareness",
                f"{b}__loyalty",
                f"{b}__marketing_investment",
                f"{b}__media_negative",
            ],
            writes=[
                f"{b}__brand_equity",
                f"{b}__price_premium",
                f"{b}__awareness",
                f"{b}__loyalty",
            ],
            initializes=[
                f"{b}__brand_equity",
                f"{b}__price_premium",
                f"{b}__awareness",
                f"{b}__loyalty",
            ],
        )

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Apply one-tick brand equity dynamics.

        Equity decays under competitive pressure and media negativity,
        and is partially rebuilt by marketing investment.
        Awareness and loyalty follow slower decay sub-models.

        All outputs normalized to [0, 1].
        """
        p = self.params
        b = p.brand_id
        dt = _DT_MAP.get(p.tick_unit, 0.25)

        equity = env.get(f"{b}__brand_equity", p.initial_brand_equity)
        awareness = env.get(f"{b}__awareness", p.initial_awareness)
        loyalty = env.get(f"{b}__loyalty", p.initial_loyalty)

        competitive_pressure = env.get("global__competitive_pressure", 0.0)
        marketing_investment = env.get(f"{b}__marketing_investment", 0.0)
        media_negative = env.get(f"{b}__media_negative", 0.0)

        # --- Equity dynamics ---
        decay_multiplier = (
            1.0
            + competitive_pressure * p.competitive_pressure_sensitivity
            + media_negative * p.media_erosion_rate
        )
        decay = p.decay_coefficient * equity * decay_multiplier * dt
        rebuild = marketing_investment * p.marketing_investment_sensitivity * (1.0 - equity) * dt
        new_equity = max(0.0, min(1.0, equity - decay + rebuild))

        # --- Awareness dynamics (0.4× decay rate, less sensitive to price competition) ---
        awareness_decay_mult = (
            1.0 + competitive_pressure * p.competitive_pressure_sensitivity * 0.4
            + media_negative * p.media_erosion_rate * 0.5
        )
        awareness_decay = p.decay_coefficient * 0.4 * awareness * awareness_decay_mult * dt
        awareness_rebuild = marketing_investment * p.marketing_investment_sensitivity * 0.6 * (1.0 - awareness) * dt
        new_awareness = max(0.0, min(1.0, awareness - awareness_decay + awareness_rebuild))

        # --- Loyalty dynamics (0.3× decay rate, more persistent — switching costs) ---
        loyalty_decay_mult = 1.0 + competitive_pressure * 0.3 * dt
        loyalty_decay = p.decay_coefficient * 0.3 * loyalty * loyalty_decay_mult * dt
        loyalty_rebuild = marketing_investment * p.marketing_investment_sensitivity * 0.4 * (1.0 - loyalty) * dt
        new_loyalty = max(0.0, min(1.0, loyalty - loyalty_decay + loyalty_rebuild))

        # --- Price premium: scales linearly with brand equity ---
        new_price_premium = new_equity * p.max_price_premium_fraction

        logger.debug(
            "BrandEquityDecay[%s] tick=%d: equity %.3f→%.3f "
            "(decay_mult=%.2f, marketing=%.2f)",
            b, tick, equity, new_equity, decay_multiplier, marketing_investment,
        )

        return {
            f"{b}__brand_equity":   new_equity,
            f"{b}__price_premium":  max(0.0, min(1.0, new_price_premium)),
            f"{b}__awareness":      new_awareness,
            f"{b}__loyalty":        new_loyalty,
        }
