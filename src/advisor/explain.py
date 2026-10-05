"""Phase 7 — the reasoning layer: Claude turns Layer 1 facts into a plain-language read.

This is Layer 2, the *voice*. It receives the structured facts assembled by `facts.py` and
explains them. The single hard rule of the project applies: **Layer 1 facts are authoritative** —
Claude explains and connects them, never overrides a number or flips a label.

ONE SOURCE OF TRUTH for behaviour: the analyst guide in `analyst-guide-system-prompt.md` (loaded
at import; a missing file is a hard, loud failure). It is the system prompt for EVERY Claude call
here — `explain`, `synthesize`, and `explain_structured` — so the three can't drift. The
structured/synthesis calls append a short task-specific note AFTER the guide, but the guide's
rules bind all of them.

Two output modes (config `advisor.explanation_style`, default `brief`):
  - brief    — obey the guide's §8 word budgets; `max_tokens` ~400 so the limit is STRUCTURAL,
               not merely requested.
  - teaching — a fuller educational breakdown, EXEMPT from §8's word budgets only; every other
               rule still binds; `max_tokens` 2048.

The guide is byte-identical on every call and sits behind a `cache_control` breakpoint, so it is
a real prompt-cache prefix (it's well above the cache minimum). The model stays config-driven
(`cfg.advisor.model`) and the call stays plain (no thinking parameter) for model-agnosticism.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config import Config
from src.signals.situation import MTF_SYNTHESIS, TEMPLATE, WORD_BUDGET

# The analyst guide IS the system prompt. Load it once, at import, and fail loudly if it's gone —
# a silent fallback to some other prompt is exactly the drift this wiring exists to prevent.
_GUIDE_PATH = Path(__file__).with_name("analyst-guide-system-prompt.md")
try:
    ANALYST_GUIDE = _GUIDE_PATH.read_text(encoding="utf-8")
except OSError as exc:  # missing / unreadable
    raise RuntimeError(
        f"Analyst guide system prompt not found at {_GUIDE_PATH} — Layer 2 cannot run without it."
    ) from exc


# Output modes. `note` is appended AFTER the guide (small, uncached); `max_tokens` makes the brief
# ceiling structural, not merely requested.
_MODES = {
    "brief": {
        "max_tokens": 400,
        "note": (
            "OUTPUT MODE: BRIEF. Section 8's word budgets are HARD CEILINGS — obey them "
            "(no clear setup 30, mildly notable 70, confirmed setup 130, multi-timeframe 150). "
            "Follow §8's format exactly: no headings, no preamble, name only the 2–3 facts that "
            "carry the read. If it will not fit the budget, say the read is unclear instead."
        ),
    },
    "teaching": {
        "max_tokens": 2048,
        "note": (
            "OUTPUT MODE: TEACHING. You are EXEMPT from Section 8's WORD BUDGETS ONLY — give a "
            "fuller educational breakdown and define terms as you go. EVERY OTHER RULE in the "
            "guide still binds without exception: facts are authoritative, invent no numbers or "
            "labels, force no signal where none exists, make no prediction, give no financial "
            "advice."
        ),
    },
}
DEFAULT_MODE = "brief"


def _mode(cfg: Config) -> dict:
    return _MODES.get(cfg.advisor.explanation_style, _MODES[DEFAULT_MODE])


# Room for the uncounted "Opposing:" line (guide §8) on top of the tier's word budget.
_OPPOSING_LINE_TOKENS = 60


def _tokens_for(words: int) -> int:
    """A max_tokens ceiling that fits `words` of prose with a little room (~1.3 tokens/word),
    so the brief budget is STRUCTURAL: the model can't write a longer answer than its tier."""
    return words * 3 + 60


def _tier_mode(cfg: Config, situation: dict | None) -> dict:
    """ROADMAP A3: when Layer 1 supplied a situation tier, the mode note names THAT tier, its
    template and budget (no menu of tiers to pick from), and brief mode's `max_tokens` comes from
    the tier. Teaching keeps the tier and template and lifts only the word cap."""
    base = _mode(cfg)
    if not situation:
        return base
    tier, words, fmt = situation["tier"], situation["word_budget"], situation["template"]
    fixed = (f"SITUATION TIER: {tier} — decided by Layer 1. Use it; never choose or change it, "
             f"and never write as though the chart were a higher tier. Format: {fmt}")
    if base is _MODES["teaching"]:
        return {"max_tokens": base["max_tokens"],
                "note": (f"{fixed}\n\n{base['note']} The tier, its format and the 'Opposing:' line "
                         "still apply — teaching lifts only the word cap.")}
    return {
        "max_tokens": _tokens_for(words) + _OPPOSING_LINE_TOKENS,
        "note": (f"{fixed}\n\nOUTPUT MODE: BRIEF. HARD CEILING: {words} words (the final "
                 "'Opposing:' line, when a strongest opposing fact is supplied, is extra and does "
                 "not count). No headings, no preamble; name only the 2–3 facts that carry the "
                 "read. If it will not fit, say the read is unclear instead."),
    }


def _system(mode: dict, task_note: str = "") -> list[dict]:
    """System prompt: the guide as a CACHED prefix (identical every call), then the small
    task/mode note as a separate, uncached block so it never invalidates the guide cache."""
    tail = f"{task_note}\n\n{mode['note']}" if task_note else mode["note"]
    return [
        {"type": "text", "text": ANALYST_GUIDE, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": tail},
    ]


def build_messages(facts_text: str) -> list[dict]:
    """The user turn: just the facts. Kept separate for testability."""
    return [{"role": "user", "content": f"Here are the computed facts:\n\n{facts_text}"}]


# Phase 20 — structured output. A forced tool call makes the model return the three fields as
# data (usable by the dashboard/alerts, and it feeds the Phase-24 API directly) instead of a
# prose blob. Tool use is broadly supported, so this stays model-agnostic like explain().
ANALYSIS_TOOL = {
    "name": "emit_analysis",
    "description": "Return the chart analysis as three structured fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "setup": {"type": "string", "description": "What the chart is showing right now, in plain terms."},
            "why": {"type": "string", "description": "Which signals agree or disagree and what that confluence means."},
            "invalidation": {"type": "string", "description": "Specific, concrete conditions that would change the read."},
        },
        "required": ["setup", "why", "invalidation"],
    },
}

_STRUCTURED_FIELDS = ("setup", "why", "invalidation")

_STRUCTURED_NOTE = (
    "TASK: return the analysis via the emit_analysis tool as three fields — `setup` (the read), "
    "`why`, and `invalidation` — instead of prose. Each field obeys the guide's rules and, in "
    "brief mode, its §8 word budgets."
)

_SYNTHESIS_NOTE = (
    "TASK: give ONE cross-timeframe read of the SAME market from the per-timeframe facts below "
    "(each labeled with an authority weight). Reason over the RAW facts, not summaries. Higher "
    "timeframes set DIRECTION/bias; lower timeframes are for TIMING only and never override them. "
    "State the higher-timeframe direction, say EXPLICITLY whether the timeframes ALIGN or CONFLICT, "
    "and give the timing if they align or 'wait / low-confidence' if they conflict. This is the "
    "multi-timeframe case in §8."
)


def build_synthesis_messages(per_tf: list[tuple[str, str, float]]) -> list[dict]:
    """The user turn: each timeframe's raw facts text, labeled with its authority weight."""
    blocks = [
        f"=== TIMEFRAME {tf} (authority weight {weight}) ===\n{text}"
        for tf, text, weight in per_tf
    ]
    return [{
        "role": "user",
        "content": "Computed facts for the same market on several timeframes:\n\n" + "\n\n".join(blocks),
    }]


def synthesize(per_tf: list[tuple[str, str, float]], cfg: Config, client=None, max_tokens: int | None = None) -> str:
    """One cross-timeframe read from the per-timeframe facts.

    `per_tf` is a list of `(timeframe, facts_text, weight)` — the RAW facts text per timeframe,
    not summaries. `client` is injectable for tests. Uses the shared analyst guide + a synthesis
    note; `max_tokens` defaults to the current mode's budget.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    # The synthesis is always the mtf_synthesis tier — set explicitly, never escalated from a
    # per-timeframe tier.
    mode = _tier_mode(cfg, {"tier": MTF_SYNTHESIS, "word_budget": WORD_BUDGET[MTF_SYNTHESIS],
                            "template": TEMPLATE[MTF_SYNTHESIS]})
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens or mode["max_tokens"],
        system=_system(mode, _SYNTHESIS_NOTE),
        messages=build_synthesis_messages(per_tf),
    )
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


def explain_structured(facts_text: str, cfg: Config, client=None, max_tokens: int | None = None,
                       situation: dict | None = None) -> dict:
    """Like `explain`, but returns `{setup, why, invalidation}` via a forced tool call.

    Same authoritative-facts guide and output mode as `explain`. `client` is injectable for tests;
    extraction is defensive so a malformed response raises a clear error rather than a KeyError.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    mode = _tier_mode(cfg, situation)
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens or mode["max_tokens"],
        system=_system(mode, _STRUCTURED_NOTE),
        messages=build_messages(facts_text),
        tools=[ANALYSIS_TOOL],
        tool_choice={"type": "tool", "name": "emit_analysis"},
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_analysis":
            data = dict(block.input)
            missing = [f for f in _STRUCTURED_FIELDS if f not in data]
            if missing:
                raise RuntimeError(f"structured analysis is missing fields: {missing}")
            return {f: data[f] for f in _STRUCTURED_FIELDS}
    raise RuntimeError("model did not return an emit_analysis tool call")


def explain(facts_text: str, cfg: Config, client=None, max_tokens: int | None = None,
            situation: dict | None = None) -> str:
    """Send the facts to Claude and return the plain-language explanation.

    `client` is injectable for testing; in normal use it's created here from the API key.
    Requires `ANTHROPIC_API_KEY` (via `cfg.require_api_key()`). The system prompt is the shared
    analyst guide; `max_tokens` defaults to the current mode's budget (brief ~400, teaching 2048).
    `situation` (facts["situation"], ROADMAP A3) fixes the tier: its template goes in the note and,
    in brief mode, its word budget sets `max_tokens`.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    mode = _tier_mode(cfg, situation)
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens or mode["max_tokens"],
        system=_system(mode),
        messages=build_messages(facts_text),
    )

    # Extract text blocks defensively — skip any thinking/tool blocks a model might emit.
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


def revise(facts_text: str, draft: str, violations: list[str], cfg: Config, client=None,
           situation: dict | None = None) -> str:
    """ROADMAP C1: ONE rewrite of an explanation that failed the integrity check. The model sees the
    same facts, its own draft, and the exact violations; nothing else changes (same guide, tier and
    budget)."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())
    mode = _tier_mode(cfg, situation)
    fix = ("Your explanation failed the app's integrity check against the computed facts:\n"
           + "\n".join(f"- {v}" for v in violations)
           + "\n\nRewrite the whole explanation, fixing exactly these problems. Use only numbers, patterns "
             "and states that appear in the facts; keep the same tier, format and rules.")
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=mode["max_tokens"],
        system=_system(mode),
        messages=build_messages(facts_text) + [{"role": "assistant", "content": draft},
                                               {"role": "user", "content": fix}],
    )
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


# --- Simplification pass 2: reads with memory ---------------------------------------------------------
# One forced tool call per read returns the prose AND the four-field thesis the next read continues
# from. A first read is the full teaching read; a continuation gets its earlier thesis + the app's
# computed comparison (MEMORY block, src/advisor/memory.py) before the current facts.

READ_TOOL = {
    "name": "emit_read",
    "description": "Return the explanation shown to the user and the thesis the next read will continue from.",
    "input_schema": {
        "type": "object",
        "properties": {
            "explanation": {"type": "string", "description": "The full plain-text write-up shown to the user (follows the guide)."},
            "read": {"type": "string", "description": "One sentence: what the chart shows now."},
            "why": {"type": "string", "description": "The 2–3 facts that carry the read, with their numbers."},
            "invalidation": {"type": "string", "description": "The concrete price or condition, from the facts, that would prove the read wrong."},
            "watch": {"type": "string", "description": "What to watch next: levels, pattern states or events from the facts."},
        },
        "required": ["explanation", "read", "why", "invalidation", "watch"],
    },
}
READ_FIELDS = ("explanation", "read", "why", "invalidation", "watch")

_FIRST_NOTE = ("TASK: the FIRST full read of this market and timeframe — later reads continue from it, so make it "
               "complete: teach what each fact means. Return it via the emit_read tool: `explanation` is the write-up "
               "shown to the user; `read`, `why`, `invalidation` and `watch` are the short thesis the next read will be "
               "compared against (use the facts' own numbers).")
_CONTINUATION_NOTE = ("TASK: a CONTINUATION. The MEMORY block holds your earlier read(s) of this market and what the "
                      "app computed has happened since. Do not repeat the teaching. In `explanation` (about 120–200 "
                      "words): what changed since your previous read, using the computed status and changes as given "
                      "(never re-judge them); whether your previous thesis holds, has weakened or is broken, and why; "
                      "and what to watch now. Refer to the earlier read in the past tense with plain labels (\"the "
                      "previous read was bullish\"). `read`, `why`, `invalidation` and `watch` describe the read NOW. "
                      "Return it via the emit_read tool.")
_FIRST_MAX_TOKENS, _CONTINUATION_MAX_TOKENS = 4000, 1600


def _read_mode(cfg: Config, situation: dict | None, continuation: bool) -> dict:
    teaching = cfg.model_copy(update={"advisor": cfg.advisor.model_copy(update={"explanation_style": "teaching"})})
    mode = _tier_mode(teaching, situation)
    if continuation:
        return {"max_tokens": _CONTINUATION_MAX_TOKENS,
                "note": mode["note"].split("\n\nOUTPUT MODE")[0] + "\n\n" + _CONTINUATION_NOTE}
    return {"max_tokens": _FIRST_MAX_TOKENS, "note": mode["note"] + "\n\n" + _FIRST_NOTE}


def read_messages(facts_text: str, memory: str | None = None) -> list[dict]:
    if not memory:
        return build_messages(facts_text)
    return [{"role": "user", "content": f"{memory}\n\nTHE COMPUTED FACTS NOW:\n\n{facts_text}"}]


def _usage(response) -> dict:
    u = getattr(response, "usage", None)
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: int(getattr(u, k, 0) or 0) for k in keys} if u is not None else {}


def _emit(response) -> dict:
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise RuntimeError("the answer was cut off (too long)")
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_read":
            data = dict(block.input)
            missing = [f for f in READ_FIELDS if not isinstance(data.get(f), str) or not data[f].strip()]
            if missing:
                raise RuntimeError(f"the read is missing fields: {missing}")
            return {f: data[f].strip() for f in READ_FIELDS}
    raise RuntimeError("model did not return an emit_read tool call")


def explain_read(facts_text: str, cfg: Config, client=None, *, situation: dict | None = None,
                 memory: str | None = None, revise: tuple[dict, list[str]] | None = None) -> dict:
    """A first read (memory None) or a continuation (memory = the MEMORY block). `revise=(draft, violations)`
    asks for ONE rewrite of a draft that failed the integrity check. Returns the five fields + `usage`.
    Raises RuntimeError without a key, on a cut-off answer, or on a malformed one."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())
    mode = _read_mode(cfg, situation, continuation=bool(memory))
    messages = read_messages(facts_text, memory)
    if revise:
        draft, violations = revise
        messages = messages + [
            {"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)},
            {"role": "user", "content": "Your read failed the app's integrity check against the computed facts:\n"
             + "\n".join(f"- {v}" for v in violations)
             + "\n\nReturn the whole read again via emit_read, fixing exactly these problems. Use only numbers, "
               "patterns and states that appear in the facts or the memory; keep the same tier, format and rules."}]
    response = client.messages.create(
        model=cfg.advisor.model, max_tokens=mode["max_tokens"], system=_system(mode), messages=messages,
        tools=[READ_TOOL], tool_choice={"type": "tool", "name": "emit_read"},
    )
    return {**_emit(response), "usage": _usage(response)}
