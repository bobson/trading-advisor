"""ROADMAP D3 — the economic calendar, including central-bank and commodity events, keyless.

Source: the Forex Factory weekly JSON (`ff_calendar_thisweek.json`) — UNOFFICIAL, so it is cached on
disk (`disk_cache`, ~1 h), parsed defensively, and the app works without it. Each event has a
currency, a time (with a UTC offset — converted to UTC here), an impact (High / Medium / Low /
Holiday), the consensus ("forecast") and the previous figure. The feed has NO actual figure, and it
covers only the current week (Sunday–Saturday, New York): over the weekend next week's events are not
visible yet.

Central-bank and commodity events are picked out of the same feed by name.
"""

from __future__ import annotations

import re

import pandas as pd

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE = "Forex Factory weekly calendar (unofficial)"

_CENTRAL_BANK = re.compile(r"rate statement|monetary policy|fomc|interest rate|official bank rate|cash rate|"
                           r"policy rate|refinancing rate|press conference|bank rate|rate decision|"
                           r"\b(?:ecb|boe|boj|rba|rbnz|snb|boc|fed)\b|minutes|governor .* speaks|"
                           r"president .* speaks|chair .* speaks", re.IGNORECASE)
_COMMODITY = re.compile(r"crude oil|natural gas|gasoline|oil inventor|eia|opec|rig count|gold", re.IGNORECASE)


def kind_of(title: str, impact: str) -> str:
    if impact.lower() == "holiday":
        return "holiday"
    if _CENTRAL_BANK.search(title):
        return "central_bank"
    if _COMMODITY.search(title):
        return "commodity"
    return "data"


def parse(payload) -> list[dict]:
    """Forex Factory rows -> events with UTC times, sorted. Malformed rows are skipped, never fatal."""
    out = []
    for r in payload or []:
        try:
            t = pd.Timestamp(r["date"]).tz_convert("UTC")
        except Exception:
            continue
        impact = str(r.get("impact") or "").strip() or "Low"
        title = str(r.get("title") or "").strip()
        out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ts": int(t.timestamp()),
                    "currency": str(r.get("country") or "").upper(), "title": title, "impact": impact,
                    "forecast": (r.get("forecast") or None), "previous": (r.get("previous") or None),
                    "actual": r.get("actual") or None, "kind": kind_of(title, impact)})
    return sorted(out, key=lambda e: e["ts"])


def fetch_week(fetch=None) -> list[dict]:
    """This week's events (raises on a failed fetch; the caller caches / degrades)."""
    if fetch is None:
        import requests
        resp = requests.get(FF_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0 (TradingWizard)"})
        resp.raise_for_status()
        payload = resp.json()
    else:
        payload = fetch(FF_URL)
    return parse(payload)


def week(fetch=None, *, ttl_s: float = 3600, cache_dir=None) -> dict:
    """{"events", "fetched_at", "stale", "error", "source"} — disk-cached in the live path."""
    if fetch is not None:                                     # tests: no disk cache
        try:
            return {"events": fetch_week(fetch), "fetched_at": None, "stale": False, "error": None, "source": SOURCE}
        except Exception as exc:
            return {"events": [], "fetched_at": None, "stale": True, "error": str(exc)[:160], "source": SOURCE}
    from src.context.disk_cache import DEFAULT_DIR, cached
    c = cached("calendar_week", ttl_s, fetch_week, cache_dir=cache_dir or DEFAULT_DIR)
    return {"events": c["data"] or [], "fetched_at": c["fetched_at"], "stale": c["stale"], "error": c["error"],
            "source": SOURCE}
