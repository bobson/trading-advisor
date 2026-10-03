"""ROADMAP D3 — news & macro context, fully offline (injected feeds and candles): calendar parsing
(offsets, holidays, blanks, malformed rows), central-bank / commodity tagging, the disk cache with a
stale fallback, RSS headlines (page only), drivers with self-proxy exclusion and honest wording, the
correlation warning, the "news soon" caution without any Finnhub key, and the facts text."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.context import drivers as D
from src.context import macro_calendar as M
from src.context.disk_cache import cached
from src.context.headlines import for_symbol, parse_rss

NOW = time.time()


def _ff(offset_h: float, title="CPI m/m", country="USD", impact="High", forecast="0.3%", previous="0.2%"):
    t = pd.Timestamp(NOW + offset_h * 3600, unit="s", tz="UTC").tz_convert("America/New_York")
    return {"title": title, "country": country, "date": t.isoformat(), "impact": impact, "forecast": forecast, "previous": previous}


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --- calendar ----------------------------------------------------------------------------------------------

def test_calendar_parses_offsets_holidays_blanks_and_skips_malformed_rows():
    rows = [_ff(2), _ff(5, title="Bank Holiday", country="GBP", impact="Holiday", forecast="", previous=""),
            {"title": "broken", "date": "not a date"}, "nonsense", _ff(-3, title="FOMC Statement", impact="High")]
    ev = M.parse(rows)
    assert [e["title"] for e in ev] == ["FOMC Statement", "CPI m/m", "Bank Holiday"]        # sorted by time, bad rows gone
    cpi = ev[1]
    assert cpi["time"].endswith("Z") and abs(cpi["ts"] - (NOW + 2 * 3600)) < 2                # offset -> UTC
    assert (cpi["forecast"], cpi["previous"], cpi["actual"]) == ("0.3%", "0.2%", None)
    assert ev[2]["forecast"] is None and ev[2]["kind"] == "holiday"


@pytest.mark.parametrize("title, kind", [("FOMC Statement", "central_bank"), ("Cash Rate", "central_bank"),
                                         ("ECB President Lagarde Speaks", "central_bank"),
                                         ("Crude Oil Inventories", "commodity"), ("Natural Gas Storage", "commodity"),
                                         ("Non-Farm Employment Change", "data")])
def test_central_bank_and_commodity_events_are_tagged_by_name(title, kind):
    assert M.kind_of(title, "High") == kind


def test_the_disk_cache_serves_fresh_then_a_stale_copy_when_the_feed_fails(tmp_path):
    calls = []
    first = cached("x", 3600, lambda: calls.append(1) or [1], cache_dir=tmp_path, now=1000)
    again = cached("x", 3600, lambda: calls.append(1) or [2], cache_dir=tmp_path, now=2000)       # within TTL
    assert first["data"] == again["data"] == [1] and calls == [1]

    def boom():
        raise RuntimeError("feed down")
    late = cached("x", 3600, boom, cache_dir=tmp_path, now=9000)
    assert late["data"] == [1] and late["stale"] and "feed down" in late["error"]
    assert cached("y", 3600, boom, cache_dir=tmp_path)["data"] is None


# --- headlines -----------------------------------------------------------------------------------------------

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Bitcoin ETFs see inflows</title><link>https://x/1</link><pubDate>Fri, 02 Oct 2026 08:20:08 +0000</pubDate></item>
<item><title>Gold steadies near highs</title><link>https://x/2</link><pubDate>Fri, 02 Oct 2026 07:00:00 GMT</pubDate></item>
<item><title></title><link>https://x/3</link></item></channel></rss>"""


def test_headlines_keep_title_link_source_time_only_and_filter_by_market():
    rows = parse_rss(RSS, "Demo", "crypto")
    assert len(rows) == 2 and set(rows[0]) == {"headline", "link", "source", "group", "ts"}
    assert [h["headline"] for h in for_symbol(rows, D.info("XAU/USD")["keywords"])] == ["Gold steadies near highs"]


# --- drivers + correlation -----------------------------------------------------------------------------------

def _daily(values, start="2026-06-01", freq="D"):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.DataFrame({"close": values}, index=idx)


def test_co_movement_joins_7_and_5_day_markets_and_excludes_self_proxies():
    rng = np.random.default_rng(0)
    base = np.cumprod(1 + rng.normal(0, 0.01, 120))
    crypto = _daily(base * 100)                                                   # every day
    fx = _daily(1 / base[:120], freq="B").iloc[:84]                               # weekdays only; = inverse "dollar"
    gold = _daily(np.cumprod(1 + rng.normal(0, 0.01, 120)) * 2000)
    rets = {"BTC/USDT": D.daily_returns(crypto), "EUR/USD": D.daily_returns(fx), "XAU/USD": D.daily_returns(gold)}
    h = D.hypothesis("EUR/USD", rets, window=60, min_n=30)
    assert "the dollar (inverse EUR/USD)" not in [i["proxy"] for i in h["items"]]          # self-proxy excluded
    hb = D.hypothesis("BTC/USDT", rets, window=60, min_n=30)
    assert "crypto (BTC)" not in [i["proxy"] for i in hb["items"]]
    assert all(i["n"] <= 60 for i in hb["items"])


def test_a_strong_co_movement_is_stated_as_a_hypothesis_and_a_weak_one_is_not():
    rng = np.random.default_rng(1)
    x = np.cumprod(1 + rng.normal(0, 0.01, 100))
    rets = {"ETH/USDT": D.daily_returns(_daily(x * 2000 * (1 + rng.normal(0, 0.001, 100)))),
            "BTC/USDT": D.daily_returns(_daily(x * 80000)),
            "XAU/USD": D.daily_returns(_daily(np.cumprod(1 + rng.normal(0, 0.01, 100)) * 2000))}
    h = D.hypothesis("ETH/USDT", rets)
    assert h["strongest"]["proxy"] == "crypto (BTC)" and "not a cause" in h["text"] and "direction" in h["text"]
    weak = D.hypothesis("XAU/USD", {"XAU/USD": rets["XAU/USD"], "BTC/USDT": rets["BTC/USDT"]})
    assert weak["strongest"] is None and weak["text"].startswith("no clear co-movement with crypto (BTC)")


def test_markets_moving_as_one_are_flagged_at_the_threshold():
    rng = np.random.default_rng(2)
    x = np.cumprod(1 + rng.normal(0, 0.01, 90))
    rets = {"BTC/USDT": D.daily_returns(_daily(x * 80000)), "ETH/USDT": D.daily_returns(_daily(x * 2500)),
            "EUR/USD": D.daily_returns(_daily(np.cumprod(1 + rng.normal(0, 0.005, 90))))}
    c = D.correlation(["BTC/USDT", "ETH/USDT", "EUR/USD"], rets, window=60, warn=0.7)
    assert [(w["a"], w["b"]) for w in c["warnings"]] == [("BTC/USDT", "ETH/USDT")]
    assert "largely the same bet" in c["warnings"][0]["text"] and len(c["pairs"]) == 3


# --- the live path: context -> caution -> facts text (all injected) -------------------------------------------

def _ctx(cfg, rows, symbol="EUR/USD"):
    from src.context.gather import gather_context
    feed = lambda url, params=None: rows if "faireconomy" in url else {}  # noqa: E731
    rng = np.random.default_rng(3)
    x = np.cumprod(1 + rng.normal(0, 0.01, 90))
    frames = {"BTC/USDT": _daily(x * 80000), "ETH/USDT": _daily(x * 2500), "SOL/USDT": _daily(x * 150),
              "EUR/USD": _daily(np.cumprod(1 + rng.normal(0, 0.005, 90))), "XAU/USD": _daily(np.cumprod(1 + rng.normal(0, 0.01, 90)) * 2000)}
    return gather_context(symbol, cfg.model_copy(update={"finnhub_api_key": None}), fetch=feed,
                          candles_for=lambda s: frames[s], now=NOW)


def test_context_lists_only_relevant_upcoming_high_impact_events(cfg):
    rows = [_ff(2, country="EUR"), _ff(3, country="JPY"), _ff(4, impact="Medium"), _ff(-5), _ff(24 * 10)]
    ctx = _ctx(cfg, rows)
    assert ctx["calendar_available"] and [e["country"] for e in ctx["economic_calendar"]] == ["EUR"]
    assert ctx["economic_calendar"][0]["forecast"] == "0.3%" and "no actual" in ctx["calendar_note"]


def test_news_soon_fires_from_the_calendar_without_any_finnhub_key(cfg):
    from src.risk.caution import _event_risk
    c = cfg.model_copy(update={"finnhub_api_key": None})
    near = _event_risk({"context": _ctx(cfg, [_ff(2)])}, c)
    far = _event_risk({"context": _ctx(cfg, [_ff(30)])}, c)
    none = _event_risk({"context": {"economic_calendar": [], "calendar_available": False}}, c)
    assert near["active"] is True and "CPI" in near["detail"]
    assert far["active"] is False and none["active"] is None


def test_facts_text_carries_drivers_and_warnings_but_never_headlines(cfg):
    from pathlib import Path

    from src.service.analyze import advise
    df = pd.read_csv(Path(__file__).parent / "fixtures" / "btc_1h_sample.csv", index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    ctx = _ctx(cfg, [_ff(2)], symbol="BTC/USDT")
    ctx["headlines_should_not_appear"] = "Bitcoin poised to rally"
    text = advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False, context=ctx).facts_text
    assert "Driver hypothesis (a CO-MOVEMENT" in text and "Correlation warning" in text
    assert "Conventional drivers (convention, not measured)" in text and "poised to rally" not in text


def test_api_macro_with_injected_feeds(cfg, monkeypatch):
    from fastapi.testclient import TestClient

    import src.api.app as api
    import src.context.gather as G
    import src.context.headlines as Hm
    import src.context.macro_calendar as Mm
    monkeypatch.setattr(Mm, "week", lambda **k: {"events": M.parse([_ff(2), _ff(3, title="Crude Oil Inventories")]),
                                                 "fetched_at": int(NOW), "stale": False, "error": None, "source": M.SOURCE})
    monkeypatch.setattr(Hm, "latest", lambda **k: {"headlines": parse_rss(RSS, "Demo", "crypto"), "fetched_at": int(NOW),
                                                   "stale": False, "error": None})
    rng = np.random.default_rng(4)
    monkeypatch.setattr(G, "_daily_candles", lambda c: (lambda s: _daily(np.cumprod(1 + rng.normal(0, 0.01, 90)) * 100)))
    api._HITS.clear()
    body = TestClient(api.app).get("/macro", params={"symbol": "BTC/USDT"}).json()
    assert [e["kind"] for e in body["calendar"]["events"]] == ["data", "commodity"]
    assert body["headlines"]["for_symbol"][0]["headline"] == "Bitcoin ETFs see inflows"
    assert body["currencies"] == ["USD"] and body["correlation"]["window"] == cfg.context.corr_window_days
    assert "text" in body["drivers"]


def test_the_offline_suite_never_fetches(cfg, monkeypatch):
    import requests

    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(requests, "get", no_net)
    assert _ctx(cfg, [_ff(1)])["calendar_available"]                     # injected feed + candles: no request
