"""Phase 13 — crypto data provider (ccxt, public/read-only).

A thin adapter over `data.exchange.fetch_ohlcv`, which owns the paging + normalization. This
just presents it behind the `DataProvider` interface so the app can pick a source by asset
class. No API keys are needed for public OHLCV.
"""

from __future__ import annotations

import pandas as pd

from src.data.base import CRYPTO, DataProvider
from src.data.exchange import fetch_ohlcv


class CryptoProvider(DataProvider):
    asset_class = CRYPTO

    def __init__(self, exchange_id: str = "binance"):
        self.exchange_id = exchange_id

    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        return fetch_ohlcv(symbol, timeframe, limit, exchange_id=self.exchange_id)
