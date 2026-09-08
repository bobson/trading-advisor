"""Phase 22 — perpetual funding rate (crypto only), a positioning/sentiment fact.

Funding is a small fee longs and shorts pay each other on a perpetual future. Persistently
high positive funding means longs are crowded (a CONTRARIAN caution); deeply negative means
shorts are crowded. It is context, not a trigger — shown as a fact, not (yet) a vote.
"""

from __future__ import annotations

from dataclasses import dataclass

# 3 funding settlements per day on binance perps -> annualize an 8h rate.
_SETTLEMENTS_PER_YEAR = 3 * 365


@dataclass
class Funding:
    rate: float          # per-8h rate as a fraction (e.g. 0.0001 = 0.01%)
    rate_pct: float      # rate as a percent per 8h
    annualized_pct: float
    state: str           # "crowded_longs" | "crowded_shorts" | "neutral"


def read_funding(exchange, perp: str, cfg) -> Funding | None:
    """Current funding for `perp` via a ccxt exchange, or None on any failure."""
    try:
        data = exchange.fetch_funding_rate(perp)
        rate = data.get("fundingRate")
        if rate is None:
            return None
        rate = float(rate)
    except Exception:
        return None

    extreme = cfg.derivatives.funding_extreme
    if rate >= extreme:
        state = "crowded_longs"
    elif rate <= -extreme:
        state = "crowded_shorts"
    else:
        state = "neutral"
    return Funding(
        rate=rate,
        rate_pct=round(rate * 100, 4),
        annualized_pct=round(rate * _SETTLEMENTS_PER_YEAR * 100, 1),
        state=state,
    )
