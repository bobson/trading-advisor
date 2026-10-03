"""ROADMAP D3 — one disk cache for the live context feeds (calendar, headlines), shared by every
process (API workers, the morning job). Unofficial feeds throttle clients that hammer them, so each
feed is fetched at most once per TTL; on a failed fetch the last good copy is served, marked stale
with its age. Only the LIVE path uses it — tests inject their own fetch and bypass it entirely.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_DIR = Path("data/context_cache")


def cached(name: str, ttl_s: float, loader, *, cache_dir: Path = DEFAULT_DIR, now: float | None = None) -> dict:
    """{"data", "fetched_at", "stale", "error"}. `loader()` returns JSON-able data or raises."""
    now = now or time.time()
    path = Path(cache_dir) / f"{name}.json"
    old = None
    if path.exists():
        try:
            old = json.loads(path.read_text())
        except Exception:
            old = None
    if old and now - old["fetched_at"] < ttl_s:
        return {"data": old["data"], "fetched_at": old["fetched_at"], "stale": False, "error": None}
    try:
        data = loader()
    except Exception as exc:
        if old:
            return {"data": old["data"], "fetched_at": old["fetched_at"], "stale": True, "error": str(exc)[:160]}
        return {"data": None, "fetched_at": None, "stale": True, "error": str(exc)[:160]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": int(now), "data": data}))
    return {"data": data, "fetched_at": int(now), "stale": False, "error": None}
