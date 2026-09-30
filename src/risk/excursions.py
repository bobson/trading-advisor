"""ROADMAP R4 — exits: how far trades went against, and how far they ran for.

Built from the SAME walk and split as R3 (`caution_stats.collect` — one case per directional read, with
its maximum adverse excursion `mae_atr`, maximum favourable excursion `mfe_atr` and where it ended
`end_atr`, all in ATR at the read, over the timeframe's horizon). Reported from the held-back 30%; the
older 70% is shown beside it as a stability check.

DEFINED BEFORE THE FIRST RUN:
  noise floor   the median MAE of the reads that ENDED in profit (end_atr > 0). "Half of the trades that
                turned out right first went this far against you" — a stop tighter than that would
                have closed at least half of the eventual winners. Not a recommended stop.
  typical run   the median MFE of all reads: half of them never got further than this in their favour
                within the horizon. A realistic ceiling for a target, not a forecast.
  stop touch    for stops at 0.5 / 1 / 1.5 / 2 / 3 ATR: the share of all reads, and of eventual
                winners, whose MAE reached that distance.
  stable        the held-back value is within 25% of the older part's (else labelled "unstable").
  exits         the Feature-8 exit rules simulated on the held-back reads, net of costs (per-trade mean
                and win rate with counts). A comparison on history, never a recommendation.
Every number carries its count; below MIN_N (20) a number is "insufficient".
"""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean

from src.config import Config

MIN_N = 20
STOPS = (0.5, 1.0, 1.5, 2.0, 3.0)
STABLE_TOL = 0.25
TF_ORDER = {"30m": 0, "1h": 1, "4h": 2, "1d": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS exit_stats (
    timeframe TEXT PRIMARY KEY,
    summary TEXT NOT NULL,          -- JSON: see excursions.summarize
    built_at INTEGER NOT NULL, params TEXT
);
"""


def _q(values: list[float], p: float) -> float | None:
    if len(values) < MIN_N:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))], 2)


def _part(cases: list[dict]) -> dict:
    winners = [c for c in cases if c["end_atr"] > 0]
    mae_all = [c["mae_atr"] for c in cases]
    mae_win = [c["mae_atr"] for c in winners]
    mfe_all = [c["mfe_atr"] for c in cases]
    return {
        "n": len(cases), "winners": len(winners),
        "noise_floor": _q(mae_win, 0.5),
        "typical_run": _q(mfe_all, 0.5),
        "mae_quartiles": [_q(mae_all, p) for p in (0.25, 0.5, 0.75, 0.9)],
        "winner_mae_deciles": [_q(mae_win, p / 10) for p in range(1, 10)],
        "mfe_quartiles": [_q(mfe_all, p) for p in (0.25, 0.5, 0.75, 0.9)],
        "stop_touch": {str(k): {"all": round(sum(m >= k for m in mae_all) / len(mae_all), 3) if len(mae_all) >= MIN_N else None,
                                "winners": round(sum(m >= k for m in mae_win) / len(mae_win), 3) if len(mae_win) >= MIN_N else None}
                       for k in STOPS},
    }


def _stable(test: float | None, tune: float | None) -> bool | None:
    if test is None or tune is None or tune == 0:
        return None
    return abs(test - tune) / abs(tune) <= STABLE_TOL


def summarize(cases: list[dict], exit_results: dict | None = None) -> dict[str, dict]:
    """{timeframe: {test, tune, stable, regimes, exits}} from R3/R4 cases (pure; testable)."""
    by_tf = defaultdict(list)
    for c in cases:
        by_tf[c["timeframe"]].append(c)
    out = {}
    for tf, cs in sorted(by_tf.items(), key=lambda kv: TF_ORDER.get(kv[0], 9)):
        test = [c for c in cs if c["part"] == "test"]
        tune = [c for c in cs if c["part"] == "tune"]
        t, u = _part(test), _part(tune)
        regs = defaultdict(list)
        for c in test:
            regs[c.get("regime", "unknown")].append(c)
        out[tf] = {
            "test": t, "tune": u,
            "stable": {k: _stable(t[k], u[k]) for k in ("noise_floor", "typical_run")},
            "regimes": {r: {"n": len(v), "noise_floor": _part(v)["noise_floor"], "typical_run": _part(v)["typical_run"]}
                        for r, v in sorted(regs.items())},
            "markets": sorted({c["symbol"] for c in test}),
            "exits": (exit_results or {}).get(tf),
        }
    return out


# --- the exit lab on the held-back reads -----------------------------------------------------------

def simulate_exits(df, cfg: Config, cases: list[dict]) -> dict[str, list[list[float]]]:
    """Net-of-cost returns of every Feature-8 exit rule, entered at each held-back read (one market;
    `cfg` request-scoped). Look-ahead-safe: `simulate_exit` reads bars <= the one it simulates."""
    from src.backtest.exits import EXIT_RULES, _net_return, simulate_exit
    from src.indicators.features import add_features
    from src.market.regime import classify_regime
    featured = add_features(df, cfg)
    regime = classify_regime(featured, cfg)
    out = {rule: [] for rule in EXIT_RULES}
    for c in cases:
        if c["part"] != "test":
            continue
        for rule in EXIT_RULES:
            t = simulate_exit(featured, c["i"], c["direction"], cfg, rule, regime=regime)
            out[rule].append([round(_net_return(t, cfg, featured), 6), t.bars_held])
    return out


def exit_table(net_returns: dict[str, list[list[float]]]) -> dict[str, dict]:
    """Per exit rule: n, mean net return per trade, win rate and average bars held (rules hold for very
    different lengths, so a mean return is only comparable next to its holding time)."""
    out = {}
    for rule, rows in net_returns.items():
        r = [x[0] for x in rows]
        ok = len(r) >= MIN_N
        out[rule] = {"n": len(r), "mean_pct": round(mean(r) * 100, 3) if ok else None,
                     "win_rate": round(sum(x > 0 for x in r) / len(r), 3) if ok else None,
                     "avg_bars": round(mean(x[1] for x in rows), 1) if rows else None}
    return out


# --- storage + what the app shows ---------------------------------------------------------------------

def save(conn, summary: dict, *, built_at: int, params: dict) -> None:
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM exit_stats")
    for tf, s in summary.items():
        conn.execute("INSERT INTO exit_stats VALUES (?,?,?,?)", (tf, json.dumps(s), built_at, json.dumps(params)))
    conn.commit()


def load(conn) -> dict[str, dict]:
    try:
        return {r["timeframe"]: json.loads(r["summary"]) for r in conn.execute("SELECT * FROM exit_stats")}
    except Exception:                                   # not built yet
        return {}


def facts_block(summary_tf: dict | None, atr: float | None) -> dict | None:
    """The chart's timeframe as facts: noise floor + typical run in ATR AND in price, with counts."""
    if not summary_tf:
        return None
    t = summary_tf["test"]
    nf, run = t["noise_floor"], t["typical_run"]
    return {
        "noise_floor_atr": nf, "typical_run_atr": run,
        "noise_floor_price": round(nf * atr, 6) if nf is not None and atr else None,
        "typical_run_price": round(run * atr, 6) if run is not None and atr else None,
        "n": t["n"], "winners": t["winners"], "stable": summary_tf["stable"],
        "stop_touch": t["stop_touch"],
        "text": text(summary_tf),
    }


def text(summary_tf: dict) -> str:
    t, st = summary_tf["test"], summary_tf["stable"]
    if t["noise_floor"] is None:
        return f"not enough history ({t['winners']} winners of {t['n']} reads)"
    tag = lambda k: "" if st.get(k) else " (unstable between periods)"  # noqa: E731
    return (f"half of the {t['winners']} past reads that ended in profit first went {t['noise_floor']} ATR against "
            f"(noise floor{tag('noise_floor')}); half of all {t['n']} reads never ran more than "
            f"{t['typical_run']} ATR in their favour (typical run{tag('typical_run')})")


def stop_warning(stop_atr: float, summary_tf: dict | None) -> dict | None:
    """For the risk calculator: is this stop inside the noise floor, and roughly how many of the past
    trades that ended in profit went further against than it (from the winners' MAE deciles)."""
    if not summary_tf or summary_tf["test"]["noise_floor"] is None:
        return None
    t = summary_tf["test"]
    deciles = [d for d in t.get("winner_mae_deciles") or [] if d is not None]
    in_ten = None
    if len(deciles) == 9:
        # winners whose MAE went beyond the stop, in tenths: 0 = fewer than 1 in 10, 9 = more than 9 in 10
        in_ten = sum(1 for d in deciles if d > stop_atr)
    return {"inside": stop_atr < t["noise_floor"], "stop_atr": round(stop_atr, 2),
            "noise_floor_atr": t["noise_floor"], "typical_run_atr": t["typical_run"],
            "winners_beyond_stop_in_10": in_ten, "n": t["n"], "winners": t["winners"],
            "stable": summary_tf["stable"].get("noise_floor")}
