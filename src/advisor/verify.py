"""Phase 20 — Layer-2 consistency check: enforce "never contradict Layer 1".

The project's hard rule is that Claude explains the computed facts and never invents numbers.
This module *checks* that instead of hoping. The model only ever sees `facts_to_prompt(facts)`,
so the authoritative set is exactly the numbers in THAT text — we extract price-like numbers
from the facts text and from the explanation with the same extractor, and flag any number the
explanation cites, in the price-magnitude band, that matches nothing the model was shown.

It is ADVISORY: it returns `{ok, issues}` and never raises or blocks. Magnitude filtering has
inherent limits — on a mid-priced asset (e.g. SOL ~150) an indicator value like Stochastic 80
can fall in-band and false-flag; on BTC (indicators sit far below 0.5x price) it's clean. That
residual noise is exactly why this informs rather than gates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.advisor.facts import facts_to_prompt

# Matches $79,381.62 / 79381.62 / 80,000 / 80k / 1.1043 — number with optional $, thousands
# commas, decimals, and a k suffix.
_PRICE_RE = re.compile(r"\$?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(k)?", re.IGNORECASE)


def extract_prices(text: str) -> list[float]:
    """Every price-like number in `text`, comma/`$`/`k` normalized to a float."""
    out: list[float] = []
    for m in _PRICE_RE.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2):  # 'k' suffix
            value *= 1000.0
        out.append(value)
    return out


@dataclass
class VerificationResult:
    ok: bool
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": list(self.issues)}


def verify_explanation(
    explanation: str,
    facts: dict,
    *,
    tolerance_pct: float = 1.0,
    band: tuple[float, float] = (0.5, 1.5),
) -> VerificationResult:
    """Flag price levels the explanation cites that the facts never showed it.

    Only numbers within `band` x the last close are checked (so RSI/ratios/percentages, which
    live far from price magnitude, are ignored). A cited number passes if it is within
    `tolerance_pct` of ANY number in the facts text (tolerance absorbs the model rounding
    79,381.62 to "79,400").
    """
    last_close = float(facts["market"]["last_close"])
    lo, hi = last_close * band[0], last_close * band[1]

    authoritative = extract_prices(facts_to_prompt(facts))
    issues: list[str] = []
    seen: set[float] = set()
    for num in extract_prices(explanation):
        if not (lo <= num <= hi) or num in seen:
            continue
        seen.add(num)
        if not any(a > 0 and abs(num - a) / a * 100.0 <= tolerance_pct for a in authoritative):
            issues.append(
                f"Explanation cites {num:g}, which is not within {tolerance_pct}% of any price "
                "the computed facts contain — possible fabricated level."
            )
    return VerificationResult(ok=not issues, issues=issues)
