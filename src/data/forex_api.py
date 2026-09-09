"""Phase 26 — forex data provider (Twelve Data).

ccxt is crypto-only, so forex needs a separate source. Twelve Data has a clean free tier with
unified symbols (EUR/USD) and OHLC time series. Needs TWELVEDATA_API_KEY (free at
twelvedata.com); without it, `fetch` raises a clear, actionable error rather than crashing.

Returns the SAME clean frame shape as the crypto path (UTC DatetimeIndex named `timestamp`;
open/high/low/close/volume; sorted; de-duped) so every detector and Layer 2 stay identical —
a candle is a candle. Forex has no real volume, so `volume` is 0.0 (the Phase-19 market
adaptation already flags forex volume as a weak tick proxy).
"""

from __future__ import annotations

import pandas as pd

from src.data.base import FOREX, DataProvider

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

# ccxt-style timeframe -> Twelve Data interval string.
_INTERVAL = {
    "15m": "15min", "30m": "30min", "1h": "1h", "2h": "2h",
    "4h": "4h", "1d": "1day", "1w": "1week",
}

_OHLC = ["open", "high", "low", "close"]


def _get_json(url: str, params: dict, timeout: int = 10):
    import requests

    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalize_twelvedata(payload) -> pd.DataFrame:
    """Turn a Twelve Data time_series payload into the standard clean OHLCV frame."""
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Twelve Data response: {type(payload).__name__}")
    if payload.get("status") == "error":
        raise RuntimeError(f"Twelve Data error: {payload.get('message', 'unknown')}")

    rows = payload.get("values") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=[*_OHLC, "volume"])

    df["timestamp"] = pd.to_datetime(df["datetime"], utc=True)
    for col in _OHLC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # FX has no real volume; keep the column (0.0) so the frame shape matches crypto.
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    else:
        df["volume"] = 0.0

    df = (
        df.dropna(subset=_OHLC)
        .drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp")
        .set_index("timestamp")
    )
    return df[[*_OHLC, "volume"]]


class ForexProvider(DataProvider):
    asset_class = FOREX

    def __init__(self, api_key: str | None = None, provider: str = "twelvedata", fetch=None):
        self.api_key = api_key
        self.provider = provider
        self._fetch = fetch or _get_json  # injectable for offline tests

    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError(
                f"Forex ({symbol}) needs TWELVEDATA_API_KEY in .env — get a free key at "
                "twelvedata.com. Crypto pairs work without a key."
            )
        interval = _INTERVAL.get(timeframe)
        if interval is None:
            raise RuntimeError(
                f"Unsupported forex timeframe {timeframe!r}; use one of {sorted(_INTERVAL)}."
            )
        payload = self._fetch(
            TWELVEDATA_URL,
            {
                "symbol": symbol,
                "interval": interval,
                "outputsize": min(int(limit), 5000),
                "order": "ASC",
                "timezone": "UTC",
                "apikey": self.api_key,
            },
        )
        return normalize_twelvedata(payload)
