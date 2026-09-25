"""ROADMAP A8 — the forward record: freeze the engine's reads every morning, judge them later.

A backtest can always be accused of hindsight; this can't. Each morning (08:00 Europe/Skopje, see
`schedule.py`) `run_morning`:

  0. fetches every watchlist market (plus any market with a read still waiting) — CLOSED candles
     only, by time: a bar is kept only if its open time + the timeframe is at or before now;
  1. REVIEW — resolves every past read whose horizon of closed bars has ended, under the rule
     version stored on it (`rule.py`), plus its coin-flip baseline;
  2. READ — runs the engine on each symbol × timeframe and FREEZES the read. `freeze_read` gets
     only candles + config — it never sees the database — so the review can't feed the read;
  3. (optional) one Claude multi-timeframe synthesis per symbol, from today's facts only.

Idempotency lives in the schema, not in Python (the timer and the API's "run now" are separate
processes): UNIQUE(run_date, symbol, timeframe) stops a second same-day run adding reads,
UNIQUE(symbol, timeframe, bar_time) stops a read with no new closed candle (forex, gold, oil at the
weekend), inserts are INSERT OR IGNORE and the review is an UPDATE … WHERE outcome IS NULL.
Missed mornings become `gap` rows — never backfilled (that would turn the record into a backtest).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.config import Config
from src.forward.rule import (
    BEARISH,
    BULLISH,
    DIRECTIONAL,
    RANGE,
    RULE_TEXT,
    RULE_VERSION,
    RULES,
    levels_for,
    resolve_baseline,
    rule_hash,
)
from src.forward.schedule import run_date as _run_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_rules (
    version INTEGER PRIMARY KEY, text TEXT NOT NULL, hash TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS forward_runs (
    run_date    TEXT PRIMARY KEY,          -- local Europe/Skopje date
    status      TEXT NOT NULL,             -- running | ok | partial | failed | gap
    trigger     TEXT,                      -- schedule | manual | api
    started_at  INTEGER, finished_at INTEGER,
    attempts    INTEGER NOT NULL DEFAULT 0,
    new_reads   INTEGER NOT NULL DEFAULT 0,
    resolved    INTEGER NOT NULL DEFAULT 0,
    skipped     TEXT,                      -- JSON [{symbol, timeframe, reason}]
    engine_commit TEXT
);
CREATE TABLE IF NOT EXISTS forward_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL, created_at INTEGER NOT NULL,
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
    bar_time INTEGER NOT NULL,              -- the last CLOSED bar's open time, epoch s UTC
    price REAL NOT NULL, atr REAL,
    tier TEXT NOT NULL, bias TEXT NOT NULL, aligned INTEGER NOT NULL, agreeing INTEGER NOT NULL,
    confidence REAL,
    read_kind TEXT NOT NULL,                -- directional | range
    direction TEXT,                         -- bullish | bearish (directional reads only)
    invalidation REAL, next_level REAL,
    near_above REAL, near_below REAL, range_low REAL, range_high REAL,
    source_above TEXT, source_below TEXT,   -- zone | atr
    sup_lower REAL, sup_upper REAL, res_lower REAL, res_upper REAL,
    patterns TEXT,                          -- JSON [{type, direction, lifecycle}]
    facts_hash TEXT NOT NULL,
    engine_commit TEXT, engine_dirty INTEGER, config_hash TEXT,
    horizon INTEGER NOT NULL, rule_version INTEGER NOT NULL,
    outcome TEXT, resolved_run_date TEXT, resolved_at INTEGER,
    baseline_direction TEXT, baseline_outcome TEXT,
    UNIQUE (run_date, symbol, timeframe),
    UNIQUE (symbol, timeframe, bar_time)
);
CREATE TABLE IF NOT EXISTS forward_syntheses (
    run_date TEXT NOT NULL, symbol TEXT NOT NULL, text TEXT NOT NULL, model TEXT, created_at INTEGER,
    PRIMARY KEY (run_date, symbol)
);
"""

# Skip reasons that are normal, not failures (a run with only these is still "ok").
NO_NEW_CANDLE = "no new closed candle since the last read"
ALREADY_READ = "already read today"
_BENIGN = (NO_NEW_CANDLE, ALREADY_READ)

_SECRETS = {"anthropic_api_key", "finnhub_api_key", "twelvedata_api_key", "oanda_api_token", "webhook_url",
            "api_key", "allowed_origins", "rate_limit_per_min"}


def connect(path: str | Path = "data/wizard.db"):
    """The wizard DB with the forward tables, in WAL mode with a busy timeout: the API reads while
    the morning job writes, from separate processes."""
    from src.store.db import connect as base_connect
    conn = base_connect(path)
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    for v, text in RULE_TEXT.items():
        conn.execute("INSERT OR IGNORE INTO forward_rules VALUES (?,?,?,?)", (v, text, rule_hash(v), int(time.time())))
    conn.commit()
    return conn


# --- engine version -------------------------------------------------------------------------------

def engine_info(cfg: Config, repo: Path | None = None) -> dict:
    """The git commit (+ whether tracked files differ from it) and a hash of the loaded config —
    editing config.yaml changes the engine without changing the commit."""
    repo = repo or Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=repo, capture_output=True,
                                text=True, timeout=5).stdout.strip() or "unknown"
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=repo, timeout=5).returncode != 0
    except Exception:                                   # pragma: no cover - no git on the machine
        commit, dirty = "unknown", False
    conf = cfg.model_dump(mode="json", exclude=_SECRETS)
    return {"commit": commit, "dirty": dirty,
            "config_hash": hashlib.sha256(json.dumps(conf, sort_keys=True).encode()).hexdigest()[:12]}


# --- candles ----------------------------------------------------------------------------------------

def _tf_delta(timeframe: str) -> pd.Timedelta:
    n, unit = int(timeframe[:-1]), timeframe[-1]
    return pd.Timedelta(**{{"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[unit]: n})


def closed_only(df: pd.DataFrame, timeframe: str, now: datetime) -> pd.DataFrame:
    """Keep only bars that have CLOSED by `now` (open time + timeframe <= now), whatever the
    provider did (Twelve Data includes the forming bar; the crypto path drops its last bar by
    position, which is a guess)."""
    return df[df.index + _tf_delta(timeframe) <= pd.Timestamp(now)]


def default_candles(cfg: Config, *, sleep=time.sleep):
    """Live candles, re-fetched every run, with a pause between Twelve Data calls (free plan: 8/min)."""
    from src.data.base import FOREX
    from src.data.registry import PROVIDER_OVERRIDE, asset_class_for, get_candles
    last = {"t": 0.0}

    def load(symbol: str, timeframe: str) -> pd.DataFrame:
        if asset_class_for(symbol) == FOREX and symbol not in PROVIDER_OVERRIDE:
            wait = cfg.morning_report.twelvedata_pause_s - (time.monotonic() - last["t"])
            if last["t"] and wait > 0:
                sleep(wait)
            last["t"] = time.monotonic()
        return get_candles(symbol, timeframe, cfg, refresh=True)
    return load


# --- 2. READ (never sees the database) ---------------------------------------------------------------

def facts_hash(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def freeze_read(df: pd.DataFrame, symbol: str, timeframe: str, cfg: Config) -> tuple[dict, str]:
    """The engine's read of the last CLOSED bar in `df`, as a frozen row (+ the facts text for the
    optional synthesis). Candles and config in, nothing else — no outcomes, no records."""
    from src.service.analyze import advise
    res = advise(symbol, timeframe, cfg, df=df, explain_enabled=False)
    f = res.facts
    conf, tier = f["confluence"], f["situation"]["tier"]
    bias = conf["bias"]
    directional = tier != "no_setup" and bias in (BULLISH, BEARISH)
    sr = f.get("support_resistance") or {}
    sup, resist = sr.get("nearest_support"), sr.get("nearest_resistance")
    atr = (f.get("volatility") or {}).get("atr")
    close = float(f["market"]["last_close"])
    lv = levels_for(bias if directional else None, close, atr, sup, resist)
    row = {
        "symbol": symbol, "timeframe": timeframe, "bar_time": int(pd.Timestamp(df.index[-1]).timestamp()),
        "price": close, "atr": atr, "tier": tier, "bias": bias, "aligned": int(bool(conf["triggered"])),
        "agreeing": int(conf["agreeing_categories"]), "confidence": conf.get("confidence"),
        "read_kind": DIRECTIONAL if directional else RANGE, "direction": bias if directional else None,
        **{k: lv[k] for k in ("invalidation", "next_level", "near_above", "near_below", "range_low",
                              "range_high", "source_above", "source_below")},
        "sup_lower": sup["lower"] if sup else None, "sup_upper": sup["upper"] if sup else None,
        "res_lower": resist["lower"] if resist else None, "res_upper": resist["upper"] if resist else None,
        "patterns": json.dumps([{"type": p["type"], "direction": p["direction"], "lifecycle": p.get("lifecycle")}
                                for p in f.get("chart_patterns") or []]),
        "facts_hash": facts_hash(f),
        "horizon": cfg.morning_report.horizons[timeframe], "rule_version": RULE_VERSION,
    }
    return row, res.facts_text


# --- 1. REVIEW ---------------------------------------------------------------------------------------

def review(conn, df: pd.DataFrame, symbol: str, timeframe: str, run_date: str, now: datetime) -> int:
    """Resolve this market's waiting reads whose horizon of closed bars has fully passed. Returns
    how many were resolved. `df` must be closed-candles-only."""
    n = 0
    pending = conn.execute("SELECT * FROM forward_reads WHERE symbol=? AND timeframe=? AND outcome IS NULL",
                           (symbol, timeframe)).fetchall()
    for r in pending:
        r = dict(r)
        after = df[df.index > pd.Timestamp(r["bar_time"], unit="s", tz="UTC")]
        if len(after) < r["horizon"]:
            continue
        win = after.iloc[: r["horizon"]]
        bars = list(zip(win["high"].astype(float), win["low"].astype(float)))
        outcome = RULES[r["rule_version"]](r, bars)
        b_dir, b_out = resolve_baseline(r, bars)
        cur = conn.execute("UPDATE forward_reads SET outcome=?, resolved_run_date=?, resolved_at=?, "
                           "baseline_direction=?, baseline_outcome=? WHERE id=? AND outcome IS NULL",
                           (outcome, run_date, int(now.timestamp()), b_dir, b_out, r["id"]))
        n += cur.rowcount
    conn.commit()
    return n


# --- gaps --------------------------------------------------------------------------------------------

def record_gaps(conn, today: date) -> list[str]:
    """Every date between the last recorded run and today with no run becomes a `gap` row."""
    row = conn.execute("SELECT MAX(run_date) FROM forward_runs WHERE run_date < ?", (today.isoformat(),)).fetchone()
    if not row or not row[0]:
        return []
    gaps, d = [], date.fromisoformat(row[0]) + timedelta(days=1)
    while d < today:
        conn.execute("INSERT OR IGNORE INTO forward_runs (run_date, status) VALUES (?, 'gap')", (d.isoformat(),))
        gaps.append(d.isoformat())
        d += timedelta(days=1)
    conn.commit()
    return gaps


# --- the morning run ----------------------------------------------------------------------------------

def run_morning(cfg: Config, conn, *, now: datetime | None = None, trigger: str = "manual",
                candles_for=None, synth_client=None, engine: dict | None = None) -> dict:
    """One morning: gaps -> fetch -> REVIEW -> READ -> (synthesis). Safe to call twice a day."""
    mr = cfg.morning_report
    now = now or datetime.now(timezone.utc)
    rd = _run_date(now, mr.timezone).isoformat()
    engine = engine or engine_info(cfg)
    candles_for = candles_for or default_candles(cfg)
    gaps = record_gaps(conn, date.fromisoformat(rd))
    conn.execute("INSERT OR IGNORE INTO forward_runs (run_date, status) VALUES (?, 'running')", (rd,))
    conn.execute("UPDATE forward_runs SET status='running', trigger=?, started_at=?, attempts=attempts+1, "
                 "engine_commit=? WHERE run_date=?", (trigger, int(now.timestamp()), engine["commit"], rd))
    conn.commit()

    watch = [(s, tf) for s in mr.symbols for tf in mr.timeframes]
    waiting = [tuple(r) for r in conn.execute(
        "SELECT DISTINCT symbol, timeframe FROM forward_reads WHERE outcome IS NULL").fetchall()]
    markets = watch + [m for m in waiting if m not in watch]

    skipped: list[dict] = []
    candles: dict[tuple, pd.DataFrame] = {}
    for sym, tf in markets:                                          # 0. fetch (closed bars only)
        try:
            df = closed_only(candles_for(sym, tf), tf, now)
            if df.empty:
                raise ValueError("no closed candles")
            candles[(sym, tf)] = df
        except Exception as exc:
            skipped.append({"symbol": sym, "timeframe": tf, "reason": f"data: {str(exc)[:160]}"})

    resolved = sum(review(conn, df, sym, tf, rd, now) for (sym, tf), df in candles.items())   # 1. REVIEW

    new_reads, texts = 0, {}                                          # 2. READ
    for sym, tf in watch:
        df = candles.get((sym, tf))
        if df is None:
            continue
        bar_time = int(pd.Timestamp(df.index[-1]).timestamp())
        if conn.execute("SELECT 1 FROM forward_reads WHERE run_date=? AND symbol=? AND timeframe=?",
                        (rd, sym, tf)).fetchone():
            skipped.append({"symbol": sym, "timeframe": tf, "reason": ALREADY_READ})
            continue
        if conn.execute("SELECT 1 FROM forward_reads WHERE symbol=? AND timeframe=? AND bar_time=?",
                        (sym, tf, bar_time)).fetchone():
            skipped.append({"symbol": sym, "timeframe": tf, "reason": NO_NEW_CANDLE})
            continue
        try:
            row, text = freeze_read(df, sym, tf, cfg)
        except Exception as exc:
            skipped.append({"symbol": sym, "timeframe": tf, "reason": f"engine: {str(exc)[:160]}"})
            continue
        row.update(run_date=rd, created_at=int(now.timestamp()), engine_commit=engine["commit"],
                   engine_dirty=int(engine["dirty"]), config_hash=engine["config_hash"])
        cols = ", ".join(row)
        cur = conn.execute(f"INSERT OR IGNORE INTO forward_reads ({cols}) VALUES ({', '.join('?' * len(row))})",
                           tuple(row.values()))
        new_reads += cur.rowcount
        if cur.rowcount:
            texts.setdefault(sym, []).append((tf, text))
    conn.commit()

    if mr.synthesis:                                                   # 3. optional synthesis
        skipped += _synthesize(cfg, conn, rd, now, texts, synth_client)

    failures = [s for s in skipped if s["reason"] not in _BENIGN]
    status = "ok" if not failures else ("failed" if not candles else "partial")
    conn.execute("UPDATE forward_runs SET status=?, finished_at=?, new_reads=new_reads+?, resolved=resolved+?, "
                 "skipped=? WHERE run_date=?",
                 (status, int(time.time()), new_reads, resolved, json.dumps(skipped), rd))
    conn.commit()
    return {"run_date": rd, "status": status, "new_reads": new_reads, "resolved": resolved,
            "skipped": skipped, "gaps": gaps, "engine": engine}


def _synthesize(cfg: Config, conn, rd: str, now: datetime, texts: dict, client) -> list[dict]:
    """One cross-timeframe read per symbol from TODAY's facts text only (never outcomes)."""
    from src.advisor.explain import synthesize
    out = []
    for sym, per in texts.items():
        if len(per) < 2:
            continue
        weights = cfg.timeframes.weights
        try:
            text = synthesize([(tf, t, weights.get(tf, 1.0)) for tf, t in per], cfg, client=client)
        except Exception as exc:
            out.append({"symbol": sym, "timeframe": "all", "reason": f"synthesis: {str(exc)[:160]}"})
            continue
        conn.execute("INSERT OR IGNORE INTO forward_syntheses VALUES (?,?,?,?,?)",
                     (rd, sym, text, cfg.advisor.model, int(now.timestamp())))
    conn.commit()
    return out
