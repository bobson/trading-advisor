"""Tests for Phase 24 — the FastAPI backend (offline, via TestClient).

`get_candles` is monkeypatched to a synthetic frame so the API tests need no cached CSV and no
network; `explain`/`context` default False so no Claude call is made.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.api.app as api
import src.service.analyze as service
from src.api.app import _CACHE, _HITS, app


@pytest.fixture(autouse=True)
def _clear_state():
    _CACHE.clear()
    _HITS.clear()
    yield
    _CACHE.clear()
    _HITS.clear()


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


def test_api_key_required_when_configured(synthetic_candles, monkeypatch):
    monkeypatch.setattr(api.cfg, "api_key", "secret")
    assert client.get("/analysis", params={"symbol": "BTC/USDT"}).status_code == 401  # no header
    ok = client.get("/analysis", params={"symbol": "BTC/USDT"}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200


def test_rate_limit_returns_429(synthetic_candles, monkeypatch):
    monkeypatch.setattr(api.cfg, "rate_limit_per_min", 2)
    assert client.get("/timeframes").status_code == 200
    assert client.get("/timeframes").status_code == 200
    assert client.get("/timeframes").status_code == 429  # 3rd in the window -> blocked


def test_analysis_forex_without_key_errors(synthetic_candles, monkeypatch):
    # Phase 26: forex is implemented but needs TWELVEDATA_API_KEY -> RuntimeError -> 502.
    from src.data.forex_api import ForexProvider
    monkeypatch.setattr(service, "get_candles",
                        lambda symbol, tf, cfg, **k: ForexProvider(api_key=None).fetch(symbol, tf, 100))
    r = client.get("/analysis", params={"symbol": "EUR/USD", "timeframe": "1h"})
    assert r.status_code == 502
