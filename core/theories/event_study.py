"""
Event Study / CAPM Abnormal Return (MacKinlay 1997)

Decomposes a security's return around an event into:
    1. Expected return (CAPM baseline): E[R] = R_f + β × (R_m - R_f)
    2. Abnormal return (AR): AR = R_actual - E[R]
    3. Cumulative abnormal return (CAR): CAR = Σ AR_t over event window

AR isolates the pure event-driven component of a price move from the
market-wide (systematic) component. CAR aggregates the signal-to-noise
ratio across the event window.

Interpretation:
    AR > 0: security outperformed CAPM expectation → positive event surprise
    AR < 0: underperformed → market penalizes the event
    |CAR| significance tested against estimation-window σ (not implemented here;
    CalendarTime or cross-sectional methods extend this module for inference)

Event windows:
    Pre-event window: baseline period before event (not simulated; supply via
                      estimation via beta_market parameter)
    Event window: [-event_window_before, +event_window_after] ticks around event
    Post-event window: drift / leakage

CAPM parameter sourcing:
    beta_market: pre-estimated from historical returns (e.g. EL beta ≈ 1.15)
    risk_free_rate: annualized (e.g. T-bill yield). Scaled per tick_unit.
    global__market_return: set by SIR/Keynesian or external shock — the market's
        return in this tick (normalized: 0.5 = 0%, scale ±40%).

Env keys read:
    global__market_return       [0,1] market portfolio return this tick (0.5 = 0%)
    {event_id}__actual_return   [0,1] security's actual return this tick (0.5 = 0%)
    {event_id}__event_active    1.0 if within event window, 0.0 otherwise

Env keys written:
    {event_id}__expected_return     [0,1] CAPM-predicted return (0.5 = 0%)
    {event_id}__abnormal_return     [0,1] AR = actual - expected (0.5 = 0%)
    {event_id}__cumulative_ar       [0,1] CAR since tick 0 (0.5 = 0%)

All return values use: normalized = 0.5 + raw_return / RETURN_SCALE
where RETURN_SCALE = 0.40 (±40% range).

Use event_id to decompose multiple simultaneous events.

References:
    MacKinlay (1997). Event Studies in Economics and Finance.
        Journal of Economic Literature 35(1): 13–39.
    Fama, Fisher, Jensen & Roll (1969). The adjustment of stock prices to new information.
        International Economic Review 10(1): 1–21.
    Brown & Warner (1985). Using daily stock returns: The case of event studies.
        Journal of Financial Economics 14(1): 3–31.
    Binder (1998). The event study methodology since 1969.
        Review of Quantitative Finance and Accounting 11(2): 111–137.
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

# Return normalization scale: raw_return in ±40% maps to [0, 1]
_RETURN_SCALE = 0.40


def _raw_return(normalized: float) -> float:
    """Convert normalized [0,1] env value to raw decimal return."""
    return (normalized - 0.5) * _RETURN_SCALE


def _norm_return(raw: float) -> float:
    """Convert raw decimal return to normalized [0,1] env value."""
    return max(0.0, min(1.0, 0.5 + raw / _RETURN_SCALE))


@register_theory("event_study")
class EventStudy(TheoryBase):
    """
    MacKinlay (1997) CAPM-based Event Study.

    Domains: corporate_finance, equity, behavioral_finance, policy_analysis
    Priority: 4 (reads market_return from SIR/Keynesian; actual_return from shocks)

    Use event_id to analyze multiple events in parallel (e.g. Puig announcement,
    Iran war onset, tariff guidance).
    """

    DOMAINS = ["corporate_finance", "equity", "behavioral_finance", "policy_analysis"]

    class Parameters(BaseModel):
        beta_market: float = Field(
            default=1.0, ge=-1.0, le=5.0,
            description=(
                "Security's market beta from estimation window. "
                "β > 1 = amplifies market moves (high-beta consumer discretionary). "
                "β < 1 = defensive. EL historical β ≈ 1.15."
            ),
        )
        risk_free_rate: float = Field(
            default=0.045, ge=0.0, le=0.20,
            description=(
                "Annualized risk-free rate (e.g. T-bill yield). "
                "Scaled by dt internally. Example: 0.045 = 4.5%% annual."
            ),
        )
        alpha: float = Field(
            default=0.0, ge=-0.10, le=0.10,
            description=(
                "Jensen's alpha: annualized abnormal return unexplained by beta. "
                "Estimated from pre-event window. Typically near 0 for efficient markets."
            ),
        )
        tick_unit: str = Field(
            default="day",
            description="Time step unit: 'day', 'week', 'month', 'quarter', or 'year'",
        )
        event_id: str = Field(
            default="event",
            description="Env key prefix; e.g. 'puig_deal' → puig_deal__abnormal_return",
        )

    def __init__(self, parameters: dict | None = None) -> None:
        super().__init__(parameters)
        self._car_raw: float = 0.0  # running CAR accumulator (raw decimal)

    @property
    def state_variables(self) -> TheoryStateVariables:
        e = self.params.event_id
        return TheoryStateVariables(
            reads=[
                "global__market_return",
                f"{e}__actual_return",
                f"{e}__event_active",
            ],
            writes=[
                f"{e}__expected_return",
                f"{e}__abnormal_return",
                f"{e}__cumulative_ar",
            ],
            initializes=[
                f"{e}__expected_return",
                f"{e}__abnormal_return",
                f"{e}__cumulative_ar",
            ],
        )

    def setup(self, env: dict[str, float]) -> dict[str, float]:
        inits = super().setup(env)
        e = self.params.event_id
        # Initialize all return keys to 0.5 (neutral)
        for key in [f"{e}__expected_return", f"{e}__abnormal_return", f"{e}__cumulative_ar"]:
            if key not in env:
                inits[key] = 0.5
        return inits

    def update(
        self,
        env: dict[str, float],
        agents: list["BDIAgent"],
        tick: int,
    ) -> dict[str, float]:
        """
        Compute CAPM expected return, abnormal return, and cumulative AR.

        Expected return (scaled to per-tick):
            E[R]_tick = (R_f + α + β × (R_m - R_f)) × dt

        Abnormal return:
            AR_tick = R_actual_tick - E[R]_tick

        CAR accumulates over all ticks.

        If event_active = 0.0, AR is still computed (pre/post-event window analysis).
        CAR always accumulates from tick 0.
        """
        p = self.params
        e = p.event_id
        dt = _DT_MAP.get(p.tick_unit, 1.0 / 365.0)

        # Read market return (normalized → raw)
        market_return_norm = env.get("global__market_return", 0.5)
        r_market = _raw_return(market_return_norm)

        # Read actual security return (normalized → raw)
        actual_return_norm = env.get(f"{e}__actual_return", 0.5)
        r_actual = _raw_return(actual_return_norm)

        # --- CAPM expected return (annualized → per tick) ---
        r_f_tick = p.risk_free_rate * dt
        alpha_tick = p.alpha * dt
        r_expected = r_f_tick + alpha_tick + p.beta_market * (r_market - r_f_tick)

        # --- Abnormal return ---
        ar = r_actual - r_expected

        # --- Cumulative AR ---
        self._car_raw += ar
        car_clamped = max(-0.90, min(0.90, self._car_raw))

        event_active = env.get(f"{e}__event_active", 0.0)
        logger.debug(
            "EventStudy[%s] tick=%d: R_m=%.4f R_actual=%.4f E[R]=%.4f AR=%.4f CAR=%.4f "
            "(event_active=%.0f)",
            e, tick, r_market, r_actual, r_expected, ar, self._car_raw, event_active,
        )

        return {
            f"{e}__expected_return": _norm_return(r_expected),
            f"{e}__abnormal_return": _norm_return(ar),
            f"{e}__cumulative_ar":   _norm_return(car_clamped),
        }
