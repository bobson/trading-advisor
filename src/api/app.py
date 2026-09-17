"""Phase 24 — FastAPI backend: the JSON contract the Svelte frontend (Phase 25) consumes.

Endpoints:
  GET /health              -> {"status": "ok"}
  GET /pairs               -> [{symbol, asset_class, label}]     (the selectable markets)
  GET /timeframes          -> ["15m","30m","1h","4h","1d"]
  GET /analysis            -> full payload for one symbol+timeframe: candles + overlays +
                              facts + confluence (+ explanation/context when asked)

CREDIT/LATENCY GUARD: `explain` and `context` default to FALSE, so a plain /analysis call makes
NO Claude call and no extra network — set `?explain=true` / `?context=true` to opt in. A small
in-memory TTL cache keyed by the query avoids recomputing on rapid repeats. Verify everything
in the auto-generated /docs before wiring the frontend.
"""

from __future__ import annotations

import logging
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from src.backtest.base_rate import load_base_rates
from src.config import load_config
from src.context import gather_context
from src.data.registry import list_pairs
from src.derivatives import gather_derivatives
from src.service.analyze import advise
from src.service.serialize import serialize_analysis

cfg = load_config()
BASE_RATES = load_base_rates()  # precomputed track record (data/base_rates.json); {} if absent

app = FastAPI(title="Trading Advisor API", version="1.0")
# CORS restricted to the configured origins (default: the local Svelte dev server), NOT "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

if not cfg.api_key:
    logging.getLogger(__name__).warning(
        "API is running WITHOUT an API_KEY — fine for local use, but set API_KEY in .env "
        "before exposing it publicly (the explain endpoint spends Claude credits)."
    )

_CACHE: dict[tuple, tuple[float, dict]] = {}
_TTL_SECONDS = 60

# --- #8 lockdown: auth + per-client rate limit (in-memory, no extra deps) ---
_HITS: dict[str, int] = {}


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """When API_KEY is configured, every data endpoint needs a matching X-API-Key header."""
    if cfg.api_key and x_api_key != cfg.api_key:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


def rate_limit(request: Request) -> None:
    """Fixed-window per-client cap (a backstop against abuse / runaway loops)."""
    limit = cfg.rate_limit_per_min
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    key = f"{ip}:{window}"
    count = _HITS.get(key, 0) + 1
    _HITS[key] = count
    if count == 1:  # new window -> drop stale windows
        for k in [k for k in _HITS if not k.endswith(f":{window}")]:
            _HITS.pop(k, None)
    if count > limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded — slow down")


_GUARDS = [Depends(rate_limit), Depends(require_api_key)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/pairs", dependencies=_GUARDS)
def pairs() -> list[dict]:
    return [{"symbol": p.symbol, "asset_class": p.asset_class, "label": p.label} for p in list_pairs()]


@app.get("/timeframes", dependencies=_GUARDS)
def timeframes() -> list[str]:
    return list(cfg.timeframes.selectable)


@app.get("/analysis", dependencies=_GUARDS)
def analysis(
    symbol: str = Query(..., description="e.g. BTC/USDT"),
    timeframe: str = Query("1h"),
    explain: bool = Query(False, description="call Claude for the explanation (uses API credit)"),
    context: bool = Query(False, description="also fetch sentiment/positioning (extra network)"),
    limit: int = Query(500, ge=50, le=5000, description="candles returned for the chart"),
    as_of_bar: int | None = Query(
        None, ge=0,
        description="historical scrubbing: recompute as of bar N only (look-ahead-safe)"),
) -> dict:
    # `as_of_bar` MUST be in the cache key — otherwise scrubbing to a new bar returns a stale
    # payload for a different bar. context/derivatives are skipped when scrubbing (they're
    # current-state and would be anachronistic against a historical bar).
    key = (symbol, timeframe, explain, context, limit, as_of_bar)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]

    scrubbing = as_of_bar is not None
    try:
        ctx = gather_context(symbol, cfg) if (context and not scrubbing) else None
        deriv = gather_derivatives(symbol, cfg) if (context and not scrubbing) else None
        result = advise(symbol, timeframe, cfg, context=ctx, derivatives=deriv,
                        explain_enabled=explain, refresh_stale=not scrubbing,
                        base_rate=BASE_RATES.get(f"{symbol}|{timeframe}"),
                        as_of_bar=as_of_bar)
    except NotImplementedError as exc:  # e.g. forex before Phase 26
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:  # data fetch / analysis failure
        raise HTTPException(status_code=502, detail=f"analysis failed: {exc}")

    payload = serialize_analysis(result, limit=limit)
    payload["as_of_bar"] = as_of_bar        # echo so the scrub UI knows the current position
    _CACHE[key] = (now, payload)
    return payload
