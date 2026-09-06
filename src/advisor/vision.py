"""Phase 10 (OPTIONAL) — explain an uploaded chart *screenshot* with Claude's vision.

This is a deliberately SECONDARY path. The whole project's premise is that computed numbers
beat pixels: the data pipeline (Phases 1–9) measures exact prices, levels, and slopes, while
a screenshot can only be eyeballed. So this module exists for the case where all you have is
an image — and its system prompt tells the model exactly that: read what's visible, be
explicit about what can't be measured from pixels, and defer to computed data when precision
matters.

Same conventions as the text explainer (`explain.py`): config-driven model, injectable client
for testing, defensive text-block extraction. The one new piece is packing the image as a
base64 content block with the right media type.
"""

from __future__ import annotations

import base64
from pathlib import Path

from src.config import Config

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_DEFAULT_QUESTION = (
    "Explain what this chart appears to show and what a learner should notice."
)

VISION_SYSTEM_PROMPT = """You are a trading educator looking at a SCREENSHOT of a price chart.

Important limitation: a screenshot is a worse data source than the underlying numbers. You \
cannot measure exact prices, levels, or slopes from pixels, and axis labels may be small or \
cropped. So describe what you can genuinely see — the overall trend shape, notable candles \
or ranges, apparent support/resistance zones, and any chart patterns — and be explicit about \
what is uncertain or unreadable. Never invent precise numbers you can't actually read.

If exact figures matter, say that the data-driven analysis (which measures real prices) is \
the authoritative source and this image read is a secondary, approximate view.

Teach as you go: define terms a learner might not know. Structure your answer as:
1. WHAT THE CHART SHOWS — the big picture in plain terms.
2. NOTABLE FEATURES — specific things worth a learner's attention, with your confidence.
3. CAVEATS — what you can't reliably tell from an image alone.

You do not place trades and you do not predict the future. No financial advice."""


def _media_type(path: Path) -> str:
    try:
        return _MEDIA_TYPES[path.suffix.lower()]
    except KeyError:
        raise ValueError(
            f"Unsupported image type '{path.suffix}'. Supported: {', '.join(sorted(_MEDIA_TYPES))}"
        )


def build_image_messages(image_bytes: bytes, media_type: str, question: str) -> list[dict]:
    """The user turn: the image as a base64 block, then the question. Separated for testing."""
    data = base64.standard_b64encode(image_bytes).decode("utf-8")
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                },
                {"type": "text", "text": question},
            ],
        }
    ]


def explain_chart_image(
    image_path: str | Path,
    cfg: Config,
    client=None,
    question: str | None = None,
    max_tokens: int = 2048,
) -> str:
    """Send a chart screenshot to Claude's vision and return a plain-language explanation.

    `client` is injectable for testing; in normal use it's built from the API key. Requires
    `ANTHROPIC_API_KEY` (via `cfg.require_api_key()`).
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No such image: {path}")
    media_type = _media_type(path)  # validate before spending an API call
    image_bytes = path.read_bytes()

    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.require_api_key())

    system = [{"type": "text", "text": VISION_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    response = client.messages.create(
        model=cfg.advisor.model,
        max_tokens=max_tokens,
        system=system,
        messages=build_image_messages(image_bytes, media_type, question or _DEFAULT_QUESTION),
    )
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
