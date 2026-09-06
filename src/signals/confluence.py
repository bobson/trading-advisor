"""Phase 6 — confluence engine: turn each detector into a vote, then flag a setup only
when enough of them agree.

The core rule of this project is that Layer 1 states facts; the confluence engine is still
Layer 1 — it does not reason, it *tallies*. Each detector emits a `Signal` (a direction —
bullish / bearish / neutral — plus a plain-language reason). `evaluate_confluence` counts
the directional votes: the side with strictly more votes wins, and a setup is flagged only
if that winning side reaches `min_agreeing_signals`. A tie (equal bullish and bearish votes)
never fires — genuine disagreement is not a setup.

The engine is split in two on purpose:
  - `evaluate_confluence(signals, min_agreeing)` is pure and knows nothing about candles;
    you can hand it a list of `Signal`s built by hand and assert the flag. This is what the
    phase's "done when" check exercises.
  - `gather_signals(featured_df, swings, cfg)` wires the real detectors into that list.

Neutral votes are recorded (they explain what the engine looked at) but never push the
count toward a setup. NaN indicator values on very short frames vote NEUTRAL rather than
letting a NaN comparison silently decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class Signal:
    name: str          # detector that voted, e.g. "trend"
    direction: str     # bullish | bearish | neutral
    reason: str        # plain-language justification


@dataclass
class ConfluenceResult:
    bias: str                 # bullish | bearish | neutral (of the winning side)
    triggered: bool           # did the winning side reach min_agreeing?
    agreeing: int             # votes on the winning side
    signals: list[Signal] = field(default_factory=list)  # every vote, in order

    @property
    def bullish(self) -> list[Signal]:
        return [s for s in self.signals if s.direction == BULLISH]

    @property
    def bearish(self) -> list[Signal]:
        return [s for s in self.signals if s.direction == BEARISH]

    @property
    def contributing(self) -> list[Signal]:
        """The signals on the winning side — the ones that justify the flag."""
        if self.bias == BULLISH:
            return self.bullish
        if self.bias == BEARISH:
            return self.bearish
        return []

    @property
    def reasons(self) -> list[str]:
        """The winning side's reasons — what to show when a setup is flagged."""
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

def evaluate_confluence(signals: list[Signal], min_agreeing: int) -> ConfluenceResult:
    """Tally votes. The side with strictly more votes wins; a setup is flagged only if the
    winning side has at least `min_agreeing` votes. A tie never fires.
    """
    bull = sum(1 for s in signals if s.direction == BULLISH)
    bear = sum(1 for s in signals if s.direction == BEARISH)

    if bull > bear:
        bias, agreeing = BULLISH, bull
    elif bear > bull:
        bias, agreeing = BEARISH, bear
    else:
        return ConfluenceResult(NEUTRAL, False, bull, list(signals))

    triggered = agreeing >= min_agreeing
    return ConfluenceResult(bias, triggered, agreeing, list(signals))


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
    ]


def analyze_confluence(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg: Config) -> ConfluenceResult:
    """Convenience: gather every detector's vote and evaluate it in one call."""
    signals = gather_signals(featured_df, swings, cfg)
    return evaluate_confluence(signals, cfg.confluence.min_agreeing_signals)
