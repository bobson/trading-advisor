"""Phase 20 — Layer-2 consistency check (verify.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.advisor.facts import build_facts
from src.advisor.verify import extract_prices, verify_explanation
from src.config import load_config
from src.indicators.features import add_features
from src.structure.swings import find_swings


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def btc_facts(cfg):
    """A BTC-scale synthetic frame so fabricated in-band levels are testable."""
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    close = 79000 + np.sin(np.arange(n) / 6.0) * 800 + np.arange(n) * 5.0
    df = pd.DataFrame(
        {"open": close, "high": close + 50, "low": close - 50, "close": close, "volume": 10.0},
        index=idx,
    )
    return build_facts(add_features(df, cfg), find_swings(df, cfg.structure.swing_sensitivity), cfg)


def test_extract_prices_handles_formats():
    got = extract_prices("resistance at 90,000, support 79381.62, a move to 80k, RSI 45")
    assert 90000.0 in got and 79381.62 in got and 80000.0 in got and 45.0 in got


def test_faithful_explanation_passes(btc_facts):
    lc = btc_facts["market"]["last_close"]
    result = verify_explanation(f"Price is trading near {lc}, holding the computed support.", btc_facts)
    assert result.ok and not result.issues


def test_fabricated_in_band_level_is_flagged(btc_facts):
    lc = btc_facts["market"]["last_close"]
    fake = round(lc * 1.12)  # in-band (< 1.5x) but not a computed level
    result = verify_explanation(f"There is major resistance at {fake} to watch above.", btc_facts)
    assert not result.ok
    assert any(str(fake) in issue for issue in result.issues)


def test_out_of_band_numbers_are_ignored(btc_facts):
    # RSI 45, a far-off 5000, and the year 2025 all sit outside 0.5x-1.5x price -> not checked.
    result = verify_explanation("RSI is 45; a crash to 5000 is unlikely; data since 2025.", btc_facts)
    assert result.ok
