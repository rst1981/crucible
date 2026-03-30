"""
Grapevine GDD Phenology & Quality Model
========================================

This module implements the European grapevine (Vitis vinifera L.) thermal accumulation
model based on Growing Degree Days (GDD) above a base temperature of 10°C.

Model Description:
------------------
Growing Degree Days (GDD) accumulate daily when mean temperature exceeds the base
temperature (T_base = 10°C). Phenological stages (bloom, veraison, harvest) are
triggered at specific GDD thresholds. Winkler (1974) defines five climate regions
by cumulative seasonal GDD.

Core Equations:
---------------
- dGDD/dt = max(0, T_daily - T_base)
  where T_daily is mean daily temperature in °C and T_base = 10°C

- Quality: Q = exp(-0.5 * ((GDD - GDD_opt) / sigma)^2)
  Gaussian quality function peaks at GDD_opt (~2000 GDD) and degrades beyond 2400 GDD

- Temperature forcing: T_effective = T_base_normalized + warming_trend * tick / ticks_per_year

Winkler Regions (cumulative seasonal GDD):
  Region I:  < 1390 GDD
  Region II: 1390–1667 GDD
  Region III:1667–1945 GDD
  Region IV: 1945–2220 GDD
  Region V:  > 2220 GDD

Optimal quality for Bordeaux varietals: 1800–2200 GDD; degradation above 2400 GDD.
Walla Walla AVA GDD projected to rise from ~2100 to ~2500–2800 by 2040s.

Environment Keys:
-----------------
Reads:
  grapevine_gdd_phenology__temperature    : normalized mean daily temperature [0,1]
  grapevine_gdd_phenology__season_fraction: fraction of growing season elapsed [0,1]

Writes/Initializes:
  grapevine_gdd_phenology__gdd_normalized   : accumulated GDD normalized to max season GDD [0,1]
  grapevine_gdd_phenology__quality          : wine quality index Q in [0,1]
  grapevine_gdd_phenology__bloom_reached    : 0 or 1, whether bloom threshold crossed
  grapevine_gdd_phenology__veraison_reached : 0 or 1, whether veraison threshold crossed
  grapevine_gdd_phenology__harvest_reached  : 0 or 1, whether harvest threshold crossed
  grapevine_gdd_phenology__winkler_region   : Winkler region index normalized to [0,1]
  grapevine_gdd_phenology__temperature      : updated temperature with warming trend
  grapevine_gdd_phenology__season_fraction  : updated season fraction

Citation:
---------
Jones & Davis (2000). Climate influences on grapevine phenology, grape composition,
and wine production and quality for Bordeaux, France.
American Journal of Enology and Viticulture.
https://arxiv.org/abs/2510.09702
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

# GDD thresholds for phenological stages (in degree-days)
_GDD_BLOOM = 150.0
_GDD_VERAISON = 1000.0
_GDD_HARVEST = 1500.0

# Winkler region boundaries (GDD)
_WINKLER_BOUNDS = [1390.0, 1667.0, 1945.0, 2220.0]  # 5 regions

# Temperature normalization: map °C range [-5, 45] -> [0, 1]
_T_MIN_C = -5.0
_T_MAX_C = 45.0
_T_RANGE_C = _T_MAX_C - _T_MIN_C  # 50 °C span


def _norm_to_celsius(normalized: float) -> float:
    """Convert normalized [0,1] temperature to Celsius."""
    return _T_MIN_C + normalized * _T_RANGE_C


def _celsius_to_norm(celsius: float) -> float:
    """Convert Celsius to normalized [0,1]."""
    return max(0.0, min(1.0, (celsius - _T_MIN_C) / _T_RANGE_C))


@register_theory("grapevine_gdd_phenology")
class GrapevineGDDPhenology(TheoryBase):
    """
    Grapevine GDD Phenology & Quality Model implementing the Jones & Davis (2000)
    thermal accumulation framework for Vitis vinifera phenological stage prediction
    and wine quality estimation.
    """

    DOMAINS = ['agriculture', 'climate', 'development', 'ecology', 'energy', 'sustainability', 'viticulture']

    class Parameters(BaseModel):
        t_base: float = Field(
            default=10.0,
            ge=0.0,
            le=20.0,
            description="Base temperature for GDD accumulation in °C (standard = 10°C)",
        )
        gdd_optimal: float = Field(
            default=2000.0,
            ge=500.0,
            le=4000.0,
            description="Optimal cumulative GDD for peak wine quality (Bordeaux ~2000)",
        )
        gdd_sigma: float = Field(
            default=300.0,
            ge=50.0,
            le=1000.0,
            description="Standard deviation of Gaussian quality function in GDD units",
        )
        annual_warming_rate: float = Field(
            default=0.04,
            ge=0.0,
            le=0.5,
            description="Annual temperature increase rate in °C per year (climate change forcing)",
        )
        ticks_per_year: int = Field(
            default=365,
            ge=1,
            le=3650,
            description="Number of simulation ticks representing one calendar year",
        )
        max_season_gdd: float = Field(
            default=3500.0,
            ge=500.0,
            le=6000.0,
            description="Maximum expected seasonal GDD for normalization purposes",
        )
        season_length_days: int = Field(
            default=200,
            ge=30,
            le=365,
            description="Length of the growing season in days",
        )
        baseline_temperature_c: float = Field(
            default=18.0,
            ge=5.0,
            le=35.0,
            description="Baseline mean daily growing-season temperature in °C",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        pfx = "grapevine_gdd_phenology"
        reads = [
            f"{pfx}__temperature",
            f"{pfx}__season_fraction",
            f"{pfx}__gdd_normalized",
        ]
        writes = [
            f"{pfx}__gdd_normalized",
            f"{pfx}__quality",
            f"{pfx}__bloom_reached",
            f"{pfx}__veraison_reached",
            f"{pfx}__harvest_reached",
            f"{pfx}__winkler_region",
            f"{pfx}__temperature",
            f"{pfx}__season_fraction",
        ]
        initializes = [
            f"{pfx}__gdd_normalized",
            f"{pfx}__quality",
            f"{pfx}__bloom_reached",
            f"{pfx}__veraison_reached",
            f"{pfx}__harvest_reached",
            f"{pfx}__winkler_region",
            f"{pfx}__temperature",
            f"{pfx}__season_fraction",
        ]
        return TheoryStateVariables(reads=reads, writes=writes, initializes=initializes)

    def update(self, env: dict, agents: list, tick: int) -> dict:
        pfx = "grapevine_gdd_phenology"
        p = self.params

        # ------------------------------------------------------------------
        # 1. Determine current year and day-within-year
        # ------------------------------------------------------------------
        year_float = tick / p.ticks_per_year
        day_of_year = tick % p.ticks_per_year  # 0-indexed day within year

        # Season fraction: fraction of growing season elapsed (0 → 1)
        # If ticks_per_year == season_length_days, every day is in season.
        season_fraction_env = env.get(f"{pfx}__season_fraction", None)
        if season_fraction_env is not None:
            season_fraction = float(season_fraction_env)
        else:
            # Compute from tick position within year
            season_fraction = min(1.0, day_of_year / max(1, p.ticks_per_year))

        # ------------------------------------------------------------------
        # 2. Compute daily temperature with warming trend
        # ------------------------------------------------------------------
        temp_norm_env = env.get(f"{pfx}__temperature", None)
        if temp_norm_env is not None:
            # Use provided temperature but overlay the warming trend
            t_daily_c = _norm_to_celsius(float(temp_norm_env))
            # Apply cumulative warming on top
            t_daily_c += p.annual_warming_rate * year_float
        else:
            # Fall back to baseline + warming trend
            t_daily_c = p.baseline_temperature_c + p.annual_warming_rate * year_float

        # Clamp to realistic range
        t_daily_c = max(_T_MIN_C, min(_T_MAX_C, t_daily_c))
        temp_norm_new = _celsius_to_norm(t_daily_c)

        # ------------------------------------------------------------------
        # 3. GDD increment for today
        # ------------------------------------------------------------------
        delta_gdd = max(0.0, t_daily_c - p.t_base)

        # ------------------------------------------------------------------
        # 4. Accumulate GDD over the season
        # ------------------------------------------------------------------
        # Retrieve currently accumulated GDD (denormalized)
        gdd_norm_prev = env.get(f"{pfx}__gdd_normalized", 0.0)
        gdd_prev = float(gdd_norm_prev) * p.max_season_gdd

        # Reset at start of new year (season_fraction near 0 and day early in year)
        if day_of_year == 0:
            gdd_prev = 0.0
            logger.debug("GDD reset at tick %d (new year start)", tick)

        gdd_current = gdd_prev + delta_gdd
        gdd_current = max(0.0, gdd_current)  # non-negative

        # Normalize GDD to [0, 1]
        gdd_normalized = min(1.0, gdd_current / p.max_season_gdd)

        # ------------------------------------------------------------------
        # 5. Quality function: Gaussian centered on GDD_optimal
        # ------------------------------------------------------------------
        # Q = exp(-0.5 * ((GDD - GDD_opt) / sigma)^2)
        z = (gdd_current - p.gdd_optimal) / p.gdd_sigma
        quality = math.exp(-0.5 * z * z)
        quality = max(0.0, min(1.0, quality))

        # ------------------------------------------------------------------
        # 6. Phenological stage indicators (soft threshold using sigmoid)
        # ------------------------------------------------------------------
        def _soft_threshold(gdd: float, threshold: float, sharpness: float = 0.02) -> float:
            """Smooth step from 0→1 as GDD crosses threshold."""
            return 1.0 / (1.0 + math.exp(-sharpness * (gdd - threshold)))

        bloom_reached = _soft_threshold(gdd_current, _GDD_BLOOM)
        veraison_reached = _soft_threshold(gdd_current, _GDD_VERAISON)
        harvest_reached = _soft_threshold(gdd_current, _GDD_HARVEST)

        # Clamp to [0, 1]
        bloom_reached = max(0.0, min(1.0, bloom_reached))
        veraison_reached = max(0.0, min(1.0, veraison_reached))
        harvest_reached = max(0.0, min(1.0, harvest_reached))

        # ------------------------------------------------------------------
        # 7. Winkler region (normalized 0→1 mapping 5 regions)
        # ------------------------------------------------------------------
        # Regions: I (<1390), II (1390-1667), III (1667-1945), IV (1945-2220), V (>2220)
        # Map region index 1-5 → normalized 0.1, 0.3, 0.5, 0.7, 0.9
        winkler_normalized_map = [0.1, 0.3, 0.5, 0.7, 0.9]
        if gdd_current < _WINKLER_BOUNDS[0]:
            winkler_region_norm = winkler_normalized_map[0]
        elif gdd_current < _WINKLER_BOUNDS[1]:
            winkler_region_norm = winkler_normalized_map[1]
        elif gdd_current < _WINKLER_BOUNDS[2]:
            winkler_region_norm = winkler_normalized_map[2]
        elif gdd_current < _WINKLER_BOUNDS[3]:
            winkler_region_norm = winkler_normalized_map[3]
        else:
            winkler_region_norm = winkler_normalized_map[4]

        # ------------------------------------------------------------------
        # 8. Update season fraction
        # ------------------------------------------------------------------
        # Advance by one tick as fraction of ticks_per_year
        new_season_fraction = min(1.0, season_fraction + 1.0 / p.ticks_per_year)

        # ------------------------------------------------------------------
        # 9. Log summary periodically
        # ------------------------------------------------------------------
        if tick % max(1, p.ticks_per_year // 4) == 0:
            logger.info(
                "tick=%d year=%.2f T=%.1f°C GDD=%.0f Q=%.3f Winkler=%.1f",
                tick, year_float, t_daily_c, gdd_current, quality,
                winkler_region_norm * 5,
            )

        return {
            f"{pfx}__gdd_normalized": max(0.0, min(1.0, gdd_normalized)),
            f"{pfx}__quality": max(0.0, min(1.0, quality)),
            f"{pfx}__bloom_reached": max(0.0, min(1.0, bloom_reached)),
            f"{pfx}__veraison_reached": max(0.0, min(1.0, veraison_reached)),
            f"{pfx}__harvest_reached": max(0.0, min(1.0, harvest_reached)),
            f"{pfx}__winkler_region": max(0.0, min(1.0, winkler_region_norm)),
            f"{pfx}__temperature": max(0.0, min(1.0, temp_norm_new)),
            f"{pfx}__season_fraction": max(0.0, min(1.0, new_season_fraction)),
        }