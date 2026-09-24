"""ROADMAP B2 — detector evaluation against gold labels: matching, precision/recall with counts,
the fixed holdout, tuning that never sees the holdout, and the measured reliability field.

Uses the committed 350-bar BTC 1h fixture, with labels built so the right answer is known."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.labels import evaluate as ev
from src.labels.evaluate import SR, Tally, detect_at, evaluate, is_holdout, split, tune

FIXTURE = Path(__file__).parent / "fixtures" / "btc_1h_sample.csv"


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def candles():
    df = pd.read_csv(FIXTURE, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _t(df, bar):
    return int(pd.Timestamp(df.index[bar]).timestamp())


def _perfect_label(df, bar, cfg, symbol="BTC/USDT", tf="1h"):
    """A labeller who marks exactly what the detector found (patterns + the shown zones)."""
    d = detect_at(df, bar, cfg)
    pats = [{"type": p.type, "points": [{"time": _t(df, b), "price": float(pr)} for b, pr in p.points]}
            for p in d["patterns"]]
    return {"symbol": symbol, "timeframe": tf, "bar": bar, "labels": {"patterns": pats, "zones": [], "nothing": False}}


def test_tally_maths():
    t = Tally(tp=3, fp=1, fn=2)
    assert (t.detections, t.gold) == (4, 5)
    assert t.precision == 0.75 and t.recall == 0.6
    assert Tally().precision is None and Tally().recall is None          # no fires ≠ perfect


def test_perfect_labels_give_full_precision_and_recall(cfg, candles):
    bar = len(candles) - 1
    lab = _perfect_label(candles, bar, cfg)
    assert lab["labels"]["patterns"], "fixture should contain detected patterns"
    rep = evaluate([lab], cfg, lambda s, tf: candles)
    for (det, _), t in rep.tallies.items():
        assert t.precision == 1.0 and t.recall == 1.0, det
    assert rep.charts == 1


def test_nothing_here_turns_every_detection_into_a_false_positive(cfg, candles):
    bar = len(candles) - 1
    n_det = len(detect_at(candles, bar, cfg)["patterns"])
    lab = {"symbol": "BTC/USDT", "timeframe": "1h", "bar": bar, "labels": {"patterns": [], "zones": [], "nothing": True}}
    rep = evaluate([lab], cfg, lambda s, tf: candles)
    pats = [t for (det, _), t in rep.tallies.items() if det != SR]
    assert sum(t.fp for t in pats) == n_det and all(t.precision == 0.0 for t in pats)
    assert (SR, "1h") not in rep.tallies          # 'nothing here' is about patterns — zones not scored


def test_a_missed_pattern_counts_against_recall(cfg, candles):
    bar = len(candles) - 1
    lab = _perfect_label(candles, bar, cfg)
    lab["labels"]["patterns"].append({"type": "rising wedge", "points": [
        {"time": _t(candles, bar - 40), "price": 60000.0}, {"time": _t(candles, bar - 5), "price": 61000.0}]})
    rep = evaluate([lab], cfg, lambda s, tf: candles)
    wedge = rep.tallies[("rising wedge", "1h")]
    assert (wedge.tp, wedge.fn, wedge.recall) == (0, 1, 0.0)


def test_endpoints_must_line_up_in_time_and_atr_scaled_price(cfg, candles):
    bar = len(candles) - 1
    lab = _perfect_label(candles, bar, cfg)
    p = lab["labels"]["patterns"][0]
    atr = detect_at(candles, bar, cfg)["atr"]
    near, far = [dict(q) for q in p["points"]], [dict(q) for q in p["points"]]
    near[0]["price"] += 0.5 * atr                           # inside 1×ATR -> still a match
    far[0]["price"] += 3.0 * atr                            # well outside -> no match
    for pts, expect in ((near, 1), (far, 0)):
        one = {**lab, "labels": {"patterns": [{"type": p["type"], "points": pts}], "zones": [], "nothing": False}}
        t = evaluate([one], cfg, lambda s, tf: candles).tallies[(p["type"], "1h")]
        assert t.tp == expect


def test_zone_matching_needs_role_and_overlap(cfg, candles):
    bar = len(candles) - 1
    d = detect_at(candles, bar, cfg)
    close = float(d["df"]["close"].iloc[-1])
    z = d["zones"].iloc[(d["zones"]["price"] - close).abs().argmin()]
    role = "support" if z["price"] < close else "resistance"
    good = {"lower": float(z["lower"]), "upper": float(z["upper"]), "role": role}
    wrong = {**good, "role": "resistance" if role == "support" else "support"}
    for zone, tp in ((good, 1), (wrong, 0)):
        lab = {"symbol": "BTC/USDT", "timeframe": "1h", "bar": bar,
               "labels": {"patterns": [], "zones": [zone], "nothing": False}}
        assert evaluate([lab], cfg, lambda s, tf: candles).tallies[(SR, "1h")].tp == tp


def test_holdout_split_is_stable_and_about_thirty_percent():
    ids = [("BTC/USDT", "1d", b) for b in range(3000)]
    hold = [i for i in ids if is_holdout(*i)]
    assert 0.25 < len(hold) / len(ids) < 0.35
    assert [i for i in ids if is_holdout(*i)] == hold                    # deterministic
    labels = [{"symbol": s, "timeframe": tf, "bar": b} for s, tf, b in ids[:200]]
    tune_set, hold_set = split(labels)
    assert not ({(x["bar"]) for x in tune_set} & {(x["bar"]) for x in hold_set})
    assert len(tune_set) + len(hold_set) == 200


def test_tuning_only_ever_sees_the_tune_split(cfg, candles, monkeypatch):
    bars = list(range(200, len(candles), 7))
    labels = [_perfect_label(candles, b, cfg) for b in bars]
    tune_set, hold_set = split(labels)
    hold_bars = {x["bar"] for x in hold_set}
    seen = []
    real = ev.evaluate_chart

    def spy(label, *a, **k):
        seen.append(label["bar"])
        return real(label, *a, **k)
    monkeypatch.setattr(ev, "evaluate_chart", spy)
    tune(tune_set, cfg, lambda s, tf: candles, ["ascending channel", "descending channel"],
         {"channel_min_r2": [0.6, 0.9]}, min_detections=0)
    assert seen and not (set(seen) & hold_bars)


def test_tuning_scores_every_candidate_and_picks_the_best_f1(cfg, candles):
    """Labels = exactly what the default channel settings detect (19 channel bars in the fixture), so
    the default scores F1 = 1.0 and must be chosen; a much stricter r² loses matches, so can't beat it."""
    bars = list(range(150, len(candles), 5))
    labels = [_perfect_label(candles, b, cfg) for b in bars]
    res = tune(labels, cfg, lambda s, tf: candles, ["ascending channel", "descending channel"],
               {"channel_min_r2": [0.6, 0.99]}, min_detections=1)
    default = next(r for r in res["log"] if r["params"]["channel_min_r2"] == 0.6)
    assert default["tp"] > 0 and default["f1"] == 1.0
    assert res["best"] == {"channel_min_r2": 0.6} and res["best_f1"] == 1.0


def test_channel_rails_option_rejects_channels_price_broke_through(cfg):
    import numpy as np

    from src.indicators.features import COL_ATR
    from src.patterns.chart_patterns import find_patterns
    from src.structure.swings import SWING_HIGH, SWING_LOW
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    c = np.linspace(100, 120, n)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, COL_ATR: 1.0}, index=idx)
    sw = pd.DataFrame([(5, 106.0, SWING_HIGH), (15, 111.0, SWING_HIGH), (25, 116.0, SWING_HIGH),
                       (10, 102.0, SWING_LOW), (20, 107.0, SWING_LOW), (30, 112.0, SWING_LOW)],
                      columns=["bar", "price", "kind"])
    assert "ascending channel" in {p.type for p in find_patterns(df, sw, cfg)}
    df.iloc[18, df.columns.get_loc("close")] = 130.0          # one close far above the upper rail
    strict = cfg.model_copy(update={"patterns": cfg.patterns.model_copy(update={"channel_respect_rails": True})})
    assert "ascending channel" in {p.type for p in find_patterns(df, sw, cfg)}      # default: still called
    assert "ascending channel" not in {p.type for p in find_patterns(df, sw, strict)}


def test_measured_reliability_fills_the_facts_field(cfg, candles):
    from src.advisor.facts import facts_to_prompt
    from src.labels.evaluate import reliability_table
    from src.service.analyze import advise
    bar = len(candles) - 1
    rep = evaluate([_perfect_label(candles, bar, cfg)], cfg, lambda s, tf: candles)
    table = reliability_table(rep, min_n=1)
    plain = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False)
    measured = advise("BTC/USDT", "1h", cfg, df=candles, explain_enabled=False, reliability=table)
    assert all(v["precision"] is None for v in plain.facts["detector_reliability"]["chart_patterns"].values())
    got = measured.facts["detector_reliability"]["chart_patterns"]
    assert any(v["precision"] == 1.0 and v["n"] >= 1 for v in got.values())
    assert "precision 1.0 over" in facts_to_prompt(measured.facts)
