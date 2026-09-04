"""Phase 3 — swing-point (pivot) detection. THE foundation of the structure layer.

A *swing high* is a local peak: a bar whose high is greater than the highs of the
`sensitivity` bars on each side. A *swing low* is the mirror image on the lows. Higher
`sensitivity` means a bar must dominate a wider neighborhood to count, so only more
major swings survive. Support/resistance, trendlines, and trend direction are all built
on top of these points — get this right and the rest follows.

Two subtleties that matter:

- **Highs come from the `high` column, lows from the `low` column** — not the close.
  A pivot is about the extreme the price actually reached, wick included.

- **Confirmation lag is real and intentional.** A swing needs `sensitivity` bars on
  BOTH sides to be confirmed, so the most recent `sensitivity` bars correctly have no
  swings yet. We filter to fully-confirmed interior positions on purpose: scipy's
  `argrelextrema` defaults to `mode='clip'`, which fabricates neighbors past the array
  edge and would otherwise flag unconfirmed pivots on the newest bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

SWING_HIGH = "high"
SWING_LOW = "low"

SWING_COLUMNS = ["swing_high", "swing_low"]


def _extrema_positions(values: np.ndarray, sensitivity: int, comparator) -> np.ndarray:
    """Positional indices of fully-confirmed local extrema (`sensitivity` bars each side)."""
    if sensitivity < 1:
        raise ValueError("sensitivity must be >= 1")
    n = len(values)
    if n == 0:
        return np.array([], dtype=int)
    pos = argrelextrema(values, comparator, order=sensitivity)[0]
    # Keep only pivots with `sensitivity` REAL bars on both sides. Everything outside
    # this band was matched against clip-fabricated neighbours and isn't confirmed.
    return pos[(pos >= sensitivity) & (pos <= n - 1 - sensitivity)]


def find_swings(df: pd.DataFrame, sensitivity: int) -> pd.DataFrame:
    """Return the detected swings as a tidy frame, sorted in time.

    Columns: `bar` (integer position in `df` — the stable key), `price`, `kind`
    ("high"|"low"). Indexed by timestamp. Note an outside bar can be both a swing high
    and a swing low, so timestamps are not guaranteed unique; use `bar` as the key.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    hi_pos = _extrema_positions(highs, sensitivity, np.greater)
    lo_pos = _extrema_positions(lows, sensitivity, np.less)

    rows = [(int(p), df.index[p], float(highs[p]), SWING_HIGH) for p in hi_pos]
    rows += [(int(p), df.index[p], float(lows[p]), SWING_LOW) for p in lo_pos]

    out = pd.DataFrame(rows, columns=["bar", "timestamp", "price", "kind"])
    return out.sort_values("bar").set_index("timestamp")


def add_swing_columns(df: pd.DataFrame, sensitivity: int) -> pd.DataFrame:
    """Return a copy of `df` with boolean `swing_high`/`swing_low` columns (for plotting)."""
    swings = find_swings(df, sensitivity)
    out = df.copy()
    out["swing_high"] = False
    out["swing_low"] = False

    hi_bars = swings.loc[swings["kind"] == SWING_HIGH, "bar"].to_numpy()
    lo_bars = swings.loc[swings["kind"] == SWING_LOW, "bar"].to_numpy()
    out.iloc[hi_bars, out.columns.get_loc("swing_high")] = True
    out.iloc[lo_bars, out.columns.get_loc("swing_low")] = True
    return out
