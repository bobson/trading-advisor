"""Feature 2 — deduplicate overlapping pattern detections.

Detectors legitimately co-fire on the same swings — an ascending triangle's near-equal highs
also read as a double top, a channel and a rectangle can share boundaries. When two detections
cover substantially the same bar range, keep the highest-QUALITY one (quality is geometry only,
so this choice is stable as price moves — see base.py).
"""

from __future__ import annotations

from src.patterns.base import CONTINUATION, Pattern


def _overlap_fraction(a: Pattern, b: Pattern) -> float:
    """Intersection of the two bar spans as a fraction of the SMALLER span (1.0 = fully covered)."""
    a0, a1 = a.span
    b0, b1 = b.span
    inter = max(0, min(a1, b1) - max(a0, b0))
    smaller = min(a1 - a0, b1 - b0)
    return inter / smaller if smaller > 0 else (1.0 if inter >= 0 and (a0, a1) == (b0, b1) else 0.0)


def dedupe_patterns(patterns: list[Pattern], *, overlap_threshold: float = 0.5) -> list[Pattern]:
    """Greedy by quality: keep the best, drop any later pattern overlapping a kept one by at least
    `overlap_threshold` of the smaller span. Ties break toward CONTINUATION patterns (the use case
    is trend riding) then more touch points, so it's deterministic and continuation-first."""
    kept: list[Pattern] = []
    ranked = sorted(patterns, key=lambda x: (x.quality, x.kind == CONTINUATION, len(x.bars), x.span[0]),
                    reverse=True)
    for p in ranked:
        if any(_overlap_fraction(p, k) >= overlap_threshold for k in kept):
            continue
        kept.append(p)
    kept.sort(key=lambda x: x.span[0])   # chronological for display
    return kept
