"""Phase 22 — aggregate crypto perp positioning (funding + open interest) into one fact dict.

CRYPTO-ONLY: forex has no consolidated perp funding/OI, so this returns None for non-crypto.
Like the Phase-21 context layer it is CURRENT-state and live-only — the caller (CLI/API)
fetches it and passes it into `advise(..., derivatives=...)`; it is NEVER wired into
`build_facts` (per-bar backtest) because current positioning on historical bars is look-ahead.
Never raises (each read degrades to None). No vote yet — pending a funding forward-return study.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.data.base import CRYPTO
from src.data.registry import asset_class_for
from src.derivatives.funding import read_funding
from src.derivatives.open_interest import read_open_interest


def _perp_symbol(symbol: str) -> str:
    """Spot symbol -> ccxt linear-perp symbol, e.g. BTC/USDT -> BTC/USDT:USDT."""
    if ":" in symbol:
        return symbol
    base, _, quote = symbol.partition("/")
    return f"{base}/{quote}:{quote}" if quote else symbol


def gather_derivatives(symbol: str, cfg, *, exchange=None) -> dict | None:
    """Funding + open interest for `symbol`'s perp, or None (crypto-only, graceful).

    `exchange` is an injectable ccxt-like object for offline tests; in the live path it is
    binance's USD-M futures market.
    """
    if not cfg.derivatives.enabled or asset_class_for(symbol) != CRYPTO:
        return None

    if exchange is None:
        import ccxt

        exchange = ccxt.binanceusdm()

    perp = _perp_symbol(symbol)
    funding = read_funding(exchange, perp, cfg)
    oi = read_open_interest(exchange, perp)
    if funding is None and oi is None:
        return None  # e.g. no perp for this symbol

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "perp": perp,
        "funding": None if funding is None else {
            "rate_pct": funding.rate_pct,
            "annualized_pct": funding.annualized_pct,
            "state": funding.state,
        },
        "open_interest": None if oi is None else {
            "amount": oi.amount,
            "notional_usd": oi.notional_usd,
        },
    }
