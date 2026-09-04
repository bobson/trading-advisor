"""Tests for the data layer.

Two kinds:
  - Pure normalization tests: no network, run everywhere, fast. These are the
    real safety net for the "clean DataFrame" guarantee.
  - A network-marked integration test: does a real (small) ccxt fetch to prove
    the pagination/plumbing works. Skip offline with:  pytest -m "not network"
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.exchange import PRICE_COLUMNS, fetch_ohlcv, normalize_ohlcv


def _raw(ts_ms, o, h, l, c, v):
    return [ts_ms, o, h, l, c, v]


HOUR = 3_600_000


def test_normalize_sorts_dedupes_and_indexes():
    # Deliberately out of order, with a duplicate timestamp (later one wins).
    raw = [
        _raw(2 * HOUR, 10, 12, 9, 11, 100),
        _raw(0 * HOUR, 8, 9, 7, 8.5, 50),
        _raw(1 * HOUR, 8.5, 11, 8, 10, 75),
        _raw(2 * HOUR, 10, 12, 9, 11.5, 120),  # dup timestamp -> keep=last
    ]
    df = normalize_ohlcv(raw)

    assert list(df.columns) == PRICE_COLUMNS
    assert len(df) == 3  # duplicate collapsed
    assert df.index.is_monotonic_increasing
    assert df.index.name == "timestamp"
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"
    # keep="last": the 2h close should be the second (11.5), not 11.0
    assert df.iloc[-1]["close"] == 11.5


def test_normalize_casts_numeric_and_drops_bad_rows():
    raw = [
        _raw(0, "8", "9", "7", "8.5", "50"),      # numeric strings -> floats
        _raw(1 * HOUR, 8.5, 11, 8, None, 75),      # missing close -> dropped
    ]
    df = normalize_ohlcv(raw)

    assert len(df) == 1
    for col in PRICE_COLUMNS:
        # numeric (not object) is the guarantee; int vs float depends on the values
        assert pd.api.types.is_numeric_dtype(df[col])


def test_normalize_empty():
    df = normalize_ohlcv([])
    assert df.empty
    assert list(df.columns) == PRICE_COLUMNS


@pytest.mark.network
def test_fetch_ohlcv_live_small():
    """Real fetch of a small window — proves ccxt + normalization work end to end."""
    df = fetch_ohlcv("BTC/USDT", "1h", limit=50, exchange_id="binance")

    assert not df.empty
    assert len(df) <= 50
    assert list(df.columns) == PRICE_COLUMNS
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates
    assert str(df.index.tz) == "UTC"
    # high should be >= low on every candle
    assert (df["high"] >= df["low"]).all()
