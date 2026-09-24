"""ROADMAP B3 — the Empirical Pattern Encyclopedia: what each chart pattern actually did, here.

Built by iterating THE look-ahead-safe walk (`backtest.evaluate.walk` — no second walker). At every
bar the detectors see only candles up to that bar; each distinct pattern (type + defining swing bars)
is recorded the FIRST time it is detected. Its outcome is then measured on the candles that FOLLOW
(that's the result being studied, never an input to the detection):

  confirmation — from a pattern first seen FORMING: the first close beyond its breakout level
      within `max_wait` bars (if the data ends before that window closes, it's PENDING and left out
      of the rate) (neutral coils — symmetric triangle, sideways channel — may break either
      edge, which sets their direction). A close beyond the invalidation first = invalidated.
  after confirmation (bar c), over the next `horizon` bars:
      follow-through — a high/low reached the pattern's measured target (patterns with a target);
      failure        — a close back through the breakout level by `patterns.reclaim_atr_mult` × ATR
                       (the app's own failed-break rule); if both happen on one bar it counts as failed;
      move           — (close[c + horizon] − close[c]) in the pattern's direction ÷ ATR at c;
      pending        — broke out too recently for the full `horizon`: left out of these rates;
      bars to resolution — bars from c to the target hit or the failure, whichever came first.
  confirmation profile — the Feature-2 categories at c (price/volume/momentum/volatility/candlestick),
      so every statistic is also split by whether each category supported the breakout.

Honesty: rates are computed ONLY from patterns first seen while still forming (a pattern first
detected after it broke out is counted as an occurrence but kept out of the rates — its survival up to
detection would bias them). Every row carries its sample size; any rate whose denominator is below
`MIN_N` (20) is stored as NULL with its counts, flagged insufficient, and never shown as a percentage.
Regime (Feature 6) is read at the bar the pattern was first seen.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from src.backtest.evaluate import walk
from src.config import Config
from src.indicators.features import COL_ATR, add_features
from src.market.regime import classify_regime
from src.patterns.base import BEARISH, BULLISH, NEUTRAL_DIR, build_confirmation
from src.patterns.chart_patterns import find_patterns

MIN_N = 20
SPLIT_CATEGORIES = ("volume", "momentum", "volatility", "candlestick")
ALL = "all"


@dataclass
class Instance:
    pattern_type: str
    symbol: str
    timeframe: str
    bars: tuple
    first_seen: int
    first_state: str                  # detector state when first seen (forming / confirmed / failed)
    regime: str
    direction: str
    breakout: float | None
    invalidation: float | None
    target: float | None
    confirmed_bar: int | None = None
    invalidated: bool = False
    outcome: str | None = None        # target | failed | open (neither within horizon) | pending | None
    pending_breakout: bool = False    # forming, and the data ended before its breakout window closed
    upper_line: tuple | None = None   # (slope, intercept) — sloped boundaries are judged bar by bar
    lower_line: tuple | None = None
    move_atr: float | None = None
    bars_to_resolution: int | None = None
    profile: dict = field(default_factory=dict)


def _resolve_breakout(inst: Instance, closes: np.ndarray, start: int, stop: int, *, window_complete: bool = True) -> None:
    """Scan closes[start:stop] for the confirmation (or invalidation) of a forming pattern. If
    nothing happened and the data ended before the full window, it's PENDING (too recent to judge)."""
    if inst.upper_line is not None and inst.lower_line is not None:
        _resolve_on_lines(inst, closes, start, stop, window_complete)
        return
    hi = lo = None
    if inst.direction == NEUTRAL_DIR and inst.breakout is not None and inst.invalidation is not None:
        hi, lo = max(inst.breakout, inst.invalidation), min(inst.breakout, inst.invalidation)
    for j in range(start, stop):
        c = closes[j]
        if hi is not None:                             # neutral coil: either edge sets the direction
            if c > hi:
                inst.direction, inst.breakout, inst.invalidation, inst.confirmed_bar = BULLISH, hi, lo, j
                return
            if c < lo:
                inst.direction, inst.breakout, inst.invalidation, inst.confirmed_bar = BEARISH, lo, hi, j
                return
            continue
        bull = inst.direction == BULLISH
        if inst.invalidation is not None and (c < inst.invalidation if bull else c > inst.invalidation):
            inst.invalidated = True
            return
        if inst.breakout is not None and (c > inst.breakout if bull else c < inst.breakout):
            inst.confirmed_bar = j
            return
    inst.pending_breakout = not window_complete


def _resolve_on_lines(inst: Instance, closes: np.ndarray, start: int, stop: int, window_complete: bool) -> None:
    """Same as `_resolve_breakout`, but against boundary LINES evaluated on each bar (wedges, channels,
    triangles, ranges). On confirmation the levels become the lines' values at that bar and the target
    keeps its measured distance from the breakout (flipped if a neutral coil breaks down)."""
    (su, iu), (sl, il) = inst.upper_line, inst.lower_line
    offset = None if inst.target is None or inst.breakout is None else inst.target - inst.breakout
    neutral = inst.direction == NEUTRAL_DIR
    for j in range(start, stop):
        c, up, lo = closes[j], su * j + iu, sl * j + il
        bull_break, bear_break = c > up, c < lo
        if neutral and (bull_break or bear_break):
            inst.direction = BULLISH if bull_break else BEARISH
        elif not neutral:
            bull = inst.direction == BULLISH
            if (bear_break if bull else bull_break):
                inst.invalidated = True
                return
            if not (bull_break if bull else bear_break):
                continue
        else:
            continue
        bull = inst.direction == BULLISH
        inst.confirmed_bar = j
        inst.breakout, inst.invalidation = (up, lo) if bull else (lo, up)
        if offset is not None:
            inst.target = inst.breakout + (abs(offset) if bull else -abs(offset))
        return
    inst.pending_breakout = not window_complete


def _measure_after(inst: Instance, df: pd.DataFrame, feat: pd.DataFrame, cfg: Config, horizon: int) -> None:
    c = inst.confirmed_bar
    n = len(df)
    atr = float(feat[COL_ATR].iloc[c]) if pd.notna(feat[COL_ATR].iloc[c]) else float(df["close"].iloc[c]) * 0.01
    bull = inst.direction == BULLISH
    sign = 1.0 if bull else -1.0
    prof = build_confirmation(inst.direction, inst.breakout, inst.invalidation, feat.iloc[: c + 1], state="confirmed")
    inst.profile = {k: v for k, v in prof.to_dict().items() if k in SPLIT_CATEGORIES}
    closes, highs, lows = df["close"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy()
    margin = cfg.patterns.reclaim_atr_mult * atr
    end = min(n, c + horizon + 1)
    # Neither target nor failure within the FULL horizon = "open"; if the data ends first, "pending".
    inst.outcome = "open" if c + horizon < n else "pending"
    for j in range(c + 1, end):
        failed = (closes[j] < inst.breakout - margin) if bull else (closes[j] > inst.breakout + margin)
        hit = inst.target is not None and ((highs[j] >= inst.target) if bull else (lows[j] <= inst.target))
        if failed or hit:
            inst.outcome = "failed" if failed else "target"     # both on one bar -> failed (conservative)
            inst.bars_to_resolution = j - c
            break
    if c + horizon < n:
        inst.move_atr = float(sign * (closes[c + horizon] - closes[c]) / atr)


def collect_instances(df: pd.DataFrame, cfg: Config, symbol: str, timeframe: str, *,
                      horizon: int = 24, max_wait: int = 50, step: int = 1) -> list[Instance]:
    """Every distinct pattern the detectors found along the walk, with its measured outcome."""
    feat_full = add_features(df, cfg)
    regimes = classify_regime(feat_full, cfg)
    closes = df["close"].to_numpy()
    seen: set = set()
    out: list[Instance] = []
    for i, _sub, feat, swings in walk(df, cfg, horizon=1, step=step):
        for p in find_patterns(feat, swings, cfg):
            key = (p.type, tuple(p.bars))
            if key in seen:
                continue
            seen.add(key)
            reg = regimes.iloc[i]
            inst = Instance(p.type, symbol, timeframe, key[1], i, p.state,
                            str(reg) if reg is not None and not pd.isna(reg) else "unknown",
                            p.direction, p.breakout_level, p.invalidation_level, p.target,
                            upper_line=p.upper_line, lower_line=p.lower_line)
            if p.state == "forming":
                stop = min(len(df), i + 1 + max_wait)
                _resolve_breakout(inst, closes, i + 1, stop, window_complete=(i + 1 + max_wait <= len(df)))
                if inst.confirmed_bar is not None:
                    _measure_after(inst, df, feat_full, cfg, horizon)
            out.append(inst)
    return out


def _q(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 3) if len(values) >= MIN_N else None


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den >= MIN_N else None


def _stats(group: list[Instance], *, split: str) -> dict:
    """One row's statistics. For split rows the population is the CONFIRMED instances with that
    profile value, so occurrence/confirmation columns describe only that sub-population."""
    forming = [x for x in group if x.first_state == "forming"]
    decided = [x for x in forming if not x.pending_breakout]          # breakout window fully observed
    confirmed = [x for x in forming if x.confirmed_bar is not None]
    pending = [x for x in confirmed if x.outcome == "pending"]        # too recent to judge the outcome
    judged = [x for x in confirmed if x.outcome != "pending"]
    with_target = [x for x in judged if x.target is not None]
    hit = [x for x in with_target if x.outcome == "target"]
    failed = [x for x in judged if x.outcome == "failed"]
    moves = [x.move_atr for x in confirmed if x.move_atr is not None]
    btr = [x.bars_to_resolution for x in confirmed if x.bars_to_resolution is not None]
    return {
        "split": split,
        "sample_size": len(group),
        "seen_forming": len(forming),
        "decided_n": len(decided),
        "pending_breakout_n": len(forming) - len(decided),
        "confirmed_n": len(confirmed),
        "invalidated_n": sum(1 for x in forming if x.invalidated),
        "confirmation_rate": _rate(len(confirmed), len(decided)),
        "judged_n": len(judged),
        "pending_outcome_n": len(pending),
        "target_n": len(with_target),
        "target_hit_n": len(hit),
        "follow_through_rate": _rate(len(hit), len(with_target)),
        "failed_n": len(failed),
        "failure_rate": _rate(len(failed), len(judged)),
        "move_n": len(moves),
        "move_atr_median": _q(moves, 50),
        "move_atr_q1": _q(moves, 25),
        "move_atr_q3": _q(moves, 75),
        "resolved_n": len(btr),
        "bars_to_resolution_median": _q([float(b) for b in btr], 50),
        "insufficient_data": len(group) < MIN_N,
    }


def aggregate(instances: list[Instance], *, examples_per_market: int = 4) -> list[dict]:
    """Rows keyed (pattern_type, timeframe, symbol, regime, split) — per symbol and regime AND rolled
    up to symbol='all' / regime='all'. Splits: 'all' plus '<category>=supports|not' per category."""
    groups: dict[tuple, list[Instance]] = defaultdict(list)
    for x in instances:
        for sym in (x.symbol, ALL):
            for reg in (x.regime, ALL):
                groups[(x.pattern_type, x.timeframe, sym, reg)].append(x)
    rows = []
    for (ptype, tf, sym, reg), group in groups.items():
        base = {"pattern_type": ptype, "timeframe": tf, "symbol": sym, "regime": reg}
        row = {**base, **_stats(group, split=ALL)}
        if reg == ALL:
            row["examples"] = _examples(group, examples_per_market)
        rows.append(row)
        confirmed = [x for x in group if x.confirmed_bar is not None]      # split rows: see _stats
        for cat in SPLIT_CATEGORIES:
            for val, members in (("supports", [x for x in confirmed if x.profile.get(cat) == "supports"]),
                                 ("not", [x for x in confirmed if x.profile.get(cat) != "supports"])):
                rows.append({**base, **_stats(members, split=f"{cat}={val}")})
    return rows


def _examples(group: list[Instance], k: int) -> list[dict]:
    """Up to k examples per market that open in the scrub view: confirmed ones at their breakout
    bar, a mix of outcomes (target / failed / open) first, most recent first."""
    out = []
    by_market: dict[tuple, list[Instance]] = defaultdict(list)
    for x in group:
        if x.confirmed_bar is not None:
            by_market[(x.symbol, x.timeframe)].append(x)
    for (sym, tf), xs in sorted(by_market.items()):
        # judged outcomes first (a pending one can't illustrate what happened yet), most recent first
        xs = sorted(xs, key=lambda x: (x.outcome == "pending", -x.confirmed_bar))
        picked, outcomes = [], set()
        for x in xs:                                   # one per outcome first, then the most recent
            if x.outcome not in outcomes:
                picked.append(x)
                outcomes.add(x.outcome)
        picked += [x for x in xs if x not in picked][: max(0, k - len(picked))]
        out += [{"symbol": sym, "timeframe": tf, "bar": x.confirmed_bar, "direction": x.direction,
                 "outcome": x.outcome, "move_atr": None if x.move_atr is None else round(x.move_atr, 2)}
                for x in picked[:k]]
    return out


# --- SQLite (LOCKED decision: precomputed table, the API only reads) ---------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS encyclopedia_stats (
    pattern_type TEXT NOT NULL, timeframe TEXT NOT NULL, symbol TEXT NOT NULL, regime TEXT NOT NULL,
    split TEXT NOT NULL,
    sample_size INTEGER NOT NULL, insufficient_data INTEGER NOT NULL,
    stats TEXT NOT NULL,          -- JSON: every count/rate/quantile (rates NULL when n < 20)
    examples TEXT,                -- JSON list (regime='all', split='all' rows only)
    built_at INTEGER NOT NULL, params TEXT,
    PRIMARY KEY (pattern_type, timeframe, symbol, regime, split)
);
"""
_KEYS = ("pattern_type", "timeframe", "symbol", "regime", "split")


def save_rows(conn, rows: list[dict], *, built_at: int, params: dict, replace_markets: list[tuple]) -> None:
    """Replace the rows for the rebuilt (symbol, timeframe) markets (and their 'all' roll-ups for
    those timeframes), then insert. Other markets' rows are kept."""
    conn.executescript(SCHEMA)
    for sym, tf in replace_markets:
        conn.execute("DELETE FROM encyclopedia_stats WHERE timeframe=? AND symbol IN (?, ?)", (tf, sym, ALL))
    for r in rows:
        stats = {k: v for k, v in r.items() if k not in _KEYS and k not in ("examples", "sample_size", "insufficient_data")}
        conn.execute(
            "INSERT OR REPLACE INTO encyclopedia_stats VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (*[r[k] for k in _KEYS], r["sample_size"], int(r["insufficient_data"]), json.dumps(stats),
             json.dumps(r.get("examples")) if r.get("examples") is not None else None,
             built_at, json.dumps(params)))
    conn.commit()


def load_rows(conn, pattern_type: str | None = None) -> list[dict]:
    try:
        cur = conn.execute("SELECT * FROM encyclopedia_stats" + (" WHERE pattern_type=?" if pattern_type else ""),
                           (pattern_type,) if pattern_type else ())
    except Exception:                                  # table not built yet
        return []
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d.update(json.loads(d.pop("stats")))
        d["examples"] = json.loads(d["examples"]) if d.get("examples") else []
        d["params"] = json.loads(d["params"]) if d.get("params") else {}
        d["insufficient_data"] = bool(d["insufficient_data"])
        out.append(d)
    return out


def instance_dicts(instances: list[Instance]) -> list[dict]:
    return [asdict(x) for x in instances]
