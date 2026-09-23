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


@dataclass
class TwoPointTrendline:
    """A classic hand-drawn-style trendline: a straight line through two swing lows (support) or
    two swing highs (resistance), kept only while no close has broken it since the first anchor."""
    kind: str                    # "support" | "resistance"
    anchors: list[tuple[int, float]]   # [(bar, price), (bar, price)], older first
    slope: float                 # price per bar

    @property
    def direction(self) -> str:
        return "rising" if self.slope > 0 else "falling" if self.slope < 0 else "flat"

    def value_at(self, bar: float) -> float:
        b0, p0 = self.anchors[0]
        return p0 + self.slope * (bar - b0)


def find_two_point_trendlines(
    featured_df: pd.DataFrame, swings: pd.DataFrame, *, atr_col: str,
    break_atr_mult: float = 0.25, max_anchors: int = 6,
) -> dict[str, TwoPointTrendline]:
    """For each side, connect the MOST RECENT swing (low for support, high for resistance) to an
    earlier swing of the same kind, and keep the line only if no close since the older anchor
    went through it by more than `break_atr_mult` × that bar's ATR. Among valid lines the
    longest (earliest older anchor, within the last `max_anchors` swings) wins — a line that has
    held longer is the more meaningful one. A side with no valid line is omitted.

    Look-ahead-safe: `swings` are confirmed pivots and only closes <= the last row are read."""
    out: dict[str, TwoPointTrendline] = {}
    if swings.empty or featured_df.empty:
        return out
    closes = featured_df["close"].to_numpy(dtype=float)
    last_close = float(closes[-1])
    atr = (featured_df[atr_col].to_numpy(dtype=float) if atr_col in featured_df.columns
           else np.full(len(closes), np.nan))
    fallback = last_close * 0.01          # ATR-less fixture: 1% of price
    atr = np.where(np.isnan(atr) | (atr <= 0), fallback, atr)
    n = len(closes)

    for kind, swing_kind in ((SUPPORT, SWING_LOW), (RESISTANCE, SWING_HIGH)):
        pts = swings[swings["kind"] == swing_kind].sort_values("bar").tail(max_anchors)
        pts = pts[(pts["bar"] >= 0) & (pts["bar"] < n)]
        if len(pts) < 2:
            continue
        b2, p2 = int(pts["bar"].iloc[-1]), float(pts["price"].iloc[-1])
        for b1, p1 in zip(pts["bar"].iloc[:-1].astype(int), pts["price"].iloc[:-1].astype(float)):
            slope = (p2 - p1) / (b2 - b1)
            bars = np.arange(b1 + 1, n)
            line = p1 + slope * (bars - b1)
            margin = break_atr_mult * atr[b1 + 1:]
            c = closes[b1 + 1:]
            broken = (c < line - margin) if kind == SUPPORT else (c > line + margin)
            if not broken.any():
                out[kind] = TwoPointTrendline(kind, [(b1, p1), (b2, p2)], float(slope))
                break                      # earliest valid anchor = the longest line
    return out
