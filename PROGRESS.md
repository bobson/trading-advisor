# PROGRESS

A state file for the "learning instrument" build. Source of truth for what's next: `ROADMAP.md`
(steps A1…D6; prompts in `PROMPTS.md`). Older plans are in `docs/archive/`. See `CLAUDE.md` for conventions.

**ROADMAP progress:** A1 ✓ (merged, `645231c`), A2 ✓ (merged, `800e12a`; docs `1003735`), A3 ✓ (merged), A4 ✓ (merged), A5 ✓ (merged), A6 ✓ (merged), A7 ✓ (merged), B1 ✓ (merged — labelling mode
built; the ≥30 labelled charts are the user's ongoing work), B2 tooling ✓ (merged — `eval_detectors.py`;
its measurement + tuning run as soon as ≥30 charts are labelled — the user has decided NOT to label, so
it stays unmeasured). B3 ✓ (merged), B4 ✓ (merged), B5 ✓ (merged), A8 ✓ (merged — forward record live since 2026-09-25 on wizard.bosfoot.com), R1 ✓ (merged), R2 ✓ (merged), R3 ✓ (merged — no condition changed the coin flip; ~80% of reads have a stop inside noise and no room after costs), R4 ✓ (merged — noise floor ~1 ATR, stable; Phase R complete), C1 slim ✓ (merged), D1 ✓ (merged), D6 ✓ (merged), D2 ✓ (merged), D5 ✓ (merged), D3 ✓ (merged), calendar archive for D4 started (merged), simplification pass 1 ✓ (merged — menu, morning report in plain words, shorter Analysis), pass 2 ✓ (merged — read memory: same candle free, continuations, Start fresh), Fibonacci + trendline fixes ✓ (merged). Remaining on demand: D4 (event study — once months of events are archived); small idea: a measured "no prior trend to reverse" fact on reversal patterns.
Order from here: user's choice. Drawing tools: deferred.

## Current state

**Direction:** honest learning instrument, not a signal generator — the backtest and the ML harness
found no predictive edge. `ROADMAP.md` is the plan (Phase A hardening → B measure detectors →
C integrity → D learning loop); the old Tier-1 feature numbering lives on inside it.

**Built and on `main`:** the core engine + FastAPI + Svelte app (original Phases 0–26); the ML "is
there an edge?" harness (no edge); Features 1 (pattern viz + research view), 2 (pattern confirmation
states), 6 (market regime), 8 (exit-rule lab), 9 (risk of ruin), 10 (honest cost model); the
hardening pass (guide wired in, brief/teaching modes); paper trading; three-candle patterns; and
**ROADMAP A1** (verification pass: chart label/regime fixes, reclaimed-neckline → `failed`,
two-point trendlines). **ROADMAP A2** (verdict as a category count, neutral styling, no-edge
disclosure; `800e12a`). **ROADMAP A3** (situation tier decided in Layer 1) and **ROADMAP A4** (support/resistance as
ATR-scaled zones) and **ROADMAP A5** (facts payload hardening) and **ROADMAP A6** (analyst guide revision +
instrument price precision) and **ROADMAP A7** (honest baselines: luck band + zero-edge calculator
default) and **ROADMAP B1** (gold-set labelling mode — `gold_labels` table), plus the user-requested
**1–2 candle patterns at levels** chart markers, the **ROADMAP B2** evaluation instrument, the **pattern life cycle** (fresh / in play /
completed / expired), and **ROADMAP B3** (the Empirical Pattern Encyclopedia — `encyclopedia_stats` +
Encyclopedia view), plus **better pattern detection + the Pattern scanner + history beside every
find** (user request), **ROADMAP B4** (verdict records beside the verdict), and **ROADMAP B5** (quality as calibrated bands; guide §3 re-ranked by measurement), and **ROADMAP A8** (the morning report / forward record). **486 tests green,
ruff + svelte-check clean.**

**Standing facts:** patterns and 3-candle candlesticks stay OUT of the confidence score (facts
only); regime is standalone (not a vote); two-point trendlines are chart-only (not in facts); the
0–1 confluence `confidence` is internal — the UI shows "N of M categories agree", never a %. The
situation tier (`facts["situation"]`: no_setup / notable / confirmed, + mtf_synthesis for the
synthesis) is Layer 1's decision; it sets the explanation's format and word budget, and Claude may
not change it. Support/resistance are ZONES (bands with touches, strength, stale flag) built by one
shared `sr_zones()`; "at support" = inside the band or within 0.25×ATR of its edge. The facts
carry pre-computed distances (ATR + %, + above / − below) to every level, the nearest structural
level above/below, pattern ages, per-signal higher-timeframe votes (`mtf.facts_from`, incl. 1w —
information only), the strongest opposing fact, an unmeasured reliability field and an explicit
`absences` list; the prompt follows the guide's §3 order.

**Known open items:** channel detector over-calls (SOL 1d eye-check FAIL → B1/B2); phone-width
right-axis price-label pile-up; the disclosure panel's evidence numbers are hard-coded from past
runs (update by hand if re-run).

**Explanation layer:** driven by `src/advisor/analyst-guide-system-prompt.md` (loaded at startup,
cached prompt prefix). Default mode `brief` (enforces the guide's §8 word budgets); `teaching`
for long-form; toggle in the UI.

**Default config:** symbol `BTC/USDT`, timeframe `1h`, exchange `binance`, history 4320 bars.
Selectable timeframes: `15m, 30m, 1h, 4h, 1d`. Registered pairs: BTC/ETH/SOL/XRP (USDT) +
EUR/USD, GBP/USD (forex via Twelve Data). New in A1: `patterns.reclaim_atr_mult` (0.25),
`structure.trendline_break_atr_mult` (0.25), `structure.trendline_max_anchors` (6). New in A4:
`structure.sr_zone_atr_mult` (0.5), `sr_near_atr_mult` (0.25), `sr_stale_bars` (120),
`sr_strength_halflife_bars` (60). New in A5: `mtf.facts_from` ([4h, 1d, 1w]) — per-signal
higher-timeframe votes shown to Claude; the veto still uses `mtf.context_from` ([4h, 1d]). Defaults
apply if `config.yaml` omits them.

---

## Log (newest first)

### Fibonacci + trendline fixes (user found both on a live BTC 1h read)

- **Outdated Fibonacci leg:** a swing is confirmed only 5 bars later, so the latest confirmed leg can
  already be history. `fib_retracement(..., df=)` now marks a leg `superseded` when price has traded
  beyond either end of it since it ended (look-ahead-safe: only bars after the leg, up to the last row).
  An outdated leg casts no vote (neutral, everywhere the vote is computed — facts, `gather_signals`, the
  backtest), isn't a level (nearest levels, pattern structure confirmation, candle "@fib" labels), isn't
  drawn, and the facts text says "OUTDATED — do not cite". On the user's candle the structure category
  went bearish → neutral.
- **Trendlines are facts now** (they were only drawn — no vote since Phase 6, never in the facts): per
  side, price now, distance, anchors, swing touches (within 0.5 ATR), bars unbroken; in the nearest
  structural levels and the Key levels panel. Still NOT a vote (unmeasured).
- **New caution `trendline_against`** ("Trendline right against the read"): an unbroken trendline
  against the read within 1 ATR. A separate condition — `no_room` is untouched because it is built from
  the forward record's frozen rule-v1 levels. Unmeasured until R3 is re-run.
- Snapshot regenerated (approved): outdated fib flag + reason, a resistance trendline, the new caution
  entry, two absences; verdict unchanged. Historical tables (encyclopedia, verdict records, caution
  stats) were built with the old fib rule — rebuild when convenient.

### Simplification pass 2 — the explanation remembers (user request)

Every explained read is stored (`analysis_reads` in the app DB; `src/advisor/memory.py`,
`src/service/read_memory.py`). The memory is data: full facts, a Layer-1 thesis (bias, tier, the
forward record's levels via `levels_for`, zones, patterns, momentum zones, trend, cautions) and Claude's
four-field thesis (read / why / invalidation / watch), returned with the prose in ONE forced tool call.
- **Same candle → the stored read, free** — even with "explain" unticked. Scrubbing never reads or writes it.
- **New candles → a continuation:** Layer 1 computes what happened since (first touch of the old next
  level / invalidation, or did the range hold; bias, tier, trend, momentum zones, patterns, cautions,
  zones; move in ATR) and Claude gets its first and latest thesis + that comparison + the current facts.
  Claude explains the status, never decides it.
- **First full read** (teaching) per market + timeframe; again after **Start fresh**, an engine change,
  more than `advisor.memory_gap_bars` candles since (1h 24, 4h 42, 1d 21, 30m 48), or a facts-only
  fallback. The brief/teaching select is gone (config `explanation_style` stays for the CLI/synthesis).
- Integrity guard: memory numbers count as known; sentences about the earlier READ (previous read /
  thesis / call…) are skipped by the direction / absence / state checks — "the last candle…", "the last
  swing low…" are still judged; prices are checked everywhere; no "Opposing" badge on continuations.
- The first read is sent along only while it is within the gap limit; after that the chain moves on.
- Full reads render Claude's **bold** / *italic* labels (escaped HTML, nothing else rendered).
- Spend guards: one call per market+timeframe at a time (lock + re-check), the explanation is no longer
  in the 60 s cache, an API error stores nothing.
- Live reads are on CLOSED candles only (`advise(closed_only=True)`): crypto unchanged, forex/gold no
  longer show the forming candle on Analysis.
- Live check (scratch DB, Sonnet): first read 8.8k tokens in / 1.1k out; same candle free; continuation
  3 candles later 9.2k in (5.8k cached) / 291 out; a continuation carrying first + previous read
  9.4k in (5.8k cached) / 313 out. 23 new tests; snapshot untouched.

### Simplification pass 1 — a simpler app (user request: "this app is becoming a lot of complicated")

The user uses Analysis, Journal, Training and the Morning report ("to see if the analysis was right or
wrong, why it was wrong and how to improve"). Nothing was removed — the rest was folded away.
- **Menu:** Analysis · Journal · Training · Morning report, the rest under **More ▾** (shows the open
  page's name; every `#/` link still works).
- **Morning report** answers in plain words first: the record in one line (directional reads that
  followed through vs a coin flip on the same reads, "too early to tell" under 20); each judged read as a
  ✓/✗ card ("Up read at X: aiming for Y, wrong below Z → price reached Y first"), with **why it may have
  gone wrong** from the cautions frozen at the read (only conditions history backs or that are
  arithmetic count as reasons; "nothing was flagged — simply wrong" otherwise; "not recorded" for
  pre-R2 reads; flagged cautions on ✓ reads shown too, so a caution never reads as "= miss"); no-setup
  reads summed in one line (ranges are narrow, missed moves common); **what the misses have in common**
  (`misses_in_common`: per caution condition, X of the misses vs Y of the hits — misses = invalidated
  only; cautions only, no after-the-fact slicing; "too few to conclude" under 20 each side). Runs,
  synthesis, scoreboard, caution tables and the rule text sit under Details.
- **Analysis:** a ☀️ Morning record box on top for the market on screen (`GET /morning/market` —
  this morning's frozen read, whether the engine's read of the last CLOSED candle has changed since,
  the last judged read with ✓/✗ and why, the record here vs a coin flip; read-only, no Claude call;
  hidden with the engine's read, on past bars and in labelling). Order: box, my call, verdict, record,
  cautions, chart, explanation; the four info panels and paper trading under **More details**.
- Backend: `report.py` `summary`, `misses_in_common`, `market_box`; 4 new tests. Snapshot untouched.
- Browser-checked at 1400px and 400px on a scratch DB with judged reads (no horizontal scroll).

### D4 prep — archiving the economic calendar (user request "2a")
- **Done:** 2026-10-04 · on `main` · **merged.**
- The keyless calendar only shows THIS week, so D4 (event study) has no history unless it's kept.
  `src/context/event_archive.py`: an `events` table keyed (time, currency, title), with
  first/last-seen times and the latest consensus/previous. The 08:00 morning job saves the week's
  events every day (`calendar archive: N new event(s) of M this week` in its log); a repeat run adds
  nothing. A week the droplet is down entirely is a gap (it can't be backfilled from this feed).
- The Macro page shows "Archive for a future event study: N events (H high-impact) saved since …".
- Verified: a test (save once, refresh, no duplicates, stats); a live morning run into a scratch DB
  saved 79 events (Sunday: the new week), the second run 0 new; the Macro line checked in the
  browser. 605 tests pass. **D4 becomes worth building once a few months of events have accumulated.**

### ROADMAP D3 — News & macro context
- **Done:** 2026-10-02 · on `main` · **merged.**
- **Calendar** (`src/context/macro_calendar.py`): the **Forex Factory weekly JSON**, keyless and
  UNOFFICIAL. Events carry currency, UTC time (offsets converted), impact, consensus and previous;
  central-bank and commodity events are tagged by name from the same feed (39 and 2 this week).
  `disk_cache.py` (one cache shared by every process, TTL ~1 h, a stale copy with its age on failure)
  keeps it from being hammered.
- **Headlines** (`headlines.py`): RSS from CoinDesk, Cointelegraph, FXStreet and ForexLive, keyless
  (headline + link + source + time only, cached ~20 min), filtered per market by keyword. **Page only,
  never in Claude's facts** (titles carry directional wording).
- **Drivers** (`drivers.py`): a per-market table (event currencies, headline keywords, conventional
  drivers labelled as convention).
  - **Driver hypothesis:** the co-movement of daily returns with the dollar (inverse EUR/USD), gold and
    BTC over 60 days, joined on common dates (7-day vs 5-day markets). Self-proxies are excluded. It's
    only stated at |ρ| ≥ 0.5 with ≥ 30 days, worded "a co-movement, not a cause — and not a direction".
  - **Correlation warning:** the followed markets (= the morning watchlist) at ρ ≥ 0.7, "largely the
    same bet". Live: BTC/ETH 0.87, BTC/SOL 0.82, ETH/SOL 0.80. All thresholds were fixed before
    looking.
- **Wiring:** `gather_context` now carries the relevant upcoming high-impact events (with consensus
  and previous), `calendar_available`, and the drivers block (the hypothesis plus the warnings that
  involve the symbol). **"News soon" (`event_risk`) is now live without a Finnhub key**; it was always
  "unavailable" before. The facts text gained labelled driver and correlation lines; the guide §5
  gained one line ("a measured co-movement, never a cause or a direction"). There's a new **Macro**
  page (`#/macro`): drivers, the correlation matrix, a calendar with market / central bank /
  commodity / all tabs, and headlines. The Analysis page's Market context panel shows the next event,
  "moves with" and "one bet with". The menu now wraps on phones (it used to run off screen).
- **Spec vs code (rule 2):** Forex Factory replaces Finnhub (unofficial, cached, fails gracefully);
  **no actual figures** in the feed; it covers **this week only**, so next week's events aren't
  visible over the weekend (the page says so); central-bank and commodity calendars come from the
  same feed by name; headlines are on the page only.
- Verified: 17 offline tests (injected feeds and candles; a test that the offline path never touches
  the network). Browser-checked live (EUR/USD and ETH) at 1300 / 400 px. 604 tests pass; the snapshot
  was regenerated with the user's approval (a one-line diff: the `event_risk` detail no longer says
  "needs FINNHUB_API_KEY").
- **Forward record (user decision):** the 08:00 run fetches the cached calendar once and freezes each
  NEW read's "news soon" flag (`news_soon`: a high-impact event for the market's currencies within
  `caution.event_hours` of the run), so R2's caution split can test it over the coming months. The
  facts hash stays candles-only; older reads keep null; a failed feed leaves the flag null ("can't
  judge"). Verified live into a scratch DB (Saturday → all `false`) plus a test (true / false / none,
  hash unchanged).

### ROADMAP D5 — Behavioural circuit breaker
- **Done:** 2026-10-01 · on `main` · **merged.**
- `src/journal/rules.py`: `trading_rules` versions (append-only, enforced by triggers).
  - **Rules** (each optional): position size ≤ % of the account, max open positions, required regimes,
    min categories agreeing, allowed markets, max decisions per week, cooling-off hours after a loss.
  - **Checks:** every **paper-trade open** and every **live journal call** (blind training is practice
    and isn't checked) is checked against the rule version ACTIVE at its time. Violations are
    recorded, never blocked. A missing input is "can't check", never a violation.
  - **Not counted:** decisions made before any rules were declared (judging them by later rules
    would be hindsight).
- **The engine's read is frozen at every paper-trade open (server side)**, so the regime and
  categories rules have real inputs: `snapshot.engine` = bias, tier, agreeing, regime, patterns, facts
  hash, commit. It never fails a trade. The journal's engine snapshot gained `agreeing`.
- `GET /discipline` + `POST /rules`; the **Discipline** page (`#/discipline`):
  - the rules, plus "declare a new version";
  - followed vs broke per record type (count, judged, wins, a % only with 20+, paper P&L);
  - outcomes per broken rule;
  - neutral after-the-fact observations: post-loss decisions (within 6 h), positions > 1.5× your
    median size, off-regime decisions, weeks > 2× your median count;
  - an ISO-week review.
- **Spec vs code (rule 2):** "max risk per trade" became "max position size as a % of the account".
  Paper trades have no stop, so per-trade risk can't be computed. Rules are checked on both records,
  compared separately.
- Verified: 10 tests (every rule; the version active at the time; can't-check; counts; neutral
  wording; blind excluded). Live on a scratch API, an XRP buy of 3,000 after declaring rules was
  opened, and three violations were recorded (30% > 10%, regime ranging, market not on the list).
  The Discipline page was browser-checked at 1100 / 400 px. 586 tests pass.

### ROADMAP D2 — Pre-registration
- **Done:** 2026-10-01 · on `main` · **merged.**
- `src/research/prereg.py`: `experiments` + `experiment_results`, **append-only enforced by SQLite
  triggers** (any UPDATE/DELETE aborts: "register a new one that supersedes it"). Gated scripts:
  backtest, backtest_suite, ml_eval, funding_study, exit_lab, measure_caution, measure_exits (data
  builders aren't experiments; `--from-cases` re-aggregation isn't a new run). The flow:
  1. `--register --question --hypothesis --metric --direction --threshold [--baseline] --predict
     pass|fail [--predicted-value] [--supersedes N]` stores the run's EXACT parameters (hashed) and
     exits.
  2. `--experiment N` runs it, and is refused if the experiment is unregistered, belongs to another
     script, already has a result, or its params differ from the registration.
  3. The result is stored and scored.
- **Multiple comparisons:** variations are grouped by question. A rate metric (with n and a
  registered baseline) needs a one-sided binomial p < 0.05 / k (Bonferroni, k = variations run so
  far). Non-rate metrics (AUC, spreads, counts) show k, marked "not correctable".
- **Dashboard** (`/experiments`, the **Experiments** page): registered / run / never run,
  passed vs missed (every miss listed, misses marked red), "your predictions: X of N right", a
  per-question table (passed vs passed after correction), each experiment's hash, params and
  supersede chain.
- Verified end to end on a scratch DB: a BTC 1d backtest was registered, a run with a tweaked
  `--step` refused, the proper run recorded (0.463, n=160, p 0.848: miss, predicted right), a repeat
  refused, an edit blocked by the trigger; a second variation got alpha 0.025. 14 tests (all 7 scripts
  refuse to run unregistered via subprocess), browser-checked at 1100 / 400 px. Experiments live in
  the local `data/wizard.db` (research is run locally, not on the droplet).

### ROADMAP D6 — Blind training mode
- **Done:** 2026-09-30 · on `main` · **merged.**
- `src/research/training.py` + `scripts/build_training_setups.py`: the `training_setups` pool, built
  from THE encyclopedia walk (look-ahead-safe). Every pattern first seen forming that later broke out
  and whose outcome is known, keyed by the breakout candle's TIME (the cache shifts, indices don't
  survive). **Built: 1,566 setups** (7 markets × 1h/4h/1d; 12 types, 5 regimes; 179 duplicates
  skipped). The JSON is at `data/training_setups.json`; `--from-file` imports it on the droplet.
- API: `GET /training/options` (counts per filter); `GET /training/next` (a random UNANSWERED setup:
  where the chart ends plus the price; **the type, direction, regime and outcome are NOT sent before
  the call**); `POST /training/answer` (logs the call to the journal as `source='blind'` at that past
  candle with horizon = the timeframe's forward horizon (24/42/21 bars), judges it at once under
  journal rule v1, and reveals the pattern and its outcome, the engine's read AT that candle (bias,
  tier, cautions) and the encyclopedia record). Blind calls feed the Journal (its "where logged"
  breakdown separates them).
- UI: a **Training** page (`#/training`) with filters (pattern / regime / timeframe) and a
  10-setup session. The blind chart shows candles + MAs + volume/RSI/MACD, with the engine's drawings
  off. The reveal chart marks "your call", "judged here", your "wrong at" line, and the TESTED
  pattern's own breakout and target (not the engine's drawings at the window's end, which showed a
  different, later pattern during testing). It ends with the session's hits, average confidence and
  Brier vs 0.25.
- **Known leaks, by design / honour system:** the time axis shows real dates, and the regime strip
  is visible (it's never up/down; the regime filter reveals it anyway). Pattern records exist only
  for 1d (the encyclopedia was built for 1d), so 1h/4h reveals say "no history yet" until it's
  rebuilt for those timeframes.
- Verified: 4 tests (setups keyed by time; nothing leaks before the call; judged at once; one call
  per setup; answered setups aren't re-offered; a setup the cache no longer covers is skipped).
  562 pass. Browser-checked a blind round and the reveal on a scratch DB at 1300 and 400 px.
- **Droplet:** `scp data/training_setups.json` up, then `build_training_setups.py --from-file` (DEPLOY.md).

### ROADMAP D1 — Prediction journal + calibration
- **Done:** 2026-09-30 · on `main` · **merged.**
- `src/journal/{store,resolve,calibration}.py`, the `journal_entries` table, and `POST/GET/DELETE
  /journal` + `GET /journal/price`. The UI: a "📝 My call" form on the Analysis page and the Morning
  report, and a new **Journal** page (`#/journal`).
- **Logging:** the server fixes the bar (the latest CLOSED candle, fresh data) and its price; the form
  shows exactly which candle and price before you log. The engine's read at that bar is frozen with
  the call (bias, tier, current patterns, Feature-6 regime, facts hash, commit). What was ON SCREEN
  (verdict, explanation) is stored, so calls split into **blind vs anchored**. An option hides the
  engine's read (verdict, record, cautions, categories, explanation, chart marker) until you log or
  reveal; on the Morning report it works per market, on the latest morning only.
- **Journal rule v1 (fixed, versioned):** the window is the closed bars after the logging bar up to
  the horizon (weeks / days / bars; 2 weeks default). **Invalidated** if the invalidation is touched
  anywhere in it; otherwise **correct** if the last close is on the called side, **incorrect** if not
  (an equal close = incorrect). A call resolves only once the data covers its window (a forex
  Saturday end waits for Monday), idempotently. Resolution happens on the Journal page and in the
  08:00 job, fetching only markets with a due call.
- **Calibration:** Brier (beside 0.25 = always saying 50%), a 10-point confidence curve (a dot and a
  rate only with 20+ calls in a band, counts otherwise), overconfidence (mean confidence − share
  right), and breakdowns by blind/anchored, timeframe, page, engine regime and pattern. No streaks,
  no praise.
- **Spec vs code (rule 2):** up/down calls only (no neutral: it needs a range, not one price);
  confidence 50–100 meaning "P(judged correct under the rule)"; live candles only (practice on past
  bars is D6); **no hedging** (one live call per market/timeframe/candle across pages — found in
  browser testing, where analysis-up + morning-down on the same candle were both accepted); deletion
  only within 5 minutes and never after resolution; an invalidation > 50% from the price is refused
  as a typo (found in testing: an invalidation of 0 had been accepted).
- The API reads an optional `TRADES_DB` env (like `MORNING_DB`) so a scratch server never writes test
  calls into the real journal. Verified: 19 tests, 558 pass. Browser-checked on a scratch DB (hide →
  log → reveal, morning per-market log, the Journal page with 140 synthetic judged calls so the curve
  has dots) at 1100/1300 and 400 px.
- **User's check:** log your first real calls with the engine's read hidden. It pays off over months,
  not days.

### ROADMAP C1 (slim) — The integrity guard
- **Done:** 2026-09-30 · on `main` · **merged.**
- `src/advisor/integrity.py`: every explanation is checked against the facts it was given, AFTER it
  is written. `advise._guard` gives a hard failure ONE rewrite (`explain.revise`: facts + the draft +
  the violation list); if it fails again, the deterministic `facts_only_summary` (tier, category
  count, record, zones, Opposing, cautions) is shown with a notice. Soft issues are a badge. The
  payload keeps `ok`/`issues` and adds `hard`/`soft`/`retried`/`fallback`/`notice`/`first_attempt_hard`.
  - **Hard:** invented price (price-band numbers matched to the facts **at the precision written**,
    ≥ 3 significant digits, dates stripped, ×/%/ATR/bars skipped); affirming a NOT PRESENT item
    (divergence, a confirmed or failed pattern); a forming or failed pattern called confirmed (not in
    conditional or negated sentences); a directional claim phrase opposing the Layer-1 bias (bare
    "bullish"/"bearish" never count).
  - **Soft:** directional phrase with no directional read; missing `Opposing:` line; over 1.2× the
    word budget (brief only, the Opposing line not counted); a pattern name not in the facts; a
    completed or expired pattern described as current.
- **Spec vs code (rule 2):** slim by agreement. The prose stays prose: no structured claims
  {text, fact_id, role, direction}, so role-fit ("a neckline can't be support") and number-meaning
  pairing are not checked. **Seen live:** Claude wrote "upper edge 1.14110 (+0.94 ATR)" when the
  facts said the lower edge 1.14011 is at +0.94 ATR. Both numbers exist, so no number check can catch
  it; only structured claims could. Also not checked: the multi-timeframe synthesis (morning report
  / CLI).
- **Real explanations pass:** 6 live Claude explanations (BTC 1h, SOL 4h, EUR/USD 1h × brief and
  teaching), report-only first. The first pass had one false alarm ("0.7" read as a price on
  EUR/USD), fixed by the significant-digit and unit rules. All 6 then pass and are saved as
  `tests/fixtures/real_explanations.json` (a regression test). The tests also caught a real hole:
  a price at the end of a sentence ("…at 91,234.56.") wasn't parsed.
- **Guide (rule 5):** §11 now says what the app checks mechanically and keeps only the unenforced
  self-checks. The rounding rule's "1% tolerance" became "checked at the precision you write it".
  The live path no longer uses `verify.py`, which is marked superseded.
- UI: "✓ Checked against the computed facts" (plus "rewritten once to fix: …"), a "⚠ N notes"
  dropdown, and an amber fallback notice. Browser-checked live (SOL 4h) and the fallback via an
  intercepted response. 12 new tests, 539 pass.
- **User's check (PROMPTS.md):** run ten analyses with "explain" across symbols and modes and count
  first-time pass / retried / fallback; that measures how often Claude drifts from the facts.

### ROADMAP R4 — Exits: how far against, how far for (Phase R complete)
- **Done:** 2026-09-28 · on `main` · **merged.**
- `src/risk/excursions.py` + `scripts/measure_exits.py`: the same walk and 70/30 split as R3.
  `caution_stats.collect` now also records MFE, where the read ended, the regime and the tier.
  **Definitions fixed before the run** (module docstring):
  - **noise floor** = median MAE of the reads that ended in profit;
  - **typical run** = median MFE of all reads;
  - **stop touch** at 0.5–3 ATR (all reads / eventual winners);
  - **stable** = held-back within 25% of the older part;
  - the 8 Feature-8 exits simulated on the held-back reads, net of costs, with the average bars held.
- **Results** (held-back 30%, 7 markets, step 4):

  | TF | reads (winners) | noise floor | typical run | winners whose MAE reached 1 ATR / 2 ATR | stable |
  |---|---|---|---|---|---|
  | 1h | 1025 (515) | 0.97 ATR (older 1.13) | 2.17 ATR (older 2.10) | 49% / 19% | yes |
  | 4h | 1156 (574) | 1.34 ATR (older 1.39) | 2.87 ATR (older 2.85) | 62% / 29% | yes |
  | 1d | 1042 (549) | 0.93 ATR (older 0.91) | 1.94 ATR (older 1.77) | 47% / 14% | yes |

  **The robust finding:** about half of the trades that ended in profit first went ~1 ATR against
  (1.3 on 4h). A stop at 1 ATR would have closed about half of the eventual winners; at 2 ATR, 1 in
  5–7. It is stable across both periods on every timeframe. With R3 (8 in 10 engine reads have an
  invalidation < 1 ATR), **most of the engine's own stops sit inside the noise floor.**
- **Exits on the held-back reads (net, per trade):** no rule is consistently better. On 1h every
  rule is mildly positive, on 4h every rule is negative, on 1d they're mixed, so the sign follows each
  period's market drift, not the exit. `fixed_target` (target, no stop by design) wins about 75% of
  the time yet loses money: rare, very large losers (held ~80 bars). Reported as history, never as a
  recommended exit.
- **Where it shows:**
  - the Caution panel: "Exits on 1h, from history: half of the 515 past reads that ended in profit
    first went 0.97 ATR against… about 369.6 against and 826.9 in favour at today's ATR";
  - `facts["exits"]` + an EXITS line in the facts text (live path only; the snapshot is unchanged);
  - the **risk calculator**: `/risk/noise_floor` warns "⚠ Stop inside normal noise… About 7 in 10 of
    them went further against than your stop", shows where a noise-floor stop would sit and how much
    the position shrinks for the same dollar risk; it asks for a real entry price if the entry isn't
    within 20% of the market.
- Verified: 9 new tests (the decile estimate never overstates: "fewer than 1 in 10" / "more than
  9 in 10"), 527 tests pass. Browser-checked the panel and the calculator on BTC 1h at 1400 and
  400 px. **Droplet:** copy `data/exit_cases.json` + `data/exit_returns.json` up and run
  `--from-cases` (DEPLOY.md).
- **Phase R summary:** no caution condition predicts which trades lose (R3), but two things hold up.
  The engine's stops are mostly inside normal noise (R3), and the noise floor is ~1 ATR, stable over
  time (R4). The app now says both, with counts, wherever a trader decides.

### ROADMAP R3 — Caution conditions measured on history (the honest test)
- **Done:** 2026-09-27 · on `main` · **merged.**
- `src/risk/caution_stats.py` + `scripts/measure_caution.py`: THE walk. Every directional read records
  its caution flags and the outcome over the timeframe's horizon: a ±1 ATR bracket (level-independent),
  the rule-v1 outcome, adverse excursion and realised range. The split is per market, 70/30 by time,
  purged at the boundary. **No thresholds were tuned** (the a-priori `caution:` values).
- **Decision rules were fixed in the docstring before any result**, by kind:
  - directional (`no_expansion`, `stretched`, `htf_against`, `thin_market` on forex/gold): `helps`
    needs a held-back loss-rate lift ≥ 5 points with n ≥ 20 on both sides, the same sign in the tune
    part, and most markets (≥ 2) agreeing, each with at least half the effect;
  - `stop_in_noise` and `no_room` = `by_construction`;
  - `volatility_extreme` = `sizing`;
  - `event_risk` = `forward_only`.
  - The honesty test caught a flaw first: a one-market effect passed because noise-sized positives
    counted as agreement. The half-effect clause was added before any real result was aggregated.
    Across 20 seeds: planted effect found 20/20, random flags 0/20, one-market effect 1/20.
- **Results** (9,781 directional reads · 7 markets × 1h/4h/1d · held-back 30%, step 4):

  | Condition | Flagged lost the ±1 ATR bracket | Unflagged | Status |
  |---|---|---|---|
  | Breakout without expansion | 30/61 (49%) | 1510/3029 (50%) | no_effect (0 markets eligible) |
  | Stretched from the average | 310/681 (46%) | 1230/2409 (51%) | no_effect (flagged lost *less*) |
  | Higher timeframe against | 171/333 (51%) | 1369/2757 (50%) | no_effect (3 of 6 markets) |
  | Thin market (forex/gold) | 52/103 (50%) | 529/1049 (50%) | no_effect |
  | Volatility extreme | next moves median 5.17 ATR (n=1021) | 5.32 ATR (n=2189) | sizing: ATR already adapts |
  | Invalidation inside noise | invalidated first 981/2299 (43%) | 161/624 (26%) | by_construction |
  | No room after costs | invalidated first 751/2339 (32%) | 391/584 (67%) | by_construction |
  | News soon | no historical calendar | | forward_only |

  **No condition changed the coin flip.** The encyclopedia hint (breakouts without expansion fail
  more) didn't carry over to directional reads, where the flag is rare. **The real finding is about
  the engine's own levels:** about 8 in 10 directional reads have an invalidation closer than 1 ATR
  AND a next level that doesn't beat it after costs. Most reads aren't tradeable as structured. The
  panel now says so on every such read.
- **Display:** active conditions are cautions only if `helps`, `by_construction` or `sizing` (each
  with its tag and a one-line record from history); `no_effect` / `insufficient` / `forward_only` ones
  become "information only". Statuses are injected in `advise` / the API (never in `build_facts`, so
  the snapshot is unchanged), and the morning report's caution split shows "history: …" per condition.
- **Spec vs code (rule 2):** the spec keeps only proven (`helps`) conditions as cautions. `stop_in_noise`
  and `no_room` can't be tested fairly (they're built from the read's own levels), so they stay
  visible, labelled "arithmetic warning (not a finding)". `volatility_extreme` stays as a sizing fact.
- **Bug fixed on the way (Feature 10 cost model):** the crypto taker fee (5 bps/side) was charged on
  forex and gold, ~11 pips per EUR/USD round trip, 1.5 ATR on 1h. Forex now pays spread plus a
  `forex_commission_pips` (0.6, round trip); gold pays a `metal_spread_usd` (0.30 $/oz) plus an
  optional commission. This also lowers forex costs in every backtest and exit-lab report. The
  forex/gold part of R3 was re-run after the fix and the verdicts didn't change. Forex "no room" is
  still flagged on 87% of reads, so it's geometry, not costs.
- Verified: 11 new R3 tests + 2 cost regressions, 518 tests pass. Browser-checked the panel (XRP 1d:
  sizing + two arithmetic warnings with their records) and the report. **Droplet:** copy
  `data/caution_cases.json` up and run `--from-cases` there (DEPLOY.md); never copy the whole DB.

### ROADMAP R2 — Caution flags frozen into the forward record
- **Done:** 2026-09-26 · on `main` · **merged.**
- Every new `forward_reads` row stores `caution` = JSON {code: true/false/null} from the same facts
  the read came from. The column is added automatically to existing DBs (the droplet's), and reads
  from before R2 stay NULL ("not recorded"). Outcome rule v1 is unchanged, as are the facts hash and
  idempotency.
- The report gains a **Caution split** (`report.caution_split`): per rule version × read kind ×
  condition, the judged reads it flagged vs the ones it didn't, pooled across timeframes. It shows
  outcome counts beside the coin flip on the same reads, a rate only with 20+ on a side, a "can't
  judge" count, and how many judged reads predate R2. The grid shows "⚠ N cautions" per read (hover
  lists them); the review lists each judged read's flags.
- Verified: 4 new tests (flags stored for all 8 codes; a pre-R2 table is migrated and its reads count
  as not recorded; the split math incl. the coin flip and can't-judge; report wiring). 505 tests
  pass. Browser-checked on a demo DB (6 mornings of fixture candles) at 1400 and 400 px.
- **The forward test of Phase R starts with the first morning after this deploy.** The first 30m/1h
  splits arrive the next day, 4h after ~a week, 1d after ~a month; rates need 20+ reads per side.

### ROADMAP R1 — Caution conditions as Layer 1 facts
- **Done:** 2026-09-26 · branch `feature/caution-conditions` · **merged to `main`.**
- `src/risk/caution.py` is the eighth part of `build_facts`: `facts["caution"]` = eight conditions, each
  {code, label, active, detail, value, status="unmeasured"}. `active` None = can't be judged here, and
  the detail says why. No vote, no confluence or tier change (the snapshot diff adds only the
  `caution` key).
  - `no_expansion`: fresh breakout with neither volume ≥1.2× nor ATR rising on the breakout bar.
  - `stretched`: ≥3 ATR from the 50-MA.
  - `volatility_extreme`: ATR in the top or bottom decile of its last 100 bars.
  - `stop_in_noise`: the read's invalidation <1 ATR away.
  - `no_room`: after the cost model, the next level is closer than the invalidation.
  - `htf_against`: the highest directional higher-timeframe trend vote, the weekly included (from
    `mtf_signals`).
  - `event_risk`: a high-impact event within 6 h, judged only in the live path once the calendar is
    injected; "unavailable" without `FINNHUB_API_KEY`, never guessed.
  - `thin_market`: forex or gold after a weekend gap, or intraday in the Sydney hours.
- The read's direction and levels are the forward record's (`read_direction`, `forward.rule.levels_for`),
  so R2 can freeze exactly these values. The thresholds are a-priori config (`caution:`); R3 may tune
  them only on the older 70%.
- Facts text: a "CAUTION CONDITIONS" block (framed as risk, not direction; "unmeasured") before the
  verdict. No analyst-guide change was needed (rule 5). UI: a Caution panel under the verdict record
  (active ones in amber, then not present / can't judge).
- Verified: 13 new tests, including one per condition (fires / doesn't) and a look-ahead guard on real
  candles that saw ≥3 conditions active. 500 other tests pass. Browser-checked on XRP 1d (3 active)
  and EUR/USD 1h (thin market) at 1400 and 400 px.

### Roadmap: Phase R added (user direction, 2026-09-26)
- The user's goal, stated plainly: direction is a coin flip; the value is knowing **when not to enter
  and when to exit**. ROADMAP §2 gained that principle and §6 a new **Phase R — Risk filters**:
  R1 caution conditions as Layer 1 facts → R2 freeze them into the forward record (early, since forward
  data takes months) → R3 measure each on a fixed 70/30 time split (keep only conditions that hold in
  the held-back part and in most markets) → R4 exits (MAE/MFE noise floor, typical run). Prompts are in
  PROMPTS.md. Placed before C1 in the remaining order, which is still to be confirmed with the user.
- Honest framing kept: risk size and costs are measurable, direction isn't. A filter is never
  presented as an edge; one that only cuts trading is reported as a cost saving.

### Deployment step 1 — automatic deploys from GitHub (user request)
- **Done:** 2026-09-26 · **merged to `main`.**
- `.github/workflows/deploy.yml`: after CI passes on a push to `main` (or the manual button), it builds
  the frontend on GitHub and SSHes to the droplet. There it runs `deploy/deploy.sh <commit>`, which
  waits for a running morning report (same lock file), resets to exactly that commit, installs deps,
  restarts the API and checks `/health`. Then it rsyncs `web/dist`.
- `vite.config.ts` reads `VITE_BASE`, so the page can live under a sub-path if ever needed.
- **Adapted to the real droplet (user, 2026-09-26):** runs as the existing `bobson` user next to
  bosfoot, behind the existing **Caddy** on **wizard.bosfoot.com** (page at `/`, API at `/api` →
  127.0.0.1:8010), with Caddy `basic_auth` as the lock (the page doesn't send `X-API-Key`). DEPLOY.md
  was rewritten in that order (DNS → code → API service → Caddy → auto-deploy → morning timer).
  `deploy/trading-wizard.service` was added; both units use `User=bobson`.
- Verified locally: the workflow YAML parses, the build works with `VITE_BASE`/`VITE_API_BASE`, and a
  dry run of `deploy.sh` (throwaway clone, stubbed sudo/systemctl/curl) reset to the commit and
  passed the health check. It waited 3 s while the morning lock was held. The real GitHub → droplet
  run is untested until the secrets exist (DEPLOY.md "Automatic deploys", steps A1–C2).

### ROADMAP A8 — Morning report: the forward record
- **Done:** 2026-09-25 · branch `feature/morning-report` · **merged to `main`.**
- **FORWARD RECORD DAY ONE: 2026-09-25** (Europe/Skopje date). This was the first run on the droplet
  (wizard.bosfoot.com): status ok, 20 reads (BTC, ETH, SOL, EUR/USD, gold × 30m/1h/4h/1d), engine
  `803421985009`. The 08:00 timer is enabled (next firing 2026-09-26 06:00 UTC = 08:00 CEST). A
  second same-day run added nothing ("already read today"), as designed. Check back ~2026-10-02 for
  the first 4h reviews and ~2026-10-24 for the first 1d reviews.
- **Run notes fix (2026-09-26):** a second same-day run used to overwrite the day's trigger and skip
  notes (day one's row reads `schedule` / "already read today" for that reason). Now the first run's
  trigger and start time are kept, and every run is appended to a new `attempt_log` column (added
  automatically to existing DBs). The page shows "Runs this morning: …". The reads were never
  affected.
- **What it does:** every day at 08:00 Europe/Skopje (`deploy/trading-wizard-morning.timer`, a
  systemd timer on the droplet) `scripts/morning_report.py` does three things. (1) Review: judges
  every past read whose horizon has passed. (2) Read: freezes a read for each watchlist market ×
  30m/1h/4h/1d, from closed candles only. (3) Synthesis: optional, one Claude call per symbol, off by
  default. Tables: `forward_reads`, `forward_runs`, `forward_syntheses`, `forward_rules` in
  `data/wizard.db`. Page: `#/morning` (review, today's grid, synthesis, scoreboard beside a coin
  flip). Manual trigger: the same script, or **Run now** (`POST /morning/run`).
- **Guarantees:**
  - Duplicate protection is in the schema, not in Python: UNIQUE(run_date, symbol, timeframe) and
    UNIQUE(symbol, timeframe, bar_time), plus a file lock.
  - Missed mornings are recorded as `gap` rows and never backfilled (the timer has
    `Persistent=false`).
  - Forex, gold and oil skip a day when there's no new closed candle.
  - The read function receives only candles and config, so the review can't feed the read.
  - Each read stores the engine commit, a dirty flag and a config hash.
- **Outcome rule v1** (`src/forward/rule.py`, text hash pinned by a test):
  - Directional reads (tier ≠ no_setup and a bullish/bearish bias): judged by first touch on
    highs/lows.
  - No-setup reads: correct if price stayed inside the zones.
  - Horizons in bars: 30m 48 · 1h 24 · 4h 42 · 1d 21.
- **Data:** gold comes from Twelve Data (verified live on the free plan). Oil comes from OANDA's
  practice API, `WTICO_USD`, because Twelve Data's free plan refuses WTI. OANDA is not verified live
  until `OANDA_API_TOKEN` is added; without it oil is skipped and the skip is recorded. Gold and oil
  are in `COMMODITIES`, not `PAIRS`, so the encyclopedia, verdict records and scanner are unchanged.
- **Oil skipped (user decision, 2026-09-26):** OANDA redirects new sign-ups to FTMO (no API), and
  Twelve Data's free plan refuses WTI, so WTI/USD is out of the watchlist. The OANDA provider stays
  in the code, unused. Oil's record starts on the day a source is added.
- **Spec vs code:** "next level / nearest level above-below" = the S/R ZONES (near edge ahead, far
  edge behind; close ± 3 ATR when there's no zone). `nearest_levels` includes round numbers, which
  sit a fraction of an ATR away and would decide almost every read on its first bar.
- **Verified:**
  - A live manual run into a scratch DB gave 20 reads in 2 minutes (oil skipped: no token).
  - Page checked in the browser at 1400px and 400px, with live reads and with a demo DB of judged
    reads, a gap and the scoreboard.
  - `systemd-analyze calendar` gives 06:00 UTC before 25 Oct and 07:00 UTC after.
  - The first real firing at 08:00 can only be confirmed on the droplet.
- **User's check:** set up the timer (DEPLOY.md), run it once by hand and read the report. Look again
  after a week (first 4h reviews) and after a month (first 1d reviews).

### ROADMAP B5 — Calibrate quality + re-rank the guide
- **Done:** 2026-09-25 · **merged to `main`.**
- **Quality bands.** Each instance's raw geometry score is stored in the encyclopedia. For each
  pattern type and timeframe, the bottom/middle/top third of its past scores (pooled across markets)
  becomes a low/medium/high band. Each band gets its own `quality=<band>` rows (all patterns seen
  forming, so the breakout rate is measured too), and the cut points are stored as `quality_cuts`.
  If a third or more of the scores are tied at the floor (e.g. the clamped 0 on triangles), the whole
  tie counts as low.
- **Where it shows.** Layer 1 (`scanner.quality_meaning`) decides whether a higher score meant fewer
  failures: high band vs low band, each needing 20+ cases, otherwise "too few cases to tell". The band
  and its counts appear on the chart pattern lines, in the Scanner, and in a new table on the
  Encyclopedia page. The prompt shows the band with its counts and never the raw 0.62; without an
  encyclopedia it says "not calibrated". The band is injected in `advise`/API like the B4 records, so
  it's kept out of `build_facts` and the snapshot is unchanged.
- **What the bands found (1d, all markets):** a higher score meant fewer failures for only 1 of 12 types:
  sideways channel (54% vs 65%). For double bottoms (59% vs 44%), double tops (64% vs 64%) and
  symmetric triangles (69% vs 64%), a higher score did NOT mean fewer failures. The other 8 types
  have too few cases per band to tell. So on its own the raw score says almost nothing, which is
  why it now shows as a band with its counts. The rebuild left all 3,636 existing encyclopedia rows
  byte-identical (only the band rows were added).
- **Spec vs code:** B2 detector precision does not exist yet (0 gold labels; the user chose not to
  label), so the re-rank uses only the encyclopedia. Trend, structure and context can't be measured
  from it and keep their places.

**§3 re-rank — justification** (crypto markets only, because forex volume is always 0 and would
fall into "not supported"; 1d, every judged pattern breakout; a category "supported" = it backed the
breakout at the breakout candle; overlapping cases, so not independent):

| § 3 item | Old → new | Evidence | Reached target (supported vs not) | Failed (supported vs not) | Consistent across pattern types? |
|---|---|---|---|---|---|
| Trend & regime | 1 → 1 | unmeasured (B2 has no labels); regime barely changed outcomes (failed 61–68% in every regime) | — | — | — |
| Structure | 2 → 2 | unmeasured (B2 has no labels) | — | — | — |
| Patterns | 3 → 3 | now weighted by each pattern's own record + quality band | — | — | — |
| **Volatility** | 5 → **4** | clearest effect | 39% (49/125) vs 20% (17/85) | 50% (75/150) vs 70% (90/128) | yes: fewer failures in 4 of 5 types with 5+ cases per side |
| **Volume** | 6 → **5** | helped pooled, mixed within types | 37% (51/138) vs 21% (15/72) | 55% (95/174) vs 67% (70/104) | mixed: fewer failures in 2 types, more in 2, same in 1 |
| **Momentum** | 4 → **6** | uninformative at breakouts: it backed 263 of 278, so almost never absent | 32% (66/206) vs 0 of 4 | 58% (153/263) vs 12 of 15 (too few) | can't tell |
| Candlestick (inside Patterns) | stays | no consistent effect | 35% (15/43) vs 31% (51/167) | 62% vs 59% | no: fewer failures in 2 types, more in 3 |
| Context | 7 → 7 | unmeasured | — | — | — |

The facts text follows the same order (sections 4 volatility, 5 volume, 6 momentum). A test reads
the guide's §3 list and checks that the facts sections match it.

### Chart labels — plain text, no coloured axis tags (user request)
- **Done:** 2026-09-25 · frontend only (`web/src/lib/PriceChart.svelte`) · **merged to `main`.**
- Coloured tags on the right price axis are removed. The one exception is the current-price tag.
- Moving averages have no label.
- Levels are labelled inside the chart as plain coloured text: S1(3) / R2(5) for rank and touches,
  Fib 62, TL, and "DBot target (35/80)" with the measured target record.
- The labels come from a `TextLabels` primitive. Crowded labels are spread evenly around their
  lines, and a thin outline in the chart's own colour keeps text readable over dotted lines
  (no box behind the text).
- Checked in the browser on BTC and XRP 1d at 1400px and 400px widths: no overlaps.
  svelte-check shows 0 errors.

### ROADMAP B4 — Data adjacency: measured records beside every directional read
- **Done:** 2026-09-24 · **branch:** `feature/data-adjacency` · **merged to `main`.**
- **Done-when → PASS:** every directional verdict and every measured target carries an adjacent count
  or "insufficient data". Browser-verified (desktop + 400px) on BTC 1d and XRP 1d. 10 new tests,
  **450 green**. No snapshot change (records are injected after build_facts, like the base rate).
- **Verdict records:** `src/research/verdict_records.py` + `scripts/build_verdict_records.py` →
  SQLite `verdict_records` (symbol × timeframe × bias × agreeing categories × aligned, + 'all markets'
  roll-up, with counts). Built by THE backtest walk (`walk` + `signal_at`; step 2) — every directional
  verdict, "resolved that way" = close 24 bars later beyond this close in the bias direction. Lookup
  prefers the market's own row at 20+ cases, else the all-markets row; <20 → "insufficient data (N
  cases)", never a %. Neutral reads have no record. Overlapping windows → cases not independent (count
  always shown).
- **Shown:** under the verdict — "Record: categories aligned bullish, 2 categories agreeing — 173 of 329
  resolved that way (53%) over 24 bars (BTC/USDT 1d). What happened before, not odds for now." (replaces
  the old Rec #2 track-record line when records exist). Beside every measured target on the chart:
  "double bottom target · hit 35/80". Beside every current pattern: its encyclopedia history (done in
  the previous step). All rendered by the UI from Layer 1 data.
- **For Claude:** facts gain `verdict_record` and a per-pattern `record`; the prompt shows a VERDICT
  RECORD line and each pattern's history line. Guide §1.4: every directional read references its record
  with the count (or says insufficient data); self-check updated.
- **First build (6 markets, 1d, ~10,300 directional verdicts):** every verdict type is near a coin flip —
  all markets: aligned bullish (2 agreeing) 867/1755 = 49%, aligned bearish (2) 844/1668 = 51%, aligned
  bullish (3) 107/201 = 53%, aligned bearish (3) 94/165 = 57%; not-aligned reads 47–51%. More agreement
  didn't reliably mean more follow-through — consistent with the no-edge finding.

### Pattern detection upgrade + Pattern scanner + history beside every find (user request)
- **Done:** 2026-09-24 · built on `main`'s working tree (user to branch/commit) · **merged to `main`.**
- **Why:** on XRP/USDT 1d the user saw a falling structure (upper line through the Aug 22 and Sep 14
  wick highs, lower through the Sep 2 and Sep 16 lows) breaking out on Sep 21; the app said "symmetric
  triangle, forming". The user wants to NOTICE patterns quickly — told plainly that the app's own
  record shows patterns haven't made these markets predictable (most breakouts failed), and that the
  prediction journal (D1) is the honest test of their own reads.
- **Detection (Layer 1, `chart_patterns.py`):**
  1. **Start after the last impulse** (continuation patterns only): drop swings before a leg that is ≥
     `patterns.impulse_atr_mult` (5) × ATR, reaches a NEW extreme beyond every earlier swing, and is ≥
     `impulse_leg_ratio` (2) × the median of the other same-direction legs (so a steady trend's legs
     and a wide range's oscillations are not "impulses"). With a trim, 2 swings per side (5+ total)
     may define a pattern. Fixes XRP (the pre-rally Aug 14 low made the lows look "rising") and the
     SOL "ascending channel" (A1 eye-check FAIL).
  2. **Wedges:** `rising wedge` / `falling wedge` — same-direction lines converging by ≥
     `wedge_min_convergence` (25%); falling = bullish (breaks above), rising = bearish; target = the
     wedge's starting height from the breakout. Channels now exclude converging lines.
  3. **Trader-style boundary lines** (`_envelope`): through two swings with every other swing inside
     (resistance touches the highest wicks) — least squares kept only for quality/slope checks. That's
     what moved the XRP breakout from Sep 20 (fit cut between peaks) to Sep 21, matching the user.
  4. **Breakout memory for line-bounded patterns** (`classify_state_path` + `_line_state`): triangles,
     channels, ranges and wedges are judged close by close against their (sloping) lines' values on
     each bar; neutral coils take the direction of the edge they break and their target follows it
     (a range breaking DOWN used to keep an upside target).
- **Real charts after:** XRP 1d → falling wedge, confirmed, broke out Sep 21 (fresh); SOL 1d → no
  channel (only the completed double bottom); BTC/ETH unchanged; EUR/USD ascending triangle → failed.
- **Encyclopedia (rebuilt, 6 markets 1d), before → after:** ascending channel seen 300→164 (judged
  breakouts 118→25), descending channel 269→176 (97→22) — over-calling largely gone. Falling wedge
  (new): target 2/43, failed 27/43 (63%); rising wedge (new): target 0/21, failed 19/21 (90%). Breakout
  memory made ranges/triangles look worse (sideways channel target 51%→33%, failed 45%→62%) — breakouts
  now counted when they happen. The encyclopedia's outcome sim also judges sloped lines bar by bar.
- **Pattern scanner** (`src/research/scanner.py`, `GET /scan?timeframes=`, cached 5 min, candles
  refreshed when a bar old, failing markets skipped): every registered pair × chosen timeframes →
  fresh breakouts (newest first), forming (closest to breakout in ATR first), in play. New **Scanner**
  view (`#/scanner`): 1d/4h/1h toggles, rows with levels, "open chart ▶" → analysis view live.
- **History beside every find:** each row, and each current pattern under the chart's tags, shows its
  type's encyclopedia record for that timeframe ("reached target 35 of 80 (44%) · failed 41 of 80
  (51%)"; a % only with 20+ cases). `/analysis` attaches `record` to each pattern. UI-rendered, not
  written by Claude (the pattern half of ROADMAP B4).
- **Snapshot:** regenerated after the user approved the diff — the fixture's ascending triangle is now
  `failed` (a close below its rising support 4 bars ago, missed by the old last-close check); tier
  unchanged. Wedges added to the textbook reader and the gold-label vocabulary.
- **Open:** symmetric triangles still have no measured target (follow-through "no cases"); B4's
  verdict-record half is not done.

### ROADMAP B3 — Empirical Pattern Encyclopedia
- **Done:** 2026-09-24 · **branch:** `feature/encyclopedia` · **merged to `main`.**
- **Done-when → PASS (precision column: unmeasured):** every detector pattern type has a page of real
  numbers with sample sizes; thin data labelled honestly (any rate under 20 cases shown as "7 of 12 —
  too few to rate", never a %); examples open in the scrub view at the breakout bar. Browser-verified
  (desktop + 400px) against a scratch build; the real table is built into `data/wizard.db` (all
  registered pairs, 1d). Detector precision shows "unmeasured" — B2 has no gold labels (user decision).
  19 new tests, **431 green**.
- **No second walker:** the backtest's inline loop was extracted into `backtest.evaluate.walk()` (+
  `default_warmup`), used by both `evaluate()` and the encyclopedia. Verified the refactor is exact:
  old vs new backtest on real BTC 1h → identical outcomes and identical report text. A test spies
  that the encyclopedia calls that very function.
- **Build:** `src/research/encyclopedia.py` + `scripts/build_encyclopedia.py`. Each distinct pattern
  (type + defining swing bars) is recorded the first time the walk detects it (look-ahead-safe; test
  mutates future bars). Outcomes on the FOLLOWING candles: breakout = first close beyond the breakout
  within 50 bars (neutral coils take the edge they break); then over 24 bars: target reached (wick),
  failure = close back through the breakout by reclaim_atr_mult × ATR (both on one bar → failed),
  move in ATR at +24, bars to resolution; confirmation profile at the breakout candle for the splits
  (volume / momentum / volatility / candlestick supported or not). Regime at first sighting.
- **Honesty rules:** rates use only patterns first seen while still FORMING (late-detected ones are
  counted as occurrences, kept out of rates — survivorship); patterns whose breakout window or 24-bar
  outcome window hasn't finished are **pending** — counted, shown as "too recent to judge", excluded
  from rates (caught in the browser: a 3-day-old breakout was being counted as "went nowhere"). Every
  row has `sample_size`; rates/quantiles are NULL below 20.
- **Storage/API/UI:** `encyclopedia_stats` (PK type × timeframe × symbol × regime × split; stats JSON;
  examples; built_at; params) with 'all' roll-ups for symbol and regime; rebuilds replace only the
  rebuilt markets. `GET /encyclopedia`, `GET /encyclopedia/{type}` (rows + textbook claim parsed from
  `docs/patterns-research.md` Parts A & C + B2 precision). New **Encyclopedia** view (`#/encyclopedia`,
  `#/encyclopedia/<type>`): list → page with textbook claim beside "what actually happened here",
  timeframe/market/regime filters, the split table, examples → analysis view scrubbed to that bar.
- **Deviation:** none in substance; "regime" is read at first sighting (not at the breakout).
- **First real build** (BTC/ETH/SOL/XRP/EUR/USD/GBP/USD, 1d; 1,712 patterns, 3,096 rows): after a
  breakout, most patterns FAILED more often than they reached target — double top 25% target / 65%
  failed (72 judged), double bottom 41% / 54% (85), ascending triangle 11% / 72% (54), descending
  channel 16% / 69% (97); sideways channel 51% / 45% (118). Median move 24 bars after a breakout is
  ~0–0.6 ATR for most types. H&S / inverse H&S have too few judged breakouts to rate (11, 18).
  Symmetric triangles have no measured target in the detector, so follow-through is "no cases".
  Consistent with the no-edge finding — the textbook's confident claims mostly don't hold here.

### Pattern life cycle — old signals labelled as history (user request)
- **Done:** 2026-09-24 · built on `main`'s working tree (user to branch/commit) · **merged to `main`.**
- **Why:** on BTC 1d the explanation said "two confirmed bullish patterns, confirmed 2 bars ago" and
  the user couldn't find them: the shape formed Aug 28 – Sep 15, the breakout was Sep 21, and the drawn
  lines stopped at Sep 15. Worse, the app had no notion of a pattern getting old — once confirmed it
  stayed "confirmed", in the present tense, for as long as the detector saw it (the limitation noted in
  A3).
- **Layer 1:** new `Pattern.lifecycle` (+ `state_bar`, `target_hit_bar`), set by
  `chart_patterns._lifecycle`, look-ahead-safe: forming · **fresh** (confirmed ≤ `patterns.fresh_bars`=3
  bars ago) · **in_play** · **completed** (a high/low reached the target since the breakout → history) ·
  **expired** (older than `expire_duration_mult`=1.0 × its own formation length, no target, no failure →
  history) · failed. `state` (forming/confirmed/failed) is unchanged. The situation tier ignores
  completed/expired patterns (history can't make a chart "confirmed"). The prompt labels each pattern
  "CONFIRMED · FRESH — broke out 2 bars ago" / "COMPLETED · HISTORY — reached its target N bars ago,
  not a current setup"; guide §3 got one line on it.
- **Chart (browser-verified, BTC 1d + SOL 1d):** the breakout level is extended to the breakout candle;
  an arrow marker there reads "DBot ✓ breakout (fresh)" / "(done)" / "DTop ✗ failed"; completed
  patterns get a "target hit" marker, are drawn grey, and lose their target price tag; the pattern
  chips read "confirmed · fresh" / "completed (history)".
- **Real charts:** BTC 1d double bottom + range → fresh (Sep 21); SOL 1d double bottom → completed (target
  117.34 hit Sep 21 — previously described as a current confirmed setup); BTC double top, EUR/USD double
  bottom → failed.
- **Snapshot:** regenerated after the user approved the diff — purely additive (`lifecycle`,
  `state_bar`, `target_hit_bar` per pattern; tier unchanged). 9 new tests, **412 green**.
- **Also noticed (not fixed):** the BTC explanation said "volume 1.41× on the breakout bars" — the 1.41×
  is the LAST (down) candle's volume; a correct number with the wrong meaning. C1's claim checks are
  what catch this.

### ROADMAP B2 — Detector precision/recall + tuning (instrument built; measurement waits for labels)
- **Done:** 2026-09-24 · **branch:** `feature/detector-eval` · **merged to `main`** (tooling).
- **Done-when → NOT YET:** "a precision/recall table per detector with counts, before and after tuning,
  on held-out labels" needs the gold set — **the real `gold_labels` table had 0 charts** when B2 was
  built. No detector was tuned and no reliability was filled with real numbers (tuning without labels
  would be guessing — exactly what B2 exists to prevent). Re-run once ≥30 charts are labelled.
- **Build:** `src/labels/evaluate.py` — detectors re-run on candles up to each labelled bar; patterns
  match when the TYPE is equal and both ENDPOINTS line up (≤ 2×swing-sensitivity bars, ≤ 1×ATR at that
  bar — scale-free); one-to-one greedy matching; S/R = the chart's nearest 3 zones per side vs your
  zones (same role, bands overlap ± 0.25×ATR), scored only where you marked zones. `Tally` → precision
  (tp/fired) and recall (tp/gold), always printed with counts; a detector that never fires has
  undefined precision, not perfect. Fixed ~30% HOLDOUT by a hash of symbol|timeframe|bar (a chart
  never changes side as the set grows). `tune()` grid-searches on the TUNE split only (a test spies to
  prove the holdout is never evaluated during search), picks best combined F1 (min fires), then
  before/after is reported on the holdout. `scripts/eval_detectors.py [--tune channels] [--write]`
  refuses to run under 30 labels without `--force`; `--write` saves `data/detector_reliability.json`.
- **Channel knobs made tunable** (defaults = old hard-coded behaviour → snapshot unchanged):
  `patterns.channel_min_r2` (0.6), `channel_min_parallel` (0.5), and the A1 idea as an option,
  `channel_respect_rails` (false) — reject a channel whose rails price closed through by >
  trendline_break_atr_mult × ATR. The tuner decides from your labels; the script only PRINTS the
  chosen values (you copy them into config.yaml).
- **Reliability field:** measured precision is injected like the base rate (`advise(reliability=…)`,
  API loads the JSON at startup) — never read inside build_facts, so the snapshot/offline tests don't
  depend on a local file. The prompt then lists "X precision P over N detections (status)"; entries
  with n < 10 are marked thin; everything unlisted stays "unverified".
- **Dry run** on a scratch DB (13 charts seeded from the detector's own output + "nothing here") showed
  the report format and caught a scoring bug: "nothing here" had also made every shown zone a false
  positive — it means *no pattern*, so zones are now scored only where zones were marked (test added).
- **Labelling implication (tell the user):** a labelled chart is treated as COMPLETE — mark every
  pattern you see (or "nothing here"), and if you mark zones, mark all the zones you'd draw there.

### 1–2 candle patterns at levels — chart markers (user request, facts-only)
- **Done:** 2026-09-24 · built on `main`'s working tree (user to branch/commit) · **merged to `main`.**
- **Why:** only the 3-candle patterns were drawn; doji/hammer/shooting star/engulfing were detected
  (and the last one votes) but never shown — ~190 per 500 candles would bury the chart.
- **What's drawn now (browser-verified on BTC 1d and XRP 1d):**
  - by default, a directional 1–2 candle pattern whose **wick tagged a level that favours it, as of
    that candle**: `H@sup`, `BeE@res`, `BuE@fib61.8`, `SS@TL` — bullish needs the nearest non-stale
    support zone below the previous close, a key Fibonacci level (38.2–78.6%) of an up-leg, or an
    unbroken support trendline; bearish the mirror. ~45–65 per 500 candles (BTC/SOL/EUR/USD 1d, BTC 1h).
  - always, the **last closed candle's** 1–2 candle pattern — the one the candlestick vote reads — as
    `CODE (last)`.
  - a study toggle **"1–2 candle patterns (all)"** (off by default) adds every other one, faded.
  - the legend explains the codes and the `@` tags.
- **Build:** `src/patterns/candle_context.py` — `candle_events()` (vectorised pattern lookup, vote
  precedence engulfing > hammer/shooting star > doji), `level_for()` (levels rebuilt as they existed at
  that bar: swings filtered to bars ≤ i − sensitivity — verified equal to recomputing on df[:i+1] up to
  the tie order of outside bars — then zones / Fibonacci / two-point trendlines on that history). An
  in-process cache per (market, bar, direction) makes repeat views and scrubbing cheap (first view of
  a market ~1.6 s, then ~0.04 s); level context covers the last 500 candles. `serialize.py` adds
  `overlays.candles_12 = {all, at_level, last}`. `find_sr_zones` clustering made linear-time (running
  sum; snapshot unchanged). 10 new tests incl. look-ahead guards.
- **How the rule was chosen (measured, not tuned to a count):** every historical zone + a 0.25×ATR "near"
  margin → 85–99% of patterns "at a level" (meaningless); nearest non-stale zone only → 64–86%; wick
  must actually TAG the level → ~50%; doji excluded (no direction for a level to favour) → final.
- **Not changed:** the candlestick VOTE (still any 1–2 candle pattern on the last bar); the facts sent
  to Claude (no "at a level" fact yet — a natural Layer-1 addition, would change the snapshot).
  Stale zones don't count as a level here (a pattern at a long-dormant zone isn't marked).

### ROADMAP B1 — Detector gold set: labelling mode
- **Done:** 2026-09-24 · **branch:** `feature/gold-set` · **merged to `main`.** Tooling done; the
  done-when's second half — **≥30 charts labelled — is the user's work and is still open (0 so far).**
- **Done-when (tooling) → PASS:** labelling mode works with the detector overlays hidden — checked in
  headless Chromium on BTC/USDT 1d at a scrubbed bar: verdict, pattern chips, facts panels, paper
  trade, S/R zones, Fibonacci, patterns, trendlines, swings, candle patterns, the verdict marker and
  the regime strip all hidden; a double top (3 wick-snapped points) + a support zone drawn, saved,
  reloaded when returning to the bar, and the detectors restored on exit. Tested against a SCRATCH
  DB (the real `data/wizard.db` untouched). 15 new tests, **382 green**.
- **Build:** `gold_labels` table (symbol, timeframe, bar, bar_time, labels JSON, created/updated;
  UNIQUE per bar → re-saving updates). `src/labels/gold.py`: `validate` (known type, ≥2 points,
  lower<upper, role; "nothing here" is a real label and can't coexist with patterns), `save` (upsert),
  `load`, `list_all`, `delete`, `summary` (charts, patterns by type, zones, "nothing here",
  per market). Vocabulary = the detector's own type names + a few it doesn't detect yet (wedges,
  flags, other) so recall can be measured on them. API: `GET /labels/types`, `GET /labels`,
  `GET /labels/one`, `PUT /labels`, `DELETE /labels/{id}`. UI: "🏷 Label this bar" in the scrub row →
  `LabelPanel.svelte` (pattern type + clicks on key points with snap-to-wick, "Add pattern"; S/R zone =
  two clicks + role; "nothing here"; note; save/update; the gold-set list with counts by type, and
  click a row to jump to that chart/bar). `PriceChart` label mode draws your labels in purple, keeps
  zoom/scroll across clicks, and ignores clicks after the labelling bar. Labelling never calls Claude.
- **Bugs found and fixed on the way:** (1) **CORS allowed only GET** since Phase 24 — every browser
  write (paper Buy/Sell/undo, label save) failed its preflight ("Failed to fetch"); now GET/POST/PUT/
  DELETE, origins still restricted (test added). (2) **Scrub race:** a request made while one was
  loading was silently dropped, so the chart could show an older bar than the slider — a label would
  have been saved to the wrong bar. Requests now queue; the API returns `bar_index` (the bar actually
  computed) and labels key to that (test added). (3) While scrubbed back, paper trades from the future
  were snapped onto the last candle; they're now skipped, and hidden entirely while labelling.
- **Deviations from ROADMAP.md:** none in substance. Labels are keyed by bar index AND bar_time, so
  B2 can match either way.

### ROADMAP A7 — Honest baselines
- **Done:** 2026-09-24 · **branch:** `feature/honest-baselines` · **merged to `main`.**
- **Done-when → PASS:** baseline band visible beside the paper P&L; calculator defaults to the
  cost-adjusted coin flip, backtest only on an explicit click labelled "Backtest — no edge found";
  checked in headless Chromium at 1400px + 400px (against a SCRATCH trades DB with 5 seeded closed
  BTC trades — the real `data/wizard.db` was never touched). 13 new tests, **367 green**.
- **Paper-trading luck band:** `src/trading/baseline.py` — `random_entry_baseline()` (pure, seeded)
  replays your k closed trades as many "monkey" records: random historical bar, random side, SAME
  holding time (in bars of the trades' timeframe) and SAME size; reports the 5th/50th/95th percentile
  of total P&L and wins, your percentile, and `inside_luck_band`. `GET /trades/baseline` (1000 runs).
  UI: range + median + a bar with your marker + a verdict ("inside the luck band — this record can't
  tell skill from luck, especially with only 5 trades"). No costs on either side (like-for-like with
  paper P&L). Refreshes after a close / undo.
- **Calculator default:** `src/risk/coin_flip.py` + `GET /risk/coin_flip` — round-trip cost from the
  Feature-10 cost model (spread, fees, ATR slippage, funding/financing over a 24-bar hold), in units
  of the risk (entry→stop), then **p = (1 − c)/(1 + R)**: the zero-edge win rate at your payoff, net of
  costs (expectancy exactly −c). Win-rate source buttons: "Coin flip, cost-adjusted (default)" /
  "Backtest — no edge found"; typing your own number is labelled as such. BTC 1h at 1.5:1 → 37.8%
  (ruin 99.7%, Kelly "don't bet").
- **Deviation / correction:** "coin flip" taken literally as 50% is only zero-edge at a 1:1 payoff.
  My first version used 0.5 − c/(1+R), which at 1.5:1 showed 47.8% — a hidden +0.2R edge that made
  ruin read 0.0% in green (caught in the browser). Replaced with the zero-edge rate 1/(1+R) net of
  costs; a test pins "expectancy = −cost at every payoff".
- **Findings:** crypto funding dominates daily holds (24-bar hold on 1d = 24 days of funding → BTC 1d
  cost ~1.1% round trip vs ~0.22% on 1h). Paper trades held minutes are rounded up to 1 bar of their
  timeframe in the luck band (overstates the monkeys' holding time for very short trades).

### ROADMAP A6 — Analyst guide revision (+ forex price-precision fix)
- **Done:** 2026-09-24 · **branch:** `feature/guide-revision` · **merged to `main`.**
- **Done-when → PASS (with findings):** guide updated; prompt tests pass (+2 new guide-rule tests;
  **354 green**); brief + teaching spot-checked on BTC 1d, SOL 1d, EUR/USD 1d — verifier OK on all
  six. Brief mode: within budget, `Opposing:` line present when supplied, conditionals two-sided,
  no directional wording against the Layer 1 bias. Teaching mode still drifts (see findings).
- **Guide changes:** §1.1 one rounding rule (prices exactly as given; other numbers ≥3 significant
  figures; no "≈"; inside the verifier's 1% tolerance). §1.4 "what it conventionally suggests"
  removed; suggests/favours/leans/path of least resistance/buyers-sellers in control are directional
  claims, allowed only in the direction of the Layer 1 bias or when attributing a detector's own vote.
  §2 conditional reads symmetric (nearest level above AND below, no "so"; "worth revisiting" gone).
  §4 "conventionally read as" labels a convention, doesn't license direction; "many false breaks"
  removed. §5 extremes = crowded positioning with no implied direction; "historically coincided with
  turning points" and the contrarian readings removed. §7 cut to one allowed observation (higher-TF
  trend vs a pattern's implied direction). §8 tier supplied/never escalated, `Opposing:` line always
  when supplied and outside the budget, teaching lifts only the word cap; examples rewritten. §8/§10
  one fact-naming style: "RSI 28 (oversold)". §11 self-check kept, noting C1 will enforce it.
- **Code alongside:** brief `max_tokens` gets +60 for the uncounted Opposing line; the teaching note
  restates that tier/format/Opposing still apply. Layer 1's own prompt text aligned with §5 (Fear &
  Greed and funding extremes → "crowded positioning, no implied direction"); two tests that pinned
  the old "contrarian" wording updated.
- **Deviation / scope added:** the forex spot-check exposed a Layer 1 bug — facts AND the pattern
  detectors rounded every price to 2 decimals. EUR/USD zones read "1.15–1.15", ATR became 0.0 (so ATR
  distances vanished), and pattern breakout levels moved ~50 pips BEFORE the state machine compared
  closes to them (wrong forex states). Fixed with `src/market/precision.py` (`price_decimals`: 2 at
  ≥100, 5 at ≥1, 6 below — the chart's existing rule; `round_price`, `fmt_price`) used by facts,
  detectors, `Pattern.to_dict`, zone/fib vote reasons and level labels. Crypto ≥100 is unchanged →
  BTC snapshot byte-identical. Regression test added. My first rounding rule ("3 significant figures
  for everything") also collapsed forex prices and was replaced by "prices exactly as given".
- **Findings:** teaching mode keeps adding things the guide now forbids: uncounted historical claims
  ("follow-through historically requires more confirmation", "often appears at a turning point"),
  invented mechanics ("a stale zone has fewer participants", "the measured target is the minimum
  move"), causal guesses ("which may explain the failure"), extra own observations (the ADX-vs-
  sideways tension, in all three teaching runs), and bold headings. Prompt rules alone don't stop
  it — C1's claim-level checks must. Candidate Layer 1 fact: label "ADX trending but swing structure
  sideways" explicitly so the model stops explaining it. Round-number step for FX is still 0.1
  (nearest 1.1 for 1.1467 — the Phase-18 "FX may want finer steps" note stands). Claude's prompt
  still carries "confidence NN%" (not removed here).

### ROADMAP A5 — Facts payload hardening
- **Done:** 2026-09-24 · **branch:** `feature/facts-hardening` · **merged to `main`.**
- **Done-when → PASS:** every field present (test per field); absences explicit in both the facts
  dict (`absences`) and the prompt ("NOT PRESENT…", "RSI divergence: none detected", "not fetched",
  "not available"); distances present on every level (tests); snapshot regenerated after the user
  reviewed the diff. 18 new tests, **351 green**, ruff + svelte-check clean. No UI change → no
  browser check needed.
- **Build:** new `src/advisor/facts_detail.py` (pure helpers) + `facts._harden()`:
  - **Distances** `{distance_atr, distance_pct}`, signed (+ above / − below): S/R zones (to the nearer
    edge, 0 inside), each key Fibonacci level, the round number, each pattern's breakout /
    invalidation / target, and the 50/200 SMAs (new `moving_averages` block).
  - **`nearest_levels.above/below`**: nearest structural level (zone edges, key Fibonacci, round
    numbers either side, pattern breakout/invalidation) with its source. MAs excluded (dynamic).
  - **Pattern ages**: `bars_since_completion` and `bars_since_state_change` (None while forming).
    `classify_state_history` now also returns where the state began; memoryless (continuation)
    patterns use the start of the current same-state run.
  - **`detector_reliability`**: every detector + pattern type `{precision: None, n: 0, status:
    unmeasured}` until B2.
  - **`mtf_signals`**: each detector's vote on the base TF and each higher TF in `mtf.facts_from`,
    resampled from the base candles, dormant below `slow_ma` bars. Base votes are reused, not recomputed.
  - **`strongest_opposing_fact`**: the opposing category with the highest configured weight, its
    detector and reason; None when nothing opposes or the read is neutral (stated either way).
  - **`absences`**: divergence, confirmed/failed/any pattern, candlestick, support/resistance zone,
    Fibonacci leg, volume, higher timeframe, opposing category, nearest level above/below.
  - **Prompt** rewritten in §3 order: 1 trend & regime (+ MAs, ADX, HTF, per-signal TF votes) →
    2 structure (nearest levels, zones, Fibonacci, round number) → 3 patterns (+ candlestick) →
    4 momentum → 5 volatility → 6 volume → 7 context/derivatives → verdict, opposing fact, track
    record, per-detector votes, reliability, NOT PRESENT. Old labels kept inside the sections.
- **Snapshot diff (approved):** purely additive (179 lines added, no existing value changed; tier
  still notable) — the new keys above plus distance fields.
- **Deviations from ROADMAP.md:** (1) the roadmap's "1d / 1w" example needed a weekly timeframe
  that wasn't configured; with the user's OK, `mtf.facts_from` [4h, 1d, 1w] was added for the
  per-signal votes ONLY — the veto (`context_from` [4h, 1d]) is unchanged, since adding 1w there
  would change daily/4h verdicts and needs a daily backtest first. 1w weeks run Mon–Sun (`W-SUN`).
  (2) Opposing fact is category-based as specified; an opposing CONFIRMED PATTERN (e.g. SOL 1d's
  bullish double bottom vs a bearish read, before A4) is not yet surfaced as the opposing fact.
- **Prompt wording fixes (after reading the real BTC 1d facts):** the verdict count now reads
  "1 of 4 voting categories agree; 2 needed to align" (was "1 of 2", i.e. agreeing-of-required);
  the veto line is labelled "Higher-timeframe veto check" and, when none applies, says so and points
  to the per-timeframe votes (it used to say "no higher timeframe available" right above the 1w
  votes); "1 bar ago" singular. Wording only — snapshot unchanged.
- **Findings:** on 1h, 1w stays dormant (~26 weeks of history < 50); on daily and 4h it is active
  (e.g. BTC 1d: trend 1d neutral / 1w bearish). The prompt still shows the internal "confidence NN%"
  to Claude — A2 removed it from the UI only; A6/C1 should decide whether Claude may see it.

### ROADMAP A4 — Support/resistance as zones + level freshness
- **Done:** 2026-09-23 · **branch:** `feature/sr-zones` · **merged to `main`.**
- **Done-when → PASS:** zones render as shaded bands in the browser (headless Chromium: BTC 1d,
  SOL 1d zoomed); stale zones are marked (fainter band + "stale" axis tag + in facts/prompt);
  snapshot regenerated after the user reviewed and approved the diff; tests for width scaling and
  staleness (13 new; **333 green**, ruff + svelte-check clean).
- **Build:** `support_resistance.py` — `find_sr_zones()` clusters swings within `sr_zone_atr_mult`
  (0.5) × ATR of the running centroid; band = centred on the touches' mean, ≥ 0.5×ATR wide, always
  covering every touch; `touches` / `first_touch` / `last_touch` / `bars_since_touch` (touch =
  a swing REVERSAL in the zone); `strength` = Σ 0.5^(age/60 bars); `stale` = no reversal for 120
  bars. `sr_zones(featured, swings, cfg)` is the ONE builder used by facts, confluence, the service
  and the chart; `zone_distance()` = 0 inside the band. `price` stays the band centre, so every old
  consumer (roles, chart-pattern structure hits, PNG chart) still works.
- **Vote:** `signal_from_support_resistance(zones, close, atr, near_atr_mult)` — at a zone = inside
  or within 0.25×ATR of its edge (was: within 0.5% of a single line). Role from the centre vs price.
  Facts `nearest_support/resistance` now carry lower/upper/touches/bars_since_touch/strength/stale/
  inside; the prompt renders them as bands ("last reversal N bars ago", STALE flag).
- **Chart:** a lightweight-charts series primitive (`ZoneBands`) fills each band under the candles;
  an axis tag at the centre (no line). Fibonacci and round numbers stay exact lines.
- **Backtest (vote-path change, BTC/USDT 1h, h=24, step=4):** **51.6% of 438 → 50.5% of 440** —
  within noise, slightly worse; NOT tuned. Still no edge.
- **Snapshot diff (approved):** the old 7-touch line at 64,166 (0.5% clustering ≈ 1.4×ATR on 1h) split
  under 0.5×ATR clustering; price is now INSIDE a 2-touch support zone 63,829–63,944 → S/R vote
  bearish→bullish → structure nets neutral → 1 agreeing category, not triggered → tier confirmed→notable.
- **Deviations from ROADMAP.md:** clustering itself also moved from a fixed 0.5% to ATR (the roadmap
  asked only for ATR-scaled *width*, but the conventions ban fixed-% thresholds and %-clusters with
  ATR-wide bands would overlap). `sr_cluster_tolerance_pct` is now used only by chart-pattern
  structure hits and the old `find_support_resistance` (kept for `show_structure.py`/tests).
- **Findings:** ATR clustering is TIGHTER than 0.5% on 1h and WIDER on daily — zones fragment on
  intraday charts. "Touch" = reversal, so a zone price is trading in right now can still be stale
  (SOL 1d: inside a zone last reversed ~270 bars ago). Not changed here: the Fibonacci vote still uses
  the percent `proximity_pct`; the PNG chart (`viz/chart.py`) still draws centre lines.

### ROADMAP A3 — Situation tier in Layer 1
- **Done:** 2026-09-23 · **branch:** `feature/situation-tier` · **merged to `main`.**
- **Done-when → PASS:** identical facts always give the same tier (test); each §2 criterion has its
  own isolated test; a forming-only chart can't be `confirmed` (test); the tier shows in the UI —
  checked in headless Chromium at 1400px and 400px (SOL 1d notable, BTC 1h notable, ETH 1h no clear
  setup). 26 new tests, **326 green**, ruff + svelte-check clean.
- **Build:** `src/signals/situation.py` — `classify_situation(facts, cfg)`, a pure function of the
  facts dict, called at the end of `build_facts` → `facts["situation"] = {tier, reasons,
  word_budget, template}`. `confirmed` = a confirmed pattern matching a triggered bias whose
  confirmation profile shows §4's shape (price supports, volume OR volatility supports, momentum and
  higher TF not contradicting). `no_setup` = any §2 criterion, each a reason code
  (`no_pattern_no_confluence`, `away_from_levels`, `conflicting_signals`, `neutral_indicators`,
  `single_weak_signal`). Precedence confirmed > no_setup > notable. Failed patterns count toward
  notable; forming patterns are ignored entirely.
- **Explanation bound by the tier:** `facts_to_prompt` leads with `SITUATION TIER`; `explain` /
  `explain_structured` take `situation=` and the mode note names ONLY that tier's template and
  budget; brief `max_tokens` = budget×3+60 (structural cap). Teaching keeps the tier, lifts only the
  word cap. `synthesize` is always `mtf_synthesis` (150). Guide §8 gained one line: use the supplied
  tier, never change it (small pull-forward from A6).
- **UI:** "Situation: notable (categories aligned; confirmed double bottom; price is at a level)"
  under the verdict, neutral styling.
- **Snapshot:** regenerated — diff is ONE added key, `situation` (fixture reads `confirmed` via its
  double top); nothing else moved. Reviewed and approved by the user with the commit.
- **Deviations from ROADMAP.md:** the premise "a forming SOL channel produced a flagged setup" doesn't
  match the code — chart patterns were never confluence voters. A day-by-day SOL 1d replay showed
  every flag came from MACD / S/R / volume. So SOL still shows "categories aligned" (2 of 4 really
  agree); the change is that its tier is `notable`, not `confirmed` (its confirmed double bottom is
  bullish vs a bearish bias). A test pins that injecting a forming pattern leaves confluence and the
  tier unchanged.
- **Findings / limitations:** §2's "away from levels" taken literally demotes a mid-range
  trend+momentum agreement to no_setup (deliberate — documented in the module). A stale confirmed
  pattern still counts as confirmed until A5 adds bars-since-confirmation. An MTF veto can leave
  "2 of 4 agree" without the "categories aligned" badge (BTC 1h) — the UI doesn't yet say why.

### ROADMAP A2 — Verdict reframe + no-edge disclosure
- **Done:** 2026-09-23 · **branch:** `feature/verdict-reframe` · frontend + one guide sentence.
  **Merged to `main`: `800e12a`** (code) + `1003735` (PROGRESS/ROADMAP updates).
- **Done-when → PASS:** no percentage labelled "confidence" anywhere in the UI, no green/red verdict
  styling, disclosure visible — checked in headless Chromium at 1400px and 400px.
- **Verdict:** "confidence NN%" → a count ("2 of 4 categories agree · 1 opposes · 1 neutral";
  denominator = categories that voted). "SETUP FLAGGED" → "categories aligned". Green/red border and
  badge removed; the chart's verdict arrow is now neutral grey. The 0–1 `confidence` stays in the
  API/facts, never displayed.
- **Other "confidence" displays found:** the paper-trade log showed "NN% conf" per read → replaced
  with "N categories agreed", bias no longer colour-coded. None left in `web/src`.
- **Disclosure:** persistent line under the title on every view — "Tested: no predictive edge. This
  tool is for reading charts, not forecasting them." — expands to a plain-language evidence panel
  (backtest 51.3% of 429, cross-coin 40–61% unstable, ML AUC 0.51 / broken calibration, funding no edge).
  The numbers are hard-coded from the documented runs; update them if the tests are re-run.
- **Guide:** removed "If asked whether it works, say so plainly." (rule 6 keeps "do not imply
  predictive power").
- **Verified in the browser** (desktop + 400px): no percentage labelled confidence, neutral verdict,
  disclosure visible on Analysis and Risk views. 300 green, svelte-check clean.
- **Kept on purpose:** the track-record line ("right NN% of the time") — a base rate shown with its
  count, not a confidence. P&L green/red and per-category vote colours (facts, not the verdict).
- **Deviations from ROADMAP.md:** (1) the count's denominator is the categories that actually voted
  (4 today: trend/momentum/structure/volume — volatility has no voter), so it reads "of 4", not the
  roadmap's "of 5" example; showing a category that can't vote would understate agreement.
  (2) The "link to the evidence" is an expandable panel under the disclosure, not a separate page —
  one click, no routing, visible on every view. (3) Went slightly wider than asked: the chart's
  verdict arrow and the paper-trade log's bias are also neutral now (same verdict, same leak).
- **Findings:** the verdict now also shows how many categories OPPOSE — the old % hid disagreement.
  The evidence figures are historical (backtest 51.3% is the Phase-17 run); no test re-run in A2.

### ROADMAP A1 — Human verification pass (+ rendering fixes, reclaim rule, 2-point trendlines)
- **Done:** 2026-09-23 · **branch:** `feature/a1-verification-fixes` · **merged to `main`: `645231c`**
  (the `fix/verification-pass` branch holds no A1 commits).
- **Done-when → PASS:** boundaries and labels render correctly in the browser (headless Chromium,
  1400px + 400px), and each eye-check is recorded pass/fail below.
- **Rendering fixes (browser-verified, desktop + 400px phone):** pattern boundary lines were already
  drawn since `32da1e5` (the review predated it) — confirmed on SOL 1d. The garbled top-left labels
  were the full-name 3-candle marker texts from `ea0294c` overlapping/clipping → markers now use
  short codes (MS/ES/3WS/3BC) with a legend row. Regime strip rebuilt: solid 22px band, no axis/logo,
  legend row with the latest regime, switches to the hovered bar's regime.
- **Reclaim rule (Layer 1):** reversal patterns (double top/bottom, H&S) now keep state history
  (`classify_state_history`): a neckline break later reclaimed by ≥ `patterns.reclaim_atr_mult`
  (0.25) × that bar's ATR reads `failed` instead of reverting to `forming`. Continuation patterns
  (sloped rails) still use the last close only. Snapshot unchanged.
- **Two-point trendlines (user request):** `find_two_point_trendlines` joins the latest swing
  low/high to an earlier one, kept only while no close crosses it by > `structure.
  trendline_break_atr_mult` (0.25) × ATR; longest valid line wins. Chart-only (teal support / pink
  resistance, `trendlines` toggle) — NOT in facts, so no explanation/snapshot change. SOL 1d: rising
  support Aug 16 → Sep 15, which the user confirmed is the line their eye draws.
- **Eye-checks (user, in the browser):**
  - **Regime labels on daily match remembered periods — PASS.** Trends read trending, chop reads
    ranging, no flicker.
  - **Old BTC 1d double top (neckline 76,264) reads `failed` — PASS.** Replay: forming → confirmed
    Sep 15–16 (closes < 76,264) → `failed` Sep 18 (close 80,884, reclaim beyond the 0.25×ATR margin).
  - **SOL 1d "ascending channel" looks like a channel — FAIL.** User: no channel. Only the lower
    rail is real (rising support Aug 16 → Sep 15, unbroken); the recent highs don't form a valid
    parallel upper rail (Aug 27 110.60 > Sep 6 107.36; Aug 9 → Sep 6 was broken Aug 27). The
    least-squares channel fit doesn't require its rails to be respected → over-calling. **Feeds B1/B2**
    as a labelled channel false positive; candidate fix: require both rails to pass the 2-point
    trendline "unbroken" test.
- **Tests:** +7 reclaim/state-history, +8 two-point trendlines. **300 green, ruff + svelte-check clean.**
- **Not done here:** phone-width right-axis label pile-up (many price-line labels cover the chart).
- **Deviations from ROADMAP.md:** (1) "pattern boundary lines not drawn" was already fixed in
  `32da1e5` — the design review predated it — so A1 verified it instead of rebuilding it. (2) The
  top-left garble had a different cause than the one fixed earlier: the full-name 3-candle markers
  from `ea0294c`. (3) PROMPTS.md expected the double top to be `failed` because price broke *above
  the neckline*; the rule fails it only on a close above the *peaks* (82,300) — or, since A1, on a
  reclaim of the neckline beyond 0.25×ATR. (4) Scope added at the user's request: the reclaim rule
  and two-point trendlines (both Layer 1, tested, snapshot unchanged).
- **Findings worth remembering:** pattern state was MEMORYLESS (last close only), so a confirmed break
  that price later reclaimed silently went back to `forming` — fixed for reversal patterns only;
  continuation patterns still work that way. The channel detector's least-squares rails don't have to
  be respected by price, which is why it over-calls. A running dev backend can be older than the
  code (the user's predated `ea0294c`), so a UI bug may not reproduce until the server restarts.

### Three-candle candlestick patterns — morning/evening star, three soldiers/crows (facts-only)
- **Built:** 2026-09-23 · **branch:** `feature/three-candle-patterns`
- **Why:** on BTC/USDT 1h the user spotted a doji-in-the-middle 3-candle shape the app couldn't
  name — we only detected 1- and 2-candle patterns (doji/hammer/shooting-star/engulfing).
- **Done-when:** each pattern fires on its textbook fixture; the last closed bar's read shows in the
  facts + a UI panel row; 3-candle markers draw on the chart; and the exact real bars the user was
  looking at detect **nothing** (all up, doji middle → read stays "doji"). All verified.
- **Design (advisor-reviewed): FACTS-ONLY, not a vote.** Making the existing candlestick vote fire
  in new situations would change confluence → the backtest → an unvalidated vote-path change (the
  Phase 9/18/22 facts-first ethos). Proof it's untouched: snapshot diff is the **single new
  `candlestick` key**, `confluence.signals` is **byte-identical**, `len(signals)==7`.
- **Build:** `features.py` — 4 boolean columns (`morning_star`/`evening_star`/
  `three_white_soldiers`/`three_black_crows`) via shift(1)/shift(2) (causal → look-ahead-safe),
  module-constant thresholds (`STRONG_BODY_MIN_FRACTION`/`STAR_BODY_MAX_RATIO`/
  `SOLDIER_WICK_MAX_FRACTION`), gaps NOT required (24/7 crypto) — reversal proven by close beyond
  candle-A's body midpoint. `candlestick_read()` names the strongest pattern (3-candle first, then
  2- then 1-candle) and labels a doji-middle star a "doji star". Wired into `facts.py`
  (`candlestick` block + prompt render), `serialize.py` (`candle_patterns` overlay — 3-candle set
  ONLY, too-frequent singles excluded), `api.ts` + `PriceChart.svelte` (labelled squares, green
  below/red above, under the `patterns` toggle), and an App.svelte panel row.
- **Tests:** `tests/test_candlesticks.py` — 8 (each pattern fires, doji-star naming, 3-candle
  precedence, causality guard, and the real-BTC no-false-positive tied to the user's exact bars).
  **284 green, ruff + svelte-check clean.** Browser-verified markers on a mock; real BTC 1h → 11
  markers / last 500 bars (~2%), current bar reads doji.
- **Deferred:** promoting any 3-candle pattern to a *vote* is a separate, backtested step — not done
  on faith. Density is fine now; if stars ever feel noisy, tighten to "close beyond candle-A open".

### Paper-trading simulator — Buy/Sell, position + PnL, chart markers
- **Built:** 2026-09-22 · **branch:** `feature/paper-trading` (spec: `paper-trading-spec.md`)
- **Done-when:** enter a `$` amount, click Buy/Sell, see it recorded (time/price/amount + on-screen
  verdict snapshot), an open position + unrealized PnL, a trades log, and green ▲ / red ▼ markers
  on the entry candle — only for the pair you're viewing. **Browser-verified** (headless Chromium +
  stateful mock): Flat → Buy opens LONG (badge, disabled same-side, relabeled close button, log
  row, green ▲ marker) → Sell closes it (Flat badge, realized-PnL record line, red ▼ close marker).
- **Locked decisions:** `$` notional (`units = amount/fill`); one position at a time per symbol
  (opposite side closes + books realized PnL, same side → 400); snapshot = whatever's on screen
  (**never a Claude call**); **live spot fill** server-side (ccxt `fetch_ticker`, graceful fallback
  to `last_close`, source tagged `live`|`last_close`); SQLite `trades` table.
- **Build:** `src/store/db.py` (+`trades` table), `src/trading/paper.py` (`live_price` w/ 5s TTL
  cache, `open_or_close`, `record`, `list_trades`, `position`, `pnl_summary`, `delete_trade`),
  API `POST/GET /trades`, `GET /trades/position`, `DELETE /trades/{id}` (guarded like the rest;
  `_TRADES_DB` tmp-path seam for tests). Frontend: typed client in `api.ts`, trade panel + badge +
  log in `App.svelte`, entry/exit markers in `PriceChart.svelte` (snap trade time → entry candle).
- **Tests:** `tests/test_paper.py` — 7 offline unit (long/short PnL signs, one-at-a-time guard,
  reopen, `live_price` ticker→fallback, injected-fetch record, summary) + 1 `TestClient` API flow
  (monkeypatched `live_price`, tmp DB). **276 green, ruff + svelte-check clean.**
- **Honest framing:** labeled "Paper trading — simulated, not advice"; live fills but no
  slippage/fees/liquidity — PnL measures discipline & read, not a real account.
- **Distinct from Feature 4** (journal/calibration): own `trades` table, shares only
  `src/store/db.py`; extract common resolve-logic later if a 2nd consumer appears.

### Feature 2 — Pattern confirmation states
- **Merged:** 2026-09-20 · **branch:** `feature/pattern-confirmation` → **`main`** (commit `6b8dfd5`, fast-forward)
- **Done-when:** every pattern reports state, breakout, invalidation, quality, and a full 7-category
  confirmation profile; overlaps are deduplicated; the guard passes. Confirmed on real data —
  BTC 1h: one *confirmed bullish ascending triangle* (4 supports / 0 contradicts); BTC 1d: one
  *forming bearish double top* (quality 0.68). No over-calling (dedupe collapses to one each).
  Snapshot diff confined to `chart_patterns`, and `confluence.signals` stays length-7 — proving
  patterns stayed OUT of the score. 24 new tests; **256 green**.
- **Build:** `src/patterns/base.py` (`Pattern` + `ConfirmationProfile`: price/volume/momentum/
  volatility/candlestick/higher_tf/structure, each supports/contradicts/neutral/unavailable;
  look-ahead-safe `classify_state`). Detectors refactored to emit `Pattern` with ATR-scaled
  tolerances; added **rectangle + channel** (continuation). `dedupe.py` keeps highest quality,
  ties preferring continuation. Wired into facts + serialize (additive chart contract → no
  `PriceChart.svelte` edit).
- **Deviations:** **flags deferred** (fuzziest, most over-call-prone geometry) — a note, not a
  gap; triangles + rectangle + channel already cover continuation. Old percent config fields kept
  (config.yaml sets them; `extra="forbid"`). Triangle quality uses flatness × linearity, not the
  degenerate flat-side r2.
- **Learned:** on the same swings a rectangle/triangle also reads as a double top/bottom — the old
  code returned all; dedupe now collapses them, and a continuation-first tie-break resolves it
  (matches the trend-riding use case). Keeping the serialize contract additive meant no chart edit
  and no browser re-verification loop.

### Feature 10 — Honest cost model
- **Merged:** 2026-09-19 · **branch:** `feature/cost-model` → **`main`** (commit `53e37df`)
- **Done-when:** every backtest reports net-of-everything by default, and you can see what fraction
  of the gross edge costs consume. Confirmed live (BTC 1d, 506 setups): **gross +0.45%/trade →
  net −0.14%** (win 50%→48%) — a gross-positive setup flips **net-negative after costs**. Costs
  consume **~133% of the gross edge**; breakeven needs a **51% win-rate vs the current 50%** (at
  payoff 1.10), or a 1.13 payoff at the current win-rate. Slippage dominates (~48 bps of ~60).
- **Build:** `src/backtest/costs.py` — per-trade round-trip cost as a fraction of notional:
  spread (crypto bps; forex pip-spread per pair, session-aware), taker fees (both sides),
  volatility-scaled slippage (`mult × ATR/price`), signed perp funding over the holding period,
  forex overnight financing, configurable tax on realised gains. `evaluate()` applies it by
  default (`costs.enabled`); `BacktestReport.costs` + `summary()` show gross vs net, per-component
  bps, cost-share-of-edge, and a breakeven win-rate/payoff. 8 new tests.
- **Deviations:** funding & crypto spread come from CONFIG defaults, not per-bar live data — the
  historical backtest doesn't carry live order-book spread or funding, so a universal config rate
  is used (funding still signed by direction: longs pay positive). Tax defaults to 0 (jurisdiction-
  specific, opt-in); the transaction costs apply regardless. Session spread multipliers are module
  constants (base spread is config). Gross stats are unchanged, so base_rate/suite/snapshot are
  untouched — costs are purely additive.
- **Learned:** volatility-scaled **slippage dominates** (~48 bps vs ~12 for spread+fees on daily
  crypto) — "fixed slippage is a lie" is the load-bearing choice; it's what flips gross-positive to
  net-negative. "Cost as % of gross profit" is ambiguous: against gross WINNINGS it read a
  reassuring 13% next to a net-NEGATIVE result; against the gross EDGE (total pre-cost P&L) it
  reads 133% — the honest denominator, consistent with net-negative.

### Feature 9 — Risk of ruin & position sizing
- **Status:** implemented 2026-09-19 · **branch:** `feature/risk-of-ruin` → **merged to `main`** (commit `41232b4`)
- **Done-when:** enter your own measured stats → see probability of ruin, expected worst drawdown,
  and a sized position, and the numbers *sober* rather than reassure. Confirmed live: 45% win at
  1:1 payoff → ~100% chance of a 50% drawdown before doubling at any risk level; full-Kelly median
  drawdown ~86% vs quarter-Kelly ~32%; the risk×win-rate table renders as a green→red cliff. 18
  new maths tests + a real headless-browser check of the calculator page. **239 tests green.**
- **Build:** `src/risk/ruin.py` — analytic ruin (diffusion two-barrier hitting probability) +
  vectorised Monte Carlo (Wilson CI + an `unresolved`-fraction bias check); bootstrap drawdown
  distribution from real trade returns; Kelly/half/quarter with drawdown pain; position-size
  calculator; ruin table. `GET /risk` + `/risk/measured`; `RiskCalculator.svelte` + a nav toggle.
- **Deviations / how win rate & payoff are handled:** win rate is pulled from the backtest
  (`base_rates.json`) with a Wilson CI and a `thin` flag when n is small. **Payoff ratio is left
  `None`** — it is NOT stored by the backtest and CANNOT be reconstructed from win rate + avg
  return (underdetermined), and the journal (Feature 4) that would supply it **doesn't exist yet**.
  So the calculator takes payoff as a user input for now; `gather_measured_stats` queries a
  `journal_entries` table defensively so it auto-populates payoff once Feature 4 lands.
- **Learned:** monotonicity of ruin (↑ with risk) only holds for a POSITIVE edge — a losing
  system's ruin can *fall* with more risk, because higher variance gives a small chance to hit the
  double first (a real result, not a bug). The i.i.d. bootstrap destroys loss clustering and so
  *understates* the longest losing streak — flagged in the output; a block-bootstrap option
  retains some clustering.

### Hardening — chart panning, analyst-guide wiring, explanation modes, Layer-1 classification
- **Merged:** 2026-09-18 · **branch:** `fix/explanation-and-chart` (commit `17f7bd1`, merge `8442a87`)
- **Chart (frontend):** fixed drag-to-pan (it was zooming) and the right edge. All panes now share
  ONE index axis (warm-up + trailing gap as whitespace) and sync by *logical* range, not time —
  no drift, so a drag can't creep into a zoom. Left edge is a hard stop; the right edge is a
  debounced snap-back to a permanent ~25-bar gap so the newest candles clear the price-axis
  labels. Verified in real headless Chromium (puppeteer), not just a build.
- **Analyst guide wired in:** `analyst-guide-system-prompt.md` is now loaded at startup (fails
  loudly if missing) and IS the system prompt for `explain`/`synthesize`/`explain_structured` —
  one source of truth, behind a cache breakpoint. **FINDING: the guide had been ORPHANED for
  several sessions** — never loaded by any code; the real prompt was a hardcoded string in
  `explain.py`, so its §8 word budgets never applied and explanations ran 1000+ words.
- **Two explanation modes, default `brief`:** brief enforces the guide's §8 budgets (`max_tokens`
  ~400 → structural, not just requested); teaching is the fuller breakdown, exempt from the
  budgets *only* (every other rule binds), `max_tokens` 2048. UI toggle added (browser-verified).
  Live check: **43 words (brief) vs 1162 (teaching)** on the same analysis.
- **Classification moved to Layer 1:** every confluence signal now carries a pre-computed vote +
  category in the facts payload; context items (Fear & Greed, funding, distance-from-ATH) are
  marked explicitly non-directional (F&G gets an extreme-vs-mid-range read per the guide's bands).
  Fixes Layer 2 classifying the same fact differently across runs. Snapshot regenerated (only the
  `category` keys added). New `tests/test_facts_classification.py`.
- **Learned:** a prompt file living next to the code is not the same as being *used* — verify the
  wiring, not the file's existence. The guide (§5) already forbade directional context reads, so
  the classification bug was the facts render not surfacing that framing, letting Layer 2 fill the
  gap.

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
