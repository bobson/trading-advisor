"""Phase 4 — fit sloped trendlines through recent swing points.

A support trendline is a least-squares fit through the last few swing lows; a resistance
trendline through the last few swing highs. `bar` (integer position) is the x-axis.

Two things to keep in mind (both inherent to the least-squares method the plan calls for):
  - It is a *best fit*, not a lower/upper bound — candles will poke below the support line
    and above the resistance line. That's expected, not a bug.
  - Fitting only the last few (default 3) swings keeps the line local and plausible; many
    points make it drift and look wrong. `r2` reports fit quality so callers can decline
    to draw a near-random line.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.structure.swings import SWING_HIGH, SWING_LOW

SUPPORT = "support"
RESISTANCE = "resistance"


@dataclass
class Trendline:
    kind: str  # "support" | "resistance"
    slope: float
    intercept: float
    bars: list[int]
    r2: float

    def value_at(self, bar: float) -> float:
        """Price on the line at a given bar position (projects/extends the line)."""
        return self.slope * bar + self.intercept


def fit_trendline(bars: np.ndarray, prices: np.ndarray, kind: str) -> Trendline:
    bars = np.asarray(bars, dtype=float)
    prices = np.asarray(prices, dtype=float)
    slope, intercept = np.polyfit(bars, prices, 1)

    predicted = slope * bars + intercept
    ss_res = float(np.sum((prices - predicted) ** 2))
    ss_tot = float(np.sum((prices - prices.mean()) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot

    return Trendline(kind, float(slope), float(intercept), [int(b) for b in bars], r2)


def find_trendlines(swings: pd.DataFrame, num_points: int = 3) -> dict[str, Trendline]:
    """Fit a support line through the last `num_points` swing lows and a resistance line
    through the last `num_points` swing highs. Omits either if there aren't enough swings.
    """
    result: dict[str, Trendline] = {}
    lows = swings[swings["kind"] == SWING_LOW].sort_values("bar")
    highs = swings[swings["kind"] == SWING_HIGH].sort_values("bar")

    if len(lows) >= num_points:
        sub = lows.tail(num_points)
        result[SUPPORT] = fit_trendline(sub["bar"].to_numpy(), sub["price"].to_numpy(), SUPPORT)
    if len(highs) >= num_points:
        sub = highs.tail(num_points)
        result[RESISTANCE] = fit_trendline(sub["bar"].to_numpy(), sub["price"].to_numpy(), RESISTANCE)
    return result
