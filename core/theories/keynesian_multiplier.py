"""
Keynesian Multiplier / Fiscal Shock Propagation

Multiplier formula:
  M = 1 / (1 - MPC*(1-t) + m)

GDP dynamics (geometric decay distributed lag):
  pending_shock accumulates from external inputs and trade disruption
  each tick: release = pending * decay_rate, remaining = pending * (1 - decay_rate)
  GDP_delta = released * M * GDP_SCALE

Okun's Law:
  delta_unemployment = okun_coefficient * delta_GDP_growth

Sanctions channel:
  if global__trade_volume < 0.5 baseline, generates negative fiscal shock
  fiscal_shock = (trade_volume - 0.5) * sanctions_exposure

Signed shock encoding:
  env stores fiscal_shock_pending as (0.5 + shock/2) to maintain [0,1] convention
  decode: shock = (encoded - 0.5) * 2
  Any external agent injecting a fiscal shock must use this encoding.

Env keys written:
    keynesian__gdp_normalized       0.5 = baseline, range spans ~+/-40% real GDP
    keynesian__fiscal_shock_pending encoded signed pending shock
    keynesian__multiplier           M / 3.0 (normalized; actual M = val * 3)
    keynesian__unemployment         unemployment rate; 0.05 = structural floor
    keynesian__mpc                  MPC parameter passthrough for observability

References:
  Keynes (1936); Blanchard & Perotti (2002) QJE; Ramey (2011) JEL
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

_GDP_BASELINE = 0.5
_GDP_SCALE    = 0.40  # normalized 1.0 unit = 40% above baseline real GDP


def _encode_shock(shock: float) -> float:
    """Encode signed shock [-1, 1] into [0, 1] env container."""
    return max(0.0, min(1.0, 0.5 + shock / 2.0))


def _decode_shock(encoded: float) -> float:
    """Decode [0, 1] env value back to signed shock."""
    return (encoded - 0.5) * 2.0


@register_theory("keynesian_multiplier")
class KeynesianMultiplier(TheoryBase):
    """
    Keynesian multiplier and fiscal shock propagation.

    Domains: macro, sanctions, economics
    Priority: 0 (runs before market theories; Porter reads keynesian__gdp_normalized)
    """

    DOMAINS = ["macro", "sanctions", "economics"]

    class Parameters(BaseModel):
        mpc: float = Field(
            default=0.72, ge=0.0, le=1.0,
            description="Marginal propensity to consume",
        )
        tax_rate: float = Field(
            default=0.28, ge=0.0, le=1.0,
            description="Effective tax rate",
        )
        import_propensity: float = Field(
            default=0.18, ge=0.0, le=1.0,
            description="Marginal propensity to import",
        )
        lag_ticks: int = Field(
            default=4, ge=1,
            description="Multiplier propagation lag in ticks (informational; geometric decay approximates)",
        )
        decay_rate: float = Field(
            default=0.35, ge=0.01, le=1.0,
            description="Geometric decay rate of pending shock per tick",
        )
        okun_coefficient: float = Field(
            default=-0.50, ge=-1.0, le=0.0,
            description="Unemployment sensitivity to GDP growth (Okun's Law)",
        )
        sanctions_exposure: float = Field(
            default=1.0, ge=0.0, le=2.0,
            description="Amplifier for trade disruption -> fiscal shock channel",
        )

    @property
    def state_variables(self) -> TheoryStateVariables:
        return TheoryStateVariables(
            reads=[
                "keynesian__fiscal_shock_pending",
                "keynesian__gdp_normalized",
                "keynesian__unemployment",
                "global__trade_volume",
            ],
            writes=[
                "keynesian__gdp_normalized",
                "keynesian__fiscal_shock_pending",
                "keynesian__multiplier",
                "keynesian__unemployment",
                "keynesian__mpc",
            ],
            initializes=[
                "keynesian__gdp_normalized",
                "keynesian__fiscal_shock_pending",
                "keynesian__multiplier",
                "keynesian__unemployment",
                "keynesian__mpc",
                "global__trade_volume",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        if "keynesian__gdp_normalized" not in env:
            inits["keynesian__gdp_normalized"] = 0.5        # baseline
        if "keynesian__unemployment" not in env:
            inits["keynesian__unemployment"] = 0.05         # structural floor
        if "keynesian__fiscal_shock_pending" not in env:
            inits["keynesian__fiscal_shock_pending"] = 0.5  # encoded zero shock
        if "global__trade_volume" not in env:
            inits["global__trade_volume"] = 0.5             # baseline
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        p = self.params

        # M = 1 / (1 - MPC*(1-t) + m)
        denom = 1.0 - p.mpc * (1.0 - p.tax_rate) + p.import_propensity
        denom = max(denom, 0.05)  # guard against degenerate params
        M = 1.0 / denom
        multiplier_norm = min(1.0, M / 3.0)

        # Decode pending shock
        shock_encoded = env.get("keynesian__fiscal_shock_pending", 0.5)
        pending_shock = _decode_shock(shock_encoded)

        # Sanctions / trade disruption channel
        trade_volume = env.get("global__trade_volume", 0.5)
        if trade_volume < 0.5:
            trade_shock = (trade_volume - 0.5) * p.sanctions_exposure
            pending_shock += trade_shock

        # Release this tick's portion
        released_shock = pending_shock * p.decay_rate
        remaining_shock = pending_shock * (1.0 - p.decay_rate)

        # GDP impact
        gdp_current = env.get("keynesian__gdp_normalized", 0.5)
        gdp_delta = released_shock * M * _GDP_SCALE
        gdp_new = max(0.0, min(1.0, gdp_current + gdp_delta))

        # Okun's Law
        gdp_growth = gdp_new - gdp_current
        unemployment_current = env.get("keynesian__unemployment", 0.05)
        unemployment_delta = p.okun_coefficient * gdp_growth * 2.0
        unemployment_new = max(0.0, min(1.0, unemployment_current + unemployment_delta))

        logger.debug(
            "Keynesian tick=%d: M=%.2f shock=%.3f->%.3f GDP=%.3f->%.3f unemp=%.3f",
            tick, M, pending_shock, remaining_shock, gdp_current, gdp_new, unemployment_new,
        )

        return {
            "keynesian__gdp_normalized":       gdp_new,
            "keynesian__fiscal_shock_pending": _encode_shock(remaining_shock),
            "keynesian__multiplier":           multiplier_norm,
            "keynesian__unemployment":         unemployment_new,
            "keynesian__mpc":                  p.mpc,
        }
