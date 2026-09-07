"""Phase 19 — market adaptation: the same detectors, made market-aware.

The indicators are identical formulas for crypto and forex, but a few things genuinely
differ, and surfacing them as CONTEXT (facts for Layer 2) is what makes the advisor "good for
both" rather than crypto-only. This module does NOT change any vote — it annotates:

  - **Volume means different things.** Crypto exchanges report real traded volume; most forex
    feeds report only TICK volume (a count of price updates) as a proxy. So forex volume is
    flagged weaker/contextual and the explanation is told to treat it as such — never present
    tick volume like real volume.
  - **Sessions & weekend gaps (forex only).** Forex has Tokyo/London/New-York sessions with
    very different volatility, and a weekend gap (Sunday's open can jump from Friday's close).
    Crypto is 24/7, so these are skipped.
  - **Volatility calibration.** A "significant move" is expressed as a multiple of ATR, so the
    notion scales sensibly between a ~80k BTC and a ~1.10 EUR/USD instead of a fixed percent.

Wiring ATR-relative thresholds into the *votes* is deliberately deferred: it is a vote-path
change whose whole purpose is cross-market, and it can only be measured once real forex data
exists (Phase 26). TODO(phase-26): revisit ATR-relative proximity AND tick-volume vote-weight
together, backtesting crypto first.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config import Config
from src.data.base import CRYPTO, FOREX
from src.data.registry import asset_class_for
from src.indicators.features import COL_ATR


@dataclass
class MarketContext:
    asset_class: str
    volume_type: str                 # "real" (crypto) | "tick" (forex proxy)
    is_24_7: bool
    active_session: str | None       # forex only
    weekend_gap: bool | None         # forex only
    significant_move_pct: float | None  # ATR * mult, as a percent of price


def _forex_session(hour_utc: int) -> str:
    """The dominant forex session for a UTC hour (approximate, standard boundaries)."""
    if 13 <= hour_utc < 16:
        return "London/New York overlap"   # the most volatile window
    if 8 <= hour_utc < 13:
        return "London"
    if 16 <= hour_utc < 21:
        return "New York"
    if 0 <= hour_utc < 8:
        return "Tokyo"
    return "Sydney / thin liquidity"


def _weekend_gap(featured_df: pd.DataFrame) -> bool:
    """True when the last bar follows an unusually large gap that crosses a weekend — the
    classic forex Sunday-open jump from Friday's close.
    """
    idx = featured_df.index
    if len(idx) < 3 or not isinstance(idx, pd.DatetimeIndex):
        return False
    deltas = idx.to_series().diff().dropna()
    step = deltas.median()
    if step <= pd.Timedelta(0):
        return False
    last_gap = idx[-1] - idx[-2]
    crosses_weekend = idx[-2].weekday() == 4 or idx[-1].weekday() in (5, 6)  # Fri before / Sat-Sun after
    return bool(last_gap > step * 2 and crosses_weekend)


def market_context(symbol: str, featured_df: pd.DataFrame, cfg: Config) -> MarketContext:
    """Build the market-aware context for `symbol` from its featured frame."""
    asset_class = asset_class_for(symbol)
    last_close = float(featured_df["close"].iloc[-1])

    atr = featured_df[COL_ATR].iloc[-1] if COL_ATR in featured_df.columns else float("nan")
    mult = cfg.market_adaptation.significant_move_atr_mult
    significant = (
        None if pd.isna(atr) or last_close <= 0
        else round(float(atr) / last_close * 100.0 * mult, 3)
    )

    if asset_class == FOREX:
        ts = featured_df.index[-1]
        hour = ts.hour if isinstance(featured_df.index, pd.DatetimeIndex) else 0
        return MarketContext(
            asset_class=FOREX,
            volume_type="tick",
            is_24_7=False,
            active_session=_forex_session(hour),
            weekend_gap=_weekend_gap(featured_df),
            significant_move_pct=significant,
        )

    return MarketContext(
        asset_class=CRYPTO,
        volume_type="real",
        is_24_7=True,
        active_session=None,
        weekend_gap=None,
        significant_move_pct=significant,
    )
