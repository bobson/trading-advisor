# Paper-trading simulator — build spec

A practice/journaling layer on top of the advisor: log simulated Buy/Sell decisions, see them on
the chart, and track a position + PnL per pair. **Paper only** — no real orders, no exchange keys,
no prediction. It's the "did I act on my read, and how did it go" loop — complementary to the
roadmap's Feature 4 (prediction journal / calibration) but a **distinct feature** (execution & PnL
vs. forecast calibration). It gets **its own `trades` table**, reusing only the shared
`src/store/db.py`. If Feature 4 later reveals common "resolve an entry against price" logic,
extract it *then* (two real consumers), not speculatively now.

## Locked decisions (from review)

- **Amount = dollar notional.** You enter `$500`; units = `amount / entry_price`. Ties into the
  Feature-9 risk calculator's position sizing.
- **One position at a time (per symbol).** You are LONG, SHORT, or FLAT. From FLAT: Buy opens a
  long, Sell opens a short. While in a position: the opposite side CLOSES it and books realized
  PnL; the same side is rejected (400 "already in a position — close it first"). No stacking, no
  partial closes, no FIFO — clean and legible on the chart.
- **Explanation snapshot = whatever is on screen (free).** A trade saves the current verdict
  (bias / confidence / agreeing categories) always, plus Claude's write-up only if `explain` was
  ticked. **A trade never triggers a Claude call** — no credit spent to place a paper trade.
- **Storage = SQLite** at `data/wizard.db` via stdlib `sqlite3` (consistent with regime/journal).
- **Fill = the LIVE spot price**, fetched SERVER-SIDE at open AND at close (crypto via
  `ccxt fetch_ticker()["last"]`; forex falls back to the latest data price until a Twelve Data live
  quote is wired in). The fetch is **graceful** — on any failure it falls back to
  `market.last_close`, so a trade is never blocked. Each row records the fill price and its source
  (`entry_source` / `exit_source` = `live` | `last_close`). This is the one place the app touches a
  live (unclosed) price — everything else stays on closed bars.

## Data model — SQLite `trades` table (append-only)

```
trades(
  id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT,
  side TEXT,            -- "buy" | "sell"
  amount_usd REAL,     -- dollar notional entered
  price REAL,          -- entry = LIVE fill price at open
  entry_source TEXT,   -- "live" | "last_close" (was the ticker fetch fresh, or a fallback?)
  units REAL,          -- amount_usd / price (stored so PnL is trivial)
  opened_at INTEGER,   -- epoch seconds UTC
  status TEXT,         -- "open" | "closed"
  closed_at INTEGER,   -- epoch secs when the opposite side closed it (NULL while open)
  exit_price REAL,     -- LIVE fill price at close (NULL while open)
  exit_source TEXT,    -- "live" | "last_close"
  realized_pnl REAL,   -- signed $ (NULL while open)
  snapshot TEXT,       -- JSON: {bias, confidence, agreeing_categories, explanation?}
  note TEXT
)
```
Append-only in spirit: closing a position UPDATES its `status/closed_at/exit_price/realized_pnl`
rather than deleting anything. A `DELETE /trades/{id}` exists only to undo a mis-click.

## Backend — `src/trading/paper.py` + API

- `live_price(symbol, cfg) -> (price, source)` — current spot: crypto via `ccxt` `fetch_ticker`
  (reusing the exchange the data layer already uses); forex → latest data price (Twelve Data quote
  is a later upgrade). **Never raises** — on failure returns `(last_close, "last_close")`. A short
  in-memory TTL cache (a few seconds) stops the position badge from hammering the exchange.
- `open_or_close(symbol, timeframe, side, amount_usd, snapshot, *, conn, cfg)` — the one entry
  point: fetches the live fill via `live_price`; if FLAT, insert an open trade; if the side is
  opposite the open position, close it (`realized_pnl = units * (exit − entry)` signed by
  direction); same side → error.
- `list_trades(symbol, *, conn)` — chronological, for the log + chart markers.
- `position(symbol, *, conn, cfg)` — fetches a live price and returns `{side, amount_usd, entry,
  units, unrealized_pnl, unrealized_pct, price}` for the open trade, or `{flat: true}`.
- `pnl_summary(symbol)` — realized total, win rate, count (honest, sample-size-labelled).
- **API** (extends `src/api/app.py`, guarded like the others): `POST /trades`,
  `GET /trades?symbol=&timeframe=`, `GET /trades/position?symbol=`, `DELETE /trades/{id}`.
  The POST body carries `{symbol, timeframe, side, amount_usd, snapshot}` — **no price** (the
  server fetches the live fill). Still **no Claude call and no full re-analysis** — only the
  lightweight ticker fetch; the verdict/explanation snapshot comes from the client.

## Frontend (Svelte)

- **Trade panel** under the verdict (only in the Analysis view, when a result is loaded): an amount
  input (`$`), a **Buy** (green) and **Sell** (red) button, and the current **position badge**
  ("Open: LONG $500 @ 76,000 · unrealized +2.1%" / "Flat"). Buttons disabled while loading; the
  same-side button is disabled when a position is open.
- **Trades log** for the current pair: time, side, amount, entry, exit, realized PnL, and the
  verdict/explanation snippet from entry. Small realized-PnL + win-rate summary (with sample size).
- New typed client calls in `web/src/lib/api.ts`; trades reload after each Buy/Sell and on symbol
  change. Nothing is drawn for other symbols.

## Chart markers

- On analyze, fetch this pair's trades and draw a marker at the candle whose day/bar contains each
  trade's `opened_at`: **green ▲ below the bar for a buy, red ▼ above the bar for a sell**, text =
  `$amount @ price`. A close reuses the closing event's marker. Reuse the existing candlestick
  `setMarkers` path (merge with the swing/confluence markers already there, sorted by time).
- Trades happen "now" but candles are closed bars, so a marker sits on the **entry candle** (the
  day of the trade) — documented, not a bug. Multiple trades on one candle stack via marker offset.

## Build order (branch `feature/paper-trading`)

1. `trades` table (in `src/store/db.py`) + `src/trading/paper.py` (`live_price`, open/close/list/
   position/pnl). Unit tests inject a fake price into `open_or_close`/`position` so they stay
   offline & deterministic: open→position→close→realized-PnL math, one-at-a-time guard, long vs
   short signs, and the graceful `last_close` fallback. The real `ccxt` ticker path gets a single
   `@pytest.mark.network` test (skipped in CI, like the exchange tests).
2. API endpoints + `TestClient` tests (offline; `live_price` monkeypatched — no Claude, no network).
3. Frontend trade panel + position badge + trades log (typed client). Browser-verify with a mock
   backend (per the standing rule: any interaction/layout change is verified in a real browser).
4. Chart entry markers (green buy / red sell on the entry candle). Browser-verify on a real pair.

## Done when

You can enter a `$` amount and click Buy or Sell; it records the time, price, amount, and the
on-screen explanation; you see your open position + unrealized PnL and a trades log; and green/red
markers appear on the chart at your entry candles — only for the pair you're viewing.

## Honest framing (non-negotiable, same as the rest of the app)

Label it **"Paper trading — simulated, not advice."** Fills are live spot prices but there's no
slippage/fees/liquidity modelled, so PnL measures your discipline and read, not a live account.
No "you would have made $X" hype. (Feature 10's cost model could later net these fills, if wanted.)
