"""Fetch OHLCV candles from an exchange via ccxt (public data, read-only).

Two responsibilities, kept separate so the pure part is testable without a network:
  - normalize_ohlcv(): turn raw ccxt rows into a clean, sorted, deduped DataFrame.
  - fetch_ohlcv():      page through the exchange to gather `limit` candles, then normalize.

Exchanges cap how many candles a single call returns (Binance ~1000), so anything
larger than that must be paged with a `since` cursor — otherwise you silently get
only the most recent ~1000 and miss the requested window.
"""

from __future__ import annotations

import time

import ccxt
import pandas as pd

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close", "volume"]

# Most exchanges return at most ~1000 candles per fetch_ohlcv call.
MAX_PER_CALL = 1000


def normalize_ohlcv(raw: list[list]) -> pd.DataFrame:
    """Convert raw ccxt OHLCV rows into a clean DataFrame.

    Guarantees every downstream detector can rely on:
      - a tz-aware (UTC) DatetimeIndex named "timestamp"
      - rows sorted ascending in time, with duplicate timestamps removed
      - numeric OHLCV columns, non-numeric/NaN rows dropped

    Note: this does NOT drop the still-forming last candle — fetch_ohlcv does that,
    because "forming" only has meaning for data fetched up to the present moment.
    """
    df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in PRICE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (
        df.dropna(subset=PRICE_COLUMNS)
        .drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .set_index("timestamp")
    )
    return df


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    limit: int,
    exchange_id: str = "binance",
    drop_forming: bool = True,
) -> pd.DataFrame:
    """Download the most recent `limit` candles for `symbol`, paging as needed.

    Returns a clean DataFrame (see normalize_ohlcv). The last candle — which is
    still forming when we fetch up to "now" — is dropped by default so detectors
    never analyze an incomplete bar.
    """
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000

    # Start one full window back from now (with a little slack for paging overlap).
    now_ms = exchange.milliseconds()
    since = now_ms - (limit + 1) * timeframe_ms

    rows: list[list] = []
    while since < now_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=MAX_PER_CALL)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        # Advance past the last candle we got; stop if the exchange stops advancing.
        next_since = last_ts + timeframe_ms
        if next_since <= since:
            break
        since = next_since
        if len(batch) < MAX_PER_CALL:
            break  # reached the present edge

    df = normalize_ohlcv(rows)
    if drop_forming and len(df):
        df = df.iloc[:-1]
    return df.tail(limit)
