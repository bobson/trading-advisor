"""Tests for Phase 23 — cross-timeframe synthesis (offline, fake client)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.advisor.explain import build_synthesis_messages, synthesize
from src.config import load_config
from src.service.analyze import advise


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class _Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Resp:
    def __init__(self, content):
        self.content = content


class _Messages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.captured = kwargs
        return _Resp([_Block("text", "Daily up, 1h pulling back — timeframes ALIGN, buy-the-dip.")])


class _FakeClient:
    def __init__(self):
        self.captured = None
        self.messages = _Messages(self)


def test_build_synthesis_messages_includes_each_timeframe_and_weight():
    msgs = build_synthesis_messages([("1h", "FACTS-1H", 1.0), ("1d", "FACTS-1D", 1.4)])
    content = msgs[0]["content"]
    assert "TIMEFRAME 1h" in content and "TIMEFRAME 1d" in content
    assert "FACTS-1H" in content and "FACTS-1D" in content        # raw facts, not summaries
    assert "weight 1.4" in content


def test_synthesize_returns_cross_tf_read(cfg):
    client = _FakeClient()
    out = synthesize([("1h", "f1", 1.0), ("1d", "f2", 1.4)], cfg, client=client)
    assert "ALIGN" in out
    assert client.captured["model"] == cfg.advisor.model


def test_advise_explain_disabled_skips_layer2(cfg):
    """Multi-timeframe path gets facts WITHOUT a per-timeframe Claude call."""
    n = 160
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 6.0) * 5 + np.arange(n) * 0.05
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0}, index=idx)
    # A client that would blow up if called — proves explain_enabled=False never calls it.
    boom = object()
    result = advise("BTC/USDT", "1h", cfg, df=df, client=boom, explain_enabled=False)
    assert result.explanation is None and result.facts_text
