"""Tests for Phase 8 — chart rendering and the analyze pipeline (offline).

The chart half is fully verifiable offline (Agg backend, synthetic candles). The full
"done when" (chart + a *real* explanation side by side) needs ANTHROPIC_API_KEY; here the
orchestration runs keyless and falls back to facts-only, which is what we assert.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make scripts/analyze.py importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze  # noqa: E402

from src.config import load_config  # noqa: E402
from src.signals.confluence import BULLISH  # noqa: E402
from src.structure.fibonacci import fib_retracement  # noqa: E402
from src.structure.support_resistance import find_support_resistance  # noqa: E402
from src.structure.swings import find_swings  # noqa: E402
from src.structure.trendlines import find_trendlines  # noqa: E402
from src.viz.chart import render_chart  # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def wave_df():
    """160 bars of a rising sine wave — guarantees regular swings, S/R, trendlines, and a fib leg."""
    n = 160
    idx = pd.date_range("2025-01-01", periods=n, freq="h")
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 6.0) + t * 0.05
    df = pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close},
        index=idx,
    )
    return df


def _detectors(df, cfg):
    swings = find_swings(df, cfg.structure.swing_sensitivity)
    levels = find_support_resistance(swings, cfg.structure.sr_cluster_tolerance_pct)
    trendlines = find_trendlines(swings)
    fib = fib_retracement(swings)
    return swings, levels, trendlines, fib


def test_render_chart_writes_png(cfg, wave_df, tmp_path):
    swings, levels, trendlines, fib = _detectors(wave_df, cfg)
    out = tmp_path / "chart.png"
    path = render_chart(
        wave_df, swings, levels, trendlines, fib,
        bias=BULLISH, triggered=True, cfg=cfg, out_path=out,
    )
    assert path == out
    assert out.exists() and out.stat().st_size > 0


def test_render_chart_no_setup_marker(cfg, wave_df, tmp_path):
    """triggered=False should still render (no marker) without error."""
    swings, levels, trendlines, fib = _detectors(wave_df, cfg)
    out = tmp_path / "chart_nosetup.png"
    render_chart(
        wave_df, swings, levels, trendlines, fib,
        bias="neutral", triggered=False, cfg=cfg, out_path=out,
    )
    assert out.exists() and out.stat().st_size > 0


def test_render_chart_handles_short_window(cfg, wave_df, tmp_path):
    """plot_bars larger than the frame must clamp, not crash."""
    out = tmp_path / "chart_short.png"
    swings, levels, trendlines, fib = _detectors(wave_df, cfg)
    render_chart(
        wave_df, swings, levels, trendlines, fib,
        bias=BULLISH, triggered=True, cfg=cfg, out_path=out, plot_bars=10_000,
    )
    assert out.exists() and out.stat().st_size > 0


def test_run_analysis_offline_falls_back(cfg, wave_df, tmp_path):
    """Full orchestration without a key: chart + markdown saved, explanation is None."""
    keyless = cfg.model_copy(update={"anthropic_api_key": None})  # force the no-key path
    result = analyze.run_analysis(wave_df, keyless, tmp_path)

    assert result.chart_path.exists() and result.chart_path.stat().st_size > 0
    assert result.text_path.exists()
    assert result.explanation is None  # no ANTHROPIC_API_KEY in the test environment

    md = result.text_path.read_text()
    assert cfg.market.symbol in md
    assert "Computed facts (Layer 1)" in md
    assert "ANTHROPIC_API_KEY is not set" in md  # the fallback note
