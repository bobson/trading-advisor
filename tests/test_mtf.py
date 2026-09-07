"""Tests for Phase 16 — multi-timeframe context and the higher-timeframe gate.

Unit-level coverage here: resampling, higher-TF trend detection, the alignment rule, and the
gate mechanics (downgrade on conflict, pass on aligned/neutral, no-op when disabled or when no
higher timeframe applies). The look-ahead guard with an ACTIVE (directional) context lives in
test_backtest.py, alongside the Phase-14 guard it mirrors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.signals.confluence import BEARISH, BULLISH, NEUTRAL, ConfluenceResult
from src.structure import mtf
from src.structure.mtf import (
    ALIGN_NEUTRAL,
    ALIGNED,
    CONFLICT,
    MtfContext,
    alignment,
    build_mtf_context,
    higher_timeframe_trend,
    resample_ohlcv,
    resolve_mtf,
)
from src.structure.trend import UPTREND


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _hourly(n, close):
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    return pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close, "volume": 10.0},
        index=idx,
    )


def test_resample_ohlcv_aggregates_correctly():
    close = np.arange(8, dtype=float)
    df = _hourly(8, close)
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2                       # 8 hourly -> 2 four-hour bars
    assert out["open"].iloc[0] == df["open"].iloc[0]
    assert out["high"].iloc[0] == df["high"].iloc[0:4].max()
    assert out["low"].iloc[0] == df["low"].iloc[0:4].min()
    assert out["close"].iloc[0] == df["close"].iloc[3]
    assert out["volume"].iloc[0] == df["volume"].iloc[0:4].sum()


def test_higher_timeframe_trend_reads_uptrend(cfg):
    n = 480
    t = np.arange(n)
    close = 100 + 6 * np.sin(t / 6.0) + t * 0.12  # rising with oscillation -> swings + uptrend
    tr = higher_timeframe_trend(_hourly(n, close), "4h", cfg)
    assert tr is not None
    assert tr.label == UPTREND


def test_higher_timeframe_trend_none_when_too_short(cfg):
    assert higher_timeframe_trend(_hourly(8, np.arange(8, dtype=float)), "1d", cfg) is None


def test_alignment_rule():
    assert alignment(BULLISH, BULLISH) == ALIGNED
    assert alignment(BULLISH, BEARISH) == CONFLICT
    assert alignment(BEARISH, BEARISH) == ALIGNED
    assert alignment(BULLISH, NEUTRAL) == ALIGN_NEUTRAL
    assert alignment(NEUTRAL, BEARISH) == ALIGN_NEUTRAL


def _triggered_bull():
    return ConfluenceResult(
        bias=BULLISH, triggered=True, confidence=0.8, agreeing_categories=3, signals=[]
    )


def test_gate_downgrades_on_conflict(cfg, monkeypatch):
    monkeypatch.setattr(mtf, "build_mtf_context", lambda df, c: MtfContext("1h", {"1d": "downtrend"}, BEARISH))
    out = resolve_mtf(_triggered_bull(), pd.DataFrame(), cfg)
    assert out.mtf_alignment == CONFLICT
    assert out.triggered is False
    assert out.mtf_downgraded is True
    assert out.bias == BULLISH  # bias is preserved; only the flag is downgraded


def test_gate_passes_on_aligned(cfg, monkeypatch):
    monkeypatch.setattr(mtf, "build_mtf_context", lambda df, c: MtfContext("1h", {"1d": "uptrend"}, BULLISH))
    out = resolve_mtf(_triggered_bull(), pd.DataFrame(), cfg)
    assert out.mtf_alignment == ALIGNED
    assert out.triggered is True
    assert out.mtf_downgraded is False


def test_gate_passes_on_neutral_higher_tf(cfg, monkeypatch):
    monkeypatch.setattr(mtf, "build_mtf_context", lambda df, c: MtfContext("1h", {"1d": "sideways"}, NEUTRAL))
    out = resolve_mtf(_triggered_bull(), pd.DataFrame(), cfg)
    assert out.mtf_alignment == ALIGN_NEUTRAL
    assert out.triggered is True


def test_gate_noop_when_disabled(cfg):
    dcfg = cfg.model_copy(update={"mtf": cfg.mtf.model_copy(update={"enabled": False})})
    out = resolve_mtf(_triggered_bull(), pd.DataFrame(), dcfg)
    assert out.mtf_alignment is None
    assert out.triggered is True


def test_alignment_none_when_no_higher_timeframe(cfg):
    """Base already at the top timeframe -> no higher TF applies -> alignment None (not 'neutral')."""
    dcfg = cfg.model_copy(update={"market": cfg.market.model_copy(update={"timeframe": "1d"})})
    out = resolve_mtf(_triggered_bull(), _hourly(60, np.arange(60, dtype=float)), dcfg)
    assert out.mtf_alignment is None
    assert out.triggered is True
    assert out.mtf_trends is None
