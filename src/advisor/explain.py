"""Phase 7 — the reasoning layer: Claude turns Layer 1 facts into a plain-language lesson.

This is Layer 2, the *voice*. It receives the structured facts assembled by `facts.py` and
explains them in trading language that teaches as it describes. The single hard rule of the
project applies here: **Layer 1 facts are authoritative.** Claude explains them, connects
them, and teaches from them — it never overrides a computed number or flips a computed
label. If the explanation disagreed with the facts, that would be a bug in how facts are
fed, not a judgement call.

The model is config-driven (`cfg.advisor.model`) — the user chose it in `config.yaml`, so we
honour it rather than hardcoding one. A `cache_control` breakpoint sits on the (stable)
system prompt; on Sonnet-tier a short teaching prompt is below the cacheable minimum so it's
effectively a no-op today, but it's the right, forward-looking placement if this ever runs
in a loop. The call stays deliberately plain (no thinking parameter) so it works across
whatever model the config names — the reasoning is light narration over facts already
computed, not fresh analysis.
"""

from __future__ import annotations

from src.config import Config

# Stable across runs — keep it byte-identical so it's a clean cache prefix.
SYSTEM_PROMPT = """You are a trading educator explaining a chart analysis to a learner.

You are given a set of COMPUTED FACTS about a market: trend, momentum (RSI/MACD), \
support/resistance levels, Fibonacci retracements, candlestick patterns, named chart \
patterns, and a "confluence" verdict that tallies how many independent signals agree.

Named chart patterns (head & shoulders, double tops, triangles) are BEST-EFFORT geometry \
that over-calls by design — treat them as lower-confidence hints, calibrate your language \
accordingly, and lean on the confluence verdict and the harder facts (levels, trend, \
momentum) as your backbone.

Absolute rules:
- These computed facts are AUTHORITATIVE. Explain them; never contradict, override, or \
invent numbers or labels. If you're tempted to disagree with a fact, explain what it means \
instead.
- Some facts answer different questions and are complementary, not contradictory. For \
example, a "nearest resistance" level is ranked by distance, while the confluence \
support/resistance vote only fires when price is within a proximity threshold — so \
"resistance at X" and "price is not near a level" can both be true. Do not manufacture a \
contradiction between complementary facts.
- You do NOT place trades and you do NOT predict the future. Your value is clarity and \
education. No financial advice.

Structure your explanation as:
1. THE SETUP — what the chart is showing right now, in plain terms.
2. WHY — which signals agree or disagree, and what that confluence (or lack of it) means.
3. WHAT WOULD INVALIDATE IT — the specific, concrete conditions (a level breaking, a signal \
flipping) that would change the read.

Teach as you go: briefly define terms a learner might not know. Be concise and grounded — \
every claim should trace back to a provided fact."""

# Phase 23 — cross-timeframe synthesis. Reasons over the RAW per-timeframe facts (never a
# summary of separate write-ups — that loses precision and can't catch real conflicts).
SYNTHESIS_SYSTEM_PROMPT = """You are a trading educator giving ONE cross-timeframe read of a \
single market.

You are given the COMPUTED FACTS for the SAME market on several timeframes, each with an \
authority weight (higher timeframe = more weight). The disciplined way to read multiple \
timeframes:
- HIGHER timeframes set the DIRECTION / bias.
- LOWER timeframes are for TIMING and entry, and must never override a higher-timeframe read.

Your job:
1. State the higher-timeframe direction.
2. Say EXPLICITLY whether the timeframes ALIGN (all pointing the same way — a stronger read) \
or CONFLICT (e.g. daily up but 1h making lower highs — a mixed, lower-confidence picture).
3. If they align, where the lower timeframe suggests timing; if they conflict, say to wait / \
treat it as low-confidence.

Absolute rules: the computed facts are AUTHORITATIVE — never invent or contradict numbers. \
You do not predict the future and give no financial advice; this is clarity and education."""


_STYLE_NOTE = {
    "teaching": "Explain like a patient mentor teaching a beginner; define jargon in a few words as it comes up.",
    "concise": "Be brief and direct; assume the reader knows basic trading terms.",
}


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


def synthesize(per_tf: list[tuple[str, str, float]], cfg: Config, client=None, max_tokens: int = 1024) -> str:
    """One cross-timeframe read from the per-timeframe facts.

    `per_tf` is a list of `(timeframe, facts_text, weight)` — the RAW facts text per timeframe,
    not summaries. `client` is injectable for tests.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    system = [{"type": "text", "text": SYNTHESIS_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens,
        system=system,
        messages=build_synthesis_messages(per_tf),
    )
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


def explain_structured(facts_text: str, cfg: Config, client=None, max_tokens: int = 1024) -> dict:
    """Like `explain`, but returns `{setup, why, invalidation}` via a forced tool call.

    Same authoritative-facts rules as `explain` (the system prompt is shared). `client` is
    injectable for tests; extraction is defensive so a malformed response raises a clear error
    rather than a KeyError.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    style = _STYLE_NOTE.get(cfg.advisor.explanation_style, _STYLE_NOTE["teaching"])
    system = [
        {
            "type": "text",
            "text": f"{SYSTEM_PROMPT}\n\nStyle: {style}",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens,
        system=system,
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


def explain(facts_text: str, cfg: Config, client=None, max_tokens: int = 2048) -> str:
    """Send the facts to Claude and return the plain-language explanation.

    `client` is injectable for testing; in normal use it's created here from the API key.
    Requires `ANTHROPIC_API_KEY` (via `cfg.require_api_key()`) — this is the one place in
    the pipeline that needs it.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    style = _STYLE_NOTE.get(cfg.advisor.explanation_style, _STYLE_NOTE["teaching"])
    system = [
        {
            "type": "text",
            "text": f"{SYSTEM_PROMPT}\n\nStyle: {style}",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens,
        system=system,
        messages=build_messages(facts_text),
    )

    # Extract text blocks defensively — skip any thinking/tool blocks a model might emit.
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
