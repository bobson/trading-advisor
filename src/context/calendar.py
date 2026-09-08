"""Phase 21 — upcoming high-impact economic events (Finnhub, needs FINNHUB_API_KEY).

UNVERIFIED against the live Finnhub response shape until a key is added — the parsing here is
best-effort and defensive. Without a key this returns [] (graceful, never raises). Matters for
both markets, especially forex (rate decisions, CPI, jobs). Forex Factory has no official API,
so we prefer a provider that does.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.context.http import get_json

CALENDAR_URL = "https://finnhub.io/api/v1/calendar/economic"


@dataclass
class Event:
    time: str
    country: str
    event: str
    impact: str


def fetch_economic_calendar(cfg, fetch=None, limit: int = 5) -> list[Event]:
    """High-impact upcoming events, or [] without a key / on any failure."""
    if not cfg.finnhub_api_key:
        return []
    fetch = fetch or get_json
    try:
        data = fetch(CALENDAR_URL, {"token": cfg.finnhub_api_key})
        rows = (data or {}).get("economicCalendar", []) or []
        events = [
            Event(
                time=str(r.get("time", "")),
                country=str(r.get("country", "")),
                event=str(r.get("event", "")),
                impact=str(r.get("impact", "")),
            )
            for r in rows
            if str(r.get("impact", "")).lower() == "high"
        ]
        return events[:limit]
    except Exception:
        return []
