"""
Real Options Agricultural Adaptation Theory Module
====================================================

Model: Dixit & Pindyck (1994) Real Options model for irreversible investment under uncertainty,
applied to winemaker replanting decisions under climate stress.

Core Equations:
    beta = (0.5 - mu/sigma^2) + sqrt((mu/sigma^2 - 0.5)^2 + 2*r/sigma^2)
        where mu = drift of climate stress, sigma = volatility, r = discount rate

    Investment threshold multiplier: beta / (beta - 1)
    V* = (beta / (beta - 1)) * I
        where I = normalized replant cost, V* = critical asset value to trigger investment

    Option value (normalized):
        option_value = max(0, current_value - exercise_threshold) * (beta / (beta - 1))

    Exercise decision:
        invest = 1 if quality_degradation > V* else 0

    Post-investment recovery:
        quality improves over payback_years ticks

Env Keys:
    Reads:
        real_options_agri_adapt__climate_stress     : normalized GDD above optimal threshold [0,1]
        real_options_agri_adapt__quality_degradation: normalized wine quality loss [0,1]
        real_options_agri_adapt__investment_state   : 0=waiting, 1=invested [0,1]
        real_options_agri_adapt__recovery_progress  : post-investment recovery progress [0,1]

    Writes/Initializes:
        real_options_agri_adapt__climate_stress
        real_options_agri_adapt__quality_degradation
        real_options_agri_adapt__investment_state
        real_options_agri_adapt__recovery_progress
        real_options_agri_adapt__option_value       : value of waiting to invest [0,1]
        real_options_agri_adapt__exercise_threshold_norm : normalized critical threshold [0,1]
        real_options_agri_adapt__beta_coefficient   : beta from real options formula [0,1]

Citation:
    Dixit, A. & Pindyck, R. (1994). Investment Under Uncertainty. Princeton University Press.
    https://press.princeton.edu/books/paperback/9780691034102/investment-under-uncertainty
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)

_THEORY_ID = "real_options_agri_adapt"


@register_theory(_THEORY_ID)
class RealOptionsAgriAdapt(TheoryBase):
    """
    Real Options model for irreversible agricultural adaptation investment.

    Models a winemaker's option to replant with climate-resilient varietals as climate
    stress increases. Uses Dixit-Pindyck (1994) framework: investment is irreversible,
    there is value in waiting, and the optimal threshold V* = beta/(beta-1) * I.
    """

    DOMAINS = ['agriculture', 'climate', 'corporate_strategy', 'ecology', 'finance', 'land', 'sustainability']

    class Parameters(BaseModel):
        replant_cost: float = Field(
            default=12000.0,
            ge=1000.0,
            le=50000.0,
            description="Replanting cost per acre in USD (irreversible investment)",
        )
        payback_years: float = Field(
            default=7.0,
            ge=1.0,
            le=20.0,
            description="Years until replanted vines reach full productivity (lead time)",
        )
        volatility: float = Field(
            default=0.15,
            ge=0.01,
            le=1.0,
            description="Volatility (sigma) of GDD / climate stress process",
        )
        discount_rate: float = Field(
            default=0.08,
            ge=0.001,
            le=0.5,
            description="Annual discount rate r for NPV calculations",
        )
        exercise_threshold: float = Field(
            default=0.30,
            ge=0.01,
            le=1.0,
            description="Normalized quality degradation level that triggers investment evaluation",
        )
        drift: float = Field(
            default=0.02,
            ge=-0.5,
            le=0.5,
            description="Drift (mu) of the climate stress GBM process per tick",
        )
        stress_diffusion: float = Field(
            default=0.03,
            ge=0.0,
            le=0.5,
            description="Per-tick increment to climate stress absent investment",
        )
        quality_stress_sensitivity: float = Field(
            default=0.5,
            ge=0.0,
            le=2.0,
            description="How strongly climate stress drives quality degradation",
        )
        recovery_rate: float = Field(
            default=0.10,
            ge=0.01,
            le=1.0,
            description="Per-tick recovery in quality_degradation after investment (post-replant improvement rate)",
        )
        max_replant_cost_norm: float = Field(
            default=20000.0,
            ge=1000.0,
            le=100000.0,
            description="Maximum replant cost used for normalization to [0,1]",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        p = _THEORY_ID
        return TheoryStateVariables(
            reads=[
                f"{p}__climate_stress",
                f"{p}__quality_degradation",
                f"{p}__investment_state",
                f"{p}__recovery_progress",
            ],
            writes=[
                f"{p}__climate_stress",
                f"{p}__quality_degradation",
                f"{p}__investment_state",
                f"{p}__recovery_progress",
                f"{p}__option_value",
                f"{p}__exercise_threshold_norm",
                f"{p}__beta_coefficient",
            ],
            initializes=[
                f"{p}__climate_stress",
                f"{p}__quality_degradation",
                f"{p}__investment_state",
                f"{p}__recovery_progress",
                f"{p}__option_value",
                f"{p}__exercise_threshold_norm",
                f"{p}__beta_coefficient",
            ],
        )

    def _compute_beta(self, mu: float, sigma: float, r: float) -> float:
        """
        Compute the beta coefficient from the Dixit-Pindyck real options formula.

        beta = (0.5 - mu/sigma^2) + sqrt((mu/sigma^2 - 0.5)^2 + 2*r/sigma^2)

        Beta > 1 always holds when r > 0.
        """
        sigma2 = sigma ** 2
        if sigma2 < 1e-10:
            sigma2 = 1e-10
        mu_over_s2 = mu / sigma2
        discriminant = (mu_over_s2 - 0.5) ** 2 + 2.0 * r / sigma2
        if discriminant < 0.0:
            discriminant = 0.0
        beta = (0.5 - mu_over_s2) + math.sqrt(discriminant)
        # beta must be > 1 for the real options formula to make sense
        beta = max(beta, 1.001)
        return beta

    def update(self, env: dict, agents: list, tick: int) -> dict:
        p = _THEORY_ID

        # --- Read current state ---
        climate_stress = env.get(f"{p}__climate_stress", 0.05)
        quality_degradation = env.get(f"{p}__quality_degradation", 0.0)
        investment_state = env.get(f"{p}__investment_state", 0.0)
        recovery_progress = env.get(f"{p}__recovery_progress", 0.0)

        # Clamp inputs
        climate_stress = max(0.0, min(1.0, climate_stress))
        quality_degradation = max(0.0, min(1.0, quality_degradation))
        investment_state = 1.0 if investment_state >= 0.5 else 0.0
        recovery_progress = max(0.0, min(1.0, recovery_progress))

        params = self.params

        # --- Compute beta (real options coefficient) ---
        beta = self._compute_beta(
            mu=params.drift,
            sigma=params.volatility,
            r=params.discount_rate,
        )
        # Normalize beta to [0, 1] for env output: typical range ~1 to ~10
        beta_norm = max(0.0, min(1.0, (beta - 1.0) / 9.0))

        # --- Investment threshold multiplier ---
        # threshold_multiplier = beta / (beta - 1)  -- always >= 1
        threshold_multiplier = beta / (beta - 1.0)

        # Normalized replant cost: I_norm in [0, 1]
        I_norm = max(0.0, min(1.0, params.replant_cost / params.max_replant_cost_norm))

        # Critical value V* (normalized): V* = threshold_multiplier * I_norm
        # This may exceed 1; we use it as a decision threshold in [0,1] space
        V_star = threshold_multiplier * I_norm
        # Normalize V* for output: clamp to [0, 1]
        V_star_norm = max(0.0, min(1.0, V_star))

        # --- Option value (value of waiting) ---
        # When quality_degradation is below V_star, waiting has value
        # option_value ~ max(0, V_star - quality_degradation) (option is in-the-money to wait)
        raw_option_value = max(0.0, V_star_norm - quality_degradation)
        option_value = max(0.0, min(1.0, raw_option_value))

        # --- Exercise / Investment decision ---
        # Invest when quality_degradation exceeds the optimal threshold V*
        # (i.e., the asset value of continuing without investment drops below the option value)
        already_invested = investment_state >= 0.5
        invest_now = False

        if not already_invested:
            # Compare quality degradation against exercise threshold (normalized V*)
            if quality_degradation >= min(V_star_norm, params.exercise_threshold):
                invest_now = True
                logger.info(
                    "tick=%d: Real options exercise triggered. "
                    "quality_degradation=%.3f >= threshold=%.3f (V*=%.3f)",
                    tick,
                    quality_degradation,
                    params.exercise_threshold,
                    V_star_norm,
                )

        # --- Update investment state ---
        if invest_now:
            new_investment_state = 1.0
            # Recovery starts; progress begins from current level
            new_recovery_progress = min(1.0, recovery_progress + params.recovery_rate)
        elif already_invested:
            new_investment_state = 1.0
            # Continue recovery over payback period
            new_recovery_progress = min(1.0, recovery_progress + params.recovery_rate)
        else:
            new_investment_state = 0.0
            new_recovery_progress = recovery_progress

        # --- Update climate stress ---
        # Climate stress increases each tick (drift + diffusion), reduced slightly by investment
        stress_increment = params.stress_diffusion * (1.0 - 0.3 * new_investment_state)
        new_climate_stress = climate_stress + stress_increment
        new_climate_stress = max(0.0, min(1.0, new_climate_stress))

        # --- Update quality degradation ---
        if already_invested or invest_now:
            # Post-investment: quality recovers proportional to recovery progress
            # Recovery reduces quality_degradation each tick
            recovery_amount = params.recovery_rate * (1.0 - recovery_progress * 0.5)
            # But climate stress still exerts some pressure (residual stress on new varietals)
            residual_stress_effect = (
                params.quality_stress_sensitivity * new_climate_stress * 0.1
            )
            new_quality_degradation = (
                quality_degradation - recovery_amount + residual_stress_effect
            )
        else:
            # No investment: quality degrades with climate stress
            stress_effect = params.quality_stress_sensitivity * new_climate_stress * params.stress_diffusion
            new_quality_degradation = quality_degradation + stress_effect

        new_quality_degradation = max(0.0, min(1.0, new_quality_degradation))

        return {
            f"{p}__climate_stress": new_climate_stress,
            f"{p}__quality_degradation": new_quality_degradation,
            f"{p}__investment_state": new_investment_state,
            f"{p}__recovery_progress": new_recovery_progress,
            f"{p}__option_value": option_value,
            f"{p}__exercise_threshold_norm": V_star_norm,
            f"{p}__beta_coefficient": beta_norm,
        }