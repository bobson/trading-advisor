"""Phase 21 — crypto Fear & Greed sentiment (alternative.me, no API key).

A single 0–100 number + label. This is the one context source that needs no key, so it's the
one actually verified against the live API this phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.context.http import get_json

FNG_URL = "https://api.alternative.me/fng/"


@dataclass
class FearGreed:
    value: int      # 0 (extreme fear) .. 100 (extreme greed)
    label: str      # e.g. "Fear", "Greed"
    as_of: str      # date the reading is for (so stale sentiment can't look present-tense)


def fetch_fear_greed(fetch=None) -> FearGreed | None:
    """Latest crypto Fear & Greed, or None on any failure (network/shape). `fetch` is
    injectable for offline tests."""
    fetch = fetch or get_json
    try:
        data = fetch(FNG_URL)
        row = data["data"][0]
        as_of = datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d")
        return FearGreed(int(row["value"]), str(row["value_classification"]), as_of)
    except Exception:
        return None
