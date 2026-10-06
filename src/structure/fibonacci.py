"""Phase 5 — Fibonacci retracement levels for the most recent price leg.

A retracement asks: after an impulse move, how far back has price pulled? We auto-pick
the latest leg — the most recent swing, plus the most recent *opposite* swing before it
— and lay the standard ratios across it.

Direction matters for where 0% sits (0% is always the impulse *end*, the most recent
swing):
  - up-leg (ends on a swing high):  level(r) = H - r*(H-L)   -> 0% at H, 100% at L
  - down-leg (ends on a swing low):  level(r) = L + r*(H-L)   -> 0% at L, 100% at H

So in both directions, `levels[0.0]` is the most-recent swing's price and `levels[1.0]`
is the older anchor's — the invariant that actually pins the direction branch.

A degenerate leg (high <= low) can only arise from a non-alternating swing sequence
(two same-kind swings in a row reaching back past a farther extreme); we return None
rather than emit inverted levels.

OUTDATED LEG: a swing is only confirmed `sensitivity` bars after it, so the latest confirmed leg can
already be history — price may have traded beyond either end of it since (a new high above an up-leg's
end or a down-leg's start, a new low below…). Given the candles, `fib_retracement(..., df=)` marks such a
leg `superseded` (with the price that broke it): its levels are not current, so it casts no vote and is
not offered as a level. Look-ahead-safe — only bars after the leg's end and up to the frame's last row.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.structure.swings import SWING_HIGH, SWING_LOW

# Standard retracement ratios (no extensions — those are a separate concept).
FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

UP = "up"
DOWN = "down"


@dataclass
class FibRetracement:
    direction: str  # "up" | "down"
    high_bar: int
    high_price: float
    low_bar: int
    low_price: float
    levels: dict[float, float]  # ratio -> price
    superseded: bool = False    # price has traded beyond the leg since it ended (see module docstring)
    superseded_by: str | None = None

    @property
    def start_bar(self) -> int:
        """Bar of the older anchor — where the leg (and the drawn band) begins."""
        return min(self.high_bar, self.low_bar)


def fib_retracement(
    swings: pd.DataFrame, ratios: list[float] = FIB_RATIOS, df: pd.DataFrame | None = None
) -> FibRetracement | None:
    """Compute retracement levels for the latest leg, or None if it can't be formed. With the candles
    (`df`, row-aligned with the swings' bars) the leg is also checked for being outdated."""
    if len(swings) < 2:
        return None

    ordered = swings.sort_values("bar")
    last = ordered.iloc[-1]
    opposite = SWING_LOW if last["kind"] == SWING_HIGH else SWING_HIGH
    prior = ordered[(ordered["bar"] < last["bar"]) & (ordered["kind"] == opposite)]
    if prior.empty:
        return None
    prev = prior.iloc[-1]  # most recent opposite swing before `last`

    if last["kind"] == SWING_HIGH:
        direction, high, low = UP, last, prev
    else:
        direction, high, low = DOWN, prev, last

    H, L = float(high["price"]), float(low["price"])
    if H <= L:
        return None  # degenerate leg from non-alternating swings

    span = H - L
    if direction == UP:
        levels = {r: H - r * span for r in ratios}
    else:
        levels = {r: L + r * span for r in ratios}

    fib = FibRetracement(
        direction=direction,
        high_bar=int(high["bar"]),
        high_price=H,
        low_bar=int(low["bar"]),
        low_price=L,
        levels=levels,
    )
    if df is not None:
        after = df.iloc[max(fib.high_bar, fib.low_bar) + 1:]
        if len(after):
            hi, lo = float(after["high"].max()), float(after["low"].min())
            if hi > H:
                fib.superseded, fib.superseded_by = True, f"price traded above the leg's high {H:.10g} since (to {hi:.10g})"
            elif lo < L:
                fib.superseded, fib.superseded_by = True, f"price traded below the leg's low {L:.10g} since (to {lo:.10g})"
    return fib
