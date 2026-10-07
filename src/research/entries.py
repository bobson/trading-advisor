"""Training on entry types — textbook entry points beyond chart patterns, found on THE look-ahead-safe walk
(`backtest.evaluate.walk`: everything at bar i is computed from bars <= i only).

  support bounce        the candle dipped into the nearest support zone and closed back above it (bullish);
  resistance rejection  … poked into the nearest resistance zone and closed back below it (bearish)
  zone breakout         the close crossed a zone's far edge (above a resistance's upper edge = bullish;
                        below a support's lower edge = bearish)
  trendline touch       the candle reached an unbroken support trendline and closed above it (bullish), or a
                        resistance trendline and closed below it (bearish)
  MA pullback           in an uptrend the candle dipped to the 50-MA and closed above it (bullish); mirrored
  RSI divergence        a new RSI divergence on the last two swings (its kind is the direction)

The same type + direction is not taken again within `COOLDOWN` bars (one setup per touch, not five).
Every setup is judged by the forward record's rule v1 — the levels `levels_for` gives the direction from
the nearest zones as of that bar, first touch of next level vs invalidation over the morning-report horizon
— and ALSO as its MIRROR: the opposite direction with the same distances (target the same way off, stop
the same way off), on the same candles. Same geometry, other side — a fair coin flip. An entry type only
means something if its side clearly beats its mirror.
"""

from __future__ import annotations

import pandas as pd

from src.indicators.features import COL_ATR, COL_SMA_SLOW

ENTRY_TYPES = ("support bounce", "resistance rejection", "zone breakout", "trendline touch", "MA pullback",
               "RSI divergence")
COOLDOWN = 5
TOUCH_ATR = 0.25           # a trendline / MA counts as reached within this × ATR
_OUT = {"followed_through": "target", "invalidated": "failed"}          # → the training table's words


def entry_levels(direction: str, close: float, atr: float, sup: dict | None, res: dict | None) -> dict:
    """The textbook trade's levels (rule v1 `levels_for`) and its MIRROR (same distances, other way)."""
    from src.forward.rule import levels_for
    lv = levels_for(direction, close, atr, sup, res)
    nxt, inv = float(lv["next_level"]), float(lv["invalidation"])
    return {"next_level": nxt, "invalidation": inv, "mirror_next": 2 * close - nxt, "mirror_invalidation": 2 * close - inv}


def judge_both(direction: str, lv: dict, bars: list[tuple[float, float]]) -> tuple[str, str]:
    """Rule v1 first touch for the textbook side and for its mirror (raw rule outcomes)."""
    from src.forward.rule import _resolve_directional
    opp = "bearish" if direction == "bullish" else "bullish"
    return (_resolve_directional(direction, lv["next_level"], lv["invalidation"], bars),
            _resolve_directional(opp, lv["mirror_next"], lv["mirror_invalidation"], bars))


def _judge(direction: str, close: float, atr: float, sup: dict | None, res: dict | None,
           future: list[tuple[float, float]]) -> tuple[str, str, dict]:
    """(outcome, mirror outcome, levels) in the training table's words."""
    lv = entry_levels(direction, close, atr, sup, res)
    own, mirror = judge_both(direction, lv, future)
    return _OUT.get(own, "open"), _OUT.get(mirror, "open"), lv


def _detect(i: int, feat: pd.DataFrame, swings: pd.DataFrame, cfg, zones: pd.DataFrame, near: dict) -> list[tuple[str, str, float]]:
    """(type, direction, level) for every entry condition true on bar i."""
    from src.structure.divergence import find_rsi_divergence
    from src.structure.trend import DOWNTREND, UPTREND, classify_trend
    from src.structure.trendlines import find_two_point_trendlines
    row, prev = feat.iloc[i], feat.iloc[i - 1]
    c, lo, hi, pc = float(row["close"]), float(row["low"]), float(row["high"]), float(prev["close"])
    atr = float(row[COL_ATR])
    out: list[tuple[str, str, float]] = []
    sup, res = near.get("nearest_support"), near.get("nearest_resistance")
    if sup and not sup["stale"] and lo <= sup["upper"] < c and pc > sup["lower"]:
        out.append(("support bounce", "bullish", sup["upper"]))
    if res and not res["stale"] and hi >= res["lower"] > c and pc < res["upper"]:
        out.append(("resistance rejection", "bearish", res["lower"]))
    if not zones.empty:
        live = zones[~zones["stale"].astype(bool)]
        up = live[(live["upper"] >= pc) & (live["upper"] < c)]
        down = live[(live["lower"] <= pc) & (live["lower"] > c)]
        if len(up):
            out.append(("zone breakout", "bullish", float(up["upper"].max())))
        elif len(down):
            out.append(("zone breakout", "bearish", float(down["lower"].min())))
    st = cfg.structure
    for kind, t in find_two_point_trendlines(feat, swings, atr_col=COL_ATR, break_atr_mult=st.trendline_break_atr_mult,
                                             max_anchors=st.trendline_max_anchors).items():
        v = t.value_at(i)
        if t.anchors[1][0] >= i - st.swing_sensitivity:
            continue                                     # the line's own newest anchor isn't a touch of it
        if kind == "support" and lo <= v + TOUCH_ATR * atr and c > v:
            out.append(("trendline touch", "bullish", round(v, 8)))
        elif kind == "resistance" and hi >= v - TOUCH_ATR * atr and c < v:
            out.append(("trendline touch", "bearish", round(v, 8)))
    ma = row.get(COL_SMA_SLOW)
    if ma is not None and not pd.isna(ma):
        ma = float(ma)
        trend = classify_trend(feat, swings).label
        if trend == UPTREND and lo <= ma + TOUCH_ATR * atr and c > ma and pc > ma:
            out.append(("MA pullback", "bullish", ma))
        elif trend == DOWNTREND and hi >= ma - TOUCH_ATR * atr and c < ma and pc < ma:
            out.append(("MA pullback", "bearish", ma))
    div = find_rsi_divergence(feat, swings)
    if div is not None:
        out.append(("RSI divergence", div.kind, c))
    return out


def collect_entries(df: pd.DataFrame, cfg, symbol: str, timeframe: str, *, horizon: int = 24, step: int = 1) -> list[dict]:
    """Every entry moment along the walk with both sides judged (`cfg` request-scoped)."""
    from src.advisor.facts import _nearest_levels
    from src.backtest.evaluate import walk
    from src.indicators.features import add_features
    from src.market.regime import classify_regime
    from src.structure.support_resistance import sr_zones
    regimes = classify_regime(add_features(df, cfg), cfg)
    highs, lows, closes = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    last_at: dict[tuple, int] = {}
    seen_div: set = set()
    out: list[dict] = []
    for i, _sub, feat, swings in walk(df, cfg, horizon=horizon, step=step):
        atr = feat[COL_ATR].iloc[-1]
        if pd.isna(atr) or atr <= 0:
            continue
        zones = sr_zones(feat, swings, cfg)
        near = _nearest_levels(zones, closes[i])
        future = list(zip(highs[i + 1:i + 1 + horizon], lows[i + 1:i + 1 + horizon]))
        for typ, direction, level in _detect(i, feat, swings, cfg, zones, near):
            if typ == "RSI divergence":
                key = (direction, tuple(swings.tail(4)["bar"]))
                if key in seen_div:
                    continue
                seen_div.add(key)
            elif i - last_at.get((typ, direction), -10 ** 9) <= COOLDOWN:
                continue
            last_at[(typ, direction)] = i
            outcome, outcome_opp, lv = _judge(direction, float(closes[i]), float(atr), near["nearest_support"],
                                              near["nearest_resistance"], future)
            sign = 1 if direction == "bullish" else -1
            reg = regimes.iloc[i]
            out.append({"symbol": symbol, "timeframe": timeframe, "bar_time": int(pd.Timestamp(df.index[i]).timestamp()),
                        "type": typ, "direction": direction,
                        "regime": str(reg) if reg is not None and not pd.isna(reg) else "unknown",
                        "outcome": outcome, "outcome_opp": outcome_opp, "family": "entry",
                        "move_atr": round(float(sign * (closes[i + horizon] - closes[i]) / atr), 3),
                        "breakout": float(level), "invalidation": float(lv["invalidation"]),
                        "target": float(lv["next_level"])})
    return out


def entries_now(featured: pd.DataFrame, swings: pd.DataFrame, cfg) -> list[dict]:
    """The entry points on the LAST bar of `featured` (the live read / the morning freeze): type, direction,
    the level, and the textbook + mirror levels they'd be judged on. No cooldown — this candle only."""
    from src.advisor.facts import _nearest_levels
    from src.market.precision import round_price
    from src.structure.support_resistance import sr_zones
    if len(featured) < 3:
        return []
    i = len(featured) - 1
    atr = featured[COL_ATR].iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return []
    close = float(featured["close"].iloc[-1])
    zones = sr_zones(featured, swings, cfg)
    near = _nearest_levels(zones, close)
    out, seen = [], set()
    for typ, direction, level in _detect(i, featured, swings, cfg, zones, near):
        if (typ, direction) in seen:
            continue
        seen.add((typ, direction))
        lv = entry_levels(direction, close, float(atr), near["nearest_support"], near["nearest_resistance"])
        out.append({"type": typ, "direction": direction, "level": round_price(level, close),
                    **{k: round_price(v, close) for k, v in lv.items()}})
    return out


def pool_records(conn, timeframe: str) -> dict:
    """Per entry type on this timeframe (all markets in the training pool): textbook side vs mirror."""
    from src.research.training import MIN_N
    out = {}
    try:
        rows = conn.execute("SELECT type, COUNT(*) n, SUM(outcome='target') t, SUM(outcome_opp='target') m "
                            "FROM training_setups WHERE family='entry' AND timeframe=? GROUP BY type", (timeframe,))
        for r in rows:
            n, t, m = r["n"], r["t"] or 0, r["m"] or 0
            out[r["type"]] = {"n": n, "target": t, "mirror_target": m, "timeframe": timeframe,
                              "target_rate": round(t / n, 3) if n >= MIN_N else None,
                              "mirror_rate": round(m / n, 3) if n >= MIN_N else None}
    except Exception:                    # no training table yet (a fresh droplet) -> no records
        return {}
    return out
