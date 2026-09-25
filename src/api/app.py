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
import os
import time
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.backtest.base_rate import load_base_rates
from src.config import load_config
from src.context import gather_context
from src.data.registry import all_pairs
from src.derivatives import gather_derivatives
from src.service.analyze import advise
from src.service.serialize import serialize_analysis

cfg = load_config()
BASE_RATES = load_base_rates()
# ROADMAP B2: measured detector precision (scripts/eval_detectors.py --write); {} until it has run.
from src.labels.evaluate import load_reliability as _load_reliability  # noqa: E402
RELIABILITY = _load_reliability()  # precomputed track record (data/base_rates.json); {} if absent

app = FastAPI(title="Trading Advisor API", version="1.0")
# CORS restricted to the configured origins (default: the local Svelte dev server), NOT "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.allowed_origins,
    # GET for reads; POST/PUT/DELETE for paper trades and gold labels (was GET-only, which made the
    # browser's preflight fail for every write). Origins stay restricted to `allowed_origins`.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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
    return [{"symbol": p.symbol, "asset_class": p.asset_class, "label": p.label} for p in all_pairs()]


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
    explanation_style: str = Query(
        "brief", description="explanation mode: 'brief' (word-budgeted) or 'teaching' (fuller)"),
) -> dict:
    # `as_of_bar` and `explanation_style` MUST be in the cache key — otherwise scrubbing to a new
    # bar, or switching modes, returns a stale payload. context/derivatives are skipped when
    # scrubbing (they're current-state and would be anachronistic against a historical bar).
    key = (symbol, timeframe, explain, context, limit, as_of_bar, explanation_style)
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
                        reliability=RELIABILITY.get("table"),
                        verdict_records=_verdict_rows(), pattern_records=_encyclopedia_top_rows(),
                        as_of_bar=as_of_bar, explanation_style=explanation_style)
    except NotImplementedError as exc:  # e.g. forex before Phase 26
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:  # data fetch / analysis failure
        raise HTTPException(status_code=502, detail=f"analysis failed: {exc}")

    payload = serialize_analysis(result, limit=limit)
    payload["as_of_bar"] = as_of_bar        # echo so the scrub UI knows the current position
    # The bar index this payload was ACTUALLY computed at (as_of_bar is clamped up to a warm-up
    # floor, and None means the latest bar). Labels are keyed to this, never to the slider value.
    payload["bar_index"] = len(result.df) - 1
    # Each detected pattern carries its measured record (encyclopedia, same timeframe, all markets) —
    # the history beside the find, rendered by the UI, never written by Claude.
    _attach_records(payload.get("chart", {}).get("overlays", {}).get("patterns", []), timeframe)
    _CACHE[key] = (now, payload)
    return payload


@app.get("/risk", dependencies=_GUARDS)
def risk(
    win_rate: float = Query(..., ge=0.0, le=1.0, description="measured win rate (0–1)"),
    payoff_ratio: float = Query(1.0, gt=0.0, description="avg win / avg loss"),
    risk_fraction: float = Query(0.01, gt=0.0, lt=1.0, description="fraction of account risked per trade"),
    account: float = Query(10_000.0, gt=0.0),
    entry: float | None = Query(None, gt=0.0),
    stop: float | None = Query(None, gt=0.0),
    drawdown: float = Query(0.5, gt=0.0, lt=1.0, description="drawdown that counts as ruin"),
    target: float = Query(2.0, gt=1.0, description="equity multiple that counts as success"),
) -> dict:
    """Feature 9 — the survival maths for the calculator: analytic + Monte Carlo risk of ruin,
    Kelly sizing with the drawdown pain, the risk×win-rate ruin table, and (if entry/stop given)
    a sized position. Pure math, no market data — deliberately sobering, not reassuring."""
    from src.risk import ruin as R

    out: dict = {
        "inputs": {"win_rate": win_rate, "payoff_ratio": payoff_ratio, "risk_fraction": risk_fraction,
                   "account": account, "drawdown": drawdown, "target": target},
        "ruin": {
            "analytic": R.risk_of_ruin_analytic(win_rate, payoff_ratio, risk_fraction, drawdown=drawdown, target=target),
            "monte_carlo": asdict(R.risk_of_ruin_mc(win_rate, payoff_ratio, risk_fraction,
                                                    drawdown=drawdown, target=target, n_paths=4000, seed=1)),
        },
        "kelly": asdict(R.kelly(win_rate, payoff_ratio)),
        "kelly_drawdowns": R.kelly_drawdown_pain(win_rate, payoff_ratio, n_paths=2000, seed=1),
        "table": R.ruin_table(payoff_ratio, drawdown=drawdown, target=target),
    }
    if entry is not None and stop is not None:
        try:
            out["position"] = asdict(R.position_size(account, entry, stop, risk_fraction))
        except ValueError as exc:
            out["position_error"] = str(exc)
    return out


@app.get("/risk/measured", dependencies=_GUARDS)
def risk_measured(symbol: str = Query(...), timeframe: str = Query("1h")) -> dict:
    """Measured win rate (and payoff ratio once the journal exists) for a pair, with a Wilson
    interval and a `thin` flag when the sample is too small to trust a point estimate."""
    from src.risk.ruin import gather_measured_stats
    return asdict(gather_measured_stats(symbol, timeframe, base_rates=BASE_RATES))


@app.get("/risk/coin_flip", dependencies=_GUARDS)
def risk_coin_flip(
    symbol: str = Query(...), timeframe: str = Query("1h"),
    entry: float = Query(..., gt=0.0), stop: float = Query(..., gt=0.0),
    payoff_ratio: float = Query(1.0, gt=0.0),
) -> dict:
    """ROADMAP A7 — the calculator's DEFAULT win rate: a coin flip minus this instrument's
    round-trip costs (Feature-10 cost model; slippage from its current ATR), in units of the risk.
    Cache-first candles; no Claude call."""
    from src.data.registry import get_candles
    from src.indicators.features import COL_ATR, add_features
    from src.risk.coin_flip import cost_adjusted_coin_flip

    feat = add_features(get_candles(symbol, timeframe, cfg), cfg)
    atr, close = feat[COL_ATR].iloc[-1], float(feat["close"].iloc[-1])
    atr_pct = 0.0 if atr != atr else float(atr) / close
    try:
        return cost_adjusted_coin_flip(symbol, timeframe, cfg, entry=entry, stop=stop,
                                       payoff_ratio=payoff_ratio, atr_pct=atr_pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- Paper-trading simulator (SQLite `trades`; live spot fills; NO Claude call) ----------------
_TRADES_DB = None   # None -> default data/wizard.db; tests point this at a tmp path


def _trades_conn():
    from src.store.db import connect
    return connect(_TRADES_DB) if _TRADES_DB else connect()


class TradeIn(BaseModel):
    symbol: str
    side: str                      # "buy" | "sell"
    amount_usd: float
    timeframe: str | None = None
    last_close: float | None = None    # fallback fill if the live ticker fetch fails
    snapshot: dict | None = None       # {bias, confidence, agreeing_categories, explanation?}
    note: str | None = None


@app.post("/trades", dependencies=_GUARDS)
def post_trade(body: TradeIn) -> dict:
    """Record a paper Buy/Sell: fetch a LIVE spot fill and open or close the position. One position
    at a time — the same side while open is a 400. No re-analysis, no Claude call."""
    from src.trading import paper
    conn = _trades_conn()
    try:
        result = paper.record(conn, body.symbol, body.timeframe, body.side, body.amount_usd, cfg,
                              last_close=body.last_close, snapshot=body.snapshot, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        state = {"trades": paper.list_trades(conn, body.symbol), "pnl": paper.pnl_summary(conn, body.symbol)}
        conn.close()
    return {"result": result, **state}


@app.get("/trades", dependencies=_GUARDS)
def get_trades(symbol: str = Query(...)) -> dict:
    from src.trading import paper
    conn = _trades_conn()
    try:
        return {"trades": paper.list_trades(conn, symbol), "pnl": paper.pnl_summary(conn, symbol)}
    finally:
        conn.close()


@app.get("/trades/position", dependencies=_GUARDS)
def get_position(symbol: str = Query(...), last_close: float | None = Query(None)) -> dict:
    """Open position + unrealized PnL at a live price (falls back to `last_close`); flat -> no fetch."""
    from src.trading import paper
    conn = _trades_conn()
    try:
        if paper._open_trade(conn, symbol) is None:
            return {"flat": True}
        price, source = paper.live_price(symbol, cfg, last_close=last_close)
        pos = paper.position(conn, symbol, price=price)
        pos["price_source"] = source
        return pos
    finally:
        conn.close()


@app.get("/trades/baseline", dependencies=_GUARDS)
def get_trades_baseline(symbol: str = Query(...)) -> dict:
    """ROADMAP A7 — what luck alone produces with your exposure: 1000 random-entry records (random
    time, random side, your holding times and sizes) on the same instrument."""
    from src.trading.baseline import baseline_for_symbol
    conn = _trades_conn()
    try:
        return baseline_for_symbol(conn, symbol, cfg)
    finally:
        conn.close()


@app.delete("/trades/{trade_id}", dependencies=_GUARDS)
def delete_trade(trade_id: int) -> dict:
    from src.trading import paper
    conn = _trades_conn()
    try:
        paper.delete_trade(conn, trade_id)
        return {"deleted": trade_id}
    finally:
        conn.close()


# --- ROADMAP B1: detector gold set (SQLite `gold_labels`; the user's own labels) -------------------
class GoldLabelIn(BaseModel):
    symbol: str
    timeframe: str
    bar: int
    bar_time: int | None = None
    labels: dict


@app.get("/labels/types", dependencies=_GUARDS)
def label_types() -> dict:
    from src.labels.gold import DETECTOR_TYPES, EXTRA_TYPES, ZONE_ROLES
    return {"detector_types": DETECTOR_TYPES, "extra_types": EXTRA_TYPES, "zone_roles": list(ZONE_ROLES)}


@app.get("/labels", dependencies=_GUARDS)
def get_labels() -> dict:
    """Every labelled chart (newest first) + the counts summary."""
    from src.labels import gold
    conn = _trades_conn()
    try:
        return {"labels": gold.list_all(conn), "summary": gold.summary(conn)}
    finally:
        conn.close()


@app.get("/labels/one", dependencies=_GUARDS)
def get_label(symbol: str = Query(...), timeframe: str = Query(...), bar: int = Query(...)) -> dict:
    from src.labels import gold
    conn = _trades_conn()
    try:
        return {"label": gold.load(conn, symbol, timeframe, bar)}
    finally:
        conn.close()


@app.put("/labels", dependencies=_GUARDS)
def put_label(body: GoldLabelIn) -> dict:
    from src.labels import gold
    conn = _trades_conn()
    try:
        row = gold.save(conn, body.symbol, body.timeframe, body.bar, body.labels, bar_time=body.bar_time)
        return {"label": row, "summary": gold.summary(conn)}
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.delete("/labels/{label_id}", dependencies=_GUARDS)
def delete_label(label_id: int) -> dict:
    from src.labels import gold
    conn = _trades_conn()
    try:
        gold.delete(conn, label_id)
        return {"deleted": label_id, "summary": gold.summary(conn)}
    finally:
        conn.close()


# --- ROADMAP B3: Empirical Pattern Encyclopedia (reads the precomputed `encyclopedia_stats`) --------
@app.get("/encyclopedia", dependencies=_GUARDS)
def encyclopedia_index() -> dict:
    """One summary line per pattern type × timeframe (symbol='all', regime='all', split='all'), plus
    when the table was built. Empty `types` means scripts/build_encyclopedia.py hasn't been run."""
    from src.research.encyclopedia import load_rows
    conn = _trades_conn()
    try:
        rows = load_rows(conn)
    finally:
        conn.close()
    top = [r for r in rows if r["symbol"] == "all" and r["regime"] == "all" and r["split"] == "all"]
    return {"built_at": max((r["built_at"] for r in rows), default=None),
            "params": top[0]["params"] if top else {},
            "types": sorted(({k: r[k] for k in r if k not in ("examples", "params")} for r in top),
                            key=lambda r: (r["pattern_type"], r["timeframe"]))}


@app.get("/encyclopedia/{pattern_type}", dependencies=_GUARDS)
def encyclopedia_page(pattern_type: str) -> dict:
    """Everything for one pattern type: every stored row (per timeframe × symbol × regime × split),
    the textbook claim from docs/patterns-research.md, and the detector's measured precision (B2 —
    'unmeasured' until gold labels exist)."""
    from src.research.encyclopedia import load_rows
    from src.research.scanner import quality_meaning
    from src.research.textbook import textbook_claim
    conn = _trades_conn()
    try:
        rows = load_rows(conn, pattern_type)
    finally:
        conn.close()
    table = RELIABILITY.get("table") or {}
    tfs = sorted({r["timeframe"] for r in rows})
    precision = {tf: table.get(f"{pattern_type}|{tf}") or {"precision": None, "n": 0, "status": "unmeasured"}
                 for tf in tfs}
    return {"pattern_type": pattern_type, "rows": rows, "textbook": textbook_claim(pattern_type),
            "detector_precision": precision,
            "quality_meaning": {tf: quality_meaning(rows, pattern_type, tf) for tf in tfs}}     # B5


# --- Pattern scanner + records beside every find ---------------------------------------------------
def _encyclopedia_top_rows() -> list[dict]:
    from src.research.encyclopedia import load_rows
    conn = _trades_conn()
    try:
        return [r for r in load_rows(conn) if r["symbol"] == "all" and r["regime"] == "all"
                and (r["split"] == "all" or r["split"].startswith("quality="))]      # + B5 quality bands
    finally:
        conn.close()


def _attach_records(patterns: list[dict], timeframe: str) -> None:
    if not patterns:
        return
    from src.research.scanner import pattern_quality, pattern_record
    rows = _encyclopedia_top_rows()
    for p in patterns:
        p["record"] = pattern_record(rows, p["type"], timeframe)
        p["quality_band"] = pattern_quality(rows, p["type"], timeframe, p.get("quality"))


_SCAN_CACHE: dict = {}
_SCAN_TTL = 300.0


@app.get("/scan", dependencies=_GUARDS)
def scan_patterns(timeframes: str = Query("1d", description="comma list, e.g. 1d,4h,1h")) -> dict:
    """Every registered pair × the given timeframes: patterns that broke out in the last few candles,
    are forming (closest to breaking out first) or are in play — each with its encyclopedia record.
    Candles older than one bar are refreshed (cache-first otherwise); a market that can't load is
    skipped and listed. Cached 5 minutes. No Claude call."""
    from src.data.registry import get_candles, list_pairs
    from src.research.scanner import scan
    from src.service.analyze import _timeframe_minutes

    tfs = [t for t in timeframes.split(",") if t]
    key = tuple(tfs)
    now = time.time()
    hit = _SCAN_CACHE.get(key)
    if hit and now - hit[0] < _SCAN_TTL:
        return hit[1]
    markets = [(p.symbol, tf) for tf in tfs for p in list_pairs()]
    result = scan(markets, cfg,
                  lambda s, tf: get_candles(s, tf, cfg, stale_after_minutes=_timeframe_minutes(tf)),
                  _encyclopedia_top_rows())
    result["scanned_at"] = int(now)
    _SCAN_CACHE[key] = (now, result)
    return result


def _verdict_rows() -> list[dict]:
    """ROADMAP B4: the precomputed verdict records ([] until scripts/build_verdict_records.py runs)."""
    from src.research.verdict_records import load
    conn = _trades_conn()
    try:
        return load(conn)
    finally:
        conn.close()


# --- ROADMAP A8: the morning report (forward record) ----------------------------------------------
# The morning job writes these tables; the API only reads them, plus a "run now" that starts the SAME
# script in its own process (its file lock stops overlap with the 08:00 timer run).
_MORNING_DB = os.getenv("MORNING_DB")          # None -> the app DB (data/wizard.db); set for a scratch DB


def _morning_db() -> str:
    return _MORNING_DB or _TRADES_DB or "data/wizard.db"


@app.get("/morning", dependencies=_GUARDS)
def morning(date: str | None = None) -> dict:
    """The morning report for `date` (a Europe/Skopje run date; default = the latest run)."""
    from src.forward.record import connect as forward_connect
    from src.forward.report import build_report
    conn = forward_connect(_morning_db())
    try:
        return build_report(conn, cfg, date)
    finally:
        conn.close()


@app.post("/morning/run", dependencies=_GUARDS)
def morning_run() -> dict:
    """Manual trigger: starts scripts/morning_report.py in the background (returns at once). The
    script's lock makes a second concurrent run exit without doing anything."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    subprocess.Popen([sys.executable, str(root / "scripts" / "morning_report.py"), "--db", _morning_db(),
                      "--trigger", "api"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {"started": True}
