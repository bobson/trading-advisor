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

_STYLE_NOTE = {
    "teaching": "Explain like a patient mentor teaching a beginner; define jargon in a few words as it comes up.",
    "concise": "Be brief and direct; assume the reader knows basic trading terms.",
}


def build_messages(facts_text: str) -> list[dict]:
    """The user turn: just the facts. Kept separate for testability."""
    return [{"role": "user", "content": f"Here are the computed facts:\n\n{facts_text}"}]


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
