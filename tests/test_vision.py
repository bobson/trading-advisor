"""Tests for Phase 10 — chart-image (vision) explanation.

Offline coverage of the plumbing: media-type detection, base64 image packing, config-driven
model, text-block extraction. The live "done when" (a real vision explanation of a chart)
needs ANTHROPIC_API_KEY and a human to eyeball one run, same as Phase 7.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.advisor.vision import _media_type, explain_chart_image
from src.config import load_config

# A minimal valid 1x1 PNG.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "chart.png"
    p.write_bytes(_PNG_1x1)
    return p


class _Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.captured = kwargs
        return _Resp([
            _Block("thinking", "skip me"),
            _Block("text", "This chart shows an uptrend. "),
            _Block("text", "Note the caveats."),
        ])


class _FakeClient:
    def __init__(self):
        self.captured = None
        self.messages = _FakeMessages(self)


# --- media type ----------------------------------------------------------------

def test_media_type_mapping():
    assert _media_type(Path("a.png")) == "image/png"
    assert _media_type(Path("a.JPG")) == "image/jpeg"
    assert _media_type(Path("a.jpeg")) == "image/jpeg"
    with pytest.raises(ValueError):
        _media_type(Path("a.bmp"))


# --- explain_chart_image plumbing ---------------------------------------------

def test_extracts_only_text_blocks(cfg, png):
    client = _FakeClient()
    out = explain_chart_image(png, cfg, client=client)
    assert out == "This chart shows an uptrend. Note the caveats."  # thinking skipped, stripped


def test_packs_image_and_uses_config_model(cfg, png):
    client = _FakeClient()
    explain_chart_image(png, cfg, client=client, question="What trend is this?")
    cap = client.captured
    assert cap["model"] == cfg.advisor.model
    assert cap["system"][0]["cache_control"] == {"type": "ephemeral"}

    content = cap["messages"][0]["content"]
    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"]["media_type"] == "image/png"
    # the base64 payload round-trips back to the original PNG bytes
    assert base64.b64decode(image_block["source"]["data"]) == _PNG_1x1
    text_block = next(b for b in content if b["type"] == "text")
    assert text_block["text"] == "What trend is this?"


def test_missing_file_raises(cfg, tmp_path):
    with pytest.raises(FileNotFoundError):
        explain_chart_image(tmp_path / "nope.png", cfg, client=_FakeClient())


def test_unsupported_type_raises(cfg, tmp_path):
    bad = tmp_path / "chart.bmp"
    bad.write_bytes(_PNG_1x1)
    with pytest.raises(ValueError):
        explain_chart_image(bad, cfg, client=_FakeClient())
