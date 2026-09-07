"""Phase 18 — psychological round-number levels.

Round prices (1.1000 in FX, 80,000 in BTC) act as magnets and barriers — traders cluster
orders there. The "roundness" scale has to follow price magnitude: 1,000 steps make sense for
a ~80k BTC, 0.01 steps for a ~1.10 EUR/USD. We derive the step from the price's order of
magnitude so one function works across every market.

This is a FACT (context for Layer 2), not a vote yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.config import Config


@dataclass
class RoundNumber:
    nearest: float       # the nearest round level to price
    step: float          # the rounding increment used (scales with price magnitude)
    distance_pct: float  # how far price sits from it, percent
    is_near: bool        # within structure.round_number_pct


def nearest_round_number(price: float, cfg: Config) -> RoundNumber | None:
    """The nearest psychological round level to `price`, or None for a non-positive price.

    Step = one order of magnitude below the price (79,381 -> 1,000 -> nearest 79,000;
    1.1043 -> 0.01 -> nearest 1.10), so the notion of "round" adapts to the instrument.
    """
    if price <= 0:
        return None
    step = 10 ** (math.floor(math.log10(price)) - 1)
    nearest = round(price / step) * step
    distance_pct = abs(price - nearest) / price * 100.0
    return RoundNumber(
        nearest=round(float(nearest), 2),
        step=float(step),
        distance_pct=round(float(distance_pct), 3),
        is_near=distance_pct <= cfg.structure.round_number_pct,
    )
