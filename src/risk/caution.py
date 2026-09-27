"""ROADMAP R1 — caution conditions: when a read is risky to act on, as Layer 1 FACTS.

Direction is a coin flip (every test agrees), but two things aren't: the SIZE of moves (volatility
clusters) and COSTS. These conditions describe the risk around a read, never its direction:

  no_expansion       a fresh breakout with neither volume nor volatility expanding on its breakout bar
  stretched          price far from its slow moving average, in ATR
  volatility_extreme ATR at an extreme of its own rolling history (a normal-size position is then an
                     oversized — or undersized — bet)
  stop_in_noise      the read's invalidation is closer than normal noise (ATR)
  no_room            after costs, the next level in the read's direction is closer than its invalidation
  htf_against        the highest directional higher-timeframe trend opposes the read
  event_risk         a high-impact economic event within N hours (needs the calendar; never guessed)
  thin_market        forex / gold just after a weekend gap, or (intraday) in the thin Sydney hours

Each entry: {code, label, active (True / False / None), detail, value, status}. `active` None means the
condition can't be judged here (`detail` says why: not applicable to a no-setup read, or its input is
unavailable). `status` is "unmeasured" for all of them until ROADMAP R3 measures each on held-back
history; nothing here changes a vote, the confluence score or the tier.

Look-ahead-safe by construction: reads only the facts (built from bars <= N) and the featured frame
up to its last row. The read's levels come from the forward record's rule (`forward.rule.levels_for`),
so R2 can freeze exactly these values.
"""

from __future__ import annotations

import pandas as pd

from src.config import Config
from src.indicators.features import COL_ATR, COL_SMA_SLOW, COL_VOLUME, COL_VOLUME_MA

UNMEASURED = "unmeasured"
_DIR = ("bullish", "bearish")

LABELS = {
    "no_expansion": "Breakout without expansion",
    "stretched": "Stretched from the average",
    "volatility_extreme": "Volatility at an extreme",
    "stop_in_noise": "Invalidation inside normal noise",
    "no_room": "Not enough room after costs",
    "htf_against": "Higher timeframe against the read",
    "event_risk": "High-impact news soon",
    "thin_market": "Thin market",
}


# ROADMAP R3: once measured, an ACTIVE condition is shown as a caution only if history backs it
# (`helps`), or it's a true arithmetic warning about the read's own levels (`by_construction`), or a
# sizing fact. `no_effect`, `insufficient` and `forward_only` ones become plain information. Before
# any measurement exists, everything is `unmeasured` and shown as a caution labelled so (R1 behaviour).
CAUTION_STATUSES = ("helps", "by_construction", "sizing", UNMEASURED)
STATUS_TAG = {"helps": "measured: flagged reads did worse on held-back history",
              "by_construction": "arithmetic warning about this read's own levels",
              "sizing": "sizing fact",
              UNMEASURED: "unmeasured",
              "no_effect": "no measured effect on held-back history",
              "insufficient": "too little history to measure",
              "forward_only": "untestable on history; only the forward record can test it"}


def is_caution(entry: dict) -> bool:
    """An ACTIVE entry that is shown as a caution (vs plain information)."""
    return bool(entry.get("active")) and entry.get("status", UNMEASURED) in CAUTION_STATUSES


def read_direction(facts: dict) -> str | None:
    """The read's direction, as the forward record defines it: tier not no_setup AND a directional
    bias. None = a no-setup (range) read."""
    bias = facts["confluence"]["bias"]
    return bias if facts["situation"]["tier"] != "no_setup" and bias in _DIR else None


def _entry(code: str, active: bool | None, detail: str, value=None) -> dict:
    return {"code": code, "label": LABELS[code], "active": active, "detail": detail, "value": value,
            "status": UNMEASURED}


def _num(x, nd=2):
    return None if x is None or pd.isna(x) else round(float(x), nd)


# --- the conditions -------------------------------------------------------------------------------

def _no_expansion(facts: dict, feat: pd.DataFrame, cfg: Config) -> dict:
    fresh = [p for p in facts.get("chart_patterns") or []
             if p.get("state") == "confirmed" and p.get("lifecycle") == "fresh"
             and p.get("bars_since_state_change") is not None]
    if not fresh:
        return _entry("no_expansion", False, "no fresh breakout to judge")
    p = min(fresh, key=lambda q: q["bars_since_state_change"])
    b = len(feat) - 1 - int(p["bars_since_state_change"])            # the breakout bar
    lb = cfg.caution.atr_expand_lookback
    if COL_ATR not in feat.columns:
        return _entry("no_expansion", None, "unavailable: no ATR")
    if b - lb < 0:
        return _entry("no_expansion", None, "unavailable: too little history before the breakout")
    vol, vol_ma = (feat[c].iloc[b] if c in feat.columns else float("nan") for c in (COL_VOLUME, COL_VOLUME_MA))
    vol_ratio = None if pd.isna(vol) or pd.isna(vol_ma) or not vol_ma or not vol else float(vol) / float(vol_ma)
    atr_now, atr_before = feat[COL_ATR].iloc[b], feat[COL_ATR].iloc[b - lb]
    if pd.isna(atr_now) or pd.isna(atr_before) or not atr_before:
        return _entry("no_expansion", None, "unavailable: no ATR at the breakout")
    atr_change = float(atr_now) / float(atr_before) - 1.0
    vol_exp = vol_ratio is not None and vol_ratio >= cfg.caution.breakout_volume_expand
    atr_exp = atr_now > atr_before
    active = not (vol_exp or atr_exp)
    vol_txt = f"volume {vol_ratio:.2f}× its average" if vol_ratio is not None else "no real volume"
    detail = (f"{p['type']} broke out {p['bars_since_state_change']} bar(s) ago with {vol_txt} and ATR "
              f"{atr_change * 100:+.0f}% over {lb} bars — "
              + ("neither expanded" if active else "expansion present"))
    return _entry("no_expansion", active, detail,
                  {"pattern": p["type"], "volume_ratio": _num(vol_ratio), "atr_change_pct": _num(atr_change * 100, 1)})


def _stretched(facts: dict, feat: pd.DataFrame, cfg: Config) -> dict:
    close, atr = facts["market"]["last_close"], _atr(facts)
    ma = feat[COL_SMA_SLOW].iloc[-1] if COL_SMA_SLOW in feat.columns and len(feat) else float("nan")
    if not atr or pd.isna(ma):
        return _entry("stretched", None, "unavailable: no ATR or moving average yet")
    d = (close - float(ma)) / atr
    active = abs(d) >= cfg.caution.stretched_atr
    side = "above" if d >= 0 else "below"
    return _entry("stretched", active, f"{abs(d):.1f} ATR {side} the {cfg.indicators.slow_ma}-MA "
                  f"(flag at {cfg.caution.stretched_atr:g})", _num(d))


def _volatility_extreme(facts: dict, feat: pd.DataFrame, cfg: Config) -> dict:
    rc = cfg.regime
    if COL_ATR not in feat.columns:
        return _entry("volatility_extreme", None, "unavailable: no ATR")
    atr = feat[COL_ATR].dropna().iloc[-rc.atr_percentile_window:]
    if len(atr) < rc.atr_percentile_min_periods:
        return _entry("volatility_extreme", None, "unavailable: not enough ATR history")
    pct = float((atr <= atr.iloc[-1]).mean())
    hi, lo = cfg.caution.volatility_high_pct, cfg.caution.volatility_low_pct
    kind = "high" if pct >= hi else "low" if pct <= lo else None
    last, n = atr.iloc[-1], len(atr)
    where = (f"ATR is the highest of the last {n} bars" if last >= atr.max() else
             f"ATR is the lowest of the last {n} bars" if last <= atr.min() else
             f"ATR is higher than {(atr < last).mean() * 100:.0f}% of the last {n} bars")
    return _entry("volatility_extreme", kind is not None,
                  where + (f" — unusually {kind}" if kind else ""), {"percentile": _num(pct), "kind": kind})


def _levels(facts: dict, direction: str, cfg: Config) -> dict:
    from src.forward.rule import levels_for
    sr = facts.get("support_resistance") or {}
    return levels_for(direction, facts["market"]["last_close"], _atr(facts), sr.get("nearest_support"),
                      sr.get("nearest_resistance"))


def _stop_in_noise(facts: dict, direction: str | None, cfg: Config) -> dict:
    if direction is None:
        return _entry("stop_in_noise", None, "not applicable: no directional read")
    atr = _atr(facts)
    if not atr:
        return _entry("stop_in_noise", None, "unavailable: no ATR")
    lv = _levels(facts, direction, cfg)
    d = abs(facts["market"]["last_close"] - lv["invalidation"]) / atr
    active = d < cfg.caution.stop_noise_atr
    return _entry("stop_in_noise", active, f"invalidation {lv['invalidation']:g} is {d:.2f} ATR away "
                  f"(noise under {cfg.caution.stop_noise_atr:g} ATR; level from {lv['source_below' if direction == 'bullish' else 'source_above']})",
                  {"distance_atr": _num(d), "invalidation": lv["invalidation"]})


def _no_room(facts: dict, direction: str | None, cfg: Config) -> dict:
    if direction is None:
        return _entry("no_room", None, "not applicable: no directional read")
    atr = _atr(facts)
    if not atr:
        return _entry("no_room", None, "unavailable: no ATR")
    from src.backtest.costs import CostModel, _tf_minutes
    close = facts["market"]["last_close"]
    lv = _levels(facts, direction, cfg)
    tf = facts["market"]["timeframe"]
    hold_h = cfg.morning_report.horizons.get(tf, 24) * _tf_minutes(tf) / 60.0
    cost = CostModel(facts["market"]["symbol"], cfg).trade_cost(direction, close, atr / close, hold_h).total * close
    reward, risk = abs(lv["next_level"] - close) - cost, abs(close - lv["invalidation"])
    active = reward < risk
    return _entry("no_room", active, f"to the next level {lv['next_level']:g}: {reward / atr:.2f} ATR after "
                  f"~{cost / atr:.2f} ATR of costs, vs {risk / atr:.2f} ATR to invalidation",
                  {"reward_atr": _num(reward / atr), "risk_atr": _num(risk / atr), "cost_atr": _num(cost / atr)})


def _htf_against(facts: dict, direction: str | None) -> dict:
    """The trend vote on every higher timeframe (`mtf_signals`, the weekly included — information
    only, never the veto), judged against the read: the HIGHEST timeframe with a directional trend."""
    if direction is None:
        return _entry("htf_against", None, "not applicable: no directional read")
    ms = facts.get("mtf_signals") or {}
    base = facts["market"]["timeframe"]
    trend = (ms.get("signals") or {}).get("trend") or {}
    higher = [tf for tf in ms.get("timeframes") or [] if tf != base and tf in trend]
    if not higher:
        return _entry("htf_against", None, "unavailable: no higher timeframe with enough history")
    directional = [tf for tf in higher if trend[tf] in _DIR]
    if not directional:
        return _entry("htf_against", False, "higher-timeframe trends are neutral: " +
                      ", ".join(f"{tf} {trend[tf]}" for tf in higher))
    tf = directional[-1]
    return _entry("htf_against", trend[tf] != direction, f"{tf} trend votes {trend[tf]}, the read is {direction}",
                  {"timeframe": tf, "trend": trend[tf]})


def _event_risk(facts: dict, cfg: Config) -> dict:
    ctx = facts.get("context")
    if not ctx or not cfg.finnhub_api_key:
        return _entry("event_risk", None, "unavailable: no economic calendar (needs FINNHUB_API_KEY)")
    now = pd.Timestamp.now(tz="UTC")
    soon = []
    for e in ctx.get("economic_calendar") or []:
        t = pd.to_datetime(e.get("time"), utc=True, errors="coerce")
        if pd.notna(t) and pd.Timedelta(0) <= t - now <= pd.Timedelta(hours=cfg.caution.event_hours):
            soon.append(f"{e.get('country', '')} {e.get('event', '')} in {(t - now).total_seconds() / 3600:.1f} h")
    return _entry("event_risk", bool(soon), "; ".join(soon) if soon else
                  f"no high-impact event in the next {cfg.caution.event_hours:g} h", soon or None)


def _thin_market(facts: dict, feat: pd.DataFrame) -> dict:
    ma = facts.get("market_adaptation") or {}
    if ma.get("asset_class") != "forex":
        return _entry("thin_market", None, "not applicable: crypto trades around the clock")
    if ma.get("weekend_gap"):
        return _entry("thin_market", True, "the last bar opened after a weekend gap")
    idx = feat.index
    if len(idx) > 1 and (idx[-1] - idx[-2]) < pd.Timedelta(hours=4) and ma.get("active_session") == "Sydney / thin liquidity":
        return _entry("thin_market", True, "the last bar is in the thin Sydney hours (21:00–24:00 UTC)")
    return _entry("thin_market", False, f"session: {ma.get('active_session') or 'daily bars'}")


def _atr(facts: dict) -> float | None:
    a = (facts.get("volatility") or {}).get("atr")
    return float(a) if a else None


def caution_conditions(facts: dict, featured: pd.DataFrame, cfg: Config) -> list[dict]:
    """All eight conditions for the last bar, in a fixed order (absences stay explicit)."""
    direction = read_direction(facts)
    return [
        _no_expansion(facts, featured, cfg),
        _stretched(facts, featured, cfg),
        _volatility_extreme(facts, featured, cfg),
        _stop_in_noise(facts, direction, cfg),
        _no_room(facts, direction, cfg),
        _htf_against(facts, direction),
        _event_risk(facts, cfg),
        _thin_market(facts, featured),
    ]


def refresh_event_risk(facts: dict, cfg: Config) -> None:
    """Live path only: once the calendar context is injected, re-judge `event_risk` in place."""
    for i, c in enumerate(facts.get("caution") or []):
        if c["code"] == "event_risk":
            facts["caution"][i] = _event_risk(facts, cfg)
