"""Save/load candles locally so we don't re-download the same history.

Stored as CSV under data/ (gitignored): human-inspectable and needs no extra
dependency (parquet would require pyarrow). The UTC DatetimeIndex round-trips.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "data"


def cache_path(
    symbol: str, timeframe: str, exchange_id: str, data_dir: Path = DATA_DIR
) -> Path:
    """Deterministic filename for a symbol/timeframe/exchange, e.g. binance_BTC-USDT_1h.csv."""
    safe_symbol = symbol.replace("/", "-")
    return Path(data_dir) / f"{exchange_id}_{safe_symbol}_{timeframe}.csv"


def save_candles(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    exchange_id: str,
    data_dir: Path = DATA_DIR,
) -> Path:
    path = cache_path(symbol, timeframe, exchange_id, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return path


def load_candles(
    symbol: str, timeframe: str, exchange_id: str, data_dir: Path = DATA_DIR
) -> pd.DataFrame:
    path = cache_path(symbol, timeframe, exchange_id, data_dir)
    df = pd.read_csv(path, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df
