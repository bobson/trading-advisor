"""ROADMAP D2 — pre-registration: write the hypothesis down BEFORE the backtest runs.

Every experiment script (backtest, backtest_suite, ml_eval, funding_study, exit_lab, measure_caution,
measure_exits) is gated:

  1. `--register` (with --question, --hypothesis, --metric, --direction, --threshold, --predict and,
     for rate metrics, --baseline) stores the hypothesis, the EXACT parameters of that run, the
     success metric and threshold, and your prediction — timestamped and hashed — then exits.
  2. `--experiment ID` runs it. Refused when the ID doesn't exist, belongs to another script, already
     has a result, or the run's parameters differ from the registered ones (no tweaking after the fact).
  3. The result is stored linked to the registration, scored against the registered threshold.

Append-only, enforced by the database (triggers): a registration or result can't be edited or
deleted. A change of mind is a NEW registration that `--supersedes` the old one; both stay visible.

Multiple comparisons: variations are grouped by `question`. For a RATE metric (a share of n cases)
with a registered baseline, the one-sided binomial p-value against the baseline must be below
0.05 / k, where k = the number of variations of that question run so far (Bonferroni). Non-rate
metrics (AUC, a spread, a count) can't be corrected this way: they show k beside the result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time

ALPHA = 0.05
SCRIPT_METRICS = {           # script -> {metric: "rate" | "value"}; a rate carries its n
    "backtest": {"win_rate": "rate", "avg_return": "value", "median_return": "value"},
    "backtest_suite": {"win_rate": "rate", "second_half_win_rate": "rate"},
    "ml_eval": {"auc": "value", "model_acc": "rate", "acc_minus_baseline": "value"},
    "funding_study": {"crowded_long_up_rate": "rate", "crowded_short_up_rate": "rate"},
    "exit_lab": {"spread_across_exits": "value", "spread_across_entries": "value", "best_exit_mean_return": "value"},
    "measure_caution": {"helps_count": "value"},
    "measure_exits": {"noise_floor_1h": "value", "noise_floor_4h": "value", "noise_floor_1d": "value"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    question TEXT NOT NULL,           -- groups variations for the multiple-comparison correction
    hypothesis TEXT NOT NULL,
    script TEXT NOT NULL,
    params TEXT NOT NULL,             -- JSON: the exact run parameters
    metric TEXT NOT NULL, direction TEXT NOT NULL, threshold REAL NOT NULL,
    baseline REAL,                    -- rate metrics: what "no effect" would score (e.g. 0.5)
    predicted_pass INTEGER NOT NULL,  -- your prediction: will it meet the threshold?
    predicted_value REAL,
    supersedes INTEGER,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_results (
    experiment_id INTEGER PRIMARY KEY,
    ran_at INTEGER NOT NULL,
    value REAL, n INTEGER,
    passed INTEGER NOT NULL,
    p_value REAL, variations INTEGER NOT NULL, corrected_alpha REAL, passed_corrected INTEGER,
    metrics TEXT NOT NULL,            -- JSON: every metric the script produced
    details TEXT,
    engine_commit TEXT
);
CREATE TRIGGER IF NOT EXISTS experiments_no_update BEFORE UPDATE ON experiments
BEGIN SELECT RAISE(ABORT, 'experiments are append-only: register a new one that supersedes it'); END;
CREATE TRIGGER IF NOT EXISTS experiments_no_delete BEFORE DELETE ON experiments
BEGIN SELECT RAISE(ABORT, 'experiments are append-only: every registration stays on the record'); END;
CREATE TRIGGER IF NOT EXISTS results_no_update BEFORE UPDATE ON experiment_results
BEGIN SELECT RAISE(ABORT, 'results are append-only'); END;
CREATE TRIGGER IF NOT EXISTS results_no_delete BEFORE DELETE ON experiment_results
BEGIN SELECT RAISE(ABORT, 'results are append-only'); END;
"""


class PreregError(ValueError):
    pass


def connect(path: str = "data/wizard.db"):
    from src.store.db import connect as base
    conn = base(path)
    conn.executescript(SCHEMA)
    return conn


def _norm(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=str)


# --- register / gate / record ------------------------------------------------------------------------------

def register(conn, *, script: str, params: dict, question: str, hypothesis: str, metric: str, direction: str,
             threshold: float, predicted_pass: bool, baseline: float | None = None,
             predicted_value: float | None = None, supersedes: int | None = None, now: float | None = None) -> dict:
    if script not in SCRIPT_METRICS:
        raise PreregError(f"unknown script {script!r}")
    kinds = SCRIPT_METRICS[script]
    if metric not in kinds:
        raise PreregError(f"{script} reports {', '.join(kinds)} — not {metric!r}")
    if direction not in (">=", "<="):
        raise PreregError("direction must be >= or <=")
    if kinds[metric] == "rate" and baseline is None:
        raise PreregError(f"{metric} is a rate: give --baseline (what no effect would score, e.g. 0.5)")
    if not question.strip() or not hypothesis.strip():
        raise PreregError("a question and a hypothesis are required")
    if supersedes is not None and conn.execute("SELECT 1 FROM experiments WHERE id=?", (supersedes,)).fetchone() is None:
        raise PreregError(f"no experiment {supersedes} to supersede")
    row = {"created_at": int(now or time.time()), "question": question.strip().lower(), "hypothesis": hypothesis.strip(),
           "script": script, "params": _norm(params), "metric": metric, "direction": direction,
           "threshold": float(threshold), "baseline": baseline, "predicted_pass": int(bool(predicted_pass)),
           "predicted_value": predicted_value, "supersedes": supersedes}
    row["hash"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    cur = conn.execute(f"INSERT INTO experiments ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                       tuple(row.values()))
    conn.commit()
    return get(conn, cur.lastrowid)


def get(conn, exp_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
    return dict(r) if r else None


def check_runnable(conn, exp_id: int | None, script: str, params: dict) -> dict:
    """The gate: the registration must exist, be this script's, have no result, and match the params."""
    if exp_id is None:
        raise PreregError("this experiment isn't registered. Register it first: add --register --question ... "
                          "--hypothesis ... --metric ... --direction '>=' --threshold ... --predict pass|fail "
                          "(and --baseline for a rate), then run with --experiment ID.")
    exp = get(conn, exp_id)
    if exp is None:
        raise PreregError(f"no experiment {exp_id}")
    if exp["script"] != script:
        raise PreregError(f"experiment {exp_id} was registered for {exp['script']}, not {script}")
    if conn.execute("SELECT 1 FROM experiment_results WHERE experiment_id=?", (exp_id,)).fetchone():
        raise PreregError(f"experiment {exp_id} already has a result — register a new variation (--supersedes {exp_id})")
    registered, now = json.loads(exp["params"]), json.loads(_norm(params))
    if registered != now:
        diff = {k: (registered.get(k), now.get(k)) for k in set(registered) | set(now) if registered.get(k) != now.get(k)}
        raise PreregError(f"the run's parameters differ from the registration: {diff} (registered, now)")
    return exp


def _p_value(value: float, n: int, baseline: float, direction: str) -> float:
    from scipy.stats import binomtest
    k = int(round(value * n))
    return float(binomtest(k, n, baseline, alternative="greater" if direction == ">=" else "less").pvalue)


def record(conn, exp_id: int, metrics: dict, *, details: dict | None = None, engine_commit: str | None = None,
           now: float | None = None) -> dict:
    """Store the run's result against its registration. `metrics` = {name: (value, n or None)}."""
    exp = get(conn, exp_id)
    value, n = metrics.get(exp["metric"], (None, None))
    passed = value is not None and (value >= exp["threshold"] if exp["direction"] == ">=" else value <= exp["threshold"])
    k = 1 + conn.execute("""SELECT COUNT(*) FROM experiment_results r JOIN experiments e ON e.id = r.experiment_id
                            WHERE e.question = ?""", (exp["question"],)).fetchone()[0]
    p = alpha = corrected = None
    if SCRIPT_METRICS[exp["script"]][exp["metric"]] == "rate" and value is not None and n:
        p = _p_value(value, n, exp["baseline"], exp["direction"])
        alpha = ALPHA / k
        corrected = int(passed and p < alpha)
    conn.execute("INSERT INTO experiment_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (exp_id, int(now or time.time()), value, n, int(passed), p, k, alpha, corrected,
                  json.dumps({m: list(v) for m, v in metrics.items()}), json.dumps(details or {}), engine_commit))
    conn.commit()
    return {**exp, "value": value, "n": n, "passed": passed, "p_value": p, "variations": k,
            "corrected_alpha": alpha, "passed_corrected": corrected}


# --- the script side: one call before the work, one after -------------------------------------------------------

def add_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("pre-registration (ROADMAP D2)")
    g.add_argument("--experiment", type=int, default=None, help="the registered experiment ID to run")
    g.add_argument("--register", action="store_true", help="register this exact run, then exit")
    g.add_argument("--question", default=None)
    g.add_argument("--hypothesis", default=None)
    g.add_argument("--metric", default=None)
    g.add_argument("--direction", default=">=")
    g.add_argument("--threshold", type=float, default=None)
    g.add_argument("--baseline", type=float, default=None)
    g.add_argument("--predict", choices=["pass", "fail"], default=None, help="will it meet the threshold?")
    g.add_argument("--predicted-value", type=float, default=None)
    g.add_argument("--supersedes", type=int, default=None)
    g.add_argument("--prereg-db", default="data/wizard.db")


_PREREG_KEYS = {"experiment", "register", "question", "hypothesis", "metric", "direction", "threshold", "baseline",
                "predict", "predicted_value", "supersedes", "prereg_db"}


def run_params(args: argparse.Namespace, ignore: tuple = ()) -> dict:
    """The parameters that define a run: every argument except the pre-registration ones and `ignore`
    (output-only flags such as --save)."""
    return {k: v for k, v in vars(args).items() if k not in _PREREG_KEYS and k not in ignore}


def gate(args: argparse.Namespace, script: str, params: dict):
    """Call at the top of an experiment script. Registers-and-exits, refuses to run, or returns the
    (connection, experiment) to record into after the work."""
    conn = connect(args.prereg_db)
    try:
        if args.register:
            missing = [f for f in ("question", "hypothesis", "metric", "threshold", "predict") if getattr(args, f) is None]
            if missing:
                raise PreregError("to register, give " + ", ".join(f"--{m.replace('_', '-')}" for m in missing))
            exp = register(conn, script=script, params=params, question=args.question, hypothesis=args.hypothesis,
                           metric=args.metric, direction=args.direction, threshold=args.threshold,
                           baseline=args.baseline, predicted_pass=args.predict == "pass",
                           predicted_value=args.predicted_value, supersedes=args.supersedes)
            print(f"Registered experiment {exp['id']} (hash {exp['hash']}). Run it with the same arguments and "
                  f"--experiment {exp['id']}.")
            sys.exit(0)
        return conn, check_runnable(conn, args.experiment, script, params)
    except PreregError as exc:
        print(f"Pre-registration: {exc}", file=sys.stderr)
        sys.exit(2)


def finish(conn, exp: dict, metrics: dict, details: dict | None = None) -> None:
    from src.config import load_config
    from src.forward.record import engine_info
    out = record(conn, exp["id"], metrics, details=details, engine_commit=engine_info(load_config())["commit"])
    verdict = "PASSED" if out["passed"] else "did not pass"
    corr = ("" if out["passed_corrected"] is None else
            f"; after the correction for {out['variations']} variation(s) (alpha {out['corrected_alpha']:.4f}, "
            f"p {out['p_value']:.4f}): {'passes' if out['passed_corrected'] else 'does NOT pass'}")
    pred = "you predicted it would pass" if exp["predicted_pass"] else "you predicted it would fail"
    print(f"\nExperiment {exp['id']}: {exp['metric']} = {out['value']} {exp['direction']} {exp['threshold']}? "
          f"{verdict}{corr}. ({pred})")
    conn.close()


# --- the dashboard -------------------------------------------------------------------------------------------------

def dashboard(conn) -> dict:
    rows = [dict(r) for r in conn.execute(
        """SELECT e.*, r.ran_at, r.value, r.n, r.passed, r.p_value, r.variations, r.corrected_alpha,
                  r.passed_corrected, r.engine_commit
           FROM experiments e LEFT JOIN experiment_results r ON r.experiment_id = e.id ORDER BY e.id DESC""")]
    ran = [r for r in rows if r["ran_at"] is not None]
    hits = sum(1 for r in ran if bool(r["passed"]) == bool(r["predicted_pass"]))
    superseded = {r["supersedes"] for r in rows if r["supersedes"]}
    for r in rows:
        r["params"] = json.loads(r["params"])
        r["superseded"] = r["id"] in superseded
    questions = {}
    for r in rows:
        q = questions.setdefault(r["question"], {"registered": 0, "ran": 0, "passed": 0, "passed_corrected": 0})
        q["registered"] += 1
        q["ran"] += int(r["ran_at"] is not None)
        q["passed"] += int(bool(r["passed"]))
        q["passed_corrected"] += int(bool(r["passed_corrected"]))
    return {"experiments": rows, "questions": questions,
            "summary": {"registered": len(rows), "ran": len(ran), "never_ran": len(rows) - len(ran),
                        "passed": sum(1 for r in ran if r["passed"]), "misses": sum(1 for r in ran if not r["passed"]),
                        "prediction_hits": hits, "prediction_n": len(ran)}}
