"""Feature 1 — look-ahead guard for historical scrubbing (`as_of_bar`).

`advise(..., as_of_bar=N)` must return EXACTLY what a run on the truncated frame `df[:N+1]`
would return — nothing after bar N may leak in. The real leak vector is NOT `add_features`
(it's causal, byte-identical on the full vs truncated frame) but `find_swings`: its
confirmed-interior filter means a swing near bar N is only confirmed by bars *after* N, so a
naive "compute on the full frame, then slice" implementation would leak boundary swings (and
the patterns built on them).

So this test (a) uses a fixture with swing activity right up to the boundary and asserts that
activity BEFORE asserting invariance (a degenerate all-None slice would pass for the wrong
reason — the Phase-14 lesson), and (b) multiplies every bar after N by 10 (finite garbage,
never NaN — NaN can't perturb argrelextrema and would pass falsely) and asserts the as-of-N
result is unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.service.analyze import advise
from src.service.serialize import serialize_chart


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _oscillating_df(n: int = 260) -> pd.DataFrame:
    """A dense oscillation (many swings, so the region before any cut is active) + slight drift."""
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100.0 + 8.0 * np.sin(t / 5.0) + t * 0.02
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2 * np.sin(t / 5.0)
    volume = 1000.0 + 300.0 * np.abs(np.sin(t / 3.0))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


def _chart(result) -> dict:
    """The chart payload minus `total_bars` (which legitimately reflects the FULL frame size and
    so differs between an as-of run and a run on the already-truncated frame)."""
    ch = serialize_chart(result)
    ch.pop("total_bars", None)
    return ch


def test_as_of_bar_equals_truncated_frame_and_has_boundary_activity(cfg):
    df = _oscillating_df()
    n = 200

    as_of = advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False, as_of_bar=n)
    truncated = advise("BTC/USDT", "1h", cfg, df=df.iloc[: n + 1], explain_enabled=False)

    as_of_chart = _chart(as_of)

    # (a) NON-DEGENERACY: the boundary region must be active, or the guard proves nothing.
    swing_bars = [int(b) for b in as_of.swings["bar"]]
    assert swing_bars, "fixture produced no swings — the guard would pass vacuously"
    assert max(swing_bars) >= n - 25, "no swing near the cut — a leak here couldn't be detected"
    # the last candle in the scrubbed view is exactly bar N
    assert as_of_chart["candles"][-1]["time"] == int(df.index[n].timestamp())

    # (b) INVARIANCE: as-of-N is byte-identical to the truncated-frame run.
    assert as_of_chart == _chart(truncated)
    assert as_of.total_bars == len(df)          # the full frame length is still reported


def test_future_mutation_does_not_change_as_of_result(cfg):
    df = _oscillating_df()
    n = 200
    baseline = _chart(advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False, as_of_bar=n))

    mutated = df.copy()
    mutated.iloc[n + 1:] *= 10.0                 # finite garbage after the cut, never NaN
    assert mutated["close"].iloc[-1] != df["close"].iloc[-1]   # the future really changed

    after = _chart(advise("BTC/USDT", "1h", cfg, df=mutated, explain_enabled=False, as_of_bar=n))
    assert after == baseline


def test_as_of_bar_clamped_to_warmup_floor(cfg):
    """A scrub below the feature-warmup floor is clamped up (never crashes add_features)."""
    df = _oscillating_df()
    res = advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False, as_of_bar=5)
    assert len(res.df) == cfg.indicators.slow_ma + 1     # clamped to the slow-MA floor
