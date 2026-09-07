"""Phase 20 — structured explanation output (explain_structured) via a forced tool call."""

from __future__ import annotations

import pytest

from src.advisor.explain import explain_structured
from src.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class _ToolBlock:
    def __init__(self, name, input_):
        self.type = "tool_use"
        self.name = name
        self.input = input_


class _Resp:
    def __init__(self, content):
        self.content = content


class _Messages:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.captured = kwargs
        return _Resp([_ToolBlock("emit_analysis", {"setup": "S", "why": "W", "invalidation": "I"})])


class _ToolClient:
    def __init__(self):
        self.captured = None
        self.messages = _Messages(self)


def test_returns_structured_fields(cfg):
    out = explain_structured("FACTS HERE", cfg, client=_ToolClient())
    assert out == {"setup": "S", "why": "W", "invalidation": "I"}


def test_forces_the_tool_and_uses_config_model(cfg):
    client = _ToolClient()
    explain_structured("FACTS HERE", cfg, client=client)
    assert client.captured["tool_choice"] == {"type": "tool", "name": "emit_analysis"}
    assert client.captured["model"] == cfg.advisor.model
    assert client.captured["tools"][0]["name"] == "emit_analysis"


def test_missing_field_raises_clearly(cfg):
    class _BadMessages(_Messages):
        def create(self, **kwargs):
            return _Resp([_ToolBlock("emit_analysis", {"setup": "only setup"})])

    client = _ToolClient()
    client.messages = _BadMessages(client)
    with pytest.raises(RuntimeError, match="missing fields"):
        explain_structured("FACTS", cfg, client=client)
