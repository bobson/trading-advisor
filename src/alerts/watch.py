"""#7 alerts — scan the watchlist and return the setups currently flagged.

`scan` runs the (free, no-Claude) analysis on each watchlist symbol and keeps those whose
confluence is triggered at or above `alerts.min_confidence`. `advise_fn` is injectable so tests
run without candles/network. Honest note: given the engine has no measured edge, these alerts
say "a setup fired", not "this will go up" — same clarity-not-prediction framing as everywhere.
"""

from __future__ import annotations

from src.service.analyze import advise


def scan(cfg, *, advise_fn=None) -> list[dict]:
    """Return a list of currently-flagged setups across the watchlist."""
    a = cfg.alerts
    if advise_fn is None:
        def advise_fn(symbol, timeframe):
            return advise(symbol, timeframe, cfg, explain_enabled=False, refresh_stale=True)

    alerts: list[dict] = []
    for symbol in a.symbols:
        try:
            result = advise_fn(symbol, a.timeframe)
        except Exception:
            continue  # a bad/uncached pair shouldn't sink the whole scan
        c = result.facts["confluence"]
        if c["triggered"] and c["confidence"] >= a.min_confidence:
            alerts.append({
                "symbol": symbol,
                "timeframe": a.timeframe,
                "bias": c["bias"],
                "confidence": c["confidence"],
                "agreeing": c["agreeing_categories"],
            })
    return alerts
