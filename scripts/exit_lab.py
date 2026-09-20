#!/usr/bin/env python
"""Feature 8 — run the exit-rule laboratory on cached candles and print the table + verdict.

Holds the entry fixed and sweeps the eight exits; holds the exit fixed and sweeps the entries;
tells you which choice moves outcomes more on your data. Net of Feature-10 costs.

    python scripts/exit_lab.py                 # uses config.yaml market
    python scripts/exit_lab.py ETH/USDT 1d     # a specific pair/timeframe
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.exits import run_exit_lab  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data.cache import load_candles  # noqa: E402


def main() -> None:
    cfg = load_config()
    symbol = sys.argv[1] if len(sys.argv) > 1 else cfg.market.symbol
    timeframe = sys.argv[2] if len(sys.argv) > 2 else cfg.market.timeframe
    cfg = cfg.model_copy(update={"market": cfg.market.model_copy(
        update={"symbol": symbol, "timeframe": timeframe})})
    df = load_candles(symbol, timeframe, cfg.market.exchange)
    print(run_exit_lab(df, cfg).summary())


if __name__ == "__main__":
    main()
