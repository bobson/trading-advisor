"""ROADMAP A8 — oil (WTI) candles from OANDA's v20 REST API (free practice/demo account).

Twelve Data's free plan covers gold but not WTI ("available starting with the Grow plan"), so
oil comes from OANDA: instrument `WTICO_USD` (a CFD on West Texas crude). Needs OANDA_API_TOKEN
in .env (a free practice-account token); without it `fetch` raises a clear RuntimeError and the
caller skips the symbol.

Only COMPLETE candles are kept (OANDA flags the forming one `complete: false`). Daily and 4h
bars are aligned to 00:00 UTC (OANDA's default is 17:00 New York) so they line up with the other
markets. Volume is OANDA's tick count — a weak proxy, like forex (the market adaptation flags it).
Returns the same clean frame shape as every other provider.

Live shape UNVERIFIED in-session (no token yet) — offline tests inject `fetch`.
"""

from __future__ import annotations

import pandas as pd

from src.data.base import FOREX, DataProvider

PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"

# app symbol -> OANDA instrument
INSTRUMENT = {"WTI/USD": "WTICO_USD", "XAU/USD": "XAU_USD", "EUR/USD": "EUR_USD"}
_GRANULARITY = {"15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D", "1w": "W"}
_OHLC = ["open", "high", "low", "close"]


def _get_json(url: str, params: dict, headers: dict, timeout: int = 15):
    import requests

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalize_oanda(payload) -> pd.DataFrame:
    """OANDA /candles payload -> the standard clean OHLCV frame (complete candles only)."""
    if not isinstance(payload, dict) or "candles" not in payload:
        raise RuntimeError(f"Unexpected OANDA response: {str(payload)[:200]}")
    rows = [
        {"timestamp": c["time"], "open": c["mid"]["o"], "high": c["mid"]["h"], "low": c["mid"]["l"],
         "close": c["mid"]["c"], "volume": c.get("volume", 0)}
        for c in payload["candles"] if c.get("complete") and c.get("mid")
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=[*_OHLC, "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for col in [*_OHLC, "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (df.dropna(subset=_OHLC).drop_duplicates(subset="timestamp", keep="last")
          .sort_values("timestamp").set_index("timestamp"))
    return df[[*_OHLC, "volume"]]


class OandaProvider(DataProvider):
    asset_class = FOREX

    def __init__(self, token: str | None = None, base_url: str = PRACTICE_URL, fetch=None):
        self.token = token
        self.base_url = base_url
        self._fetch = fetch or _get_json      # injectable for offline tests

    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        if not self.token:
            raise RuntimeError(f"{symbol} needs OANDA_API_TOKEN in .env (a free OANDA practice-account token).")
        inst, gran = INSTRUMENT.get(symbol), _GRANULARITY.get(timeframe)
        if inst is None or gran is None:
            raise RuntimeError(f"OANDA: unsupported {symbol} {timeframe}")
        payload = self._fetch(
            f"{self.base_url}/instruments/{inst}/candles",
            {"granularity": gran, "count": min(int(limit), 5000), "price": "M",
             "dailyAlignment": 0, "alignmentTimezone": "UTC"},
            {"Authorization": f"Bearer {self.token}"},
        )
        return normalize_oanda(payload)
