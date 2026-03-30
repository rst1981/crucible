"""
Bordeaux Wine Vintage Quality Model
=====================================
Implements the hedonic regression model from:
    Ashenfelter, O. (1989). Bordeaux Wine Vintage Quality and the Weather.
    Chance, 2(3), 7-14. https://www.jstor.org/stable/2555489

Model Equations
---------------
ln(price) = alpha + beta_temp * avg_summer_temp
           + beta_rain_winter * winter_rain
           + beta_rain_harvest * harvest_rain
           + beta_age * age

Quality score:
    Q = base_quality * exp(temp_effect + rain_effect)
    Q *= max(0, 1 - smoke_taint)   # taint modifier

Empirical coefficients (from paper):
    beta_temp         = 0.616
    beta_rain_winter  = 0.00117
    beta_rain_harvest = -0.00386

Environment Keys (all normalized to [0, 1])
-------------------------------------------
Reads:
    bordeaux_wine_quality__summer_temp      : normalized avg summer temperature
    bordeaux_wine_quality__winter_rain      : normalized winter rainfall
    bordeaux_wine_quality__harvest_rain     : normalized harvest rainfall
    bordeaux_wine_quality__vine_age         : normalized vine / vintage age
    bordeaux_wine_quality__smoke_taint      : smoke taint level (0=none, 1=full)

Writes / Initializes:
    bordeaux_wine_quality__quality_score    : overall quality [0, 1]
    bordeaux_wine_quality__price_index      : relative price index [0, 1]
    bordeaux_wine_quality__climate_stress   : composite climate stress [0, 1]
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


@register_theory("bordeaux_wine_quality")
class BordeauxWineQuality(TheoryBase):
    """Hedonic regression model linking Bordeaux wine quality to climate variables."""

    DOMAINS = ['agriculture', 'consumer_behavior', 'ecology', 'market', 'sustainability', 'viticulture']

    class Parameters(BaseModel):
        temp_sensitivity: float = Field(
            default=0.616,
            ge=0.0,
            le=5.0,
            description=(
                "Coefficient on average summer temperature in the log-price regression "
                "(beta_temp from Ashenfelter 1989). Higher values amplify temperature effects."
            ),
        )
        winter_rain_coeff: float = Field(
            default=0.00117,
            ge=0.0,
            le=0.1,
            description=(
                "Coefficient on winter rainfall (mm) in the log-price regression "
                "(beta_rain_winter from Ashenfelter 1989). Winter rain benefits the vine."
            ),
        )
        harvest_rain_penalty: float = Field(
            default=0.00386,
            ge=0.0,
            le=0.1,
            description=(
                "Absolute value of the coefficient on harvest rainfall in the log-price "
                "regression (beta_rain_harvest from Ashenfelter 1989). Rain at harvest "
                "hurts quality; applied as a negative effect."
            ),
        )
        age_decay: float = Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description=(
                "Rate at which older vintages lose quality in the simplified model. "
                "Applied as an exponential decay on the age dimension."
            ),
        )
        base_quality: float = Field(
            default=0.5,
            ge=0.0,
            le=1.0,
            description=(
                "Baseline quality index before climate adjustments. "
                "Corresponds to alpha (intercept) in the regression, normalized to [0, 1]."
            ),
        )
        # Scaling factors to map normalized env inputs to realistic physical units
        temp_scale: float = Field(
            default=20.0,
            ge=1.0,
            le=50.0,
            description=(
                "Multiplier to convert normalized summer temperature [0, 1] into "
                "degrees Celsius deviation from a baseline (e.g., 0→0°C, 1→20°C)."
            ),
        )
        winter_rain_scale: float = Field(
            default=600.0,
            ge=1.0,
            le=2000.0,
            description=(
                "Multiplier to convert normalized winter rain [0, 1] into millimetres "
                "(e.g., 0→0 mm, 1→600 mm)."
            ),
        )
        harvest_rain_scale: float = Field(
            default=200.0,
            ge=1.0,
            le=1000.0,
            description=(
                "Multiplier to convert normalized harvest rain [0, 1] into millimetres "
                "(e.g., 0→0 mm, 1→200 mm)."
            ),
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "bordeaux_wine_quality__summer_temp",
                "bordeaux_wine_quality__winter_rain",
                "bordeaux_wine_quality__harvest_rain",
                "bordeaux_wine_quality__vine_age",
                "bordeaux_wine_quality__smoke_taint",
            ],
            writes=[
                "bordeaux_wine_quality__quality_score",
                "bordeaux_wine_quality__price_index",
                "bordeaux_wine_quality__climate_stress",
            ],
            initializes=[
                "bordeaux_wine_quality__summer_temp",
                "bordeaux_wine_quality__winter_rain",
                "bordeaux_wine_quality__harvest_rain",
                "bordeaux_wine_quality__vine_age",
                "bordeaux_wine_quality__smoke_taint",
                "bordeaux_wine_quality__quality_score",
                "bordeaux_wine_quality__price_index",
                "bordeaux_wine_quality__climate_stress",
            ],
        )

    def update(self, env: dict, agents: list["BDIAgent"], tick: int) -> dict[str, float]:
        p = self.params  # type: ignore[attr-defined]

        # -----------------------------------------------------------------
        # 1. Read normalized environment values
        # -----------------------------------------------------------------
        norm_temp = float(env.get("bordeaux_wine_quality__summer_temp", 0.5))
        norm_winter_rain = float(env.get("bordeaux_wine_quality__winter_rain", 0.5))
        norm_harvest_rain = float(env.get("bordeaux_wine_quality__harvest_rain", 0.2))
        norm_age = float(env.get("bordeaux_wine_quality__vine_age", 0.1))
        smoke_taint = float(env.get("bordeaux_wine_quality__smoke_taint", 0.0))

        # Clamp inputs to [0, 1]
        norm_temp = max(0.0, min(1.0, norm_temp))
        norm_winter_rain = max(0.0, min(1.0, norm_winter_rain))
        norm_harvest_rain = max(0.0, min(1.0, norm_harvest_rain))
        norm_age = max(0.0, min(1.0, norm_age))
        smoke_taint = max(0.0, min(1.0, smoke_taint))

        # -----------------------------------------------------------------
        # 2. Convert normalized inputs to physical-unit proxies
        # -----------------------------------------------------------------
        summer_temp_c = norm_temp * p.temp_scale           # °C deviation
        winter_rain_mm = norm_winter_rain * p.winter_rain_scale  # mm
        harvest_rain_mm = norm_harvest_rain * p.harvest_rain_scale  # mm

        # -----------------------------------------------------------------
        # 3. Compute regression components (Ashenfelter 1989)
        #    ln(price) ~ beta_temp*T + beta_winter*W + beta_harvest*H + beta_age*age
        # -----------------------------------------------------------------
        temp_effect = p.temp_sensitivity * summer_temp_c
        winter_rain_effect = p.winter_rain_coeff * winter_rain_mm
        harvest_rain_effect = -p.harvest_rain_penalty * harvest_rain_mm

        # Age effect: older vintages (higher norm_age) decay in quality
        age_effect = -p.age_decay * norm_age

        # Combined log-scale effect
        log_effect = temp_effect + winter_rain_effect + harvest_rain_effect + age_effect

        logger.debug(
            "tick=%d temp_eff=%.4f winter_eff=%.4f harvest_eff=%.4f age_eff=%.4f",
            tick, temp_effect, winter_rain_effect, harvest_rain_effect, age_effect,
        )

        # -----------------------------------------------------------------
        # 4. Quality score: Q = base * exp(log_effect) * taint_modifier
        # -----------------------------------------------------------------
        quality_raw = p.base_quality * math.exp(log_effect)

        # Smoke taint modifier: multiplicative penalty
        taint_modifier = max(0.0, 1.0 - smoke_taint)
        quality_with_taint = quality_raw * taint_modifier

        # Normalize quality to [0, 1] using a logistic squash
        # Centre around base_quality so that no effect → ~base_quality output
        quality_score = max(0.0, min(1.0, quality_with_taint))

        # -----------------------------------------------------------------
        # 5. Price index: proportional to quality, monotone in quality_score
        #    ln(price_index) ~ log_effect  →  price_index scaled to [0, 1]
        # -----------------------------------------------------------------
        # Use a sigmoid mapping centred on the neutral point (log_effect = 0)
        price_index = 1.0 / (1.0 + math.exp(-log_effect))
        # Apply taint to price as well
        price_index = max(0.0, min(1.0, price_index * taint_modifier))

        # -----------------------------------------------------------------
        # 6. Climate stress: composite measure of adverse conditions
        #    High harvest rain + low summer temp + high taint → high stress
        # -----------------------------------------------------------------
        # Stress components (each in [0, 1]):
        heat_deficit = 1.0 - norm_temp          # low temp = stress
        excess_harvest_rain = norm_harvest_rain  # high harvest rain = stress
        taint_stress = smoke_taint              # direct taint stress
        drought_stress = max(0.0, 0.5 - norm_winter_rain)  # too little winter rain

        climate_stress = max(0.0, min(1.0, (
            0.35 * heat_deficit
            + 0.35 * excess_harvest_rain
            + 0.20 * taint_stress
            + 0.10 * drought_stress
        )))

        logger.debug(
            "tick=%d quality=%.4f price=%.4f stress=%.4f",
            tick, quality_score, price_index, climate_stress,
        )

        return {
            "bordeaux_wine_quality__quality_score": quality_score,
            "bordeaux_wine_quality__price_index": price_index,
            "bordeaux_wine_quality__climate_stress": climate_stress,
        }