# PROGRESS

A state file for the Tier-1 "learning instrument" build. Planning docs: `final-roadmap.md`
(strategy) + `tier1-build-spec.md` (implementation). See `CLAUDE.md` for conventions.

## Current state

**Built (Tier 1):** Feature 1 (pattern visualization + multi-panel research view + history
scrubber) and Feature 6 (market regime classifier). Both merged to `main`, 209 tests green,
ruff clean. A temporary regime strip overlay exists in the working tree (uncommitted) for
eyeballing the classifier. Regime is standalone infrastructure — it runs and caches but is not
surfaced in any vote/facts (the encyclopedia consumes it next).

**Next:** Feature 2 (pattern confirmation states) → Feature 3 (empirical pattern encyclopedia,
which segments by regime) → Feature 4 (prediction journal + calibration) → Feature 5 (blind
training) → Feature 7 (explanation integrity guard).

**Default config:** symbol `BTC/USDT`, timeframe `1h`, exchange `binance`, history 4320 bars.
Selectable timeframes: `15m, 30m, 1h, 4h, 1d`. Registered pairs: BTC/ETH/SOL/XRP (USDT) +
EUR/USD, GBP/USD (forex via Twelve Data).

---

## Log (newest first)

### Feature 6 — Market regime detection
- **Merged:** 2026-09-18 · **branch:** `feature/regime` (commit `dce3906`)
- **Done-when:** every bar labeled trending_up/down / ranging / volatile / quiet; stable, not
  flickering; look-ahead test passes. On real BTC data: daily 5.5% switch rate (~2.5-week
  regimes), weekly 4.3% (~23 weeks), all five labels present. Look-ahead guard proven to *bite*
  (fails when a whole-series percentile is injected). 8 new tests.
- **Decisions/deviations:** ADX + slow-MA slope + rolling ATR percentile; persistence hysteresis
  (a new regime must hold N bars). First use of SQLite (`data/wizard.db`, `regime_cache`).
  Standalone — wired into no vote/facts by design.
- **Learned:** trend must take priority over volatility, else trending-but-volatile markets
  mislabel. ATR percentile is *relative*, so a permanently-flat series reads `ranging`, not
  `quiet` — quiet needs contrast.

### Feature 1 — Pattern visualization + multi-panel research view
- **Merged:** 2026-09-18 · **branch:** `feature/pattern-viz` (commit `d7c0dc9`)
- **Done-when:** scrub to any past bar and see what the engine saw then, all panels drawn, guard
  test passes. Backend + guard test green (201 tests); `as_of_bar=N` proven equal to a
  truncated-frame run, future-mutation leaves bar N unchanged. Frontend built + type-checked
  clean; **browser-unverified** (no `npm run` this session).
- **Decisions/deviations:** endpoint is `/analysis` (spec said `/report`). Pattern `state` is a
  lightweight look-ahead-safe read; `quality` and per-boundary lines are deferred to Feature 2.
  Patterns stay out of the confidence score until measured.
- **Learned:** the look-ahead leak vector is `find_swings` (confirmed-interior filter), not
  `add_features` (causal); the guard must assert boundary activity *before* invariance or it
  passes vacuously.
