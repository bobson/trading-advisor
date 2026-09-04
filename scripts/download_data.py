#!/usr/bin/env python3
"""Phase 1 one-off: download history for the configured symbol and cache it.

Usage (from repo root, venv active):
    python scripts/download_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script (python scripts/download_data.py) by putting
# the repo root on the path so `import src...` works.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config  # noqa: E402
from src.data.cache import save_candles  # noqa: E402
from src.data.exchange import fetch_ohlcv  # noqa: E402


def main() -> None:
    cfg = load_config()
    m = cfg.market
    print(
        f"Fetching {m.history_candles} {m.timeframe} candles for "
        f"{m.symbol} from {m.exchange}..."
    )
    df = fetch_ohlcv(m.symbol, m.timeframe, m.history_candles, exchange_id=m.exchange)
    path = save_candles(df, m.symbol, m.timeframe, m.exchange)
    print(f"Saved {len(df)} candles to {path}")
    print(f"Range: {df.index[0]}  ->  {df.index[-1]}")
    print(df.tail())


if __name__ == "__main__":
    main()
