"""Phase 22 — open interest (crypto only), a positioning/conviction fact.

Open interest is the total size of outstanding perpetual positions. Rising OI alongside a
price move signals fresh conviction; falling OI signals positions unwinding. Only the CURRENT
value is read here — binance caps OI *history* to ~30 days, so a proper OI trend/backtest is
deferred (documented in CLAUDE.md). Context, not a vote.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpenInterest:
    amount: float               # contracts
    notional_usd: float | None  # USD value if the exchange reports it


def read_open_interest(exchange, perp: str) -> OpenInterest | None:
    """Current open interest for `perp` via a ccxt exchange, or None on any failure."""
    try:
        data = exchange.fetch_open_interest(perp)
        amount = data.get("openInterestAmount")
        if amount is None:
            return None
        value = data.get("openInterestValue")
        return OpenInterest(
            amount=round(float(amount), 2),
            notional_usd=None if value is None else round(float(value), 2),
        )
    except Exception:
        return None
