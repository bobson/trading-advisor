"""ROADMAP C1 (slim) — the integrity guard: Claude's explanation is checked against the facts it was
given, mechanically, instead of by the guide's §11 self-check.

The prose stays prose (the full spec's structured-claims rebuild was scoped down with the user); every
explanation is checked AFTER it is written. False alarms are the real risk — a hard failure costs a
retry and can replace a good explanation with the facts-only fallback — so only PRECISE checks are
hard, and anything heuristic is soft (a warning badge, never a rewrite).

HARD (one retry with the violation list; if it still fails, the deterministic facts-only summary):
  invented_price     a price-magnitude number (0.5–1.5 × last close) that matches no number in the
                     facts text AT THE PRECISION IT IS WRITTEN (84,400 matches 84,410.24 at hundreds;
                     1.1391 must match to the fourth decimal). Dates and times are stripped first.
  contradicts_absence  affirming what the facts list as NOT PRESENT (a divergence, a confirmed or a
                     failed chart pattern) outside a negated sentence.
  state_upgrade      a pattern the facts call forming (or failed) described as confirmed / broken out,
                     outside a conditional or negated sentence ("a close above X would confirm it"
                     passes).
  opposite_direction a directional claim phrase ("favours the bulls", "likely to fall", "path of least
                     resistance is up" …) opposing the Layer-1 bias. Bare "bullish"/"bearish" never
                     count — the Opposing line and category reads use them correctly.
SOFT (badge only):
  directional_phrase a directional claim phrase when the tier is no_setup or the bias is neutral.
  missing_opposing   no "Opposing:" line although a strongest opposing fact was supplied.
  over_budget        brief mode only: more than 1.2 × the tier's word budget (the Opposing line is
                     not counted).
  unknown_pattern    a chart-pattern name that isn't in the facts, outside a negated sentence.
  history_as_current a completed / expired pattern described as a current setup.
Not checked: the multi-timeframe synthesis (morning report and --timeframes CLI).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.advisor.facts import facts_to_prompt

HARD = ("invented_price", "contradicts_absence", "state_upgrade", "opposite_direction")
BUDGET_MARGIN = 1.2

_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\+\d{2}:\d{2})?)?(?:\s*UTC)?\b"
                      r"|\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|CEST|CET)?\b"
                      r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?\b"
                      r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?\b")
# A number may end a sentence ("…at 91,234.56."): only a digit, or a dot FOLLOWED by a digit, extends it.
_NUM_RE = re.compile(r"\$?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(k)?(?!\d)(?!\.\d)", re.IGNORECASE)

_NEGATION = re.compile(r"\b(no|not|none|never|without|absent|lacks?|lacking|isn't|aren't|wasn't|hasn't|haven't"
                       r"|doesn't|didn't|nor|neither)\b|n't\b", re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(would|could|if|unless|needs?|until|yet|watch|once|only on|on a close|when|should"
                          r"|to confirm|for confirmation|confirmation (?:would|needs|requires)|awaiting|pending)\b",
                          re.IGNORECASE)
_CONFIRMED_WORDS = re.compile(r"\b(confirmed|confirms|broke out|broken out|has broken|breakout (?:has|had) "
                              r"(?:occurred|happened)|completed the breakout)\b", re.IGNORECASE)

_UP = [r"suggests? (?:further |more )?(?:upside|higher prices|a (?:rally|move up|push higher))",
       r"favou?rs? (?:the )?(?:bulls|upside|buyers|longs)", r"likely to (?:rise|rally|climb|move higher|break (?:out|higher|up))",
       r"poised (?:to|for) (?:rise|rally|climb|break out|move higher|(?:the )?upside|a rally)",
       r"path of least resistance (?:is|looks|appears|remains) (?:up|higher|to the upside)",
       r"(?:buyers|bulls) (?:are|remain|stay) in control", r"set (?:to|for) (?:rally|rise|climb|move higher)"]
_DOWN = [r"suggests? (?:further |more )?(?:downside|lower prices|a (?:drop|decline|move down|push lower|sell-?off))",
         r"favou?rs? (?:the )?(?:bears|downside|sellers|shorts)", r"likely to (?:fall|drop|decline|slide|move lower|break (?:down|lower))",
         r"poised (?:to|for) (?:fall|drop|decline|break down|move lower|(?:the )?downside|a drop)",
         r"path of least resistance (?:is|looks|appears|remains) (?:down|lower|to the downside)",
         r"(?:sellers|bears) (?:are|remain|stay) in control", r"set (?:to|for) (?:fall|drop|decline|move lower)"]
_UP_RE = re.compile("|".join(_UP), re.IGNORECASE)
_DOWN_RE = re.compile("|".join(_DOWN), re.IGNORECASE)

# chart-pattern vocabulary: full names + the generic word each one belongs to
_PATTERN_NAMES = ("double top", "double bottom", "triple top", "triple bottom", "inverse head and shoulders",
                  "head and shoulders", "ascending triangle", "descending triangle", "symmetric triangle",
                  "sideways channel", "ascending channel", "descending channel", "rising wedge", "falling wedge",
                  "bull flag", "bear flag", "pennant", "cup and handle", "rectangle")
_HISTORY_AS_CURRENT = re.compile(r"\b(current|active|live|valid|in play|setup (?:is|remains)|is forming|still forming)\b",
                                 re.IGNORECASE)
_PAST = re.compile(r"\b(completed|expired|history|historical|earlier|past|previous|already reached|played out)\b",
                   re.IGNORECASE)


@dataclass
class IntegrityResult:
    hard: list[dict] = field(default_factory=list)
    soft: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard

    def issues(self) -> list[str]:
        return [f"{v['check']}: {v['detail']}" for v in self.hard + self.soft]


# --- helpers ---------------------------------------------------------------------------------------

def _strip_dates(text: str) -> str:
    return _DATE_RE.sub(" ", text)


def _numbers(text: str) -> list[tuple[float, float, str, str]]:
    """(value, precision unit, raw, the text right after it) for every number: 84,400 -> unit 100;
    1.1391 -> 0.0001; 84k -> 1000."""
    out = []
    clean = _strip_dates(text)
    for m in _NUM_RE.finditer(clean):
        raw = m.group(1)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if "." in raw:
            unit = 10 ** -len(raw.split(".")[1])
        else:
            digits = raw.replace(",", "")
            zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
            unit = 10 ** zeros
        if m.group(2):                                   # "84k" / "84.4k"
            value *= 1000.0
            unit *= 1000.0
        out.append((value, float(unit), m.group(0), clean[m.end():m.end() + 8]))
    return out


_UNIT_AFTER = re.compile(r"\s*(?:×|x\b|%|atr\b|bars?\b|pips?\b|r\b|sd\b|σ)", re.IGNORECASE)


def _sig_digits(raw: str) -> int:
    d = raw.replace(",", "").replace("$", "").lower().rstrip("k").replace(".", "").lstrip("0")
    return len(d.rstrip("0")) if "." not in raw else len(d)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _mentions(sentence: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}s?\b", sentence, re.IGNORECASE) is not None


def _generic(name: str) -> str:
    return name.split()[-1]


# --- the checks ------------------------------------------------------------------------------------------

def _invented_prices(text: str, facts: dict) -> list[dict]:
    last = float(facts["market"]["last_close"])
    lo, hi = last * 0.5, last * 1.5
    known = [n[0] for n in _numbers(facts_to_prompt(facts))]
    out, seen = [], set()
    for value, unit, raw, after in _numbers(text):
        if not (lo <= value <= hi) or raw in seen or _UNIT_AFTER.match(after) or _sig_digits(raw) < 3:
            continue            # ratios / ATR multiples / percentages, and 1–2 digit numbers, aren't price claims
        seen.add(raw)
        if not any(abs(k - value) <= unit + 1e-12 for k in known):
            out.append({"check": "invented_price", "detail": f"{raw} matches no number in the facts at that precision"})
    return out


def _absences(text: str, facts: dict) -> list[dict]:
    absent = " ".join(facts.get("absences") or []).lower()
    out = []
    for s in _sentences(text):
        if _NEGATION.search(s):
            continue
        if "no rsi divergence" in absent and re.search(r"\bdivergen", s, re.IGNORECASE):
            out.append({"check": "contradicts_absence", "detail": f"claims a divergence; the facts say none: “{s.strip()[:120]}”"})
        if "no confirmed chart pattern" in absent and _CONFIRMED_WORDS.search(s) and \
                any(_mentions(s, n) or _mentions(s, _generic(n)) for n in _PATTERN_NAMES) and not _CONDITIONAL.search(s):
            out.append({"check": "contradicts_absence", "detail": f"claims a confirmed pattern; the facts list none: “{s.strip()[:120]}”"})
        if "no failed chart pattern" in absent and re.search(r"\b(failed|failure)\b", s, re.IGNORECASE) and \
                any(_mentions(s, n) for n in _PATTERN_NAMES) and not _CONDITIONAL.search(s):
            out.append({"check": "contradicts_absence", "detail": f"claims a failed pattern; the facts list none: “{s.strip()[:120]}”"})
    return out


def _state_upgrades(text: str, facts: dict) -> list[dict]:
    pats = facts.get("chart_patterns") or []
    out = []
    for p in pats:
        if p.get("state") not in ("forming", "failed"):
            continue
        same_generic = [q for q in pats if _generic(q["type"]) == _generic(p["type"])]
        names = [p["type"]] + ([_generic(p["type"])] if len(same_generic) == 1 else [])
        for s in _sentences(text):
            if any(_mentions(s, n) for n in names) and _CONFIRMED_WORDS.search(s) \
                    and not _CONDITIONAL.search(s) and not _NEGATION.search(s):
                out.append({"check": "state_upgrade",
                            "detail": f"{p['type']} is {p['state']} in the facts but described as confirmed: “{s.strip()[:120]}”"})
    return out


def _direction(text: str, facts: dict) -> tuple[list[dict], list[dict]]:
    bias = facts["confluence"]["bias"]
    tier = (facts.get("situation") or {}).get("tier")
    hard, soft = [], []
    for s in _sentences(text):
        if _NEGATION.search(s):
            continue
        for rx, d in ((_UP_RE, "bullish"), (_DOWN_RE, "bearish")):
            m = rx.search(s)
            if not m:
                continue
            if bias in ("bullish", "bearish") and d != bias:
                hard.append({"check": "opposite_direction",
                             "detail": f"“{m.group(0)}” is {d} but the Layer-1 read is {bias}"})
            elif tier == "no_setup" or bias not in ("bullish", "bearish"):
                soft.append({"check": "directional_phrase",
                             "detail": f"“{m.group(0)}” although there is no directional read"})
    return hard, soft


def _soft_checks(text: str, facts: dict, style: str) -> list[dict]:
    out = []
    if facts.get("strongest_opposing_fact") and not re.search(r"^\s*\**opposing\**\s*:", text, re.IGNORECASE | re.M):
        out.append({"check": "missing_opposing", "detail": "no 'Opposing:' line although the facts supply one"})
    budget = (facts.get("situation") or {}).get("word_budget")
    if style == "brief" and budget:
        body = "\n".join(l for l in text.splitlines() if not re.match(r"^\s*\**opposing\**\s*:", l, re.IGNORECASE))
        words = len(re.findall(r"\b\w[\w'’-]*\b", body))
        if words > budget * BUDGET_MARGIN:
            out.append({"check": "over_budget", "detail": f"{words} words for a {budget}-word budget"})
    present = {p["type"] for p in facts.get("chart_patterns") or []}
    generics = {_generic(t) for t in present}
    for name in _PATTERN_NAMES:
        if name in present or name == "head and shoulders" and "inverse head and shoulders" in present:
            continue
        for s in _sentences(text):
            if _mentions(s, name) and not _NEGATION.search(s) and _generic(name) not in generics:
                out.append({"check": "unknown_pattern", "detail": f"mentions a {name}, which the facts don't list"})
                break
    for p in facts.get("chart_patterns") or []:
        if p.get("lifecycle") in ("completed", "expired"):
            for s in _sentences(text):
                if _mentions(s, p["type"]) and _HISTORY_AS_CURRENT.search(s) and not _PAST.search(s):
                    out.append({"check": "history_as_current",
                                "detail": f"{p['type']} is {p['lifecycle']} (history) but reads as current: “{s.strip()[:120]}”"})
                    break
    return out


def check_explanation(text: str, facts: dict, *, style: str = "brief") -> IntegrityResult:
    """All checks on one explanation. `style` = the explanation mode (brief / teaching)."""
    dir_hard, dir_soft = _direction(text, facts)
    hard = _invented_prices(text, facts) + _absences(text, facts) + _state_upgrades(text, facts) + dir_hard
    soft = dir_soft + _soft_checks(text, facts, style)
    return IntegrityResult(hard=hard, soft=soft)


# --- the deterministic fallback ---------------------------------------------------------------------------

_TIER_WORDS = {"no_setup": "No clear setup", "notable": "Notable", "confirmed": "Confirmed setup"}


def facts_only_summary(facts: dict) -> str:
    """What the app says when Claude's text fails the check twice: Layer 1 only, no prose judgement."""
    c = facts["confluence"]
    sit = facts.get("situation") or {}
    lines = []
    total = len(c.get("categories") or {})
    read = (f"{c['bias']} — {c['agreeing_categories']} of {total} categories agree"
            if c["bias"] in ("bullish", "bearish") else "no directional read")
    lines.append(f"{_TIER_WORDS.get(sit.get('tier'), sit.get('tier', ''))}: {read}.")
    rec = facts.get("verdict_record")
    if rec:
        from src.research.verdict_records import record_text
        lines.append(f"Record: {record_text(rec)}.")
    sr = facts.get("support_resistance") or {}
    for key, word in (("nearest_support", "Support"), ("nearest_resistance", "Resistance")):
        z = sr.get(key)
        if z:
            d = z.get("distance_atr")
            lines.append(f"{word}: {z['lower']:g}–{z['upper']:g}" + (f" ({d:+g} ATR)" if d is not None else "") + ".")
    opp = facts.get("strongest_opposing_fact")
    if opp:
        lines.append(f"Opposing: {opp['category']} votes {opp['direction']}.")
    from src.risk.caution import is_caution
    cautions = [x["label"].lower() for x in facts.get("caution") or [] if is_caution(x)]
    if cautions:
        lines.append("Caution: " + "; ".join(cautions) + ".")
    return "\n".join(lines)
