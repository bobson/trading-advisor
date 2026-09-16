"""Phase C of the ML plan — the walk-forward instrument (does a model beat a coin flip?).

Walk-forward = train on the past, test on the UNTOUCHED future, roll forward (sklearn's
`TimeSeriesSplit` — never shuffles a time series). We pool the out-of-sample predictions across
folds and report accuracy, AUC, and CALIBRATION vs the majority-class baseline. Everything is
out-of-sample by construction, so an honest number can't be faked by overfitting.

`evaluate_walkforward(X, y)` is the pure instrument (crafted X/y in tests prove it *finds* a
real signal AND reports ~0.5 on pure noise — i.e. it doesn't hallucinate an edge or leak).
`walk_forward_eval(df, cfg)` builds Phase-A features + Phase-B labels, reduces to a binary
up-vs-down target (dropping the rare timeout), and runs the instrument.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from src.ml.features_matrix import FEATURE_COLUMNS, build_feature_matrix
from src.ml.labels import triple_barrier_labels


def _calibration(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 5) -> list[dict]:
    """Per predicted-probability bin: mean predicted vs actual win rate (n). Well-calibrated =
    predicted ≈ actual."""
    out = []
    edges = np.linspace(0.0, 1.0, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob >= lo) & (y_prob < hi) if hi < 1.0 else (y_prob >= lo) & (y_prob <= hi)
        if mask.sum() == 0:
            continue
        out.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "predicted": round(float(y_prob[mask].mean()), 3),
            "actual": round(float(y_true[mask].mean()), 3),
            "n": int(mask.sum()),
        })
    return out


def evaluate_walkforward(X: pd.DataFrame, y: pd.Series, *, n_folds: int = 5, seed: int = 0) -> dict:
    """Pooled out-of-sample metrics from walk-forward folds. `y` is binary (1=up, 0=down)."""
    y_arr = y.to_numpy()
    tscv = TimeSeriesSplit(n_splits=n_folds)
    oos_true: list[int] = []
    oos_prob: list[float] = []
    for train_idx, test_idx in tscv.split(X):
        if len(np.unique(y_arr[train_idx])) < 2:
            continue  # a fold with one class can't train a classifier
        model = HistGradientBoostingClassifier(max_iter=150, random_state=seed)
        model.fit(X.iloc[train_idx], y_arr[train_idx])
        prob = model.predict_proba(X.iloc[test_idx])[:, 1]
        oos_true.extend(y_arr[test_idx].tolist())
        oos_prob.extend(prob.tolist())

    yt = np.asarray(oos_true)
    yp = np.asarray(oos_prob)
    up_rate = float(yt.mean()) if len(yt) else 0.0
    return {
        "n_oos": int(len(yt)),
        "baseline_acc": round(max(up_rate, 1 - up_rate), 3),   # always-predict-majority
        "model_acc": round(float(accuracy_score(yt, yp >= 0.5)), 3) if len(yt) else None,
        "auc": round(float(roc_auc_score(yt, yp)), 3) if len(np.unique(yt)) == 2 else None,
        "up_rate": round(up_rate, 3),
        "calibration": _calibration(yt, yp),
    }


def walk_forward_eval(df: pd.DataFrame, cfg, *, horizon: int = 24, atr_mult: float = 1.0,
                      n_folds: int = 5) -> dict:
    """Build features + labels for `df` and run the walk-forward evaluation (up vs down)."""
    X = build_feature_matrix(df, cfg)
    y = triple_barrier_labels(df, cfg, horizon=horizon, atr_mult=atr_mult)

    # Keep rows with a usable label (drop the rare timeout); leave feature NaN to the model —
    # HistGradientBoosting handles NaN natively, so warm-up / volume-less rows aren't discarded.
    data = X.copy()
    data["_label"] = y
    data = data[data["_label"].notna() & (data["_label"] != 0)]
    binary = (data["_label"] > 0).astype(int)

    result = evaluate_walkforward(data[FEATURE_COLUMNS], binary, n_folds=n_folds)
    result.update({"horizon": horizon, "atr_mult": atr_mult, "features": len(FEATURE_COLUMNS)})
    return result
