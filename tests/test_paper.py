"""Paper-trading simulator — position/PnL maths and the one-at-a-time guard (offline)."""

from __future__ import annotations

import pytest

from src.config import load_config
from src.store.db import connect
from src.trading import paper


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --- long round trip --------------------------------------------------------------------------

def test_long_open_position_and_close_realized_pnl(conn):
    o = paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 500.0, price=100.0, now=1)
    assert o["action"] == "opened" and o["units"] == 5.0

    pos = paper.position(conn, "BTC/USDT", price=110.0)      # +10% -> +$50 on 5 units
    assert not pos["flat"] and pos["side"] == "buy"
    assert pos["unrealized_pnl"] == 50.0 and pos["unrealized_pct"] == 10.0

    c = paper.open_or_close(conn, "BTC/USDT", "1d", paper.SELL, 999.0, price=110.0, now=2)
    assert c["action"] == "closed" and c["realized_pnl"] == 50.0
    assert paper.position(conn, "BTC/USDT", price=110.0)["flat"] is True


def test_short_profits_when_price_falls(conn):
    paper.open_or_close(conn, "ETH/USDT", "1d", paper.SELL, 500.0, price=100.0, now=1)   # short 5 units
    pos = paper.position(conn, "ETH/USDT", price=90.0)
    assert pos["side"] == "sell" and pos["unrealized_pnl"] == 50.0 and pos["unrealized_pct"] == 10.0
    c = paper.open_or_close(conn, "ETH/USDT", "1d", paper.BUY, 500.0, price=90.0, now=2)
    assert c["realized_pnl"] == 50.0


# --- one position at a time -------------------------------------------------------------------

def test_same_side_while_open_is_rejected(conn):
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 500.0, price=100.0)
    with pytest.raises(ValueError, match="already in a buy position"):
        paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 200.0, price=105.0)


def test_reopen_after_close(conn):
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 500.0, price=100.0, now=1)
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.SELL, 500.0, price=110.0, now=2)   # close
    o = paper.open_or_close(conn, "BTC/USDT", "1d", paper.SELL, 500.0, price=110.0, now=3)  # new short
    assert o["action"] == "opened" and o["side"] == "sell"


# --- live_price fallback ----------------------------------------------------------------------

def test_live_price_uses_ticker_then_falls_back(cfg):
    paper._TICKER_CACHE.clear()
    price, src = paper.live_price("BTC/USDT", cfg, last_close=100.0, fetch=lambda s: 123.4)
    assert (price, src) == (123.4, "live")
    paper._TICKER_CACHE.clear()
    price, src = paper.live_price("BTC/USDT", cfg, last_close=100.0, fetch=lambda s: None)  # fetch fails
    assert (price, src) == (100.0, "last_close")


def test_record_uses_injected_fetch_offline(conn, cfg):
    r = paper.record(conn, "SOL/USDT", "1d", paper.BUY, 200.0, cfg, last_close=50.0, fetch=lambda s: 40.0)
    assert r["action"] == "opened" and r["price"] == 40.0 and r["units"] == 5.0


# --- summary + list ---------------------------------------------------------------------------

def test_pnl_summary_and_list(conn):
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 100.0, price=100.0, now=1)
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.SELL, 100.0, price=110.0, now=2)   # +$10
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.BUY, 100.0, price=100.0, now=3)
    paper.open_or_close(conn, "BTC/USDT", "1d", paper.SELL, 100.0, price=90.0, now=4)    # -$10
    s = paper.pnl_summary(conn, "BTC/USDT")
    assert s["closed"] == 2 and s["wins"] == 1 and s["realized_total"] == 0.0 and s["win_rate"] == 0.5
    trades = paper.list_trades(conn, "BTC/USDT")
    assert len(trades) == 2 and [t["status"] for t in trades] == ["closed", "closed"]


# --- API (offline: tmp DB + monkeypatched live price, no network/Claude) -----------------------

def test_trade_api_flow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import src.api.app as api

    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(paper, "live_price", lambda symbol, cfg, **kw: (kw.get("last_close") or 100.0, "last_close"))
    c = TestClient(api.app)

    opened = c.post("/trades", json={"symbol": "BTC/USDT", "side": "buy", "amount_usd": 500, "last_close": 100.0})
    assert opened.status_code == 200 and opened.json()["result"]["action"] == "opened"

    dup = c.post("/trades", json={"symbol": "BTC/USDT", "side": "buy", "amount_usd": 100, "last_close": 105.0})
    assert dup.status_code == 400                                   # one position at a time

    pos = c.get("/trades/position", params={"symbol": "BTC/USDT", "last_close": 110.0}).json()
    assert pos["flat"] is False and pos["unrealized_pnl"] == 50.0

    closed = c.post("/trades", json={"symbol": "BTC/USDT", "side": "sell", "amount_usd": 500, "last_close": 110.0}).json()
    assert closed["result"]["realized_pnl"] == 50.0 and closed["pnl"]["realized_total"] == 50.0
    assert c.get("/trades/position", params={"symbol": "BTC/USDT"}).json()["flat"] is True
