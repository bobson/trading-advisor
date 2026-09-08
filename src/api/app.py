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

import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_config
from src.context import gather_context
from src.data.registry import list_pairs
from src.derivatives import gather_derivatives
from src.service.analyze import advise
from src.service.serialize import serialize_analysis

cfg = load_config()

app = FastAPI(title="Trading Advisor API", version="1.0")
# The Svelte dev server runs on a different origin; allow it (tighten for production if needed).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_CACHE: dict[tuple, tuple[float, dict]] = {}
_TTL_SECONDS = 60


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/pairs")
def pairs() -> list[dict]:
    return [{"symbol": p.symbol, "asset_class": p.asset_class, "label": p.label} for p in list_pairs()]


@app.get("/timeframes")
def timeframes() -> list[str]:
    return list(cfg.timeframes.selectable)


@app.get("/analysis")
def analysis(
    symbol: str = Query(..., description="e.g. BTC/USDT"),
    timeframe: str = Query("1h"),
    explain: bool = Query(False, description="call Claude for the explanation (uses API credit)"),
    context: bool = Query(False, description="also fetch sentiment/positioning (extra network)"),
    limit: int = Query(500, ge=50, le=5000, description="candles returned for the chart"),
) -> dict:
    key = (symbol, timeframe, explain, context, limit)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]

    try:
        ctx = gather_context(symbol, cfg) if context else None
        deriv = gather_derivatives(symbol, cfg) if context else None
        result = advise(symbol, timeframe, cfg, context=ctx, derivatives=deriv, explain_enabled=explain)
    except NotImplementedError as exc:  # e.g. forex before Phase 26
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:  # data fetch / analysis failure
        raise HTTPException(status_code=502, detail=f"analysis failed: {exc}")

    payload = serialize_analysis(result, limit=limit)
    _CACHE[key] = (now, payload)
    return payload
