"""Confluence engine — Phase 6 (tally) rebuilt in Phase 17 as a category-aware confidence.

Still Layer 1: it does not reason, it scores. Each detector emits a `Signal` (bullish /
bearish / neutral + a reason). But raw votes double-count correlated signals (rsi & macd are
both momentum; S/R & fib & a candle at a level are all "structure"), so Phase 17 groups
signals into INDEPENDENT categories (see `SIGNAL_CATEGORY`), collapses each to one net vote,
and scores by category weight:

  - `evaluate_confluence(signals, cfg)` is pure over a `Signal` list: each category nets a
    direction (majority of its own signals), the heavier-weighted side wins (a weight tie nets
    neutral), and `confidence` is the winning weight as a fraction of the ACTIVE category
    weight — a genuine 0–1 that rewards breadth across categories. A setup is flagged only when
    at least `require_categories` categories agree. This confidence is PRE-MTF.
  - `gather_signals(featured_df, swings, cfg)` wires the real detectors into that list.
  - `analyze_confluence(...)` runs both AND `resolve_mtf`, so every one-call consumer sees the
    FINAL confidence/verdict (the multi-timeframe gate can veto a flag and grade the score).

Neutral votes are recorded but never push a category toward a side. NaN indicator values on
short frames vote NEUTRAL rather than letting a NaN comparison silently decide.

Backtest verdict (BTC/USDT 1h): the category COLLAPSE improved selectivity (overall win-rate
best of any phase); the category WEIGHTS added ~nothing over uniform and are kept as untuned
neutral priors — deliberately not fitted to the backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.config import Config
from src.indicators.features import (
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_RSI,
    COL_VOLUME,
    COL_VOLUME_MA,
)
from src.structure.fibonacci import UP, FibRetracement, fib_retracement
from src.structure.support_resistance import (
    RESISTANCE,
    SUPPORT,
    annotate_roles,
    find_support_resistance,
)
from src.structure.trend import (
    DOWNTREND,
    UPTREND,
    TrendResult,
    classify_trend,
)

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

# Fib ratios that count as meaningful retracement support/resistance (the shallow 0.236
# and the full 0.0/1.0 endpoints are not "price holding a level").
KEY_FIB_RATIOS = [0.382, 0.5, 0.618, 0.786]

# Phase 17: which INDEPENDENT category each detector belongs to. Signals inside one category
# are correlated (rsi & macd are both momentum; S/R & fib & a candle at a level are all
# "structure"), so they collapse to a single category vote instead of double-counting. This is
# the fix for the S/R+fib overlap the plan calls out (the same reason the trendline vote was
# dropped in Phase 6). Volatility has no detector until Phase 18.
SIGNAL_CATEGORY = {
    "trend": "trend",
    "rsi": "momentum",
    "macd": "momentum",
    "candlestick": "structure",
    "support_resistance": "structure",
    "fibonacci": "structure",
    "volume": "volume",
}


@dataclass
class Signal:
    name: str          # detector that voted, e.g. "trend"
    direction: str     # bullish | bearish | neutral
    reason: str        # plain-language justification


@dataclass
class ConfluenceResult:
    bias: str                 # bullish | bearish | neutral (of the winning side)
    triggered: bool           # did the winning side span >= require_categories (and survive MTF)?
    confidence: float         # 0–1 score (pre-MTF out of evaluate_confluence; FINAL after resolve_mtf)
    agreeing_categories: int  # how many independent categories net the winning bias
    signals: list[Signal] = field(default_factory=list)  # every vote, in order
    categories: dict = field(default_factory=dict)       # category -> net direction (collapsed)
    # Phase 16 multi-timeframe context (set by structure.mtf.resolve_mtf; None = no MTF applied).
    mtf_alignment: Optional[str] = None      # "aligned" | "conflict" | "neutral" | None
    mtf_trends: Optional[dict] = None        # {higher_timeframe: trend_label}
    mtf_downgraded: bool = False             # True when the MTF gate flipped triggered off

    @property
    def bullish(self) -> list[Signal]:
        return [s for s in self.signals if s.direction == BULLISH]

    @property
    def bearish(self) -> list[Signal]:
        return [s for s in self.signals if s.direction == BEARISH]

    @property
    def contributing(self) -> list[Signal]:
        """Signals that drive the WINNING CATEGORIES — category-consistent with the score.

        A signal only contributes if it points the winning way AND its category netted that
        way; a lone bullish candle inside a structure category that netted bearish is not
        listed, so the reasons never contradict the category breakdown.
        """
        if self.bias not in (BULLISH, BEARISH):
            return []
        winning = {cat for cat, direction in self.categories.items() if direction == self.bias}
        return [
            s for s in self.signals
            if s.direction == self.bias and SIGNAL_CATEGORY.get(s.name) in winning
        ]

    @property
    def reasons(self) -> list[str]:
        """The winning categories' reasons — what to show when a setup is flagged."""
        return [s.reason for s in self.contributing]


# --- per-detector votes (pure; take already-computed facts) --------------------

def signal_from_trend(trend: TrendResult) -> Signal:
    if trend.label == UPTREND:
        direction = BULLISH
    elif trend.label == DOWNTREND:
        direction = BEARISH
    else:
        direction = NEUTRAL
    # The trend detector already carries its reasoning; pass its summary line through.
    reason = trend.reasons[0] if trend.reasons else f"Trend is {trend.label}."
    return Signal("trend", direction, reason)


def signal_from_rsi(featured_df: pd.DataFrame, cfg: Config) -> Signal:
    rsi = featured_df[COL_RSI].iloc[-1]
    if pd.isna(rsi):
        return Signal("rsi", NEUTRAL, "Not enough history yet to read RSI.")
    rsi = float(rsi)
    ind = cfg.indicators
    if rsi <= ind.rsi_oversold:
        return Signal("rsi", BULLISH, f"RSI is {rsi:.0f}, oversold (below {ind.rsi_oversold}).")
    if rsi >= ind.rsi_overbought:
        return Signal("rsi", BEARISH, f"RSI is {rsi:.0f}, overbought (above {ind.rsi_overbought}).")
    return Signal("rsi", NEUTRAL, f"RSI is {rsi:.0f}, in the neutral zone.")


def signal_from_macd(featured_df: pd.DataFrame) -> Signal:
    macd = featured_df[COL_MACD].iloc[-1]
    signal = featured_df[COL_MACD_SIGNAL].iloc[-1]
    if pd.isna(macd) or pd.isna(signal):
        return Signal("macd", NEUTRAL, "Not enough history yet to read MACD.")
    if macd > signal:
        return Signal("macd", BULLISH, "MACD line is above its signal line (bullish momentum).")
    if macd < signal:
        return Signal("macd", BEARISH, "MACD line is below its signal line (bearish momentum).")
    return Signal("macd", NEUTRAL, "MACD line is level with its signal line.")


def signal_from_patterns(featured_df: pd.DataFrame) -> Signal:
    last = featured_df.iloc[-1]
    if bool(last[COL_BULLISH_ENGULFING]):
        return Signal("candlestick", BULLISH, "The last candle is a bullish engulfing.")
    if bool(last[COL_HAMMER]):
        return Signal("candlestick", BULLISH, "The last candle is a hammer (potential bullish reversal).")
    if bool(last[COL_BEARISH_ENGULFING]):
        return Signal("candlestick", BEARISH, "The last candle is a bearish engulfing.")
    if bool(last[COL_DOJI]):
        return Signal("candlestick", NEUTRAL, "The last candle is a doji (indecision).")
    return Signal("candlestick", NEUTRAL, "No notable candlestick pattern on the last candle.")


def signal_from_volume(featured_df: pd.DataFrame, cfg: Config) -> Signal:
    """Volume CONFIRMS the last candle's direction — it doesn't have a direction of its own.

    A move on above-average volume (>= `confluence.volume_confirm_factor` x the volume MA) is
    backed by participation, so it votes in the candle's direction (up candle -> bullish,
    down candle -> bearish). Below that bar — or with no volume data at all — it votes NEUTRAL:
    a move on thin volume is not confirmed, so it must not add weight to a setup. (Phase 17
    replaces this vote with a proper strength multiplier once confluence carries a confidence.)
    """
    if COL_VOLUME not in featured_df.columns or COL_VOLUME_MA not in featured_df.columns:
        return Signal("volume", NEUTRAL, "No volume data to confirm the move.")

    vol = featured_df[COL_VOLUME].iloc[-1]
    vol_ma = featured_df[COL_VOLUME_MA].iloc[-1]
    if pd.isna(vol) or pd.isna(vol_ma) or vol_ma <= 0:
        return Signal("volume", NEUTRAL, "Not enough history yet to gauge average volume.")

    ratio = float(vol) / float(vol_ma)
    factor = cfg.confluence.volume_confirm_factor
    if ratio < factor:
        return Signal(
            "volume", NEUTRAL,
            f"Volume is {ratio:.1f}x its average — below the {factor:g}x bar, so the move is "
            "not confirmed by participation.",
        )

    open_ = float(featured_df["open"].iloc[-1])
    close = float(featured_df["close"].iloc[-1])
    if close > open_:
        return Signal("volume", BULLISH, f"Above-average volume ({ratio:.1f}x) confirms the up candle.")
    if close < open_:
        return Signal("volume", BEARISH, f"Above-average volume ({ratio:.1f}x) confirms the down candle.")
    return Signal("volume", NEUTRAL, f"Above-average volume ({ratio:.1f}x) but the candle is flat.")


def signal_from_support_resistance(
    levels: pd.DataFrame, last_close: float, proximity_pct: float
) -> Signal:
    """Vote bullish if price is sitting on a support level (potential bounce), bearish if
    pressed against a resistance level. Uses the nearest level within `proximity_pct`.
    """
    if levels.empty:
        return Signal("support_resistance", NEUTRAL, "No support/resistance levels detected.")

    roled = annotate_roles(levels, last_close)
    roled = roled.assign(distance_pct=(roled["price"] - last_close).abs() / last_close * 100.0)
    near = roled[roled["distance_pct"] <= proximity_pct]
    if near.empty:
        return Signal("support_resistance", NEUTRAL, "Price is not near a support/resistance level.")

    nearest = near.sort_values("distance_pct").iloc[0]
    price = float(nearest["price"])
    if nearest["role"] == SUPPORT:
        return Signal("support_resistance", BULLISH, f"Price is testing support near {price:.2f}.")
    return Signal("support_resistance", BEARISH, f"Price is testing resistance near {price:.2f}.")


def signal_from_fibonacci(
    fib: FibRetracement | None, last_close: float, proximity_pct: float
) -> Signal:
    """Vote when price is holding a key retracement level. On an up-leg those levels act as
    support (bullish); on a down-leg as resistance (bearish).
    """
    if fib is None:
        return Signal("fibonacci", NEUTRAL, "No clean price leg to draw Fibonacci on.")

    hits = [
        (r, price)
        for r, price in fib.levels.items()
        if r in KEY_FIB_RATIOS and abs(price - last_close) / last_close * 100.0 <= proximity_pct
    ]
    if not hits:
        return Signal("fibonacci", NEUTRAL, "Price is not near a key Fibonacci level.")

    ratio, price = min(hits, key=lambda rp: abs(rp[1] - last_close))
    pct = f"{ratio * 100:.1f}%"
    if fib.direction == UP:
        return Signal("fibonacci", BULLISH, f"Price is holding the {pct} Fibonacci retracement (support) near {price:.2f}.")
    return Signal("fibonacci", BEARISH, f"Price is stalling at the {pct} Fibonacci retracement (resistance) near {price:.2f}.")


# --- aggregation ---------------------------------------------------------------

def _category_net(signals: list[Signal], category: str) -> str:
    """A category's single net direction: the majority of its own signals (a tie or
    all-neutral nets NEUTRAL). This is where correlated signals collapse to one vote.
    """
    members = [s for s in signals if SIGNAL_CATEGORY.get(s.name) == category]
    bull = sum(1 for s in members if s.direction == BULLISH)
    bear = sum(1 for s in members if s.direction == BEARISH)
    if bull > bear:
        return BULLISH
    if bear > bull:
        return BEARISH
    return NEUTRAL


def evaluate_confluence(
    signals: list[Signal], cfg: Config, *, require_categories: Optional[int] = None
) -> ConfluenceResult:
    """Category-aware confluence with a 0–1 confidence (Phase 17).

    Each independent category (trend / momentum / structure / volume / …) contributes ONE net
    vote — correlated signals inside a category collapse instead of double-counting. The side
    with the greater summed category WEIGHT wins (a weight tie nets neutral). Confidence is the
    winning weight as a fraction of the weight of all ACTIVE categories (those with a signal),
    so it is a genuine 0–1 that rewards breadth across categories. A setup is flagged only when
    at least `require_categories` categories net the winning bias.

    This confidence is PRE-MTF; `structure.mtf.resolve_mtf` produces the final value and may
    veto the flag. Weights come from config and are deliberately not tuned to the backtest.
    """
    if require_categories is None:
        require_categories = cfg.confluence.require_categories
    weights = cfg.confluence.category_weights

    active = sorted({SIGNAL_CATEGORY[s.name] for s in signals if s.name in SIGNAL_CATEGORY})
    categories = {cat: _category_net(signals, cat) for cat in active}

    bull_w = sum(weights.get(cat, 1.0) for cat, d in categories.items() if d == BULLISH)
    bear_w = sum(weights.get(cat, 1.0) for cat, d in categories.items() if d == BEARISH)
    total_w = sum(weights.get(cat, 1.0) for cat in active)

    if bull_w > bear_w:
        bias, win_w = BULLISH, bull_w
    elif bear_w > bull_w:
        bias, win_w = BEARISH, bear_w
    else:
        bias, win_w = NEUTRAL, 0.0

    agreeing = sum(1 for d in categories.values() if d == bias) if bias != NEUTRAL else 0
    confidence = round(win_w / total_w, 3) if total_w > 0 else 0.0
    triggered = bias != NEUTRAL and agreeing >= require_categories

    return ConfluenceResult(
        bias=bias,
        triggered=triggered,
        confidence=confidence,
        agreeing_categories=agreeing,
        signals=list(signals),
        categories=categories,
    )


def gather_signals(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config) -> list[Signal]:
    """Run every detector on the featured frame + swings and collect their votes."""
    last_close = float(featured_df["close"].iloc[-1])
    tol = cfg.structure.sr_cluster_tolerance_pct
    prox = cfg.confluence.proximity_pct

    trend = classify_trend(featured_df, swings)
    levels = find_support_resistance(swings, tol)
    fib = fib_retracement(swings)

    return [
        signal_from_trend(trend),
        signal_from_rsi(featured_df, cfg),
        signal_from_macd(featured_df),
        signal_from_patterns(featured_df),
        signal_from_support_resistance(levels, last_close, prox),
        signal_from_fibonacci(fib, last_close, prox),
        signal_from_volume(featured_df, cfg),
    ]


def analyze_confluence(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config) -> ConfluenceResult:
    """Convenience: gather votes, score them, AND apply the multi-timeframe gate — so every
    consumer of this one-call path sees the same FINAL confidence/verdict as facts and the
    backtest (never a pre-MTF number). `resolve_mtf` is imported lazily to avoid a cycle.
    """
    from src.structure.mtf import resolve_mtf

    signals = gather_signals(featured_df, swings, cfg)
    result = evaluate_confluence(signals, cfg)
    return resolve_mtf(result, featured_df, cfg)
