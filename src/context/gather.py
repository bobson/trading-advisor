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
from src.context.fundamentals import fetch_fundamentals
from src.context.news import fetch_news
from src.context.sentiment import fetch_fear_greed
from src.data.base import CRYPTO
from src.data.registry import asset_class_for


def gather_context(symbol: str, cfg, *, fetch=None, candles_for=None, now: float | None = None) -> dict:
    """Fetch the enabled context sources for `symbol`. `fetch` / `candles_for` are injectable for
    offline tests (with an injected `fetch` and no `candles_for`, the driver block is skipped)."""
    import time

    from src.context import drivers as D
    from src.context.macro_calendar import week
    c = cfg.context
    is_crypto = asset_class_for(symbol) == CRYPTO
    now = now or time.time()

    fg = fetch_fear_greed(fetch) if (c.fear_greed and is_crypto) else None
    fundamentals = fetch_fundamentals(symbol, fetch) if (c.fundamentals and is_crypto) else None
    news = fetch_news(cfg, fetch) if c.news else []

    # D3: the (keyless, cached) weekly calendar; the old Finnhub path only if a key is set and the feed failed.
    calendar, available, cal_note = [], False, None
    if c.economic_calendar:
        wk = week(fetch, ttl_s=c.calendar_ttl_min * 60)
        if wk["events"]:
            available = True
            cur = set(D.info(symbol)["currencies"])
            calendar = [{"time": e["time"], "country": e["currency"], "event": e["title"], "impact": e["impact"],
                         "forecast": e["forecast"], "previous": e["previous"], "kind": e["kind"]}
                        for e in wk["events"] if e["currency"] in cur and e["impact"] == "High"
                        and 0 <= e["ts"] - now <= c.event_days * 86400]
            cal_note = (f"{wk['source']}" + (f", stale copy ({wk['error']})" if wk["stale"] else "")
                        + "; covers this week only — no actual figures")
        elif cfg.finnhub_api_key:
            calendar = [{"time": e.time, "country": e.country, "event": e.event, "impact": e.impact}
                        for e in fetch_economic_calendar(cfg, fetch)]
            available = True

    drivers = None
    if candles_for is not None or fetch is None:
        loader = candles_for or _daily_candles(cfg)
        followed = list(c.followed or cfg.morning_report.symbols)
        rets = D.returns_for(sorted(set(followed + [symbol] + [p for p, _ in D.PROXIES.values()])), loader)
        corr = D.correlation(followed if symbol in followed else followed + [symbol], rets,
                             window=c.corr_window_days, warn=c.corr_warn)
        drivers = {"hypothesis": D.hypothesis(symbol, rets, window=c.corr_window_days, min_n=c.corr_min_n,
                                              min_rho=c.driver_min_rho),
                   "correlation_warnings": [w for w in corr["warnings"] if symbol in (w["a"], w["b"])]}

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fear_greed": None if fg is None else {"value": fg.value, "label": fg.label, "as_of": fg.as_of},
        "fundamentals": fundamentals,
        "economic_calendar": calendar,
        "calendar_available": available,
        "calendar_note": cal_note,
        "drivers": drivers,
        "news": [{"headline": h.headline, "source": h.source, "when": h.when} for h in news],
    }


def _daily_candles(cfg):
    """Daily candles for the correlation work, refreshed when older than a day (cache-first otherwise)."""
    from src.data.registry import get_candles
    return lambda s: get_candles(s, "1d", cfg, stale_after_minutes=24 * 60)
