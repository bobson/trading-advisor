"""Price precision — how many decimals an instrument's prices need.

Rounding every price to 2 decimals is right for BTC (80,000) and wrong for EUR/USD (1.1464 →
1.15), where it erases levels, zeroes the ATR and moves pattern breakout levels by ~50 pips. One
rule, shared by the facts, the pattern detectors and the chart: decimals follow the price's
magnitude.
"""

from __future__ import annotations


def price_decimals(ref: float) -> int:
    """2 decimals at >= 100 (BTC, SOL), 5 at >= 1 (EUR/USD 1.14689), 6 below 1."""
    p = abs(float(ref))
    if p >= 100:
        return 2
    if p >= 1:
        return 5
    return 6


def round_price(x: float, ref: float | None = None) -> float:
    """Round `x` to the precision of `ref` (default: its own magnitude)."""
    return round(float(x), price_decimals(x if ref is None else ref))


def fmt_price(x: float, ref: float | None = None) -> str:
    """`x` as text with the instrument's fixed decimals ('63944.10', '1.14689')."""
    d = price_decimals(x if ref is None else ref)
    return f"{float(x):.{d}f}"
