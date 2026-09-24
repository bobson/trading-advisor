"""Pattern scanner — notice patterns across every pair and timeframe quickly.

For each market it runs the same detectors the chart uses on the latest candles and returns the
patterns worth a look NOW:
  fresh    — broke out within the last `patterns.fresh_bars` candles,
  forming  — not broken out yet, sorted by how close price is to the breakout (in ATR),
  in_play  — broke out a while ago and neither reached its target nor failed yet.
Completed / expired / failed patterns are history and are left out.

Every row carries the pattern type's measured record from the encyclopedia (all markets, all regimes,
same timeframe): how often it reached its target and how often it failed after a breakout — as
counts, and as a rate only with 20+ cases. A record is what happened before, not odds for this one.
"""

from __future__ import annotations

import pandas as pd

from src.config import Config
from src.indicators.features import COL_ATR, add_features
from src.patterns.chart_patterns import find_patterns
from src.structure.swings import find_swings

SHOWN = ("fresh", "forming", "in_play")


def pattern_record(rows: list[dict], pattern_type: str, timeframe: str) -> dict | None:
    """The encyclopedia's 'all markets, all regimes' record for a type on a timeframe, or None."""
    for r in rows:
        if (r["pattern_type"] == pattern_type and r["timeframe"] == timeframe and r["symbol"] == "all"
                and r["regime"] == "all" and r["split"] == "all"):
            return {k: r.get(k) for k in ("sample_size", "judged_n", "target_n", "target_hit_n",
                                          "follow_through_rate", "failed_n", "failure_rate", "move_atr_median")}
    return None


def _distance_atr(p, close: float, atr: float) -> float | None:
    """How far price is from the breakout, in ATR (0 once broken). Neutral coils: the nearer edge."""
    if not atr or p.breakout_level is None:
        return None
    if p.state != "forming":
        return 0.0
    levels = [p.breakout_level] + ([p.invalidation_level] if p.direction == "neutral" and p.invalidation_level else [])
    return round(min(abs(lv - close) for lv in levels) / atr, 2)


def scan_market(df: pd.DataFrame, symbol: str, timeframe: str, cfg: Config, records: list[dict]) -> list[dict]:
    feat = add_features(df, cfg)
    swings = find_swings(df, cfg.structure.swing_sensitivity)
    close = float(df["close"].iloc[-1])
    atr = float(feat[COL_ATR].iloc[-1]) if pd.notna(feat[COL_ATR].iloc[-1]) else None
    out = []
    for p in find_patterns(feat, swings, cfg):
        if p.lifecycle not in SHOWN:
            continue
        out.append({
            "symbol": symbol, "timeframe": timeframe, "type": p.type, "direction": p.direction,
            "lifecycle": p.lifecycle, "bars_since_breakout": p.bars_since_state_change,
            "breakout_level": p.breakout_level, "invalidation_level": p.invalidation_level,
            "target": p.target, "last_close": close, "distance_atr": _distance_atr(p, close, atr),
            "quality": p.quality, "last_time": int(pd.Timestamp(df.index[-1]).timestamp()),
            "record": pattern_record(records, p.type, timeframe),
        })
    return out


def scan(markets: list[tuple[str, str]], cfg: Config, candles_for, records: list[dict]) -> dict:
    """Scan every (symbol, timeframe). A market that can't load (no data / no key) is skipped and
    listed, never fatal. Rows come back grouped: fresh first (newest breakout first), then forming
    (closest to breaking out first), then in play."""
    rows, skipped = [], []
    for sym, tf in markets:
        try:
            rows += scan_market(candles_for(sym, tf), sym, tf, cfg, records)
        except Exception as exc:                               # pragma: no cover - network/data issues
            skipped.append({"symbol": sym, "timeframe": tf, "reason": str(exc)[:160]})
    order = {"fresh": 0, "forming": 1, "in_play": 2}
    rows.sort(key=lambda r: (order[r["lifecycle"]],
                             r["bars_since_breakout"] if r["lifecycle"] != "forming" else (r["distance_atr"] or 99)))
    return {"rows": rows, "skipped": skipped, "markets": len(markets)}
