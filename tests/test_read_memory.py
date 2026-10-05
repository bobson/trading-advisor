"""Simplification pass 2 — read memory: stored reads, continuations, the computed comparison, the spend
guards, and the integrity check on continuation text. All offline (fake Claude client)."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.advisor import memory as M
from src.advisor.integrity import check_explanation
from src.config import load_config
from src.service.analyze import advise
from src.service.read_memory import explained_read

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cfg():
    return load_config().model_copy(update={"anthropic_api_key": None})


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIX / "btc_1h_sample.csv", index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


_FIELDS = {"explanation": "The read is explained here, with what each fact means.",
           "read": "A read of the chart now.", "why": "Two facts carry it.",
           "invalidation": "A close beyond the nearest zone.", "watch": "The nearest zones."}


class Fake:
    """A Claude client that returns an emit_read tool call (or what `reply` says)."""
    def __init__(self, reply=None, stop_reason="tool_use"):
        self.calls, self.reply, self.stop_reason = [], reply or [dict(_FIELDS)], stop_reason
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        data = self.reply[min(len(self.calls) - 1, len(self.reply) - 1)]
        block = SimpleNamespace(type="tool_use", name="emit_read", input=data)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=300, cache_read_input_tokens=5000,
                                cache_creation_input_tokens=0)
        return SimpleNamespace(content=[block], stop_reason=self.stop_reason, usage=usage)


def _result(cfg, candles, n):
    return advise("BTC/USDT", "1h", cfg, df=candles.iloc[:n], explain_enabled=False)


def _read(cfg, candles, n, conn, client, **kw):
    return explained_read(_result(cfg, candles, n), conn, cfg, spend=kw.pop("spend", True), client=client, **kw)


def _rows(conn):
    return conn.execute("SELECT COUNT(*) FROM analysis_reads").fetchone()[0]


# --- the flow ---------------------------------------------------------------------------------------------

def test_first_read_is_a_full_teaching_read_and_anchors_its_chain(cfg, candles):
    conn, client = M.connect(":memory:"), Fake()
    out = _read(cfg, candles, 300, conn, client)
    assert out["memory"]["kind"] == "first" and out["memory"]["reason"] == "none_before"
    assert out["explanation"] == _FIELDS["explanation"] and len(client.calls) == 1
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "emit_read"} and call["max_tokens"] >= 3000
    assert "FIRST full read" in call["system"][1]["text"]
    row = M.latest(conn, "BTC/USDT", "1h")
    assert row["anchor_id"] == row["id"] and row["thesis"]["watch"] == _FIELDS["watch"]
    assert row["bar_time"] == int(candles.index[299].timestamp()) and row["usage"]["output_tokens"] == 300


def test_the_same_candle_comes_back_from_memory_with_no_call(cfg, candles):
    conn, client = M.connect(":memory:"), Fake()
    _read(cfg, candles, 300, conn, client)
    again = _read(cfg, candles, 300, conn, client)
    free = _read(cfg, candles, 300, conn, client, spend=False)          # even with explain off
    assert len(client.calls) == 1 and _rows(conn) == 1
    for out in (again, free):
        assert out["memory"]["kind"] == "stored" and out["explanation"] == _FIELDS["explanation"]
        assert out["memory"]["usage"] is None


def test_new_candles_get_a_continuation_fed_the_thesis_and_the_computed_comparison(cfg, candles):
    conn, client = M.connect(":memory:"), Fake()
    _read(cfg, candles, 300, conn, client)
    first = M.latest(conn, "BTC/USDT", "1h")
    out = _read(cfg, candles, 303, conn, client)
    assert out["memory"]["kind"] == "continuation" and out["memory"]["candles_since"] == 3
    prompt = client.calls[1]["messages"][0]["content"]
    assert "MEMORY" in prompt and "WHAT HAPPENED SINCE THE PREVIOUS READ (3 closed candles" in prompt
    assert _FIELDS["watch"] in prompt and "THE COMPUTED FACTS NOW" in prompt
    assert "CONTINUATION" in client.calls[1]["system"][1]["text"] and client.calls[1]["max_tokens"] < 3000
    row = M.latest(conn, "BTC/USDT", "1h")
    assert row["parent_id"] == first["id"] and row["anchor_id"] == first["id"]
    assert row["comparison"]["status"] in ("followed_through", "invalidated", "both_touched", "open", "unscorable",
                                           "stayed_inside", "left_above", "left_below", "left_both_ways")
    _read(cfg, candles, 305, conn, client)                              # a second continuation keeps the anchor
    third = M.latest(conn, "BTC/USDT", "1h")
    assert third["anchor_id"] == first["id"] and "First full read" in client.calls[2]["messages"][0]["content"]


def test_a_first_read_older_than_the_gap_limit_is_no_longer_sent(cfg, candles):
    conn, client = M.connect(":memory:"), Fake()
    gap = M.gap_limit(cfg, "1h")
    _read(cfg, candles, 300, conn, client)
    _read(cfg, candles, 300 + gap - 2, conn, client)                    # continuation 1 (anchor = first read)
    _read(cfg, candles, 300 + gap + 2, conn, client)                    # first read now > gap candles old
    assert "First full read" not in client.calls[2]["messages"][0]["content"]
    last = M.latest(conn, "BTC/USDT", "1h")
    assert last["kind"] == "continuation" and last["anchor_id"] == last["parent_id"]


def test_explain_off_on_a_new_candle_spends_nothing_and_says_what_a_click_would_do(cfg, candles):
    conn, client = M.connect(":memory:"), Fake()
    _read(cfg, candles, 300, conn, client)
    out = _read(cfg, candles, 302, conn, client, spend=False)
    assert out["explanation"] is None and out["memory"] == {"kind": "none", "next": "continuation", "reason": None,
                                                             "candles_since": 2}
    assert len(client.calls) == 1 and _rows(conn) == 1


def test_no_key_spends_and_stores_nothing(cfg, candles):
    conn = M.connect(":memory:")
    out = explained_read(_result(cfg, candles, 300), conn, cfg, spend=True)        # no client, no key
    assert out["explanation"] is None and out["memory"]["next"] == "first" and _rows(conn) == 0


@pytest.mark.parametrize("case", ["fresh", "engine_changed", "gap"])
def test_a_fresh_full_read_on_start_fresh_engine_change_or_a_long_gap(cfg, candles, monkeypatch, case):
    conn, client = M.connect(":memory:"), Fake()
    _read(cfg, candles, 300, conn, client)
    n, kw = 302, {}
    if case == "fresh":
        n, kw = 300, {"fresh": True}                                     # even on the same candle
    elif case == "engine_changed":
        monkeypatch.setattr(M, "fingerprint", lambda c: "another-engine")
    else:
        n = 300 + M.gap_limit(cfg, "1h") + 1
    out = _read(cfg, candles, n, conn, client, **kw)
    assert out["memory"]["kind"] == "first" and out["memory"]["reason"] == case and len(client.calls) == 2


def test_a_cut_off_answer_shows_the_facts_and_the_next_candle_starts_fresh(cfg, candles):
    conn = M.connect(":memory:")
    out = _read(cfg, candles, 300, conn, Fake(stop_reason="max_tokens"))
    assert out["verification"]["fallback"] and "cut off" in out["verification"]["notice"]
    assert M.latest(conn, "BTC/USDT", "1h")["thesis"] is None
    nxt = _read(cfg, candles, 301, conn, Fake())
    assert nxt["memory"]["kind"] == "first" and nxt["memory"]["reason"] == "no_thesis"


def test_an_api_error_stores_nothing(cfg, candles):
    class Boom(Fake):
        def _create(self, **kw):
            raise ConnectionError("network down")
    conn = M.connect(":memory:")
    out = _read(cfg, candles, 300, conn, Boom())
    assert out["explanation"] is None and "network down" in out["memory"]["error"] and _rows(conn) == 0


def test_a_continuation_that_fails_the_check_is_rewritten_once(cfg, candles):
    conn = M.connect(":memory:")
    _read(cfg, candles, 300, conn, Fake())
    bad = {**_FIELDS, "explanation": f"Resistance now sits at {candles['close'].iloc[301] * 1.07:,.2f}."}
    client = Fake(reply=[bad, dict(_FIELDS)])
    out = _read(cfg, candles, 302, conn, client)
    assert len(client.calls) == 2 and out["verification"]["retried"] and not out["verification"]["fallback"]
    assert "integrity check" in client.calls[1]["messages"][-1]["content"]


# --- the comparison (Layer 1, computed) ---------------------------------------------------------------------

def _prev(kind="directional", direction="bullish"):
    return {"time": "t0", "price": 100.0, "atr": 2.0, "read_kind": kind, "direction": direction, "next_level": 110.0,
            "invalidation": 95.0, "range_low": 95.0, "range_high": 110.0, "bias": "bullish", "tier": "notable",
            "patterns": {"double top": "forming"}, "cautions": ["stop_in_noise"], "support": {"lower": 94, "upper": 95},
            "resistance": {"lower": 110, "upper": 111}, "rsi_zone": "neutral", "macd_state": "bullish"}


def _bars(*hl):
    return pd.DataFrame({"high": [h for h, _ in hl], "low": [lo for _, lo in hl]})


@pytest.mark.parametrize("bars,status", [
    (_bars((105, 99), (111, 104)), "followed_through"),
    (_bars((104, 96), (101, 94)), "invalidated"),
    (_bars((112, 94),), "both_touched"),
    (_bars((104, 97), (106, 99)), "open"),
])
def test_directional_status_is_first_touch(bars, status):
    now = {**_prev(), "time": "t1", "price": 104.0}
    assert M.compare(_prev(), now, bars)["status"] == status


@pytest.mark.parametrize("bars,status", [
    (_bars((109, 96),), "stayed_inside"), (_bars((112, 96),), "left_above"),
    (_bars((109, 93),), "left_below"), (_bars((112, 93),), "left_both_ways"),
])
def test_range_status(bars, status):
    prev = _prev("range", None)
    assert M.compare(prev, {**prev, "time": "t1"}, bars)["status"] == status


def test_the_comparison_names_every_change_and_the_memory_text_carries_it():
    prev = _prev()
    now = {**prev, "time": "t1", "price": 104.0, "bias": "bearish", "tier": "no_setup", "rsi_zone": "overbought",
           "patterns": {"double top": "confirmed", "bull flag": "forming"}, "cautions": ["no_room"],
           "support": {"lower": 98, "upper": 99}}
    cmp = M.compare(prev, now, _bars((105, 99), (106, 100)))
    assert cmp["changes"]["bias"] == ["bullish", "bearish"] and cmp["move_atr"] == 2.0
    assert cmp["patterns"]["changed"] == {"double top": ["forming", "confirmed"]}
    assert cmp["patterns"]["new"] == {"bull flag": "forming"}
    assert cmp["cautions_on"] == ["no_room"] and cmp["cautions_off"] == ["stop_in_noise"]
    row = {"id": 1, "thesis_l1": {**prev, "tier": "notable", "caution_labels": {}}, "thesis": dict(_FIELDS)}
    text = M.memory_text(row, row, cmp)
    for s in ("Status: price touched neither 110.00 (next level) nor 95 (invalidation)", "Bias: bullish → bearish",
              "Pattern double top: forming → confirmed", "New pattern: bull flag", "Nearest support zone: 94–95 → 98–99"):
        assert s in text, s


# --- the integrity check on continuations ------------------------------------------------------------------

@pytest.fixture(scope="module")
def facts(cfg, candles):
    return advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False).facts


def test_prices_from_the_memory_are_known_and_honest_past_references_pass(facts):
    f = copy.deepcopy(facts)
    f["confluence"] = {**f["confluence"], "bias": "bearish"}
    f["situation"] = {**f["situation"], "tier": "notable"}
    old = round(facts["market"]["last_close"] * 1.07, 2)
    memory = f"Previous read — invalidation {old:,.2f}."
    text = f"The previous read said the path of least resistance is up, with its invalidation at {old:,.2f}."
    hard = [v["check"] for v in check_explanation(text, f, style="teaching", known_text=memory, continuation=True).hard]
    assert hard == []
    # without the memory the old price is unknown, and the earlier-read sentence is judged as current
    hard = [v["check"] for v in check_explanation(text, f, style="teaching").hard]
    assert set(hard) == {"invented_price", "opposite_direction"}
    # a real claim about NOW is still caught in a continuation
    now = [v["check"] for v in check_explanation("Momentum favours the bulls now.", f, style="teaching",
                                                 known_text=memory, continuation=True).hard]
    assert now == ["opposite_direction"]
    for current in ("The last candle favours the bulls.", "Price bounced from the last swing low and is likely to rise."):
        hard = [v["check"] for v in check_explanation(current, f, style="teaching", known_text=memory, continuation=True).hard]
        assert hard == ["opposite_direction"], current


# --- the API --------------------------------------------------------------------------------------------------

def test_api_spends_once_per_candle_and_scrubbing_never_touches_the_memory(cfg, candles, monkeypatch):
    from fastapi.testclient import TestClient

    import src.advisor.explain as E
    import src.api.app as api
    calls = []

    def fake_read(facts_text, c, client=None, **kw):
        calls.append(kw.get("memory"))
        return {**_FIELDS, "usage": {"input_tokens": 1, "output_tokens": 1}}
    monkeypatch.setattr(E, "explain_read", fake_read)
    monkeypatch.setattr(api, "cfg", api.cfg.model_copy(update={"anthropic_api_key": "test"}))
    monkeypatch.setattr("src.service.analyze.get_candles", lambda *a, **k: candles)
    api._CACHE.clear(); api._HITS.clear()
    c = TestClient(api.app)
    q = {"symbol": "BTC/USDT", "timeframe": "1h", "explain": "true"}
    a = c.get("/analysis", params=q).json()
    b = c.get("/analysis", params=q).json()
    assert a["memory"]["kind"] == "first" and b["memory"]["kind"] == "stored" and len(calls) == 1
    assert b["explanation"] == _FIELDS["explanation"]
    s = c.get("/analysis", params={**q, "as_of_bar": 300}).json()
    assert s["memory"] is None and s["explanation"] is None and len(calls) == 1
    f = c.get("/analysis", params={**q, "fresh": "true"}).json()
    assert f["memory"]["kind"] == "first" and f["memory"]["reason"] == "fresh" and len(calls) == 2
    conn = M.connect(api._TRADES_DB)
    assert _rows(conn) == 2
