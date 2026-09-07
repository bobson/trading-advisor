"""Phase 13 — the data-source abstraction.

A candle is a candle, whatever market it comes from. `DataProvider` is the interface every
source implements; the app selects one by the pair's asset class (see `registry.py`) and
never otherwise cares whether it's crypto or forex — so every detector and Layer 2 stay
identical across markets. Keep this module dependency-light (ABC + constants only) so nothing
imports back into it and creates a cycle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

CRYPTO = "crypto"
FOREX = "forex"


class DataProvider(ABC):
    """Fetch OHLCV candles for one asset class.

    Implementations return a clean DataFrame in the same shape as
    `data.exchange.normalize_ohlcv`: a UTC `DatetimeIndex` named ``timestamp``, numeric
    ``open/high/low/close/volume`` columns, sorted ascending with duplicates removed.
    """

    asset_class: str

    @abstractmethod
    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Return the most recent `limit` candles for `symbol` at `timeframe`."""
        raise NotImplementedError
