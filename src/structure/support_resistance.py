"""Phase 4 — cluster swing points into horizontal support/resistance levels.

Swings that reversed price at roughly the same value mark a level the market respects.
We cluster all swing prices (highs and lows together — a broken resistance often becomes
support, so the level matters regardless of which side first formed it) and score each
level by how many swings touched it. A level's *role* (support vs resistance) is relative
to the current price, so it's assigned separately via `annotate_roles`.

`tolerance_pct` is a PERCENT (config `sr_cluster_tolerance_pct: 0.5` == 0.5%), converted
to a fraction here. Using it directly as a fraction would be a 50% band that collapses
everything into one meaningless mega-level — hence the explicit /100 and its test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SUPPORT = "support"
RESISTANCE = "resistance"


def find_support_resistance(
    swings: pd.DataFrame, tolerance_pct: float, min_touches: int = 2
) -> pd.DataFrame:
    """Cluster swing prices into levels.

    Returns a frame sorted by price with columns `price` (cluster mean) and `touches`
    (swings in the cluster), keeping only levels with at least `min_touches` touches.
    """
    empty = pd.DataFrame(columns=["price", "touches"])
    if swings.empty:
        return empty

    tol = tolerance_pct / 100.0  # percent -> fraction
    prices = np.sort(swings["price"].to_numpy())

    clusters: list[list[float]] = [[float(prices[0])]]
    for p in prices[1:]:
        centroid = float(np.mean(clusters[-1]))
        if abs(p - centroid) / centroid <= tol:
            clusters[-1].append(float(p))
        else:
            clusters.append([float(p)])

    levels = [
        (float(np.mean(c)), len(c)) for c in clusters if len(c) >= min_touches
    ]
    if not levels:
        return empty
    return (
        pd.DataFrame(levels, columns=["price", "touches"])
        .sort_values("price")
        .reset_index(drop=True)
    )


def annotate_roles(levels: pd.DataFrame, last_close: float) -> pd.DataFrame:
    """Add a `role` column: levels below the current price are support, above are resistance."""
    out = levels.copy()
    out["role"] = np.where(out["price"] < last_close, SUPPORT, RESISTANCE)
    return out


# --- ROADMAP A4: support/resistance as ZONES -------------------------------------------------
#
# A single line at 76,132 implies false precision — price respects an AREA. Each level becomes a
# band built from its touching swings, with ATR-scaled width (so it means the same on an 80k BTC
# and a 1.10 EUR/USD), its touch history, a recency-weighted strength, and a stale flag.

ZONE_COLUMNS = ["price", "lower", "upper", "touches", "first_touch", "last_touch",
                "bars_since_touch", "strength", "stale"]


def find_sr_zones(
    swings: pd.DataFrame, atr: float, n_bars: int, *, zone_atr_mult: float = 0.5,
    stale_bars: int = 120, halflife_bars: int = 60, min_touches: int = 2,
) -> pd.DataFrame:
    """Cluster swing prices into support/resistance ZONES.

    - Clustering: a swing joins the current cluster when it is within `zone_atr_mult` × ATR of
      the cluster's centroid (ATR-scaled, not a fixed percent).
    - Band: centred on the touches' mean, as wide as their spread but never narrower than
      `zone_atr_mult` × ATR, and always covering every touch.
    - `first_touch` / `last_touch` are swing BAR positions; `bars_since_touch` counts to the last
      bar (`n_bars - 1`).
    - `strength` = Σ 0.5^(age / halflife_bars) over the touches — recent touches count more.
    - `stale` = untouched for at least `stale_bars` bars (a bar count, so it scales with the
      timeframe rather than a calendar date).

    `price` is the band centre, so every consumer of the old `price`/`touches` frame still works.
    Look-ahead-safe: swings are confirmed pivots and `atr`/`n_bars` come from bars <= N.
    """
    if swings.empty or not (atr > 0):
        return pd.DataFrame(columns=ZONE_COLUMNS)
    tol = zone_atr_mult * atr
    pts = swings.sort_values("price")[["price", "bar"]].to_numpy(dtype=float)

    clusters: list[list[tuple[float, int]]] = [[(pts[0][0], int(pts[0][1]))]]
    run_sum = float(pts[0][0])                    # running sum of the current cluster (O(n), not O(n²))
    for price, bar in pts[1:]:
        centroid = run_sum / len(clusters[-1])
        if abs(price - centroid) <= tol:
            clusters[-1].append((float(price), int(bar)))
            run_sum += float(price)
        else:
            clusters.append([(float(price), int(bar))])
            run_sum = float(price)

    last = n_bars - 1
    rows = []
    for c in clusters:
        if len(c) < min_touches:
            continue
        prices = [p for p, _ in c]
        bars = [b for _, b in c]
        centre = float(np.mean(prices))
        half = max(max(prices) - min(prices), tol) / 2
        lower, upper = min(centre - half, min(prices)), max(centre + half, max(prices))
        since = last - max(bars)
        strength = float(sum(0.5 ** ((last - b) / halflife_bars) for b in bars))
        rows.append((centre, lower, upper, len(c), min(bars), max(bars), since,
                     round(strength, 3), since >= stale_bars))
    if not rows:
        return pd.DataFrame(columns=ZONE_COLUMNS)
    return pd.DataFrame(rows, columns=ZONE_COLUMNS).sort_values("price").reset_index(drop=True)


def zone_distance(zones: pd.DataFrame, price: float) -> pd.Series:
    """Distance from `price` to each zone's band: 0 inside the band, else to the nearer edge."""
    below = (zones["lower"] - price).clip(lower=0)
    above = (price - zones["upper"]).clip(lower=0)
    return below + above


def current_atr(featured_df: pd.DataFrame) -> float:
    """ATR at the last bar (falls back to 1% of price on warm-up / ATR-less frames)."""
    from src.indicators.features import COL_ATR   # local: keep this module import-light
    last_close = float(featured_df["close"].iloc[-1])
    atr = float(featured_df[COL_ATR].iloc[-1]) if COL_ATR in featured_df.columns else float("nan")
    return atr if atr == atr and atr > 0 else last_close * 0.01


def sr_zones(featured_df: pd.DataFrame, swings: pd.DataFrame, cfg) -> pd.DataFrame:
    """The ONE way zones are built from a featured frame + swings + config — facts, confluence,
    the service and the chart all call this, so the drawn band is the band that voted."""
    s = cfg.structure
    return find_sr_zones(swings, current_atr(featured_df), len(featured_df),
                         zone_atr_mult=s.sr_zone_atr_mult, stale_bars=s.sr_stale_bars,
                         halflife_bars=s.sr_strength_halflife_bars)
