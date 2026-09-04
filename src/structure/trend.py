"""Phase 4 — classify the trend as up / down / sideways.

Structure first, then confirmation:
  - Higher highs AND higher lows over the last few swings  -> uptrend structure
  - Lower highs AND lower lows                              -> downtrend structure
  - anything else                                           -> sideways
Then the slow moving average must agree: an "uptrend" whose 50-MA isn't rising is
downgraded to sideways (unconfirmed), and likewise for downtrends. `sideways` is the
neutral fallback, never an error.

Uses the last 3 swings of each kind (not 2): a single noisy pivot shouldn't flip the
label. Reads the SMA column produced in Phase 2 — this aligns with swing `bar`s only
because `add_features` preserves row count, so callers should pass the featured frame
built from the same candles the swings came from.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.indicators.features import COL_SMA_SLOW
from src.structure.swings import SWING_HIGH, SWING_LOW

UPTREND = "uptrend"
DOWNTREND = "downtrend"
SIDEWAYS = "sideways"


@dataclass
class TrendResult:
    label: str
    reasons: list[str]


def _ma_slope(series: pd.Series, window: int) -> float:
    """Change in the (NaN-dropped) series over `window` bars; ~0 if too short."""
    valid = series.dropna()
    if len(valid) < window + 1:
        return 0.0
    return float(valid.iloc[-1] - valid.iloc[-1 - window])


def classify_trend(
    featured_df: pd.DataFrame,
    swings: pd.DataFrame,
    slope_window: int = 10,
    num_swings: int = 3,
) -> TrendResult:
    highs = swings[swings["kind"] == SWING_HIGH].sort_values("bar")["price"].to_numpy()
    lows = swings[swings["kind"] == SWING_LOW].sort_values("bar")["price"].to_numpy()

    if len(highs) < num_swings or len(lows) < num_swings:
        return TrendResult(SIDEWAYS, ["Not enough confirmed swings to judge the trend."])

    last_highs, last_lows = highs[-num_swings:], lows[-num_swings:]
    higher_highs = bool(np.all(np.diff(last_highs) > 0))
    higher_lows = bool(np.all(np.diff(last_lows) > 0))
    lower_highs = bool(np.all(np.diff(last_highs) < 0))
    lower_lows = bool(np.all(np.diff(last_lows) < 0))

    reasons: list[str] = []
    if higher_highs and higher_lows:
        structure = UPTREND
        reasons.append("Price is making higher highs and higher lows.")
    elif lower_highs and lower_lows:
        structure = DOWNTREND
        reasons.append("Price is making lower highs and lower lows.")
    else:
        return TrendResult(
            SIDEWAYS,
            ["Swing highs and lows are not consistently rising or falling."],
        )

    slope = _ma_slope(featured_df[COL_SMA_SLOW], slope_window)

    if structure == UPTREND:
        if slope > 0:
            reasons.append("The 50-period moving average is rising, confirming the uptrend.")
            return TrendResult(UPTREND, reasons)
        reasons.append("But the 50-period moving average is not rising, so the uptrend is unconfirmed.")
        return TrendResult(SIDEWAYS, reasons)

    # structure == DOWNTREND
    if slope < 0:
        reasons.append("The 50-period moving average is falling, confirming the downtrend.")
        return TrendResult(DOWNTREND, reasons)
    reasons.append("But the 50-period moving average is not falling, so the downtrend is unconfirmed.")
    return TrendResult(SIDEWAYS, reasons)
