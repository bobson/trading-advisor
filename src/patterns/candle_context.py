"""1- and 2-candle patterns IN CONTEXT — which ones sit at a level that favours them.

A hammer mid-range is noise; a hammer whose low tags a support zone is the textbook setup. This
module marks a 1-/2-candle pattern only when, AT THE TIME THAT CANDLE CLOSED, a level that fits its
direction was within reach:

  bullish (hammer, bullish engulfing) — the candle's lower wick TAGGED a support: the nearest
      non-stale support zone below the previous close, a key Fibonacci retracement (38.2–78.6%) of
      an UP-leg, or an unbroken support trendline;
  bearish (shooting star, bearish engulfing) — its upper wick tagged a resistance (mirror).

"Tagged" = the level (or any part of the zone's band) lies between the wick's tip and the body — the
candle actually traded there. A doji has no direction for a level to favour, so it is never marked
"at a level" (it still shows in the all-patterns view and as the last-candle marker).

Why this strict (measured on BTC/SOL 1d, BTC 1h, EUR/USD 1d, last 500 candles): with every historical
zone and a 0.25×ATR "near" margin, 85–99% of patterns counted as "at a level"; nearest non-stale
zone only → 64–86%; wick must actually tag → ~50%, and excluding direction-less doji → ~45–65 of 500.

LOOK-AHEAD SAFE: every level is the one that existed at that candle. The swings known at bar i are
the full swing list filtered to bars <= i − sensitivity (verified equal to recomputing on df[:i+1];
only the tie order of outside bars differs), and zones / Fibonacci / trendlines are rebuilt from
those swings and the candles up to i. Facts-only — nothing here feeds a vote.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators.features import (
    COL_ATR,
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_SHOOTING_STAR,
)
from src.market.precision import fmt_price
from src.structure.fibonacci import UP, fib_retracement
from src.structure.support_resistance import find_sr_zones
from src.structure.trendlines import RESISTANCE, SUPPORT, find_two_point_trendlines

# (column, label, short code, direction) — precedence matches the candlestick VOTE
# (`signal_from_patterns`): engulfing > hammer/shooting star > doji.
ONE_TWO_CANDLE = [
    (COL_BULLISH_ENGULFING, "bullish engulfing", "BuE", "bullish"),
    (COL_HAMMER, "hammer", "H", "bullish"),
    (COL_BEARISH_ENGULFING, "bearish engulfing", "BeE", "bearish"),
    (COL_SHOOTING_STAR, "shooting star", "SS", "bearish"),
    (COL_DOJI, "doji", "D", "neutral"),
]
_KEY_FIB = (0.382, 0.5, 0.618, 0.786)


def pattern_on(row) -> tuple[str, str, str] | None:
    """The one 1-/2-candle pattern on this bar (same precedence as the vote), or None."""
    for col, label, code, direction in ONE_TWO_CANDLE:
        if bool(row.get(col, False)):
            return label, code, direction
    return None


def _levels_at(featured: pd.DataFrame, swings: pd.DataFrame, i: int, cfg, atr: float) -> list[dict]:
    """Support/resistance levels as they existed when bar i closed. Each: {kind, lo, hi, name}."""
    s = cfg.structure
    known = swings[swings["bar"] <= i - s.swing_sensitivity]
    if known.empty:
        return []
    close = float(featured["close"].iloc[i])
    # Zones: only the NEAREST non-stale support below and resistance above the PREVIOUS close —
    # what "price is at support" means everywhere else in the app. Every historical zone would
    # make nearly every candle "at a level" (measured: 85–99%), which says nothing.
    ref = float(featured["close"].iloc[i - 1]) if i > 0 else close
    zones = find_sr_zones(known, atr, i + 1, zone_atr_mult=s.sr_zone_atr_mult,
                          stale_bars=s.sr_stale_bars, halflife_bars=s.sr_strength_halflife_bars)
    out: list[dict] = []
    if not zones.empty:
        live = zones[~zones["stale"].astype(bool)]
        below = live[live["price"] < ref].sort_values("price")
        above = live[live["price"] >= ref].sort_values("price")
        for kind, z in ((SUPPORT, below.iloc[-1] if len(below) else None),
                        (RESISTANCE, above.iloc[0] if len(above) else None)):
            if z is not None:
                out.append({"kind": kind, "lo": float(z["lower"]), "hi": float(z["upper"]),
                            "name": f"{kind} zone {fmt_price(z['lower'], close)}–{fmt_price(z['upper'], close)}"})
    fib = fib_retracement(known.sort_values(["bar", "kind"]))
    if fib is not None:
        kind = SUPPORT if fib.direction == UP else RESISTANCE
        for r in _KEY_FIB:
            if r in fib.levels:
                v = float(fib.levels[r])
                out.append({"kind": kind, "lo": v, "hi": v, "name": f"fib {r * 100:.1f}%"})
    lines = find_two_point_trendlines(featured.iloc[: i + 1], known, atr_col=COL_ATR,
                                      break_atr_mult=s.trendline_break_atr_mult,
                                      max_anchors=s.trendline_max_anchors)
    for kind, tl in lines.items():
        v = float(tl.value_at(i))
        out.append({"kind": kind, "lo": v, "hi": v, "name": f"{tl.direction} {kind} trendline"})
    return out


def _touches(level: dict, low: float, high: float, margin: float) -> bool:
    """The level (a band or a line) is within the candle's range, widened by `margin`."""
    return level["lo"] <= high + margin and level["hi"] >= low - margin


def level_for(featured: pd.DataFrame, swings: pd.DataFrame, i: int, direction: str, cfg) -> dict | None:
    """The level that favours a `direction` pattern on bar i, or None. Bullish needs a SUPPORT
    tagged by the candle's lower wick, bearish a RESISTANCE tagged by its upper wick; a doji → None.
    Ties → the level nearest the relevant wick tip."""
    row = featured.iloc[i]
    atr = float(row[COL_ATR]) if COL_ATR in featured.columns and pd.notna(row[COL_ATR]) else 0.0
    if not atr > 0:
        return None                         # no ATR yet (warm-up) → no honest tolerance
    if direction not in ("bullish", "bearish"):
        return None                         # a doji has no direction for a level to favour
    margin = 0.0                            # the wick must actually TAG the level (see module doc)
    low, high = float(row["low"]), float(row["high"])
    body_lo = min(float(row["open"]), float(row["close"]))
    body_hi = max(float(row["open"]), float(row["close"]))
    best, best_d = None, float("inf")
    for lv in _levels_at(featured, swings, i, cfg, atr):
        if direction == "bullish":
            # support tagged by the lower wick: level between the low and the body bottom (± margin)
            ok = lv["kind"] == SUPPORT and _touches(lv, low, body_lo, margin)
            d = abs((lv["lo"] + lv["hi"]) / 2 - low)
        else:
            ok = lv["kind"] == RESISTANCE and _touches(lv, body_hi, high, margin)
            d = abs((lv["lo"] + lv["hi"]) / 2 - high)
        if ok and d < best_d:
            best, best_d = lv, d
    return best


# A candle's level context depends only on bars <= it, so once computed it never changes — cache it
# per (market, bar time) so scrubbing only pays for candles it hasn't seen. The LAST bar is never
# cached (it may still be forming in live data). Bounded; cleared wholesale when full.
_LEVEL_CACHE: dict[tuple, str | None] = {}
_CACHE_MAX = 50_000


def candle_events(featured: pd.DataFrame, swings: pd.DataFrame, cfg, *, start: int = 0,
                  level_from: int | None = None, market: tuple | None = None) -> list[dict]:
    """Every 1-/2-candle pattern from bar `start` on: [{bar, label, code, direction, level|None}].
    `level` names the level it tagged (as of that bar), or None. Level context is computed only for
    bars >= `level_from` (default `start`) — it's the slow part — and cached per `market` key."""
    level_from = start if level_from is None else level_from
    n = len(featured)
    which = np.full(n, -1)                      # index into ONE_TWO_CANDLE, by vote precedence
    for k, (col, *_) in enumerate(ONE_TWO_CANDLE):
        if col in featured.columns:
            hit = featured[col].fillna(False).to_numpy(dtype=bool)
            which[(which < 0) & hit] = k
    last = n - 1
    out = []
    for i in np.flatnonzero(which >= 0):
        i = int(i)
        if i < start:
            continue
        _, label, code, direction = ONE_TWO_CANDLE[which[i]]
        level = None
        if direction != "neutral" and i >= level_from:
            key = (market, featured.index[i], direction) if market else None
            if key is not None and i != last and key in _LEVEL_CACHE:
                level = _LEVEL_CACHE[key]
            else:
                lv = level_for(featured, swings, i, direction, cfg)
                level = lv["name"] if lv else None
                if key is not None and i != last:
                    if len(_LEVEL_CACHE) >= _CACHE_MAX:
                        _LEVEL_CACHE.clear()
                    _LEVEL_CACHE[key] = level
        out.append({"bar": i, "label": label, "code": code, "direction": direction, "level": level})
    return out
