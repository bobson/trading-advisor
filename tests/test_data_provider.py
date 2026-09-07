"""Tests for Phase 13 — the data-source abstraction, registry, quality gate, and facade.

All offline. The crypto provider's live fetch is covered by the network-marked test in
test_exchange.py; here we exercise the dispatch, the quality gate, and the cache-first facade
with synthetic frames and a temp cache dir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.data.base import CRYPTO, FOREX
from src.data.cache import load_candles, save_candles
from src.data.crypto_ccxt import CryptoProvider
from src.data.forex_api import ForexProvider
from src.data.quality import check_candles, clean_candles
from src.data.registry import (
    Pair,
    asset_class_for,
    get_candles,
    list_pairs,
    provider_for,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _clean_df(n=48, start="2025-01-01"):
    """A clean, monotonic OHLCV frame with a 'timestamp' index (round-trips through CSV)."""
    idx = pd.date_range(start, periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.arange(n) * 0.5
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 10.0),
        },
        index=idx,
    )


# --- registry / dispatch -------------------------------------------------------

def test_list_pairs_non_empty_and_filterable():
    pairs = list_pairs()
    assert pairs and all(isinstance(p, Pair) for p in pairs)
    assert list_pairs(FOREX) and all(p.asset_class == FOREX for p in list_pairs(FOREX))
    assert all(p.asset_class == CRYPTO for p in list_pairs(CRYPTO))


def test_asset_class_lookup_and_unknown_default():
    assert asset_class_for("BTC/USDT") == CRYPTO
    assert asset_class_for("EUR/USD") == FOREX
    assert asset_class_for("DOGE/USDT") == CRYPTO  # unknown -> crypto (only live provider)


def test_provider_dispatch(cfg):
    assert isinstance(provider_for("BTC/USDT", cfg), CryptoProvider)
    assert isinstance(provider_for("EUR/USD", cfg), ForexProvider)


def test_forex_provider_raises_clearly():
    with pytest.raises(NotImplementedError, match="Phase 26"):
        ForexProvider().fetch("EUR/USD", "1h", 100)


# --- quality gate --------------------------------------------------------------

def test_check_candles_clean_is_ok():
    report = check_candles(_clean_df())
    assert report.ok
    assert report.duplicate_timestamps == 0 and report.invalid_hl == 0


def test_check_candles_flags_structural_corruption():
    df = _clean_df(n=10)
    # Corrupt it: duplicate the last timestamp, a high<low bar, and a NaN close.
    dup = df.iloc[[-1]]
    df = pd.concat([df, dup])                     # duplicate timestamp
    df.iloc[3, df.columns.get_loc("high")] = 0.0  # high < low
    df.iloc[5, df.columns.get_loc("close")] = np.nan

    report = check_candles(df)
    assert not report.ok
    assert report.duplicate_timestamps >= 1
    assert report.invalid_hl >= 1
    assert report.nan_rows >= 1
    s = report.summary()
    assert "duplicate" in s and "high < low" in s and "NaN" in s


def test_gaps_and_outliers_are_advisory_not_failing():
    df = _clean_df(n=20)
    df = df.drop(df.index[10])                    # a time gap
    df.iloc[15, df.columns.get_loc("close")] *= 3  # a huge single-bar move (outlier)
    report = check_candles(df)
    assert report.gaps >= 1
    assert report.outliers >= 1
    assert report.ok  # advisory issues never flip .ok


def test_clean_candles_dedups_sorts_and_keeps_volume():
    df = _clean_df(n=6)
    shuffled = pd.concat([df.iloc[[-1]], df])     # out of order + a duplicate
    cleaned = clean_candles(shuffled)
    assert cleaned.index.is_monotonic_increasing
    assert not cleaned.index.has_duplicates
    assert "volume" in cleaned.columns            # volume must survive (Phase 15)
    assert len(cleaned) == len(df)


# --- facade (cache-first, offline) ---------------------------------------------

def test_get_candles_cache_first_matches_direct_load(cfg, tmp_path):
    """Cache-first + quality gate must not mutate already-clean cached data (regression proxy)."""
    df = _clean_df(n=72)
    save_candles(df, "BTC/USDT", "1h", cfg.market.exchange, tmp_path)

    direct = load_candles("BTC/USDT", "1h", cfg.market.exchange, tmp_path)
    via_facade = get_candles("BTC/USDT", "1h", cfg, data_dir=tmp_path)  # no network: cache hit

    pd.testing.assert_frame_equal(via_facade, direct)


def test_get_candles_raises_on_empty_after_clean(cfg, tmp_path):
    empty = _clean_df(n=0)
    save_candles(empty, "BTC/USDT", "1h", cfg.market.exchange, tmp_path)
    with pytest.raises(ValueError, match="empty"):
        get_candles("BTC/USDT", "1h", cfg, data_dir=tmp_path)
