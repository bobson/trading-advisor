# Patterns & Confirmation — Research Reference

A catalogue of chart patterns, candlestick patterns, and the indicators conventionally
used to confirm them.

**Read this first.** Everything below is **trading convention**, drawn from technical-analysis
literature and practitioner usage. It is **not established fact**, and most of it has never
been rigorously validated. Your app already has a backtest and an ML harness that returned an
honest "no edge" verdict — that machinery, not this document, is the arbiter of what actually
holds. Treat this as a **hypothesis list to test and to draw**, not a rulebook to encode.

Workflow this document is built for: **draw everything first → look at real setups with
indicator panels visible → form your own view of what confirms what → then test it.**

---

## Part A — The pattern catalogue

### A1. Reversal chart patterns
| Pattern | Shape | Breakout / trigger level |
|---|---|---|
| **Double top / bottom** | Two roughly equal peaks (or troughs) | Neckline (the trough between the peaks) |
| **Triple top / bottom** | Three roughly equal peaks/troughs | Neckline |
| **Head & shoulders** | High, higher high, high — with a neckline | Neckline |
| **Inverse head & shoulders** | Mirror image at a bottom | Neckline |
| **Rounding top / bottom (saucer)** | Slow, curved turn; no sharp pivot | Rim of the saucer |
| **Diamond top / bottom** | Broadening then narrowing (rare) | Lower/upper diamond edge |
| **Broadening formation (megaphone)** | Widening highs and lows; expanding volatility | Ambiguous — weak, often skipped |
| **Rising wedge** | Converging lines, both sloping **up** | Lower line (bearish) |
| **Falling wedge** | Converging lines, both sloping **down** | Upper line (bullish) |
| **V-top / V-bottom (spike)** | Sharp reversal, no consolidation | Hard to trade; largely retrospective |

> Wedges are ambiguous: usually reversal, but continuation in some contexts. Flag both readings.

### A2. Continuation chart patterns
| Pattern | Shape | Breakout / trigger level |
|---|---|---|
| **Ascending triangle** | Flat resistance + rising lows | Horizontal resistance |
| **Descending triangle** | Flat support + falling highs | Horizontal support |
| **Symmetrical triangle** | Lower highs **and** higher lows converging | Whichever line breaks |
| **Rectangle (range)** | Horizontal support and resistance | Either boundary |
| **Channel** (ascending / descending / horizontal) | Two parallel trendlines | Either boundary |
| **Bull / bear flag** | Sharp "pole" then a small counter-slope channel | Flag boundary |
| **Pennant** | Sharp pole then a tiny symmetrical triangle | Pennant boundary |
| **Cup and handle** (+ inverted) | Rounded base then small pullback | Handle's upper boundary |
| **Measured move** | Leg, consolidation, second leg of similar size | Consolidation boundary |

### A3. Candlestick patterns
**Single-candle:** doji (plus dragonfly, gravestone, long-legged), hammer, hanging man,
shooting star, inverted hammer, marubozu, spinning top.

**Two-candle:** bullish/bearish engulfing, harami (+ harami cross), piercing line,
dark cloud cover, tweezer top/bottom.

**Three-candle:** morning star, evening star, three white soldiers, three black crows,
three inside up/down, three outside up/down.

> Candlesticks are *local* signals — one to three bars. Their conventional value is as a
> **trigger at a level identified by something else** (a pattern boundary, S/R, a Fib level),
> not as standalone signals. That's the single most useful idea in this document.

---

## Part B — The confirmation toolkit

Seven independent *categories* of confirmation. The useful principle: confirmations from
**different categories** are worth far more than several from the same one (your confluence
engine already encodes this).

1. **Price** — a *close* beyond the breakout level (not just an intrabar poke); a successful
   retest of the broken level from the other side. The most fundamental confirmation.
2. **Volume** — expansion on the breakout bar vs the volume MA; contraction inside the pattern;
   OBV trending with the breakout direction. *(Crypto only for real volume; forex is tick volume.)*
3. **Momentum** — RSI, MACD, Stochastic: direction, crossovers, and especially **divergence**
   against the pattern's later peaks.
4. **Trend / regime** — ADX (is there a trend at all?), MA alignment, and **higher-timeframe
   trend agreement**. Determines whether a continuation or reversal reading even makes sense.
5. **Volatility** — ATR expanding on breakout; Bollinger squeeze resolving into expansion.
   Distinguishes a real break from a drift.
6. **Candlestick** — a reversal candle printing exactly at the pattern's level.
7. **Structure** — the pattern completing *at* an S/R zone, Fibonacci level, or round number.

---

## Part C — The confirmation matrix (hypotheses to test)

Conventional pairings, by pattern family. **Test these; don't assume them.**

### Double top / bottom, triple top / bottom
- **Momentum divergence** is the classic tell: second peak higher but RSI lower (bearish), or
  second trough lower but RSI higher (bullish). Widely cited as the strongest confirmation here.
- **Volume:** conventionally lower on the second peak, expanding on the neckline break.
- **Candlestick at the second peak:** shooting star / bearish engulfing (top), hammer /
  bullish engulfing (bottom). ← *your shooting-star example; this is its textbook home*
- **Structure:** stronger when the peaks land on a known resistance zone or round number.
- **Price:** neckline close, then retest.

### Head & shoulders (+ inverse)
- **Volume:** the canonical sequence is heavy on the left shoulder, lighter on the head,
  lightest on the right shoulder, expanding on the neckline break.
- **Momentum:** divergence between head and right shoulder.
- **Price:** neckline close + retest; measured target = head-to-neckline distance projected.
- **Trend:** should appear *after* an established trend — H&S in a range is meaningless.

### Ascending / descending / symmetrical triangles
- **Volume:** contracting into the apex, expanding on the break. Most-cited triangle confirmation.
- **Volatility:** Bollinger squeeze inside the triangle, expansion on the break; ATR rising.
- **Trend/ADX:** ADX low inside (consolidation), rising on the break. Direction of the
  prior trend supports the continuation reading.
- **Candlestick:** marubozu / strong engulfing on the breakout bar.
- **Caution:** triangles produce many false breaks — price confirmation (close, then retest)
  matters more here than almost anywhere else.

### Rectangles / channels
- **Structure:** the boundaries *are* S/R — confirm with touch count and reaction quality.
- **Candlestick at boundaries:** rejection candles (pin bars, engulfing) at the edge.
- **Momentum:** Stochastic/RSI overbought at the top, oversold at the bottom — classic
  range-trading read (note this is the *opposite* use of RSI from a trend context).
- **Volume:** expansion on the eventual breakout; low volume inside.
- **ADX:** low ADX confirms the range is genuine; rising ADX warns it's ending.

### Flags / pennants
- **Volume:** heavy on the pole, contracting through the flag, expanding on the break.
- **Trend:** only valid *with* the prevailing trend; MA alignment and higher-TF agreement matter.
- **Duration:** short by definition — a long "flag" is a different pattern (channel/rectangle).

### Wedges
- **Momentum divergence** is the main confirmation (price making new extremes, momentum not).
- **Volume:** conventionally declining through the wedge.
- **Price:** break of the relevant boundary with a close.

### Cup and handle
- **Volume:** high at the cup's left, low at the base, expanding on the handle breakout.
- **Trend:** requires a prior uptrend.
- **Duration:** long-forming; unreliable on low timeframes.

### Candlestick patterns (as triggers, not standalone)
- **Location is everything:** a hammer at a support zone, Fib level, or pattern boundary is
  meaningful; the same hammer mid-range is noise.
- **Confirm with:** the next candle continuing the implied direction; volume on the signal
  candle; momentum agreement (RSI oversold under a hammer at support).
- **Trend context:** shooting stars matter at the *top* of an advance; hammers at the *bottom*
  of a decline. Your ADX/trend module is what makes that judgement possible.

---

## Part D — Cross-cutting notes

**Which indicators pair with the most patterns?** By breadth of conventional use:
1. **Volume / volume MA** — cited for nearly every pattern (crypto only for real volume)
2. **RSI (especially divergence)** — reversal patterns above all
3. **ADX** — tells you whether a continuation or reversal reading is even appropriate
4. **ATR / Bollinger** — breakout quality and false-break filtering
5. **MACD** — slower; better as trend/momentum context than a precise trigger
6. **Higher-timeframe trend** — the strongest single contextual filter you already have

**The recurring shape of a confirmation, across every pattern:**
`pattern boundary + close beyond it + expansion (volume/volatility) + momentum not disagreeing
+ higher-timeframe trend not opposing`

**Honest caveats**
- These pairings are convention. The literature that quantifies them is thin, its methods
  vary, and results rarely replicate cleanly.
- Confirmation reduces false signals **and** reduces sample size — waiting for a retest means
  fewer, later entries. That trade-off is real and is itself worth measuring.
- Beware fitting: with ~20 patterns × ~7 confirmation categories you have a large search
  space, and something will look good by chance. Your ML harness already showed ~50% on pure
  noise — hold any promising pairing to that same standard, and report sample size always.

---

## Part E — Build implication: draw first

To actually *see* which indicators line up with which patterns, the chart needs:
- **Main panel:** candles + all detected patterns drawn (boundaries, neckline, breakout level,
  invalidation), plus S/R, trendlines, Fibonacci, round numbers.
- **Sub-panels, visible together:** volume + volume MA; RSI (with divergence marked);
  MACD (line/signal/histogram); optionally ADX and ATR.
- **Pattern state shown visually:** forming vs confirmed vs failed, distinctly styled.
- **Toggles** for each overlay and sub-panel, so you can isolate what you're studying.
- **Scrub/step through history** so you can walk to past patterns and inspect what the
  indicators were doing at the moment each one completed.

That last point is the one that turns this from a dashboard into a research tool: being able
to step to every historical pattern and look at the panels is how you'll form real opinions
about confirmation — rather than adopting them from a document like this one.
