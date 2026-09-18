"""Guards the analyst-guide wiring: the guide IS the system prompt on every Claude call, it's a
cached prefix, and the two output modes set the right token budgets. This is the regression test
for the bug where the guide existed on disk but was never passed to the model."""

from __future__ import annotations

import pytest

from src.advisor import explain as ex
from src.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self):
        self.content = [_TextBlock("ok")]


class _Messages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.captured = kwargs
        return _Resp()


class _Client:
    def __init__(self):
        self.captured = None
        self.messages = _Messages(self)


def _with_mode(cfg, mode):
    return cfg.model_copy(update={"advisor": cfg.advisor.model_copy(update={"explanation_style": mode})})


def test_guide_is_loaded_nonempty():
    assert ex.ANALYST_GUIDE.strip() and "Word budgets" in ex.ANALYST_GUIDE


def test_explain_sends_guide_as_cached_system_prefix(cfg):
    client = _Client()
    ex.explain("FACTS", _with_mode(cfg, "brief"), client=client)
    system = client.captured["system"]
    assert system[0]["text"] == ex.ANALYST_GUIDE                 # the guide itself, verbatim
    assert system[0]["cache_control"] == {"type": "ephemeral"}   # cached prefix


@pytest.mark.parametrize("mode,expected_tokens", [("brief", 400), ("teaching", 2048)])
def test_mode_sets_token_budget(cfg, mode, expected_tokens):
    client = _Client()
    ex.explain("FACTS", _with_mode(cfg, mode), client=client)
    assert client.captured["max_tokens"] == expected_tokens
    # the mode note rides in the second (uncached) system block, after the guide
    assert mode.upper() in client.captured["system"][1]["text"].upper()


def test_default_mode_is_brief(cfg):
    assert cfg.advisor.explanation_style == "brief"


def test_synthesis_and_structured_also_use_the_guide(cfg):
    c1 = _Client()
    ex.synthesize([("1d", "FACTS", 1.4)], cfg, client=c1)
    assert c1.captured["system"][0]["text"] == ex.ANALYST_GUIDE
    assert "cross-timeframe" in c1.captured["system"][1]["text"].lower()
