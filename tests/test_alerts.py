"""Tests for #7 — watchlist alerts (offline; advise + webhook injected)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.alerts.notify import format_alert, send_webhook
from src.alerts.watch import scan
from src.config import load_config


@pytest.fixture(scope="module")
def cfg():
    base = load_config()
    return base.model_copy(update={"alerts": base.alerts.model_copy(update={
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"], "timeframe": "1h", "min_confidence": 0.5})})


def _result(triggered, confidence, bias="bullish", cats=2):
    return SimpleNamespace(facts={"confluence": {
        "triggered": triggered, "confidence": confidence, "bias": bias, "agreeing_categories": cats}})


def test_scan_keeps_only_triggered_and_confident(cfg):
    responses = {
        "BTC/USDT": _result(True, 0.60),    # flagged, confident -> alert
        "ETH/USDT": _result(False, 0.90),   # not triggered -> skip
        "SOL/USDT": _result(True, 0.30),    # triggered but below min_confidence -> skip
    }
    alerts = scan(cfg, advise_fn=lambda s, t: responses[s])
    assert [a["symbol"] for a in alerts] == ["BTC/USDT"]
    assert alerts[0]["confidence"] == 0.60


def test_scan_skips_failing_symbol(cfg):
    def advise_fn(s, t):
        if s == "ETH/USDT":
            raise RuntimeError("no data")
        return _result(True, 0.7)
    alerts = scan(cfg, advise_fn=advise_fn)
    assert {a["symbol"] for a in alerts} == {"BTC/USDT", "SOL/USDT"}  # ETH failure didn't sink it


def test_format_alert():
    msg = format_alert({"symbol": "BTC/USDT", "timeframe": "1h", "bias": "bullish", "confidence": 0.6, "agreeing": 3})
    assert "BTC/USDT" in msg and "BULLISH" in msg and "60%" in msg


def test_send_webhook_paths():
    assert send_webhook("hi", None) is False                       # no URL
    sent = {}
    assert send_webhook("hi", "http://x", post=lambda u, p: sent.update(p)) is True
    assert sent["content"] == "hi"
    assert send_webhook("hi", "http://x", post=lambda u, p: (_ for _ in ()).throw(RuntimeError())) is False
