"""Paper-trading simulator — record simulated Buy/Sell decisions and track a position + PnL.

Paper ONLY: no real orders, no exchange keys with trade permissions, no prediction. One position
at a time per symbol (LONG / SHORT / FLAT): from FLAT a Buy opens a long and a Sell opens a short;
while in a position the OPPOSITE side closes it and books realized PnL, and the same side is
rejected. Fills use a LIVE spot price (crypto via ccxt), gracefully falling back to the last close
so a trade is never blocked. Amounts are dollar notional; `units = amount_usd / fill_price`.

PnL here measures your discipline and read, not a live account — no slippage/fees/liquidity are
modelled (Feature 10's cost model could net these fills later).
"""

from __future__ import annotations

import json
import time

from src.config import Config
from src.data.base import CRYPTO
from src.data.registry import asset_class_for

BUY = "buy"
SELL = "sell"
OPEN = "open"
CLOSED = "closed"

_TICKER_TTL = 5.0                      # seconds; avoids hammering the exchange on rapid polls
_TICKER_CACHE: dict[str, tuple[float, float]] = {}   # symbol -> (fetched_at, price)


def live_price(symbol: str, cfg: Config, *, last_close: float | None = None, fetch=None) -> tuple[float, str]:
    """Current spot price + source ("live" | "last_close"). Crypto uses ccxt `fetch_ticker`; any
    failure (or forex, for now) falls back to `last_close`. NEVER raises unless there is no price
    at all. `fetch(symbol)->price|None` is injectable for offline tests."""
    now = time.time()
    cached = _TICKER_CACHE.get(symbol)
    if cached and now - cached[0] < _TICKER_TTL:
        return cached[1], "live"

    price = None
    if fetch is not None:
        price = fetch(symbol)
    elif asset_class_for(symbol) == CRYPTO:
        try:
            import ccxt
            exchange = getattr(ccxt, cfg.market.exchange)()
            price = float(exchange.fetch_ticker(symbol)["last"])
        except Exception:
            price = None

    if price and price > 0:
        _TICKER_CACHE[symbol] = (now, float(price))
        return float(price), "live"
    if last_close and last_close > 0:
        return float(last_close), "last_close"
    raise ValueError(f"no price available for {symbol} (live fetch failed and no last_close given)")


def _open_trade(conn, symbol: str):
    return conn.execute(
        "SELECT * FROM trades WHERE symbol=? AND status=? ORDER BY opened_at DESC LIMIT 1",
        (symbol, OPEN),
    ).fetchone()


def _pnl(side: str, entry: float, exit_: float, units: float) -> float:
    """Realized/unrealized PnL in $: longs profit when price rises, shorts when it falls."""
    direction = 1.0 if side == BUY else -1.0
    return direction * units * (exit_ - entry)


def open_or_close(conn, symbol: str, timeframe: str | None, side: str, amount_usd: float, *,
                  price: float, source: str = "live", snapshot: dict | None = None,
                  note: str | None = None, now: int | None = None) -> dict:
    """Open a position (if FLAT) or close the open one (if `side` is opposite it). Same side while
    open raises ValueError. `price` is the already-fetched fill; use `record` to fetch it live."""
    if side not in (BUY, SELL):
        raise ValueError("side must be 'buy' or 'sell'")
    if amount_usd <= 0 or price <= 0:
        raise ValueError("amount_usd and price must be positive")
    now = int(now if now is not None else time.time())

    row = _open_trade(conn, symbol)
    if row is None:                              # FLAT -> open
        units = amount_usd / price
        cur = conn.execute(
            "INSERT INTO trades(symbol,timeframe,side,amount_usd,price,entry_source,units,opened_at,"
            "status,snapshot,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (symbol, timeframe, side, amount_usd, price, source, units, now, OPEN,
             json.dumps(snapshot or {}), note),
        )
        conn.commit()
        return {"action": "opened", "id": cur.lastrowid, "side": side, "price": price,
                "units": round(units, 8), "source": source}

    if row["side"] == side:
        raise ValueError(f"already in a {side} position for {symbol} — close it first")

    realized = _pnl(row["side"], row["price"], price, row["units"])
    conn.execute(
        "UPDATE trades SET status=?, closed_at=?, exit_price=?, exit_source=?, realized_pnl=? WHERE id=?",
        (CLOSED, now, price, source, realized, row["id"]),
    )
    conn.commit()
    return {"action": "closed", "id": row["id"], "side": row["side"], "entry": row["price"],
            "exit": price, "realized_pnl": round(realized, 2), "source": source}


def record(conn, symbol: str, timeframe: str | None, side: str, amount_usd: float, cfg: Config, *,
           last_close: float | None = None, snapshot: dict | None = None, note: str | None = None,
           fetch=None) -> dict:
    """The API entry point: fetch the live fill, then open/close. No re-analysis, no Claude call."""
    price, source = live_price(symbol, cfg, last_close=last_close, fetch=fetch)
    return open_or_close(conn, symbol, timeframe, side, amount_usd, price=price, source=source,
                         snapshot=snapshot, note=note)


def list_trades(conn, symbol: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM trades WHERE symbol=? ORDER BY opened_at, id", (symbol,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["snapshot"] = json.loads(d["snapshot"]) if d.get("snapshot") else {}
        out.append(d)
    return out


def position(conn, symbol: str, *, price: float) -> dict:
    """The open position + unrealized PnL at `price`, or {"flat": True}."""
    row = _open_trade(conn, symbol)
    if row is None:
        return {"flat": True}
    unrealized = _pnl(row["side"], row["price"], price, row["units"])
    direction = 1.0 if row["side"] == BUY else -1.0
    return {
        "flat": False, "id": row["id"], "side": row["side"], "amount_usd": row["amount_usd"],
        "entry": row["price"], "units": round(row["units"], 8), "price": round(float(price), 8),
        "unrealized_pnl": round(unrealized, 2),
        "unrealized_pct": round(direction * (price - row["price"]) / row["price"] * 100, 3),
    }


def pnl_summary(conn, symbol: str) -> dict:
    """Realized results over CLOSED trades — sample-size labelled, no hype."""
    pnls = [r["realized_pnl"] for r in conn.execute(
        "SELECT realized_pnl FROM trades WHERE symbol=? AND status=? AND realized_pnl IS NOT NULL",
        (symbol, CLOSED)).fetchall()]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    return {"closed": n, "wins": wins, "realized_total": round(sum(pnls), 2),
            "win_rate": round(wins / n, 3) if n else None}


def delete_trade(conn, trade_id: int) -> None:
    """Undo a mis-click."""
    conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    conn.commit()
