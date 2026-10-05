"""Simplification pass 2 — read memory: every explained read is stored, so the explanation can continue
from the last one instead of starting over.

  same candle      the stored read comes back — no Claude call, no credit.
  new candles      Layer 1 COMPUTES what happened since the previous read (did price reach its next
                   level or its invalidation first, did the range hold, what changed in the read,
                   patterns, momentum, trend, cautions, zones) and Claude writes a CONTINUATION from
                   its own earlier thesis + that comparison + the full current facts.
  first read       per market + timeframe: the full teaching read. Also after "Start fresh", when the
                   engine changed (fingerprint of the engine code + analyst guide + config), when the
                   last read is more than `advisor.memory_gap_bars` candles old, or when the last
                   read had no usable thesis (facts-only fallback).

The memory is DATA, not prose: the full facts, a Layer-1 thesis (bias, tier, the levels the forward
record would judge — `forward.rule.levels_for` — zones, patterns, momentum zones, trend, cautions) and
Claude's own four-field thesis (read / why / invalidation / watch). Claude explains the computed status;
it never decides it. Live path only — scrubbing never reads or writes memory, and `build_facts` is
untouched (snapshot unchanged).
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
    bar_time INTEGER NOT NULL,            -- the last CLOSED candle the facts were computed on (epoch s UTC)
    created_at INTEGER NOT NULL,
    kind TEXT NOT NULL,                   -- first | continuation
    reason TEXT,                          -- why a first read: none_before | fresh | engine_changed | gap | no_thesis
    parent_id INTEGER, anchor_id INTEGER, -- the read it continues, and the first read of the chain
    fingerprint TEXT NOT NULL,            -- engine code + analyst guide + config
    facts_json TEXT NOT NULL, facts_text TEXT NOT NULL,
    thesis_l1 TEXT NOT NULL,              -- Layer-1 thesis (JSON)
    thesis TEXT,                          -- Claude's {read, why, invalidation, watch}; NULL = facts-only fallback
    comparison TEXT,                      -- what happened since the parent (JSON), continuations only
    explanation TEXT NOT NULL, verification TEXT,
    model TEXT, usage TEXT                -- the Claude call(s): tokens in / out / cached
);
CREATE INDEX IF NOT EXISTS analysis_reads_market ON analysis_reads (symbol, timeframe, id);
"""

FIRST, CONTINUATION, STORED = "first", "continuation", "stored"
THESIS_FIELDS = ("read", "why", "invalidation", "watch")


def connect(path: str | None = None):
    from src.store.db import connect as base
    conn = base(path) if path else base()
    conn.executescript(SCHEMA)
    return conn


# --- the engine fingerprint ----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _code_hash() -> str:
    root = Path(__file__).resolve().parents[1]                   # src/
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.py")):
        h.update(str(f.relative_to(root)).encode())
        h.update(f.read_bytes())
    h.update((root / "advisor" / "analyst-guide-system-prompt.md").read_bytes())
    return h.hexdigest()


def fingerprint(cfg: Config) -> str:
    """Changes when the engine code, the analyst guide or config.yaml changes — not on docs/frontend pushes."""
    from src.forward.record import _SECRETS
    conf = json.dumps(cfg.model_dump(mode="json", exclude=_SECRETS), sort_keys=True)
    return hashlib.sha256((_code_hash() + conf).encode()).hexdigest()[:16]


# --- the Layer-1 thesis --------------------------------------------------------------------------------

def bar_time_of(facts: dict) -> int:
    return int(pd.Timestamp(facts["market"]["last_time"]).timestamp())


def thesis_l1(facts: dict) -> dict:
    """What the read said, as numbers and labels the next read can be compared against."""
    from src.forward.rule import BEARISH, BULLISH, levels_for
    from src.risk.caution import is_caution
    c, sit = facts["confluence"], facts.get("situation") or {}
    bias, tier = c["bias"], sit.get("tier")
    directional = tier != "no_setup" and bias in (BULLISH, BEARISH)
    sr = facts.get("support_resistance") or {}
    sup, res = sr.get("nearest_support"), sr.get("nearest_resistance")
    vol, mom = facts.get("volatility") or {}, facts.get("momentum") or {}
    close = float(facts["market"]["last_close"])
    lv = levels_for(bias if directional else None, close, vol.get("atr"), sup, res)
    zone = lambda z: {"lower": z["lower"], "upper": z["upper"]} if z else None  # noqa: E731
    return {
        "bar_time": bar_time_of(facts), "time": str(facts["market"]["last_time"]), "price": close,
        "atr": vol.get("atr"), "bias": bias, "tier": tier, "agreeing": c.get("agreeing_categories"),
        "read_kind": "directional" if directional else "range", "direction": bias if directional else None,
        "next_level": lv["next_level"], "invalidation": lv["invalidation"],
        "range_low": lv["range_low"], "range_high": lv["range_high"],
        "support": zone(sup), "resistance": zone(res),
        "patterns": {p["type"]: p.get("lifecycle") or p.get("state") for p in facts.get("chart_patterns") or []},
        "rsi_zone": mom.get("rsi_zone"), "macd_state": mom.get("macd_state"),
        "stochastic_zone": mom.get("stochastic_zone"), "trend": (facts.get("trend") or {}).get("label"),
        "regime": vol.get("regime"),
        "cautions": [x["code"] for x in facts.get("caution") or [] if is_caution(x)],
        "caution_labels": {x["code"]: x["label"] for x in facts.get("caution") or []},
    }


# --- what happened since -------------------------------------------------------------------------------

def compare(prev: dict, now: dict, bars: pd.DataFrame) -> dict:
    """The computed comparison between the previous read and now. `bars` = the closed candles AFTER the
    previous read's candle, up to and including the current one (high / low columns)."""
    from src.forward.rule import AMBIGUOUS, EXPIRED, _resolve_directional
    hl = list(zip(bars["high"].astype(float), bars["low"].astype(float)))
    out: dict = {"candles": len(hl), "from_time": prev["time"], "to_time": now["time"],
                 "price_then": prev["price"], "price_now": now["price"],
                 "high_since": max((h for h, _ in hl), default=None), "low_since": min((lo for _, lo in hl), default=None)}
    atr = prev.get("atr")
    out["move_atr"] = round((now["price"] - prev["price"]) / atr, 2) if atr else None
    if prev["read_kind"] == "directional":
        st = _resolve_directional(prev["direction"], prev["next_level"], prev["invalidation"], hl)
        out["status"] = {EXPIRED: "open", AMBIGUOUS: "both_touched"}.get(st, st)
    else:
        above = any(h > prev["range_high"] for h, _ in hl)
        below = any(lo < prev["range_low"] for _, lo in hl)
        out["status"] = "left_both_ways" if above and below else "left_above" if above else \
            "left_below" if below else "stayed_inside"
    changes = {}
    for k in ("bias", "tier", "read_kind", "trend", "regime", "rsi_zone", "macd_state", "stochastic_zone"):
        if prev.get(k) != now.get(k):
            changes[k] = [prev.get(k), now.get(k)]
    out["changes"] = changes
    pp, pn = prev.get("patterns") or {}, now.get("patterns") or {}
    out["patterns"] = {"new": {t: s for t, s in pn.items() if t not in pp},
                       "gone": {t: s for t, s in pp.items() if t not in pn},
                       "changed": {t: [pp[t], pn[t]] for t in pn if t in pp and pp[t] != pn[t]}}
    pc, nc = set(prev.get("cautions") or []), set(now.get("cautions") or [])
    out["cautions_on"], out["cautions_off"] = sorted(nc - pc), sorted(pc - nc)
    out["zones"] = {k: [prev.get(k), now.get(k)] for k in ("support", "resistance") if prev.get(k) != now.get(k)}
    return out


def _p(x) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.5g}"


_STATUS = {
    "followed_through": "price reached the previous read's next level {nl} FIRST — the read followed through",
    "invalidated": "price touched the previous read's invalidation {inv} FIRST — the read was invalidated",
    "both_touched": "price touched both {nl} and {inv} inside one candle — the order can't be known",
    "unscorable": "the previous read had no levels to check",
    "open": "price touched neither {nl} (next level) nor {inv} (invalidation) — the read is still open",
    "stayed_inside": "price stayed inside the previous range {lo}–{hi}",
    "left_above": "price left the previous range {lo}–{hi} above",
    "left_below": "price left the previous range {lo}–{hi} below",
    "left_both_ways": "price left the previous range {lo}–{hi} on both sides",
}
_WORD = {"bias": "bias", "tier": "situation tier", "read_kind": "read kind", "trend": "trend", "regime": "volatility regime",
         "rsi_zone": "RSI zone", "macd_state": "MACD", "stochastic_zone": "stochastic zone"}


def _thesis_lines(label: str, row: dict) -> list[str]:
    l1, th = row["thesis_l1"], row.get("thesis") or {}
    read = (f"{l1['direction']} ({l1['tier']}) at {_p(l1['price'])}: next level {_p(l1['next_level'])}, "
            f"invalidation {_p(l1['invalidation'])}" if l1["read_kind"] == "directional"
            else f"no directional read ({l1['tier']}) at {_p(l1['price'])}: range {_p(l1['range_low'])}–{_p(l1['range_high'])}")
    lines = [f"{label} — candle {l1['time']}: {read}."]
    lines += [f"  {f}: {th[f]}" for f in THESIS_FIELDS if th.get(f)]
    return lines


def memory_text(anchor: dict, parent: dict, cmp: dict) -> str:
    """The MEMORY block Claude gets on a continuation: its own thesis (first read + the latest), then the
    computed comparison. Every number here is also a known number for the integrity check."""
    lines = ["MEMORY — YOUR EARLIER READS OF THIS MARKET (the statuses below are COMPUTED by the app; "
             "explain them, never re-judge them)"]
    if anchor["id"] != parent["id"]:
        lines += _thesis_lines("First full read", anchor)
    lines += _thesis_lines("Previous read" if anchor["id"] != parent["id"] else "Previous read (your first full read)", parent)
    l1 = parent["thesis_l1"]
    lines.append(f"\nWHAT HAPPENED SINCE THE PREVIOUS READ ({cmp['candles']} closed candles, {cmp['from_time']} → {cmp['to_time']})")
    mv = f" ({cmp['move_atr']:+g} ATR)" if cmp.get("move_atr") is not None else ""
    lines.append(f"- Price: {_p(cmp['price_then'])} → {_p(cmp['price_now'])}{mv}; high since {_p(cmp['high_since'])}, "
                 f"low since {_p(cmp['low_since'])}.")
    lines.append("- Status: " + _STATUS[cmp["status"]].format(nl=_p(l1["next_level"]), inv=_p(l1["invalidation"]),
                                                              lo=_p(l1["range_low"]), hi=_p(l1["range_high"])) + ".")
    for k, (a, b) in cmp["changes"].items():
        lines.append(f"- {_WORD[k].capitalize()}: {a} → {b}.")
    if not cmp["changes"]:
        lines.append("- The read itself (bias, tier, trend, momentum zones) is unchanged.")
    pat = cmp["patterns"]
    for t, (a, b) in pat["changed"].items():
        lines.append(f"- Pattern {t}: {a} → {b}.")
    for t, s in pat["new"].items():
        lines.append(f"- New pattern: {t} ({s}).")
    for t, s in pat["gone"].items():
        lines.append(f"- No longer detected: {t} (was {s}).")
    labels = {**l1.get("caution_labels", {})}
    if cmp["cautions_on"]:
        lines.append("- Cautions now on: " + ", ".join(labels.get(c, c).lower() for c in cmp["cautions_on"]) + ".")
    if cmp["cautions_off"]:
        lines.append("- Cautions now off: " + ", ".join(labels.get(c, c).lower() for c in cmp["cautions_off"]) + ".")
    for k, (a, b) in cmp["zones"].items():
        z = lambda v: f"{_p(v['lower'])}–{_p(v['upper'])}" if v else "none"  # noqa: E731
        lines.append(f"- Nearest {k} zone: {z(a)} → {z(b)}.")
    return "\n".join(lines)


# --- the store -----------------------------------------------------------------------------------------

def _row(r) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("thesis_l1", "thesis", "comparison", "verification", "usage"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    d.pop("facts_json", None)
    return d


def latest(conn, symbol: str, timeframe: str) -> dict | None:
    return _row(conn.execute("SELECT * FROM analysis_reads WHERE symbol=? AND timeframe=? ORDER BY id DESC LIMIT 1",
                             (symbol, timeframe)).fetchone())


def get(conn, read_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM analysis_reads WHERE id=?", (read_id,)).fetchone())


def gap_limit(cfg: Config, timeframe: str) -> int:
    return cfg.advisor.memory_gap_bars.get(timeframe, cfg.advisor.memory_gap_default)


def plan(conn, cfg: Config, symbol: str, timeframe: str, bar_time: int, df: pd.DataFrame, *, fresh: bool = False) -> dict:
    """What this request does: {"kind": stored, "row"} | {"kind": continuation, "parent", "anchor", "bars"}
    | {"kind": first, "reason"}. `df` = the closed candles the facts were computed on."""
    fp = fingerprint(cfg)
    last = latest(conn, symbol, timeframe)
    if last and not fresh and last["bar_time"] == bar_time and last["fingerprint"] == fp:
        return {"kind": STORED, "row": last}
    if fresh:
        return {"kind": FIRST, "reason": "fresh"}
    if last is None:
        return {"kind": FIRST, "reason": "none_before"}
    if last["fingerprint"] != fp:
        return {"kind": FIRST, "reason": "engine_changed"}
    if not last.get("thesis"):
        return {"kind": FIRST, "reason": "no_thesis"}
    times = pd.Index([int(pd.Timestamp(t).timestamp()) for t in df.index])
    bars = df[times > last["bar_time"]]
    if last["bar_time"] > bar_time or len(bars) == 0 or len(bars) > gap_limit(cfg, timeframe):
        return {"kind": FIRST, "reason": "gap"}
    anchor = (get(conn, last["anchor_id"]) if last.get("anchor_id") else None) or last
    if (times > anchor["bar_time"]).sum() > gap_limit(cfg, timeframe):
        anchor = last                     # the first read is too old to carry: the chain moves on from the last read
    return {"kind": CONTINUATION, "parent": last, "anchor": anchor, "bars": bars}


def save(conn, cfg: Config, *, symbol: str, timeframe: str, facts: dict, facts_text: str, kind: str,
         reason: str | None, parent: dict | None, anchor: dict | None, thesis: dict | None,
         comparison: dict | None, explanation: str, verification: dict | None, model: str | None,
         usage: dict | None, now: float | None = None) -> int:
    l1 = thesis_l1(facts)
    anchor_id = (anchor or {}).get("id") if kind == CONTINUATION else None
    cur = conn.execute(
        "INSERT INTO analysis_reads (symbol, timeframe, bar_time, created_at, kind, reason, parent_id, anchor_id, "
        "fingerprint, facts_json, facts_text, thesis_l1, thesis, comparison, explanation, verification, model, usage) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (symbol, timeframe, l1["bar_time"], int(now or time.time()), kind, reason, (parent or {}).get("id"), anchor_id,
         fingerprint(cfg), json.dumps(facts, default=str), facts_text, json.dumps(l1),
         json.dumps(thesis) if thesis else None, json.dumps(comparison, default=str) if comparison else None,
         explanation, json.dumps(verification) if verification else None, model, json.dumps(usage) if usage else None))
    conn.commit()
    if kind == FIRST and thesis:                                 # a first read anchors its own chain
        conn.execute("UPDATE analysis_reads SET anchor_id=id WHERE id=?", (cur.lastrowid,))
        conn.commit()
    return cur.lastrowid
