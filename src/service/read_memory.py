"""Simplification pass 2 — the explained read, with memory (see `src/advisor/memory.py`).

`explained_read(result, conn, cfg, spend=…)` takes a finished Layer-1 analysis (closed candles, no
explanation yet) and returns the explanation for it:

  same candle as the last read  -> the stored read (free, even when `spend` is False)
  `spend` False                 -> nothing, plus what a click would do (first read or continuation)
  otherwise                     -> ONE Claude call (first full read, or a continuation fed the earlier
                                   thesis + the computed comparison), the integrity check (one rewrite;
                                   then the facts-only summary), and the read is stored.

A facts-only fallback is stored too (the same candle stays free) but has no thesis, so the next new
candle starts a fresh full read. No key, or an API / network error -> nothing is stored.
"""

from __future__ import annotations

from src.advisor import memory as M
from src.config import Config

_NOTICE = ("Claude's explanation didn't pass the integrity check against the computed facts twice, so only the "
           "computed facts are shown.")


def _all_text(out: dict) -> str:
    return "\n".join(out[f] for f in ("explanation", "read", "why", "invalidation", "watch"))


def _add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


def payload(row: dict, *, stored: bool, parent: dict | None = None) -> dict:
    """The `memory` field of the API payload."""
    cmp = row.get("comparison") or {}
    return {
        "kind": M.STORED if stored else row["kind"], "read_kind": row["kind"], "reason": row.get("reason"),
        "read_id": row["id"], "bar_time": row["bar_time"], "created_at": row["created_at"],
        "candles_since": cmp.get("candles"), "status": cmp.get("status"), "from_time": cmp.get("from_time"),
        "usage": None if stored else row.get("usage"), "model": row.get("model"),
        "has_thesis": bool(row.get("thesis")),
    }


def explained_read(result, conn, cfg: Config, *, spend: bool, fresh: bool = False, client=None) -> dict:
    from src.advisor.explain import explain_read
    from src.advisor.integrity import check_explanation, facts_only_summary

    facts = result.facts
    symbol, timeframe = facts["market"]["symbol"], facts["market"]["timeframe"]
    p = M.plan(conn, cfg, symbol, timeframe, M.bar_time_of(facts), result.df, fresh=fresh)
    if p["kind"] == M.STORED:
        row = p["row"]
        return {"explanation": row["explanation"], "verification": row["verification"], "memory": payload(row, stored=True)}
    nxt = {"kind": "none", "next": p["kind"], "reason": p.get("reason"),
           "candles_since": len(p["bars"]) if p["kind"] == M.CONTINUATION else None}
    if not spend or (client is None and not cfg.anthropic_api_key):
        return {"explanation": None, "verification": None, "memory": nxt}

    mem_text, cmp, parent, anchor = None, None, None, None
    if p["kind"] == M.CONTINUATION:
        parent, anchor = p["parent"], p["anchor"]
        cmp = M.compare(parent["thesis_l1"], M.thesis_l1(facts), p["bars"])
        mem_text = M.memory_text(anchor, parent, cmp)
    situation = facts.get("situation")
    check = lambda o: check_explanation(_all_text(o), facts, style="teaching", known_text=mem_text or "",  # noqa: E731
                                        continuation=bool(mem_text))
    usage: dict = {}
    thesis, notice, retried, first_hard = None, None, False, []
    try:
        out = explain_read(result.facts_text, cfg, client, situation=situation, memory=mem_text)
        usage = _add(usage, out["usage"])
        res = check(out)
        if res.hard:
            retried, first_hard = True, res.hard
            try:
                out2 = explain_read(result.facts_text, cfg, client, situation=situation, memory=mem_text,
                                    revise=({f: out[f] for f in M.THESIS_FIELDS + ("explanation",)},
                                            [f"{v['check']}: {v['detail']}" for v in res.hard]))
                usage = _add(usage, out2["usage"])
                out, res = out2, check(out2)
            except RuntimeError:
                pass
        if res.hard:
            explanation, notice = facts_only_summary(facts), _NOTICE
        else:
            explanation, thesis = out["explanation"], {f: out[f] for f in M.THESIS_FIELDS}
        verification = {"ok": not res.hard, "issues": res.issues(), "hard": res.hard, "soft": res.soft,
                        "first_attempt_hard": first_hard, "retried": retried, "fallback": bool(notice), "notice": notice}
    except RuntimeError as exc:                     # cut off / malformed answer: the facts stand on their own
        explanation = facts_only_summary(facts)
        notice = f"Claude's answer couldn't be used ({exc}), so only the computed facts are shown."
        verification = {"ok": True, "issues": [], "hard": [], "soft": [], "first_attempt_hard": [], "retried": False,
                        "fallback": True, "notice": notice}
    except Exception as exc:                        # API / network error: nothing stored, try again later
        return {"explanation": None, "verification": None, "memory": {**nxt, "error": str(exc)[:200]}}

    read_id = M.save(conn, cfg, symbol=symbol, timeframe=timeframe, facts=facts, facts_text=result.facts_text,
                     kind=p["kind"], reason=p.get("reason"), parent=parent, anchor=anchor, thesis=thesis,
                     comparison=cmp, explanation=explanation, verification=verification, model=cfg.advisor.model,
                     usage=usage or None)
    row = M.get(conn, read_id)
    return {"explanation": explanation, "verification": verification, "memory": payload(row, stored=False)}
