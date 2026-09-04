#!/usr/bin/env python3
"""Phase 2 check: print the last closed candles with indicators so you can eyeball
them against TradingView.

Usage (from repo root, venv active; run download_data.py first):
    python scripts/show_indicators.py

To match TradingView: use the same symbol/timeframe, set its moving-average overlay to
SMA with the configured lengths, and compare against the last *closed* bar (this data
drops the still-forming candle).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402
from src.indicators.features import (  # noqa: E402
    INDICATOR_COLUMNS,
    PATTERN_COLUMNS,
    add_features,
)


def main() -> None:
    cfg = load_config()
    m, ind = cfg.market, cfg.indicators

    df = load_candles(m.symbol, m.timeframe, m.exchange)
    feat = add_features(df, cfg)

    print(f"{m.symbol} {m.timeframe} on {m.exchange} — last closed candles")
    print(
        f"SMA lengths: fast={ind.fast_ma} slow={ind.slow_ma} | "
        f"RSI={ind.rsi_period} | MACD=12/26/9"
    )
    print(
        "NOTE: the forming candle is already dropped — compare against the last CLOSED "
        "bar on TradingView, and set TV's moving averages to SMA.\n"
    )

    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(feat[["close", *INDICATOR_COLUMNS]].tail(5).round(2))

        recent = feat[PATTERN_COLUMNS].tail(30)
        fired = recent[recent.any(axis=1)]
        print("\nCandlestick patterns in the last 30 bars:")
        print(fired if not fired.empty else "  (none fired)")


if __name__ == "__main__":
    main()
