"""
Stochastic Smoke Taint Crop Disruption Model
=============================================

This module implements a stochastic acute crop quality loss model based on wildfire smoke taint
in premium wine production, as described in:

    Anonymous (2020). Stochastic Crop Disruption: Wildfire Smoke Taint and Acute Vintage Loss
    in Premium Wine. arXiv:2008.01035.

Model Description
-----------------
Wildfire smoke taint (driven by guaiacol and 4-methylguaiacol compounds) can render wine
unviable above a contamination threshold. The model captures:

1. **Smoke Event Probability**: Each season, a smoke event occurs with Poisson-derived probability:
       p(t) = min(1, smoke_prob_base + smoke_prob_rate * tick)
   reflecting the observed trend from p≈0.05 (pre-2010) to p≈0.15 (2030s).

2. **Taint Severity**: When a smoke event occurs, severity is drawn from a Beta distribution
   parameterized by taint_severity_mean and taint_severity_concentration:
       severity ~ Beta(alpha, beta)
   where alpha = mean * concentration, beta = (1 - mean) * concentration.

3. **Revenue Loss**: Normalized revenue loss:
       R_loss_norm = severity * crop_exposure
   where crop_exposure accounts for the fraction of vineyard acreage exposed.

4. **Cumulative Impact**: Tracks running average of smoke events and crop loss over time.

Env Keys (all prefixed with "smoke_taint_crop_disruption__")
------------------------------------------------------------
- smoke_event_occurred    : [0,1] binary indicator of smoke event this tick
- taint_severity          : [0,1] severity of smoke taint (0=none, 1=total loss)
- revenue_loss_fraction   : [0,1] normalized revenue loss fraction this tick
- cumulative_loss_index   : [0,1] running average of revenue losses
- smoke_probability       : [0,1] current per-tick smoke event probability
- crop_viability          : [0,1] remaining crop viability after taint (1=full, 0=total write-off)

Citation
--------
Anonymous (2020). Stochastic Crop Disruption: Wildfire Smoke Taint and Acute Vintage Loss
in Premium Wine. arXiv:2008.01035. https://arxiv.org/abs/2008.01035
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from core.theories import register_theory
from core.theories.base import TheoryBase, TheoryStateVariables

if TYPE_CHECKING:
    from core.agents.base import BDIAgent

logger = logging.getLogger(__name__)


@register_theory("smoke_taint_crop_disruption")
class SmokeTaintCropDisruption(TheoryBase):
    """
    Stochastic Smoke Taint Crop Disruption model for premium wine production.

    Models the increasing frequency and severity of wildfire smoke events and
    their economic impact on vineyard crop viability and revenue.
    """

    DOMAINS = ['agriculture', 'climate', 'ecology', 'market', 'supply_chain', 'sustainability', 'viticulture']

    class Parameters(BaseModel):
        smoke_prob_base: float = Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description="Base per-season smoke event probability (pre-2010 baseline ≈ 0.05)",
        )
        smoke_prob_rate: float = Field(
            default=0.005,
            ge=0.0,
            le=0.1,
            description="Annual increase rate in smoke probability (trend toward 0.15 by 2030s)",
        )
        taint_severity_mean: float = Field(
            default=0.6,
            ge=0.01,
            le=0.99,
            description="Mean severity of smoke taint when event occurs (Beta distribution mean)",
        )
        taint_severity_concentration: float = Field(
            default=4.0,
            ge=0.5,
            le=50.0,
            description="Concentration parameter for Beta distribution (higher = less variance)",
        )
        crop_exposure_fraction: float = Field(
            default=0.75,
            ge=0.0,
            le=1.0,
            description="Fraction of total vineyard acreage exposed to smoke events",
        )
        revenue_per_acre_norm: float = Field(
            default=8000.0,
            ge=0.0,
            le=100000.0,
            description="Revenue per acre (USD) used for loss scaling reference; 8000 typical premium",
        )
        cumulative_loss_decay: float = Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description="Exponential decay rate for cumulative loss index (0=no decay, 1=full reset)",
        )
        taint_threshold: float = Field(
            default=0.5,
            ge=0.0,
            le=1.0,
            description="Severity threshold above which wine is deemed commercially unviable",
        )
        random_seed: int = Field(
            default=-1,
            ge=-1,
            le=2**31 - 1,
            description="RNG seed for reproducibility; -1 means non-deterministic",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "smoke_taint_crop_disruption__smoke_event_occurred",
                "smoke_taint_crop_disruption__cumulative_loss_index",
                "smoke_taint_crop_disruption__smoke_probability",
            ],
            writes=[
                "smoke_taint_crop_disruption__smoke_event_occurred",
                "smoke_taint_crop_disruption__taint_severity",
                "smoke_taint_crop_disruption__revenue_loss_fraction",
                "smoke_taint_crop_disruption__cumulative_loss_index",
                "smoke_taint_crop_disruption__smoke_probability",
                "smoke_taint_crop_disruption__crop_viability",
            ],
            initializes=[
                "smoke_taint_crop_disruption__smoke_event_occurred",
                "smoke_taint_crop_disruption__taint_severity",
                "smoke_taint_crop_disruption__revenue_loss_fraction",
                "smoke_taint_crop_disruption__cumulative_loss_index",
                "smoke_taint_crop_disruption__smoke_probability",
                "smoke_taint_crop_disruption__crop_viability",
            ],
        )

    def _beta_sample(self, mean: float, concentration: float, rng: random.Random) -> float:
        """
        Sample from a Beta(alpha, beta) distribution using the mean and concentration
        parameterization: alpha = mean * concentration, beta = (1 - mean) * concentration.

        Falls back to the mean if parameters are degenerate.
        """
        alpha = mean * concentration
        beta_param = (1.0 - mean) * concentration
        if alpha <= 0.0 or beta_param <= 0.0:
            return mean
        try:
            return rng.betavariate(alpha, beta_param)
        except Exception:
            logger.warning("Beta sampling failed; returning mean value.")
            return mean

    def _poisson_event(self, probability: float, rng: random.Random) -> bool:
        """
        Determine whether a Poisson event occurs in a single tick given per-tick probability p.
        Uses the zero-count probability of Poisson: P(event) = 1 - exp(-p).
        For small p, this ≈ p.
        """
        poisson_prob = 1.0 - math.exp(-probability)
        return rng.random() < poisson_prob

    def update(self, env: dict, agents: list, tick: int) -> dict:
        """
        Update the smoke taint crop disruption state for one tick (season).

        Steps:
        1. Compute current smoke event probability (trending upward over time).
        2. Draw stochastic smoke event occurrence via Poisson process.
        3. If event occurs, sample taint severity from Beta distribution.
        4. Compute normalized revenue loss fraction.
        5. Update cumulative loss index via exponential moving average.
        6. Compute crop viability as complement of effective loss.

        Returns
        -------
        dict[str, float]
            Updated env variables, all in [0, 1].
        """
        p = self.params

        # Initialize RNG
        if p.random_seed >= 0:
            rng = random.Random(p.random_seed + tick)
        else:
            rng = random.Random()

        # --- Step 1: Compute current smoke probability ---
        # p(t) = min(1, smoke_prob_base + smoke_prob_rate * tick)
        smoke_prob = min(1.0, p.smoke_prob_base + p.smoke_prob_rate * tick)

        # --- Step 2: Determine smoke event occurrence ---
        smoke_occurred = self._poisson_event(smoke_prob, rng)
        smoke_event_val = 1.0 if smoke_occurred else 0.0

        # --- Step 3: Sample taint severity if event occurred ---
        if smoke_occurred:
            severity = self._beta_sample(
                p.taint_severity_mean, p.taint_severity_concentration, rng
            )
            severity = max(0.0, min(1.0, severity))
        else:
            severity = 0.0

        # --- Step 4: Compute revenue loss fraction ---
        # R_loss_norm = severity * crop_exposure_fraction
        # Accounts for only exposed portion of vineyard
        revenue_loss = severity * p.crop_exposure_fraction
        revenue_loss = max(0.0, min(1.0, revenue_loss))

        # --- Step 5: Update cumulative loss index ---
        # Exponential moving average: cumulative = (1 - decay) * previous + decay * current_loss
        prev_cumulative = env.get("smoke_taint_crop_disruption__cumulative_loss_index", 0.0)
        prev_cumulative = max(0.0, min(1.0, prev_cumulative))
        cumulative_loss = (1.0 - p.cumulative_loss_decay) * prev_cumulative + p.cumulative_loss_decay * revenue_loss
        cumulative_loss = max(0.0, min(1.0, cumulative_loss))

        # --- Step 6: Compute crop viability ---
        # If severity exceeds taint_threshold, crop is commercially unviable (viability = 0)
        # Otherwise, viability = 1 - severity (partial loss)
        if smoke_occurred and severity >= p.taint_threshold:
            # Above threshold: full write-off for exposed portion
            crop_viability = max(0.0, 1.0 - p.crop_exposure_fraction)
        else:
            crop_viability = max(0.0, 1.0 - revenue_loss)

        crop_viability = max(0.0, min(1.0, crop_viability))

        logger.debug(
            "tick=%d smoke_prob=%.4f smoke_occurred=%s severity=%.4f "
            "revenue_loss=%.4f cumulative=%.4f crop_viability=%.4f",
            tick, smoke_prob, smoke_occurred, severity,
            revenue_loss, cumulative_loss, crop_viability,
        )

        return {
            "smoke_taint_crop_disruption__smoke_event_occurred": smoke_event_val,
            "smoke_taint_crop_disruption__taint_severity": severity,
            "smoke_taint_crop_disruption__revenue_loss_fraction": revenue_loss,
            "smoke_taint_crop_disruption__cumulative_loss_index": cumulative_loss,
            "smoke_taint_crop_disruption__smoke_probability": smoke_prob,
            "smoke_taint_crop_disruption__crop_viability": crop_viability,
        }