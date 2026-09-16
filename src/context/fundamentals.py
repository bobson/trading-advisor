"""Crypto fundamentals via CoinGecko (no key) — market cap, supply, volume, ATH distance.

Context for Layer 2, not a detector — the "how big / how liquid / how far from its peak" picture
that price alone doesn't show. Crypto-only (forex fundamentals are macro = the economic
calendar). Graceful: any failure or unknown symbol -> None. `fetch` is injectable for tests.
"""

from __future__ import annotations

from src.context.http import get_json

MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Base ticker -> CoinGecko id, for the registered crypto pairs.
_COINGECKO_ID = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple"}


def _r(value, digits: int):
    return None if value is None else round(float(value), digits)


def fetch_fundamentals(symbol: str, fetch=None) -> dict | None:
    """CoinGecko market fundamentals for `symbol`'s base coin, or None (unknown/failure)."""
    coin_id = _COINGECKO_ID.get(symbol.split("/")[0].upper())
    if coin_id is None:
        return None
    fetch = fetch or get_json
    try:
        data = fetch(MARKETS_URL, {"vs_currency": "usd", "ids": coin_id})
        if not data:
            return None
        d = data[0]
        return {
            "coin": coin_id,
            "market_cap": d.get("market_cap"),
            "volume_24h": d.get("total_volume"),
            "circulating_supply": d.get("circulating_supply"),
            "ath": d.get("ath"),
            "ath_change_pct": _r(d.get("ath_change_percentage"), 1),
            "change_24h_pct": _r(d.get("price_change_percentage_24h"), 2),
        }
    except Exception:
        return None
