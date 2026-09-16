"""Phase B of the ML plan — triple-barrier labels (what the model tries to predict).

For each bar we set two barriers from information known AT THAT BAR: an upper barrier at
`close + atr_mult*ATR` and a lower at `close - atr_mult*ATR`. Then we walk forward up to
`horizon` bars and label by which barrier price touches FIRST:
  +1 (up)   — the upper barrier is hit first (a winning long / losing short)
  -1 (down) — the lower barrier is hit first
   0        — neither within the horizon (a timeout / chop)

This is realistic — it's how a trade with a target and a stop actually resolves — and far less
noisy than "was the close higher N bars later". The label reads the FUTURE, which is fine: it's
the answer the model learns, only ever used at training time. The FEATURES (Phase A) remain
strictly causal, so nothing leaks into the model's inputs.

The barrier width uses ATR (causal, known at the bar). The last `horizon` bars can't be labeled
(not enough future) and are NaN, as are warm-up bars with no ATR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators.features import COL_ATR, add_features


def triple_barrier_labels(
    df: pd.DataFrame,
    cfg=None,
    *,
    horizon: int = 24,
    atr_mult: float = 1.0,
    atr: pd.Series | None = None,
) -> pd.Series:
    """Label each bar +1 / -1 / 0 by the first barrier hit within `horizon`.

    `atr` is injectable (tests pass a known ATR); otherwise it's computed via `add_features`
    (requires `cfg`). If both barriers are touched in the SAME future bar, we resolve UP first
    (a fixed, documented convention — such bars are inherently ambiguous).
    """
    if atr is None:
        atr = add_features(df, cfg)[COL_ATR]

    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    atr_arr = np.asarray(atr, dtype=float)
    n = len(df)

    labels = np.full(n, np.nan)
    for i in range(n - horizon):
        a = atr_arr[i]
        if np.isnan(a) or a <= 0:
            continue
        upper = close[i] + atr_mult * a
        lower = close[i] - atr_mult * a
        outcome = 0
        for j in range(i + 1, i + 1 + horizon):
            if high[j] >= upper:      # up barrier hit first (checked before down on ties)
                outcome = 1
                break
            if low[j] <= lower:
                outcome = -1
                break
        labels[i] = outcome

    return pd.Series(labels, index=df.index, name="label")
