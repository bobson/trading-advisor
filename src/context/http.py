"""Shared HTTP helper for the Phase 21 context sources.

A single small `get_json` with a HARD timeout — graceful degradation against a live network
means a slow endpoint must fail fast (and be caught by the caller) rather than stalling the
whole CLI/API call. Callers wrap this in `try/except Exception` and degrade to None/[].
"""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT = 5  # seconds — fail fast so context never hangs the pipeline


def get_json(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT):
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
