"""Feature 2 — overlapping detections collapse to the highest-quality one."""

from __future__ import annotations

from src.patterns.base import CONTINUATION, FORMING, Pattern
from src.patterns.dedupe import dedupe_patterns


def _p(bars, quality, type_="x"):
    return Pattern(type=type_, kind=CONTINUATION, direction="bullish", state=FORMING,
                   bars=bars, quality=quality)


def test_overlapping_keeps_highest_quality():
    a = _p([10, 15, 20], 0.9, "triangle")
    b = _p([11, 16, 21], 0.5, "double top")   # ~same range, lower quality
    out = dedupe_patterns([b, a])
    assert len(out) == 1 and out[0].type == "triangle"


def test_non_overlapping_both_survive():
    a = _p([10, 20], 0.4)
    b = _p([50, 60], 0.9)
    out = dedupe_patterns([a, b])
    assert len(out) == 2
    assert [p.span[0] for p in out] == [10, 50]   # returned chronologically


def test_small_overlap_below_threshold_keeps_both():
    a = _p([10, 30], 0.9)          # span 20
    b = _p([28, 48], 0.8)          # overlaps bars 28..30 = 2 of smaller span 20 -> 0.1 < 0.5
    assert len(dedupe_patterns([a, b])) == 2


def test_identical_span_keeps_better():
    out = dedupe_patterns([_p([5, 9], 0.3, "a"), _p([5, 9], 0.7, "b")])
    assert len(out) == 1 and out[0].type == "b"
