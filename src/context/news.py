"""Phase 21 — recent crypto headlines (Finnhub, needs FINNHUB_API_KEY).

UNVERIFIED against the live Finnhub response shape until a key is added. Without a key this
returns [] (graceful, never raises). Claude summarizes/factors these in — they are context,
not prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.context.http import get_json

NEWS_URL = "https://finnhub.io/api/v1/news"


@dataclass
class Headline:
    headline: str
    source: str
    when: str


def fetch_news(cfg, fetch=None, limit: int = 5) -> list[Headline]:
    """Recent crypto headlines, or [] without a key / on any failure."""
    if not cfg.finnhub_api_key:
        return []
    fetch = fetch or get_json
    try:
        rows = fetch(NEWS_URL, {"category": "crypto", "token": cfg.finnhub_api_key}) or []
        out: list[Headline] = []
        for a in rows[:limit]:
            ts = a.get("datetime")
            when = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                if ts else ""
            )
            out.append(Headline(str(a.get("headline", "")), str(a.get("source", "")), when))
        return out
    except Exception:
        return []
