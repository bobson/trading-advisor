"""Phase 13 — forex data provider SLOT.

ccxt is crypto-only, so forex needs a separate source (candidates: Twelve Data, Alpha
Vantage, Finnhub — key'd and rate-limited). That wiring is Phase 26; this stub keeps the
abstraction honest so the rest of the app is already asset-class agnostic. Selecting a forex
pair today raises a clear, actionable error rather than silently doing the wrong thing.
"""

from __future__ import annotations

import pandas as pd

from src.data.base import FOREX, DataProvider


class ForexProvider(DataProvider):
    asset_class = FOREX

    def __init__(self, provider: str = "twelvedata"):
        self.provider = provider

    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        raise NotImplementedError(
            f"Forex data ({symbol}) is not wired yet — Phase 26 implements a provider "
            f"(configured: {self.provider!r}; candidates: Twelve Data / Alpha Vantage / "
            "Finnhub). Crypto pairs work today."
        )
