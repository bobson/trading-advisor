"""Phase A of the ML plan — turn history into a look-ahead-safe feature matrix.

One row per bar; every column is known AT THAT BAR'S CLOSE (causal), so a model trained on
row i never peeks at the future. We reuse `add_features` (proven causal in Phase 14 — SMA/RSI/
MACD/ATR/ADX/Stochastic/Bollinger depend only on the past) and engineer scale-FREE features
(normalized by price, or already-bounded oscillators) so they generalize across coins and price
levels instead of memorizing "BTC ~ 80,000".

Warm-up rows carry NaN (indicators need history); alignment with the candle index is preserved
so labels (Phase B) line up. The caller drops NaN rows at train time. A guard test proves that
mutating future bars never changes an earlier row.
"""

from __future__ import annotations

import pandas as pd

from src.config import Config
from src.indicators.features import (
    COL_ADX,
    COL_ATR,
    COL_BB_PCT,
    COL_MACD_HIST,
    COL_RSI,
    COL_SMA_FAST,
    COL_SMA_SLOW,
    COL_STOCH_K,
    COL_VOLUME,
    COL_VOLUME_MA,
    add_features,
)

# The model's input columns (stable contract for Phase B/C).
FEATURE_COLUMNS = [
    "rsi",             # 0–100 momentum oscillator
    "adx",             # 0–100 trend strength
    "stoch_k",         # 0–100 momentum oscillator
    "bb_pct",          # %B: where price sits across the Bollinger band (0=lower, 1=upper)
    "atr_pct",         # volatility as a fraction of price
    "macd_hist_norm",  # MACD histogram, price-normalized
    "sma_slow_dist",   # distance of price above/below the slow MA (fraction)
    "sma_cross",       # fast-minus-slow MA spread (fraction)
    "vol_ratio",       # volume vs its average
    "ret_1",           # trailing 1-bar return
    "ret_5",           # trailing 5-bar return
    "ret_10",          # trailing 10-bar return
]


def build_feature_matrix(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Return a causal, scale-free feature matrix (one row per bar, aligned to `df.index`)."""
    feat = add_features(df, cfg)
    close = feat["close"]
    vol_ma = feat[COL_VOLUME_MA]

    out = pd.DataFrame(index=feat.index)
    out["rsi"] = feat[COL_RSI]
    out["adx"] = feat[COL_ADX]
    out["stoch_k"] = feat[COL_STOCH_K]
    out["bb_pct"] = feat[COL_BB_PCT]
    out["atr_pct"] = feat[COL_ATR] / close
    out["macd_hist_norm"] = feat[COL_MACD_HIST] / close
    out["sma_slow_dist"] = (close - feat[COL_SMA_SLOW]) / close
    out["sma_cross"] = (feat[COL_SMA_FAST] - feat[COL_SMA_SLOW]) / close
    # volume vs its average; NaN when the frame carries no volume (some synthetic/forex frames)
    if COL_VOLUME in feat.columns:
        out["vol_ratio"] = feat[COL_VOLUME] / vol_ma.where(vol_ma > 0)  # avoid /0 -> NaN
    else:
        out["vol_ratio"] = float("nan")
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)

    return out[FEATURE_COLUMNS]
