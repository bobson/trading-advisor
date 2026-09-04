"""Config loads, validates, and rejects typos."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Config, load_config


def test_load_config_reads_yaml():
    cfg = load_config()  # reads the repo's config.yaml
    assert cfg.market.symbol == "BTC/USDT"
    assert cfg.market.timeframe == "1h"
    assert cfg.confluence.min_agreeing_signals >= 1


def test_unknown_key_is_rejected():
    # A typo like "symobl" must fail loudly rather than being ignored.
    bad = {
        "market": {"symobl": "BTC/USDT"},
        "structure": {},
        "indicators": {},
        "confluence": {},
        "advisor": {},
    }
    with pytest.raises(ValidationError):
        Config(**bad)


def test_require_api_key_raises_when_missing():
    cfg = load_config()
    cfg.anthropic_api_key = None
    with pytest.raises(RuntimeError):
        cfg.require_api_key()
