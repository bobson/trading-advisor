"""Phase 9 (OPTIONAL) — named chart patterns via geometry on swing points.

Head & shoulders, double top/bottom, and triangles, detected by rules over the recent
swings. This is the fuzziest detector in the project and it's meant to be: it will miss
some real patterns and over-call some non-patterns. Two design choices keep the over-calling
in check — the failure mode that matters most:

- **Two separate tolerances, not one.** A double top needs the two peaks *equal* within
  `price_tolerance_pct` AND the trough between them *deep enough* (`min_trough_pct`) to be a
  genuine reversal rather than two similar highs a few ticks apart. Head & shoulders likewise
  needs the head to clear both shoulders by more than tolerance while the shoulders match
  within it.
- **Only the recent tail.** Patterns describe *current* structure, so we scan the last few
  swings, not all history.

Triangle flatness is normalised by price: a raw price-per-bar slope means nothing across
symbols (BTC at 80k vs ETH at 3k), so we measure the fitted line's percentage change across
its own span and compare that to `flat_slope_pct`.

Swings are not guaranteed to strictly alternate (an outside bar can be both, and the newest
bars may repeat a kind), so every walker reads highs and lows independently and tolerates
gaps rather than assuming H-L-H-L order.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import Config
from src.structure.swings import SWING_HIGH, SWING_LOW
from src.structure.trendlines import RESISTANCE, SUPPORT, fit_trendline

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

# Human-readable pattern names (used in facts/display).
DOUBLE_TOP = "double top"
DOUBLE_BOTTOM = "double bottom"
HEAD_AND_SHOULDERS = "head and shoulders"
INVERSE_HEAD_AND_SHOULDERS = "inverse head and shoulders"
ASCENDING_TRIANGLE = "ascending triangle"
DESCENDING_TRIANGLE = "descending triangle"
SYMMETRIC_TRIANGLE = "symmetric triangle"

DEFAULT_LOOKBACK = 7  # how many recent swings to consider


@dataclass
class ChartPattern:
    name: str
    direction: str          # bullish | bearish | neutral
    bars: list[int]         # key swing bars that define the pattern
    reason: str             # plain-language description
    neckline: float | None = None
    target: float | None = None


def _pct_diff(a: float, b: float) -> float:
    """Absolute difference as a fraction of the larger magnitude."""
    denom = max(abs(a), abs(b))
    return abs(a - b) / denom if denom else 0.0


def _rel_change_pct(slope: float, bars: np.ndarray, mean_price: float) -> float:
    """A fitted line's price change across its own span, as a percent of mean price."""
    span = float(bars.max() - bars.min())
    if mean_price == 0:
        return 0.0
    return slope * span / mean_price * 100.0


def _detect_double(highs: pd.DataFrame, lows: pd.DataFrame, cfg: Config, top: bool) -> ChartPattern | None:
    """Double top (top=True) or double bottom (top=False)."""
    tol = cfg.patterns.price_tolerance_pct / 100.0
    min_trough = cfg.patterns.min_trough_pct / 100.0

    peaks = highs if top else lows
    valleys = lows if top else highs
    if len(peaks) < 2:
        return None

    p1, p2 = peaks.iloc[-2], peaks.iloc[-1]
    between = valleys[(valleys["bar"] > p1["bar"]) & (valleys["bar"] < p2["bar"])]
    if between.empty or _pct_diff(p1["price"], p2["price"]) > tol:
        return None

    if top:
        level = min(p1["price"], p2["price"])
        mid_row = between.loc[between["price"].idxmin()]  # deepest trough between the peaks
        mid = float(mid_row["price"])
        depth = (level - mid) / level
        neckline, target = mid, mid - (level - mid)
        name, direction = DOUBLE_TOP, BEARISH
    else:
        level = max(p1["price"], p2["price"])
        mid_row = between.loc[between["price"].idxmax()]  # highest peak between the troughs
        mid = float(mid_row["price"])
        depth = (mid - level) / level
        neckline, target = mid, mid + (mid - level)
        name, direction = DOUBLE_BOTTOM, BULLISH

    if depth < min_trough:
        return None

    kind = "peaks" if top else "troughs"
    return ChartPattern(
        name=name,
        direction=direction,
        bars=[int(p1["bar"]), int(mid_row["bar"]), int(p2["bar"])],
        reason=f"Two {kind} at ~{level:.2f} with a reversal between them (neckline {neckline:.2f}).",
        neckline=round(float(neckline), 2),
        target=round(float(target), 2),
    )


def _detect_head_and_shoulders(highs: pd.DataFrame, lows: pd.DataFrame, cfg: Config, top: bool) -> ChartPattern | None:
    """Head & shoulders (top=True, bearish) or inverse H&S (top=False, bullish)."""
    tol = cfg.patterns.price_tolerance_pct / 100.0
    min_depth = cfg.patterns.min_trough_pct / 100.0

    peaks = highs if top else lows
    valleys = lows if top else highs
    if len(peaks) < 3:
        return None

    ls, head, rs = peaks.iloc[-3], peaks.iloc[-2], peaks.iloc[-1]
    shoulder = max(ls["price"], rs["price"]) if top else min(ls["price"], rs["price"])

    # Head must clear both shoulders by more than tolerance; shoulders ~equal within it.
    head_clears = (head["price"] - shoulder) / head["price"] > tol if top else (shoulder - head["price"]) / abs(head["price"]) > tol
    if not head_clears or _pct_diff(ls["price"], rs["price"]) > tol:
        return None

    left = valleys[(valleys["bar"] > ls["bar"]) & (valleys["bar"] < head["bar"])]
    right = valleys[(valleys["bar"] > head["bar"]) & (valleys["bar"] < rs["bar"])]
    if left.empty or right.empty:
        return None

    neckline = float((left["price"].mean() + right["price"].mean()) / 2)
    # The head must sit a real distance from the neckline (depth guard against noise).
    depth = abs(head["price"] - neckline) / abs(head["price"])
    if depth < min_depth:
        return None

    if top:
        name, direction = HEAD_AND_SHOULDERS, BEARISH
        target = neckline - (head["price"] - neckline)
    else:
        name, direction = INVERSE_HEAD_AND_SHOULDERS, BULLISH
        target = neckline + (neckline - head["price"])

    return ChartPattern(
        name=name,
        direction=direction,
        bars=[int(ls["bar"]), int(head["bar"]), int(rs["bar"])],
        reason=f"Three swings with the middle one most extreme ({head['price']:.2f}) and matching "
               f"shoulders; neckline {neckline:.2f}.",
        neckline=round(neckline, 2),
        target=round(float(target), 2),
    )


def _detect_triangle(highs: pd.DataFrame, lows: pd.DataFrame, cfg: Config) -> ChartPattern | None:
    """Ascending / descending / symmetric triangle from the last 3 highs and 3 lows."""
    if len(highs) < 3 or len(lows) < 3:
        return None
    flat = cfg.patterns.flat_slope_pct

    hi = highs.tail(3)
    lo = lows.tail(3)
    mean_price = float(pd.concat([hi["price"], lo["price"]]).mean())

    hi_line = fit_trendline(hi["bar"].to_numpy(), hi["price"].to_numpy(), RESISTANCE)
    lo_line = fit_trendline(lo["bar"].to_numpy(), lo["price"].to_numpy(), SUPPORT)
    hi_rc = _rel_change_pct(hi_line.slope, hi["bar"].to_numpy(), mean_price)
    lo_rc = _rel_change_pct(lo_line.slope, lo["bar"].to_numpy(), mean_price)

    def cls(rc: float) -> str:
        if abs(rc) < flat:
            return "flat"
        return "rising" if rc > 0 else "falling"

    hc, lc = cls(hi_rc), cls(lo_rc)
    if hc == "flat" and lc == "rising":
        name, direction, desc = ASCENDING_TRIANGLE, BULLISH, "flat highs with rising lows (buyers pressing into resistance)"
    elif lc == "flat" and hc == "falling":
        name, direction, desc = DESCENDING_TRIANGLE, BEARISH, "flat lows with falling highs (sellers pressing into support)"
    elif hc == "falling" and lc == "rising":
        name, direction, desc = SYMMETRIC_TRIANGLE, NEUTRAL, "falling highs and rising lows converging (a coil, direction unresolved)"
    else:
        return None

    bars = [int(b) for b in pd.concat([hi["bar"], lo["bar"]]).sort_values().tolist()]
    return ChartPattern(
        name=name,
        direction=direction,
        bars=bars,
        reason=f"Recent highs and lows form {desc}.",
    )


def find_chart_patterns(
    swings: pd.DataFrame, cfg: Config, lookback: int = DEFAULT_LOOKBACK
) -> list[ChartPattern]:
    """Detect chart patterns in the most recent `lookback` swings. Best-effort — see module docstring."""
    if swings.empty:
        return []

    tail = swings.sort_values("bar").tail(lookback)
    highs = tail[tail["kind"] == SWING_HIGH].sort_values("bar")
    lows = tail[tail["kind"] == SWING_LOW].sort_values("bar")

    candidates = [
        _detect_head_and_shoulders(highs, lows, cfg, top=True),
        _detect_head_and_shoulders(highs, lows, cfg, top=False),
        _detect_double(highs, lows, cfg, top=True),
        _detect_double(highs, lows, cfg, top=False),
        _detect_triangle(highs, lows, cfg),
    ]
    return [c for c in candidates if c is not None]
