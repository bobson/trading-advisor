"""Tests for Phase 26 — forex data provider (Twelve Data), offline via an injected fetch.

The live Twelve Data shape is UNVERIFIED until a key is added; these pin the parsing, the
no-key error, and the crypto-vs-forex dispatch.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.config import load_config
from src.data.crypto_ccxt import CryptoProvider
from src.data.forex_api import ForexProvider, normalize_twelvedata
from src.data.registry import provider_for

_PAYLOAD = {
    "status": "ok",
    "values": [
        {"datetime": "2025-01-01 00:00:00", "open": "1.1000", "high": "1.1020", "low": "1.0990", "close": "1.1010"},
        {"datetime": "2025-01-01 01:00:00", "open": "1.1010", "high": "1.1035", "low": "1.1005", "close": "1.1030"},
    ],
}


def test_normalize_twelvedata_shape():
    df = normalize_twelvedata(_PAYLOAD)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert str(df.index.tz) == "UTC" and df.index.name == "timestamp"
    assert df.index.is_monotonic_increasing
    assert df["close"].iloc[-1] == 1.1030
    assert (df["volume"] == 0.0).all()  # FX has no real volume


def test_normalize_twelvedata_error_raises():
    with pytest.raises(RuntimeError, match="Twelve Data error"):
        normalize_twelvedata({"status": "error", "message": "bad symbol"})


def test_forex_fetch_with_injected_client():
    p = ForexProvider(api_key="TESTKEY", fetch=lambda url, params, timeout=10: _PAYLOAD)
    df = p.fetch("EUR/USD", "1h", 500)
    assert len(df) == 2 and df["open"].iloc[0] == 1.1000


def test_forex_without_key_raises_clearly():
    with pytest.raises(RuntimeError, match="TWELVEDATA_API_KEY"):
        ForexProvider(api_key=None).fetch("EUR/USD", "1h", 500)


def test_forex_rejects_unknown_timeframe():
    with pytest.raises(RuntimeError, match="Unsupported forex timeframe"):
        ForexProvider(api_key="K").fetch("EUR/USD", "3h", 500)


def test_provider_dispatch_passes_key():
    cfg = load_config().model_copy(update={"twelvedata_api_key": "K"})
    fx = provider_for("EUR/USD", cfg)
    assert isinstance(fx, ForexProvider) and fx.api_key == "K"
    assert isinstance(provider_for("BTC/USDT", cfg), CryptoProvider)
