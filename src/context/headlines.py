"""ROADMAP D3 — recent headlines from public RSS feeds, keyless: headline + link + source + time only
(never article bodies). Shown on the page only — NOT fed to Claude: titles often carry directional
language ("poised to rally") that would leak into the explanation.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

FEEDS = {
    "CoinDesk": ("https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
    "Cointelegraph": ("https://cointelegraph.com/rss", "crypto"),
    "FXStreet": ("https://www.fxstreet.com/rss/news", "macro"),
    "ForexLive": ("https://www.forexlive.com/feed/news", "macro"),
}


def _when(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(parsedate_to_datetime(text).timestamp())
    except Exception:
        try:
            return int(pd.Timestamp(text, tz="UTC").timestamp())
        except Exception:
            return None


def parse_rss(content: bytes, source: str, group: str) -> list[dict]:
    out = []
    for it in ET.fromstring(content).findall(".//item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        if title and link:
            out.append({"headline": title, "link": link, "source": source, "group": group, "ts": _when(it.findtext("pubDate"))})
    return out


def fetch_all(fetch=None) -> list[dict]:
    """Every feed; a failing feed is skipped. Newest first."""
    rows = []
    for source, (url, group) in FEEDS.items():
        try:
            if fetch is None:
                import requests
                r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (TradingWizard)"})
                r.raise_for_status()
                content = r.content
            else:
                content = fetch(url)
            rows += parse_rss(content, source, group)
        except Exception:
            continue
    if not rows:
        raise RuntimeError("no headline feed answered")
    return sorted(rows, key=lambda h: h["ts"] or 0, reverse=True)


def latest(fetch=None, *, ttl_s: float = 1200, cache_dir=None) -> dict:
    if fetch is not None:
        try:
            return {"headlines": fetch_all(fetch), "fetched_at": None, "stale": False, "error": None}
        except Exception as exc:
            return {"headlines": [], "fetched_at": None, "stale": True, "error": str(exc)[:160]}
    from src.context.disk_cache import DEFAULT_DIR, cached
    c = cached("headlines", ttl_s, fetch_all, cache_dir=cache_dir or DEFAULT_DIR)
    return {"headlines": c["data"] or [], "fetched_at": c["fetched_at"], "stale": c["stale"], "error": c["error"]}


def for_symbol(rows: list[dict], keywords: list[str], limit: int = 8) -> list[dict]:
    """Headlines mentioning the market (by keyword), newest first."""
    pat = [k.lower() for k in keywords]
    return [h for h in rows if any(k in h["headline"].lower() for k in pat)][:limit]
