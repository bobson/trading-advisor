"""Phase 14 — backtest / forward-return evaluator (the validation instrument)."""

from src.backtest.evaluate import (
    BacktestReport,
    SetupOutcome,
    Stats,
    evaluate,
    signal_at,
)

__all__ = ["BacktestReport", "SetupOutcome", "Stats", "evaluate", "signal_at"]
