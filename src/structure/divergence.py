"""Phase 18 — RSI divergence, built on the existing swing points.

Divergence is a classic early-reversal warning: price makes a new extreme but momentum (RSI)
does not confirm it.
  - BEARISH: a higher swing high in price, but a lower RSI at that high — buying is tiring.
  - BULLISH: a lower swing low in price, but a higher RSI at that low — selling is fading.

This is a FACT (context for Layer 2), not a vote yet. It reads RSI at the last two confirmed
swing highs / lows — so it inherits the swing detector's non-repainting guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.features import COL_RSI
from src.structure.swings import SWING_HIGH, SWING_LOW


@dataclass
class Divergence:
    kind: str    # "bullish" | "bearish"
    reason: str


def find_rsi_divergence(featured_df: pd.DataFrame, swings: pd.DataFrame) -> Divergence | None:
    """Detect RSI divergence across the last two swing highs (bearish) or lows (bullish).

    `featured_df` must be row-aligned with the swings' integer `bar` index (RSI is looked up by
    position). Returns None when there aren't two swings of a kind or RSI is unavailable.
    """
    rsi = featured_df[COL_RSI]
    n = len(rsi)

    def _rsi_at(bar: int):
        if 0 <= bar < n:
            v = rsi.iloc[bar]
            return None if pd.isna(v) else float(v)
        return None

    highs = swings[swings["kind"] == SWING_HIGH].sort_values("bar")
    if len(highs) >= 2:
        a, b = highs.iloc[-2], highs.iloc[-1]
        ra, rb = _rsi_at(int(a["bar"])), _rsi_at(int(b["bar"]))
        if ra is not None and rb is not None and b["price"] > a["price"] and rb < ra:
            return Divergence(
                "bearish",
                f"Price made a higher high ({a['price']:.2f} -> {b['price']:.2f}) but RSI made a "
                f"lower high ({ra:.0f} -> {rb:.0f}) — upside momentum is weakening.",
            )

    lows = swings[swings["kind"] == SWING_LOW].sort_values("bar")
    if len(lows) >= 2:
        a, b = lows.iloc[-2], lows.iloc[-1]
        ra, rb = _rsi_at(int(a["bar"])), _rsi_at(int(b["bar"]))
        if ra is not None and rb is not None and b["price"] < a["price"] and rb > ra:
            return Divergence(
                "bullish",
                f"Price made a lower low ({a['price']:.2f} -> {b['price']:.2f}) but RSI made a "
                f"higher low ({ra:.0f} -> {rb:.0f}) — downside momentum is fading.",
            )

    return None
