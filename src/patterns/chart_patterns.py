"""Feature 2 (was Phase 9) — named chart patterns as `Pattern` objects with state, levels,
quality, and a confirmation profile.

Geometry over the recent swings detects the shape; `base.py` adds the look-ahead-safe state and
the seven-category confirmation; `dedupe.py` collapses overlapping detections. Tolerances are
ATR-scaled (scale-free across an 80k BTC and a 1.10 EUR/USD), not fixed percentages.

CONTINUATION patterns are prioritised (triangles, rectangles, channels) — the use case is
multi-week trend riding, where reversal patterns (double tops/bottoms, head & shoulders) mainly
flag where a trend ENDS. Flags/pennants are deliberately deferred (the fuzziest, most
over-call-prone geometry) and can be added later without touching the machinery.

Anti-over-call is still the whole game: peaks "equal" within `equal_atr_mult × ATR` AND the
reversal/range at least `depth_atr_mult × ATR` deep. Patterns are kept OUT of the confluence
score — facts and chart only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import Config
from src.indicators.features import COL_ATR
from src.market.precision import round_price
from src.patterns.base import (
    BEARISH,
    BULLISH,
    CONFIRMED,
    CONTINUATION,
    FORMING,
    NEUTRAL_DIR,
    REVERSAL,
    Pattern,
    build_confirmation,
    classify_state,
    classify_state_history,
)
from src.patterns.dedupe import dedupe_patterns
from src.structure.swings import SWING_HIGH, SWING_LOW
from src.structure.trendlines import RESISTANCE, SUPPORT, fit_trendline

# Pattern type names.
DOUBLE_TOP = "double top"
DOUBLE_BOTTOM = "double bottom"
HEAD_AND_SHOULDERS = "head and shoulders"
INVERSE_HEAD_AND_SHOULDERS = "inverse head and shoulders"
ASCENDING_TRIANGLE = "ascending triangle"
DESCENDING_TRIANGLE = "descending triangle"
SYMMETRIC_TRIANGLE = "symmetric triangle"
RECTANGLE = "sideways channel"   # a horizontal range: flat-top resistance, flat-bottom support
ASCENDING_CHANNEL = "ascending channel"
DESCENDING_CHANNEL = "descending channel"

DEFAULT_LOOKBACK = 7


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _pt(row) -> tuple:
    return (int(row["bar"]), float(row["price"]))


def _seg(line, b0, b1) -> list:
    """A sloped boundary segment from a fitted trendline, as two (bar, price) endpoints."""
    return [(int(b0), float(line.value_at(b0))), (int(b1), float(line.value_at(b1)))]


def _hseg(price, b0, b1) -> list:
    """A horizontal boundary segment (e.g. a neckline or a rectangle edge)."""
    return [(int(b0), float(price)), (int(b1), float(price))]


def _rel_change_pct(slope: float, bars: np.ndarray, mean_price: float) -> float:
    span = float(bars.max() - bars.min())
    return slope * span / mean_price * 100.0 if mean_price else 0.0


# --- geometry detectors: emit a Pattern with GEOMETRY only (state/confirmation added later) ---

def _detect_double(highs, lows, cfg, atr, *, top: bool) -> Pattern | None:
    tol = cfg.patterns.equal_atr_mult * atr
    min_depth = cfg.patterns.depth_atr_mult * atr
    peaks = highs if top else lows
    valleys = lows if top else highs
    if len(peaks) < 2:
        return None
    p1, p2 = peaks.iloc[-2], peaks.iloc[-1]
    between = valleys[(valleys["bar"] > p1["bar"]) & (valleys["bar"] < p2["bar"])]
    if between.empty or abs(p1["price"] - p2["price"]) > tol:
        return None

    if top:
        level = min(p1["price"], p2["price"])
        mid_row = between.loc[between["price"].idxmin()]
        mid = float(mid_row["price"])
        depth = level - mid
        neckline, target = mid, mid - (level - mid)
        invalidation = max(p1["price"], p2["price"])   # a close back above the peaks kills it
        name, direction = DOUBLE_TOP, BEARISH
    else:
        level = max(p1["price"], p2["price"])
        mid_row = between.loc[between["price"].idxmax()]
        mid = float(mid_row["price"])
        depth = mid - level
        neckline, target = mid, mid + (mid - level)
        invalidation = min(p1["price"], p2["price"])
        name, direction = DOUBLE_BOTTOM, BULLISH
    if depth < min_depth:
        return None

    quality = _clamp01(1 - abs(p1["price"] - p2["price"]) / (2 * tol)) if tol > 0 else 0.5
    return Pattern(
        type=name, kind=REVERSAL, direction=direction, state=FORMING,
        bars=[int(p1["bar"]), int(mid_row["bar"]), int(p2["bar"])],
        points=[_pt(p1), _pt(mid_row), _pt(p2)],
        # the base line connects the two defining extremes (the two lows of a double bottom / two
        # peaks of a double top), plus the neckline (the breakout level, at the swing between them).
        lines=[[_pt(p1), _pt(p2)], _hseg(neckline, p1["bar"], p2["bar"])],
        breakout_level=round_price(float(neckline)), invalidation_level=round_price(float(invalidation)),
        target=round_price(float(target)), quality=round(quality, 3),
        reason=f"Two {'peaks' if top else 'troughs'} ~equal (within {tol:.4g}, ATR-scaled) with a reversal between.",
    )


def _detect_head_and_shoulders(highs, lows, cfg, atr, *, top: bool) -> Pattern | None:
    tol = cfg.patterns.equal_atr_mult * atr
    min_depth = cfg.patterns.depth_atr_mult * atr
    peaks = highs if top else lows
    valleys = lows if top else highs
    if len(peaks) < 3:
        return None
    ls, head, rs = peaks.iloc[-3], peaks.iloc[-2], peaks.iloc[-1]
    shoulder = max(ls["price"], rs["price"]) if top else min(ls["price"], rs["price"])
    head_clears = (head["price"] - shoulder) > tol if top else (shoulder - head["price"]) > tol
    if not head_clears or abs(ls["price"] - rs["price"]) > tol:
        return None
    left = valleys[(valleys["bar"] > ls["bar"]) & (valleys["bar"] < head["bar"])]
    right = valleys[(valleys["bar"] > head["bar"]) & (valleys["bar"] < rs["bar"])]
    if left.empty or right.empty:
        return None
    neckline = float((left["price"].mean() + right["price"].mean()) / 2)
    if abs(head["price"] - neckline) < min_depth:
        return None

    if top:
        name, direction = HEAD_AND_SHOULDERS, BEARISH
        target = neckline - (head["price"] - neckline)
        invalidation = float(head["price"])
    else:
        name, direction = INVERSE_HEAD_AND_SHOULDERS, BULLISH
        target = neckline + (neckline - head["price"])
        invalidation = float(head["price"])
    quality = _clamp01(1 - abs(ls["price"] - rs["price"]) / (2 * tol)) if tol > 0 else 0.5
    return Pattern(
        type=name, kind=REVERSAL, direction=direction, state=FORMING,
        bars=[int(ls["bar"]), int(head["bar"]), int(rs["bar"])],
        points=[_pt(ls), _pt(head), _pt(rs)],
        lines=[_hseg(neckline, ls["bar"], rs["bar"])],
        breakout_level=round_price(neckline), invalidation_level=round_price(invalidation),
        target=round_price(float(target)), quality=round(quality, 3),
        reason="Three swings, middle most extreme, matching shoulders; break of the neckline confirms.",
    )


def _detect_triangle(highs, lows, cfg, atr) -> Pattern | None:
    if len(highs) < 3 or len(lows) < 3:
        return None
    flat = cfg.patterns.flat_slope_pct
    hi, lo = highs.tail(3), lows.tail(3)
    mean_price = float(pd.concat([hi["price"], lo["price"]]).mean())
    hi_line = fit_trendline(hi["bar"].to_numpy(), hi["price"].to_numpy(), RESISTANCE)
    lo_line = fit_trendline(lo["bar"].to_numpy(), lo["price"].to_numpy(), SUPPORT)
    hc = _cls(_rel_change_pct(hi_line.slope, hi["bar"].to_numpy(), mean_price), flat)
    lc = _cls(_rel_change_pct(lo_line.slope, lo["bar"].to_numpy(), mean_price), flat)
    upper, lower = float(hi["price"].max()), float(lo["price"].min())

    if hc == "flat" and lc == "rising":
        name, direction, breakout, inval = ASCENDING_TRIANGLE, BULLISH, upper, lower
    elif lc == "flat" and hc == "falling":
        name, direction, breakout, inval = DESCENDING_TRIANGLE, BEARISH, lower, upper
    elif hc == "falling" and lc == "rising":
        name, direction, breakout, inval = SYMMETRIC_TRIANGLE, NEUTRAL_DIR, upper, lower
    else:
        return None

    height = upper - lower
    target = (breakout + height if direction == BULLISH
              else breakout - height if direction == BEARISH else None)
    # Quality from the TEMPLATE fit, not raw r2 (a flat side's r2 is degenerate): the flat side's
    # flatness × the sloped side's linearity.
    tol = cfg.patterns.equal_atr_mult * atr
    hi_r2 = 0.0 if pd.isna(hi_line.r2) else max(0.0, hi_line.r2)
    lo_r2 = 0.0 if pd.isna(lo_line.r2) else max(0.0, lo_line.r2)
    hi_flat = _clamp01(1 - (float(hi["price"].max()) - float(hi["price"].min())) / tol) if tol > 0 else 0.5
    lo_flat = _clamp01(1 - (float(lo["price"].max()) - float(lo["price"].min())) / tol) if tol > 0 else 0.5
    if direction == BULLISH:        # ascending: flat highs × rising lows
        quality = _clamp01(hi_flat * lo_r2)
    elif direction == BEARISH:      # descending: flat lows × falling highs
        quality = _clamp01(lo_flat * hi_r2)
    else:                           # symmetric: both sloped
        quality = _clamp01((hi_r2 + lo_r2) / 2)
    tb0 = int(min(hi["bar"].min(), lo["bar"].min()))
    tb1 = int(max(hi["bar"].max(), lo["bar"].max()))
    return Pattern(
        type=name, kind=CONTINUATION, direction=direction, state=FORMING,
        bars=[int(b) for b in pd.concat([hi["bar"], lo["bar"]]).sort_values()],
        points=[_pt(r) for _, r in pd.concat([hi, lo]).sort_values("bar").iterrows()],
        lines=[_seg(hi_line, tb0, tb1), _seg(lo_line, tb0, tb1)],
        breakout_level=round_price(breakout), invalidation_level=round_price(inval),
        target=None if target is None else round_price(target), quality=round(quality, 3),
        reason="Converging highs and lows (triangle).",
    )


def _detect_rectangle(highs, lows, cfg, atr) -> Pattern | None:
    """A range: flat highs (resistance) and flat lows (support). Continuation until it breaks."""
    if len(highs) < 2 or len(lows) < 2:
        return None
    tol = cfg.patterns.equal_atr_mult * atr
    # The flat top/bottom often span only the last two swings each (older swings belong to the
    # move INTO the range), so 2 flat highs + 2 flat lows define the sideways channel.
    hi, lo = highs.tail(2), lows.tail(2)
    if (hi["price"].max() - hi["price"].min()) > tol or (lo["price"].max() - lo["price"].min()) > tol:
        return None
    upper, lower = float(hi["price"].mean()), float(lo["price"].mean())
    height = upper - lower
    if height < cfg.patterns.depth_atr_mult * atr:      # too shallow to be a real range
        return None
    flat_dev = (hi["price"].max() - hi["price"].min()) + (lo["price"].max() - lo["price"].min())
    quality = _clamp01(1 - flat_dev / (4 * tol)) if tol > 0 else 0.5
    rb0 = int(min(hi["bar"].min(), lo["bar"].min()))
    rb1 = int(max(hi["bar"].max(), lo["bar"].max()))
    return Pattern(
        type=RECTANGLE, kind=CONTINUATION, direction=NEUTRAL_DIR, state=FORMING,
        bars=[int(b) for b in pd.concat([hi["bar"], lo["bar"]]).sort_values()],
        points=[_pt(r) for _, r in pd.concat([hi, lo]).sort_values("bar").iterrows()],
        lines=[_hseg(upper, rb0, rb1), _hseg(lower, rb0, rb1)],
        breakout_level=round_price(upper), invalidation_level=round_price(lower),
        target=round_price(upper + height), quality=round(quality, 3),
        reason="Sideways channel — flat-top resistance and flat-bottom support; a close beyond "
               "either edge resolves it.",
    )


def _detect_channel(highs, lows, cfg, atr, closes=None) -> Pattern | None:
    """Parallel sloped highs and lows — a trending channel (continuation of that trend).
    Thresholds come from `cfg.patterns.channel_*` (B2-tunable). With `channel_respect_rails`, a
    channel is only real if no close since its first anchor went beyond either rail by more than
    `structure.trendline_break_atr_mult` × ATR (A1 finding: least-squares rails needn't be respected)."""
    if len(highs) < 3 or len(lows) < 3:
        return None
    hi, lo = highs.tail(3), lows.tail(3)
    hi_line = fit_trendline(hi["bar"].to_numpy(), hi["price"].to_numpy(), RESISTANCE)
    lo_line = fit_trendline(lo["bar"].to_numpy(), lo["price"].to_numpy(), SUPPORT)
    pc = cfg.patterns
    if hi_line.r2 < pc.channel_min_r2 or lo_line.r2 < pc.channel_min_r2:
        return None
    s1, s2 = hi_line.slope, lo_line.slope
    if s1 * s2 <= 0:                        # slopes must point the same way
        return None
    mean_price = float(pd.concat([hi["price"], lo["price"]]).mean())
    rc = _rel_change_pct((s1 + s2) / 2, hi["bar"].to_numpy(), mean_price)
    if abs(rc) < cfg.patterns.flat_slope_pct:   # ~flat is a rectangle, not a channel
        return None
    parallel = 1 - abs(s1 - s2) / (max(abs(s1), abs(s2)) or 1)
    if parallel < pc.channel_min_parallel:
        return None
    if pc.channel_respect_rails and closes is not None:
        start = int(min(hi["bar"].min(), lo["bar"].min()))
        seg = np.asarray(closes[start:], dtype=float)
        bars = np.arange(start, start + len(seg))
        margin = cfg.structure.trendline_break_atr_mult * atr
        if ((seg > hi_line.slope * bars + hi_line.intercept + margin).any()
                or (seg < lo_line.slope * bars + lo_line.intercept - margin).any()):
            return None

    direction = BULLISH if rc > 0 else BEARISH
    name = ASCENDING_CHANNEL if rc > 0 else DESCENDING_CHANNEL
    last_bar = int(max(hi["bar"].max(), lo["bar"].max()))
    upper, lower = hi_line.value_at(last_bar), lo_line.value_at(last_bar)
    breakout, inval = (upper, lower) if direction == BULLISH else (lower, upper)
    height = abs(upper - lower)
    target = breakout + height if direction == BULLISH else breakout - height
    quality = _clamp01(parallel * (hi_line.r2 + lo_line.r2) / 2)
    cb0 = int(min(hi["bar"].min(), lo["bar"].min()))
    return Pattern(
        type=name, kind=CONTINUATION, direction=direction, state=FORMING,
        bars=[int(b) for b in pd.concat([hi["bar"], lo["bar"]]).sort_values()],
        points=[_pt(r) for _, r in pd.concat([hi, lo]).sort_values("bar").iterrows()],
        lines=[_seg(hi_line, cb0, last_bar), _seg(lo_line, cb0, last_bar)],
        breakout_level=round_price(float(breakout)), invalidation_level=round_price(float(inval)),
        target=round_price(float(target)), quality=round(quality, 3),
        reason="Parallel sloped highs and lows — a channel riding the trend.",
    )


FRESH, IN_PLAY, COMPLETED, EXPIRED = "fresh", "in_play", "completed", "expired"


def _lifecycle(p: Pattern, featured_df: pd.DataFrame, cfg: Config) -> None:
    """What a pattern is NOW, after its breakout — so an old signal is never narrated as current.

      forming   — not broken out yet (state forming)
      failed    — state failed
      completed — confirmed, and price has since REACHED the target (a high/low through it on any
                  bar from the breakout candle to bar N): the move is done; history only
      fresh     — confirmed within the last `patterns.fresh_bars` bars (and target not reached)
      expired   — confirmed longer ago than `expire_duration_mult` × the pattern's own formation
                  length, without reaching the target or failing: history only
      in_play   — confirmed, not fresh, not completed, not expired: the breakout is still being tested

    Look-ahead-safe: reads only bars <= N (the last row of `featured_df`)."""
    n = len(featured_df)
    if p.state == FORMING:
        p.lifecycle = FORMING
        return
    if p.bars_since_state_change is not None:
        p.state_bar = n - 1 - p.bars_since_state_change
    if p.state != CONFIRMED:
        p.lifecycle = p.state                          # "failed"
        return
    if p.state_bar is None:
        p.lifecycle = IN_PLAY
        return
    since = p.bars_since_state_change
    after = featured_df.iloc[p.state_bar:]
    if p.target is not None and len(after):
        hit = (after["high"] >= p.target) if p.direction == BULLISH else (after["low"] <= p.target)
        if hit.any():
            p.target_hit_bar = p.state_bar + int(hit.to_numpy().argmax())
            p.lifecycle = COMPLETED
            return
    pc = cfg.patterns
    if since <= pc.fresh_bars:
        p.lifecycle = FRESH
        return
    duration = max(1, max(p.bars) - min(p.bars)) if p.bars else 1
    p.lifecycle = EXPIRED if since > pc.expire_duration_mult * duration else IN_PLAY


def _cls(rc: float, flat: float) -> str:
    if abs(rc) < flat:
        return "flat"
    return "rising" if rc > 0 else "falling"


def _structure_hit(price, levels, fib, round_number, cfg) -> bool:
    """Does the breakout level coincide with an S/R level, a Fib level, or a round number?"""
    if price is None:
        return False
    tol = cfg.structure.sr_cluster_tolerance_pct / 100.0 * price
    prices: list[float] = []
    if levels is not None:
        prices += [float(x) for x in levels]
    if fib is not None:
        prices += [float(v) for v in fib.levels.values()]
    if round_number is not None:
        prices.append(float(round_number.nearest))
    return any(abs(price - x) <= tol for x in prices)


def find_patterns(
    featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config, *,
    higher_tf_trend: str | None = None, structure_levels=None, fib=None, round_number=None,
    lookback: int = DEFAULT_LOOKBACK,
) -> list[Pattern]:
    """Detect patterns on the recent swings and return deduped `Pattern`s with state + a full
    confirmation profile. Look-ahead-safe: everything reads bars <= the last row of
    `featured_df` (callers slice to bar N in the backtest / historical scrub)."""
    if swings.empty or featured_df.empty:
        return []
    atr = float(featured_df[COL_ATR].iloc[-1]) if COL_ATR in featured_df.columns else float("nan")
    if pd.isna(atr) or atr <= 0:                      # ATR-less fixture: fall back to 1% of price
        atr = float(featured_df["close"].iloc[-1]) * 0.01

    tail = swings.sort_values("bar").tail(lookback)
    highs = tail[tail["kind"] == SWING_HIGH].sort_values("bar")
    lows = tail[tail["kind"] == SWING_LOW].sort_values("bar")

    raw = [
        _detect_head_and_shoulders(highs, lows, cfg, atr, top=True),
        _detect_head_and_shoulders(highs, lows, cfg, atr, top=False),
        _detect_double(highs, lows, cfg, atr, top=True),
        _detect_double(highs, lows, cfg, atr, top=False),
        _detect_triangle(highs, lows, cfg, atr),
        _detect_rectangle(highs, lows, cfg, atr),
        _detect_channel(highs, lows, cfg, atr, closes=featured_df["close"].to_numpy()),
    ]
    patterns = dedupe_patterns([p for p in raw if p is not None])

    last_close = float(featured_df["close"].iloc[-1])
    n_bars = len(featured_df)
    has_structure = structure_levels is not None or fib is not None or round_number is not None
    for p in patterns:
        # neutral coils (symmetric triangle / rectangle) resolve direction on a close beyond an edge
        if p.direction == NEUTRAL_DIR and p.breakout_level is not None and p.invalidation_level is not None:
            hi_b = max(p.breakout_level, p.invalidation_level)
            lo_b = min(p.breakout_level, p.invalidation_level)
            if last_close > hi_b:
                p.direction, p.breakout_level, p.invalidation_level = BULLISH, hi_b, lo_b
            elif last_close < lo_b:
                p.direction, p.breakout_level, p.invalidation_level = BEARISH, lo_b, hi_b
        if p.kind == REVERSAL and p.bars:
            # Reversal patterns remember their history since completion, so a neckline break that
            # price later reclaims reads `failed` instead of reverting to `forming`.
            # The reclaim needs a close back through the neckline by reclaim_atr_mult × THAT bar's
            # ATR (falling back to the bar-N ATR on warm-up/ATR-less frames).
            after = featured_df.iloc[max(p.bars) + 1:]
            bar_atr = (after[COL_ATR].fillna(atr) if COL_ATR in after.columns
                       else pd.Series(atr, index=after.index))
            p.state, reclaimed, since = classify_state_history(
                p.direction, p.breakout_level, p.invalidation_level, after["close"],
                margins=bar_atr * cfg.patterns.reclaim_atr_mult)
            if reclaimed:
                p.reason += " Broke the neckline, then closed back through it: failed break."
            if since is not None:
                p.bars_since_state_change = len(after) - 1 - since
        else:
            p.state = classify_state(p.direction, p.breakout_level, p.invalidation_level, last_close)
            if p.state != FORMING and p.bars:
                # memoryless state: it began where the current unbroken run of same-state closes began
                run, closes = 0, featured_df["close"].iloc[max(p.bars) + 1:].to_numpy(dtype=float)
                for c in closes[::-1]:
                    if classify_state(p.direction, p.breakout_level, p.invalidation_level, c) != p.state:
                        break
                    run += 1
                p.bars_since_state_change = run - 1 if run else None
        if p.bars:
            p.bars_since_completion = n_bars - 1 - max(p.bars)
        _lifecycle(p, featured_df, cfg)
        hit = _structure_hit(p.breakout_level, structure_levels, fib, round_number, cfg) if has_structure else None
        p.confirmation = build_confirmation(
            p.direction, p.breakout_level, p.invalidation_level, featured_df,
            state=p.state, higher_tf_trend=higher_tf_trend, structure_hit=hit,
        )
    return patterns
