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


_BAND_KEYS = ("sample_size", "judged_n", "target_n", "target_hit_n", "follow_through_rate", "failed_n", "failure_rate",
              "decided_n", "confirmed_n", "confirmation_rate")


def _top(rows: list[dict], pattern_type: str, timeframe: str, split: str) -> dict | None:
    return next((r for r in rows if r["pattern_type"] == pattern_type and r["timeframe"] == timeframe
                 and r["symbol"] == "all" and r["regime"] == "all" and r["split"] == split), None)


def quality_meaning(rows: list[dict], pattern_type: str, timeframe: str) -> str:
    """ROADMAP B5 — whether a higher quality score meant anything for this type, decided HERE (Layer 1)
    from the encyclopedia: the high band vs the low band after a breakout. Both bands need MIN_N (20)
    judged cases; otherwise 'too few cases to tell'."""
    hi, lo = _top(rows, pattern_type, timeframe, "quality=high"), _top(rows, pattern_type, timeframe, "quality=low")
    if not hi or not lo or hi.get("failure_rate") is None or lo.get("failure_rate") is None:
        return "too few cases to tell whether a higher score meant fewer failures"
    if hi["failure_rate"] < lo["failure_rate"]:
        return (f"higher-scored ones failed less often ({hi['failure_rate'] * 100:.0f}% vs "
                f"{lo['failure_rate'] * 100:.0f}% for the low band)")
    return (f"a higher score did NOT mean fewer failures ({hi['failure_rate'] * 100:.0f}% vs "
            f"{lo['failure_rate'] * 100:.0f}% for the low band)")


def pattern_quality(rows: list[dict], pattern_type: str, timeframe: str, quality: float | None) -> dict | None:
    """ROADMAP B5 — the raw 0–1 geometry score translated into its calibrated band: low / medium /
    high = the bottom / middle / top third of this pattern type's past scores on this timeframe (all
    markets, the cut points the encyclopedia build used), with what the patterns in that band did.
    None when the encyclopedia has no bands for the type (old build, too few cases, or every score
    identical)."""
    from src.research.encyclopedia import quality_band
    top = _top(rows, pattern_type, timeframe, "all")
    cuts = (top or {}).get("quality_cuts")
    band = quality_band(quality, cuts)
    if band is None:
        return None
    row = _top(rows, pattern_type, timeframe, f"quality={band}") or {}
    return {"band": band, "cuts": cuts, "raw": quality, **{k: row.get(k) for k in _BAND_KEYS},
            "meaning": quality_meaning(rows, pattern_type, timeframe)}


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
            "quality_band": pattern_quality(records, p.type, timeframe, p.quality),
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
