"""ROADMAP R3 — measure each caution condition on history, honestly.

Walks THE look-ahead-safe walk (`backtest.evaluate.walk`, no second walker). At every scanned bar
with a DIRECTIONAL read (the forward record's definition: `caution.read_direction`) it records the
caution flags the engine would have shown (`build_facts` on bars <= i) and what happened over the
timeframe's horizon (`morning_report.horizons`, in bars):

  bracket   — enter at the close in the read's direction with a ±1 ATR bracket (ATR at the read);
              the first touch wins: stop first = "loss", target first = "win", both inside one bar =
              "ambiguous" (excluded), neither = "none" (excluded). Level-independent, so it can judge
              a condition without re-measuring the read's own levels.
  rule_v1   — the forward record's outcome on the read's own levels (followed / invalidated / ...).
  mae_atr   — how far price went against the read over the horizon, in ATR.
  range_atr — the full high-low range over the horizon, in ATR (for the sizing condition).

DECIDED BEFORE THE FIRST RUN (never adjusted after seeing results):
  * Split per market by time: the first 70% of scanned bars = "tune", the last 30% = "test" (the
    held-back part, reported once). Tune bars whose horizon reaches into the test part are PURGED.
    No threshold is tuned in this pass — the a-priori `caution:` config values are used as they are.
  * What each condition is judged by:
      no_expansion, stretched, htf_against  -> DIRECTIONAL: the bracket loss rate, flagged vs not.
          `helps` = in the TEST part (pooled across markets and timeframes) the flagged loss rate is at
          least MIN_EFFECT (5 points) above the unflagged one with n >= MIN_N (20) on both sides, AND the
          tune part shows the same sign, AND most markets with n >= MIN_N on both sides (at least 2)
          AGREE in the test part — a market agrees only if its own difference is at least half the
          required effect (MIN_EFFECT / 2), so noise-sized positives in no-effect markets can't carry a
          one-market effect. Below MIN_N -> `insufficient`; otherwise `no_effect`. (The half-effect
          clause was added before any real result was aggregated, after the one-market test failed.)
      thin_market                          -> the same test, on forex/gold cases only.
      stop_in_noise, no_room               -> `by_construction`: built from the read's own levels, so a
          rule-v1 comparison would be circular. Reported (invalidated-first rates), kept visible as
          arithmetic warnings, never counted as a finding.
      volatility_extreme                   -> `sizing`: ATR-normalised brackets cancel it by design; the
          realised range (in ATR) flagged vs not is reported as a sizing fact.
      event_risk                           -> `forward_only`: no historical calendar; only the forward
          record can test it (with a FINNHUB_API_KEY).
  * Overlapping horizons (step << horizon) make cases non-independent, so the per-market consistency
    is the real guard, and the number of cells tested is reported beside every status.
"""

from __future__ import annotations

import importlib
import json
from collections import defaultdict
from statistics import median

import pandas as pd

from src.config import Config
from src.forward.rule import _resolve_directional, levels_for
from src.risk.caution import LABELS, read_direction

_ev = importlib.import_module("src.backtest.evaluate")      # the module (the package re-exports a function)

MIN_N = 20
MIN_EFFECT = 0.05
TUNE_SHARE = 0.70
DIRECTIONAL_CODES = ("no_expansion", "stretched", "htf_against", "thin_market")
BY_CONSTRUCTION = ("stop_in_noise", "no_room")
SIZING = ("volatility_extreme",)
FORWARD_ONLY = ("event_risk",)

SCHEMA = """
CREATE TABLE IF NOT EXISTS caution_stats (
    code TEXT PRIMARY KEY, status TEXT NOT NULL, metric TEXT NOT NULL,
    summary TEXT NOT NULL,     -- JSON: pooled test/tune sides, per-market and per-timeframe test cells
    cells_tested INTEGER NOT NULL, built_at INTEGER NOT NULL, params TEXT
);
"""


# --- collect: one case per directional read along THE walk ---------------------------------------

def _bracket(direction: str, close: float, atr: float, highs, lows) -> str:
    up, down = close + atr, close - atr
    for h, lo in zip(highs, lows):
        hit_up, hit_down = h >= up, lo <= down
        if hit_up and hit_down:
            return "ambiguous"
        if hit_up or hit_down:
            return "win" if hit_up == (direction == "bullish") else "loss"
    return "none"


def collect(df: pd.DataFrame, cfg: Config, symbol: str, timeframe: str, *, step: int = 4) -> list[dict]:
    """Cases for one market. `cfg` must be request-scoped to (symbol, timeframe)."""
    from src.advisor.facts import build_facts
    from src.data.registry import asset_class_for
    horizon = cfg.morning_report.horizons.get(timeframe, 24)
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    scanned = list(range(_ev.default_warmup(cfg), len(df) - horizon, step))
    if not scanned:
        return []
    cut = scanned[int(len(scanned) * TUNE_SHARE)]
    asset = asset_class_for(symbol)
    out = []
    for i, _sub, feat, swings in _ev.walk(df, cfg, horizon=horizon, step=step):
        facts = build_facts(feat, swings, cfg)
        direction = read_direction(facts)
        atr = (facts.get("volatility") or {}).get("atr")
        if direction is None or not atr:
            continue
        part = "test" if i >= cut else ("tune" if i + horizon < cut else "purged")
        close = float(facts["market"]["last_close"])
        h, lo = highs[i + 1: i + 1 + horizon], lows[i + 1: i + 1 + horizon]
        sr = facts.get("support_resistance") or {}
        lv = levels_for(direction, close, atr, sr.get("nearest_support"), sr.get("nearest_resistance"))
        adverse = (close - lo.min()) if direction == "bullish" else (h.max() - close)
        out.append({
            "symbol": symbol, "timeframe": timeframe, "asset": asset, "i": i, "part": part,
            "direction": direction, "flags": {c["code"]: c["active"] for c in facts.get("caution") or []},
            "bracket": _bracket(direction, close, atr, h, lo),
            "rule_v1": _resolve_directional(direction, lv["next_level"], lv["invalidation"], list(zip(h, lo))),
            "mae_atr": round(max(0.0, float(adverse)) / atr, 3),
            "range_atr": round(float(h.max() - lo.min()) / atr, 3),
        })
    return out


# --- aggregate: pure, testable without the walk ---------------------------------------------------

def _side(cases: list[dict], key: str, bad: str, good: tuple) -> dict:
    judged = [c for c in cases if c[key] == bad or c[key] in good]
    n, b = len(judged), sum(1 for c in judged if c[key] == bad)
    return {"n": n, "bad": b, "rate": round(b / n, 3) if n else None}


def _compare(cases: list[dict], code: str, key: str = "bracket", bad: str = "loss", good=("win",)) -> dict:
    on = [c for c in cases if c["flags"].get(code) is True]
    off = [c for c in cases if c["flags"].get(code) is False]
    f, u = _side(on, key, bad, good), _side(off, key, bad, good)
    diff = round(f["rate"] - u["rate"], 3) if f["n"] >= MIN_N and u["n"] >= MIN_N else None
    return {"flagged": f, "unflagged": u, "diff": diff,
            "mae_flagged": round(median([c["mae_atr"] for c in on]), 2) if on else None,
            "mae_unflagged": round(median([c["mae_atr"] for c in off]), 2) if off else None}


def _cells(cases: list[dict], code: str, by: str, **kw) -> dict:
    groups = defaultdict(list)
    for c in cases:
        groups[c[by]].append(c)
    return {k: _compare(v, code, **kw) for k, v in sorted(groups.items())}


def judge_directional(cases: list[dict], code: str) -> dict:
    """The pre-registered decision for a direction-bearing condition (see the module docstring)."""
    test = [c for c in cases if c["part"] == "test"]
    tune = [c for c in cases if c["part"] == "tune"]
    t, u = _compare(test, code), _compare(tune, code)
    markets = _cells(test, code, "symbol")
    eligible = {m: v["diff"] for m, v in markets.items() if v["diff"] is not None}
    agreeing = sum(1 for d in eligible.values() if d >= MIN_EFFECT / 2)
    if t["diff"] is None:
        status = "insufficient"
    elif (t["diff"] >= MIN_EFFECT and u["diff"] is not None and u["diff"] > 0
          and len(eligible) >= 2 and agreeing > len(eligible) / 2):
        status = "helps"
    else:
        status = "no_effect"
    return {"status": status, "metric": "±1 ATR bracket loss rate, flagged vs not (held-back 30%)",
            "test": t, "tune": u, "markets": markets, "timeframes": _cells(test, code, "timeframe"),
            "markets_agreeing": f"{agreeing} of {len(eligible)}",
            "cells_tested": 1 + len(markets) + len(set(c["timeframe"] for c in test))}


def aggregate(cases: list[dict]) -> dict[str, dict]:
    """{code: {status, metric, summary..., cells_tested}} for all eight conditions."""
    out = {}
    fx = [c for c in cases if c["asset"] == "forex"]
    for code in LABELS:
        if code in DIRECTIONAL_CODES:
            out[code] = judge_directional(fx if code == "thin_market" else cases, code)
        elif code in BY_CONSTRUCTION:
            test = [c for c in cases if c["part"] == "test"]
            cmp_ = _compare(test, code, key="rule_v1", bad="invalidated", good=("followed_through", "expired"))
            out[code] = {"status": "by_construction", "cells_tested": 0,
                         "metric": "rule-v1 invalidated-first rate (circular: the condition is built from those levels)",
                         "test": cmp_}
        elif code in SIZING:
            test = [c for c in cases if c["part"] == "test"]
            on = [c["range_atr"] for c in test if c["flags"].get(code) is True]
            off = [c["range_atr"] for c in test if c["flags"].get(code) is False]
            out[code] = {"status": "sizing", "cells_tested": 0,
                         "metric": "realised high-low range over the horizon, in ATR at the read (median)",
                         "test": {"flagged": {"n": len(on), "range_atr": round(median(on), 2) if on else None},
                                  "unflagged": {"n": len(off), "range_atr": round(median(off), 2) if off else None}}}
        else:
            out[code] = {"status": "forward_only", "cells_tested": 0,
                         "metric": "no historical economic calendar; only the forward record can test it",
                         "test": None}
    return out


# --- storage + injection ------------------------------------------------------------------------------

def save(conn, stats: dict, *, built_at: int, params: dict) -> None:
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM caution_stats")
    for code, s in stats.items():
        summary = {k: v for k, v in s.items() if k not in ("status", "metric", "cells_tested")}
        conn.execute("INSERT INTO caution_stats VALUES (?,?,?,?,?,?,?)",
                     (code, s["status"], s["metric"], json.dumps(summary), s["cells_tested"], built_at,
                      json.dumps(params)))
    conn.commit()


def load(conn) -> dict[str, dict]:
    try:
        rows = conn.execute("SELECT * FROM caution_stats").fetchall()
    except Exception:                                         # not built yet
        return {}
    return {r["code"]: {"status": r["status"], "metric": r["metric"], **json.loads(r["summary"]),
                        "cells_tested": r["cells_tested"], "built_at": r["built_at"]} for r in rows}


def _pct(side: dict) -> str:
    return f"{side['bad']} of {side['n']}" + (f" ({side['rate'] * 100:.0f}%)" if side["n"] >= MIN_N else "")


def record_text(code: str, s: dict) -> str:
    """One plain line for the UI / facts: what history said about this condition."""
    st = s["status"]
    if st in ("helps", "no_effect", "insufficient"):
        t = s["test"]
        return (f"held-back history: reads with it lost a ±1 ATR bracket {_pct(t['flagged'])} vs "
                f"{_pct(t['unflagged'])} without")
    if st == "by_construction":
        t = s["test"]
        return (f"arithmetic warning (not a finding): reads with it hit their invalidation first "
                f"{_pct(t['flagged'])} vs {_pct(t['unflagged'])}")
    if st == "sizing":
        t = s["test"]
        return (f"sizing fact: the next moves spanned a median {t['flagged']['range_atr']} ATR when flagged "
                f"vs {t['unflagged']['range_atr']} ATR otherwise")
    return "can only be tested by the forward record"


def apply_stats(facts: dict, stats: dict) -> None:
    """Live path (like the B4 records — never inside build_facts): stamp each caution entry with its
    measured status and one-line record."""
    for c in facts.get("caution") or []:
        s = stats.get(c["code"])
        if s:
            c["status"] = s["status"]
            c["record"] = record_text(c["code"], s)
