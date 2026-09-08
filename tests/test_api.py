"""Tests for Phase 24 — the FastAPI backend (offline, via TestClient).

`get_candles` is monkeypatched to a synthetic frame so the API tests need no cached CSV and no
network; `explain`/`context` default False so no Claude call is made.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.service.analyze as service
from src.api.app import _CACHE, app


@pytest.fixture(autouse=True)
def _clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


@pytest.fixture
def synthetic_candles(monkeypatch):
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    close = 100 + np.sin(np.arange(n) / 6.0) * 5 + np.arange(n) * 0.05
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0},
        index=idx,
    )
    monkeypatch.setattr(service, "get_candles", lambda *a, **k: df)
    return df


client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_pairs_and_timeframes():
    pairs = client.get("/pairs").json()
    assert any(p["symbol"] == "BTC/USDT" for p in pairs)
    assert all({"symbol", "asset_class", "label"} <= set(p) for p in pairs)
    tfs = client.get("/timeframes").json()
    assert "1h" in tfs and "5m" not in tfs


def test_analysis_returns_full_payload(synthetic_candles):
    r = client.get("/analysis", params={"symbol": "BTC/USDT", "timeframe": "1h"})
    assert r.status_code == 200
    body = r.json()
    # chart data for the frontend
    assert body["chart"]["candles"] and {"time", "open", "high", "low", "close"} <= set(body["chart"]["candles"][0])
    assert "levels" in body["chart"]["overlays"] and "fibonacci" in body["chart"]["overlays"]
    # facts + verdict
    assert body["market"]["symbol"] == "BTC/USDT"
    assert "confluence" in body and "confidence" in body["confluence"]
    # explain defaulted false -> no Claude call -> no explanation
    assert body["explanation"] is None


def test_analysis_forex_without_provider_is_501(synthetic_candles, monkeypatch):
    # Force the real (unimplemented) forex fetch by removing the synthetic override for a forex pair.
    from src.data.forex_api import ForexProvider
    monkeypatch.setattr(service, "get_candles",
                        lambda symbol, tf, cfg, **k: ForexProvider().fetch(symbol, tf, 100))
    r = client.get("/analysis", params={"symbol": "EUR/USD", "timeframe": "1h"})
    assert r.status_code == 501
