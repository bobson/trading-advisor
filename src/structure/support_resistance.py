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
