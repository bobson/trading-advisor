"""Phase 21 — aggregate the enabled context sources into one JSON-safe dict.

`gather_context` never raises (each source degrades to None/[] internally) and stamps the
result with `as_of` so Layer 2 knows when it was pulled. It is CURRENT-state only — the caller
(the live CLI/API path) fetches it and passes it into `advise(..., context=...)`; it must NEVER
be wired into `build_facts` (which runs per-bar in the backtest — current sentiment on
historical bars would be look-ahead bias and would break the snapshot).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.context.calendar import fetch_economic_calendar
from src.context.news import fetch_news
from src.context.sentiment import fetch_fear_greed
from src.data.base import CRYPTO
from src.data.registry import asset_class_for


def gather_context(symbol: str, cfg, *, fetch=None) -> dict:
    """Fetch the enabled context sources for `symbol`. `fetch` is injectable for offline tests."""
    c = cfg.context
    is_crypto = asset_class_for(symbol) == CRYPTO

    fg = fetch_fear_greed(fetch) if (c.fear_greed and is_crypto) else None
    calendar = fetch_economic_calendar(cfg, fetch) if c.economic_calendar else []
    news = fetch_news(cfg, fetch) if c.news else []

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fear_greed": None if fg is None else {"value": fg.value, "label": fg.label, "as_of": fg.as_of},
        "economic_calendar": [
            {"time": e.time, "country": e.country, "event": e.event, "impact": e.impact}
            for e in calendar
        ],
        "news": [{"headline": h.headline, "source": h.source, "when": h.when} for h in news],
    }
