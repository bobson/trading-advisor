<script lang="ts">
  import { onMount } from 'svelte'
  import PriceChart from './lib/PriceChart.svelte'
  import RiskCalculator from './lib/RiskCalculator.svelte'
  import {
    getPairs, getTimeframes, getAnalysis, getTrades, getPosition, postTrade, deleteTrade,
    type Pair, type Analysis, type PanelToggles, type Trade, type TradePnl, type Position,
  } from './lib/api'

  let view = $state<'analysis' | 'risk'>('analysis')
  let pairs = $state<Pair[]>([])
  let timeframes = $state<string[]>([])
  let symbol = $state('BTC/USDT')
  let timeframe = $state('1h')
  let explain = $state(false)
  let explanationStyle = $state<'brief' | 'teaching'>('brief')
  let auto = $state(false)
  let loading = $state(false)
  let error = $state<string | null>(null)
  let result = $state<Analysis | null>(null)
  const REFRESH_MS = 30_000

  // ---- per-overlay / per-pane toggles, persisted to localStorage ----
  const DEFAULT_TOGGLES: PanelToggles = {
    trendlines: true, levels: true, fib: true, swings: true, patterns: true, marker: true, ma: true,
    volume: true, rsi: true, macd: true, adx: false, atr: false,
  }
  const TOGGLE_KEY = 'tw.toggles'
  function loadToggles(): PanelToggles {
    try { return { ...DEFAULT_TOGGLES, ...JSON.parse(localStorage.getItem(TOGGLE_KEY) || '{}') } }
    catch { return { ...DEFAULT_TOGGLES } }
  }
  let toggles = $state<PanelToggles>(loadToggles())
  $effect(() => { localStorage.setItem(TOGGLE_KEY, JSON.stringify(toggles)) })
  const OVERLAY_KEYS: (keyof PanelToggles)[] = ['trendlines', 'levels', 'fib', 'swings', 'patterns', 'marker', 'ma']
  const PANE_KEYS: (keyof PanelToggles)[] = ['volume', 'rsi', 'macd', 'adx', 'atr']

  // ---- historical scrubbing (as_of_bar) ----
  let asOfBar = $state<number | null>(null)          // null = live / latest bar
  const totalBars = $derived(result?.chart.total_bars ?? 0)
  const scrubMax = $derived(Math.max(0, totalBars - 1))
  const scrubValue = $derived(asOfBar ?? scrubMax)   // slider sits at the right when live
  let scrubTimer: any = null
  function scrubTo(bar: number) {
    asOfBar = Math.min(Math.max(0, bar), scrubMax)
    clearTimeout(scrubTimer)
    scrubTimer = setTimeout(() => run(false), 180)    // debounce; per-bar responses are cached
  }
  function stepScrub(delta: number) { scrubTo((asOfBar ?? scrubMax) + delta) }
  function goLive() { asOfBar = null; run() }
  function onScrubKey(e: KeyboardEvent) {
    const step = e.shiftKey ? 10 : 1
    if (e.key === 'ArrowLeft') { e.preventDefault(); stepScrub(-step) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); stepScrub(step) }
  }

  onMount(async () => {
    try {
      pairs = await getPairs()
      timeframes = await getTimeframes()
      if (pairs.length && !pairs.some((p) => p.symbol === symbol)) symbol = pairs[0].symbol
      if (timeframes.length && !timeframes.includes(timeframe)) timeframe = timeframes[0]
    } catch (e: any) {
      error = `Could not reach the API (${e.message}). Is the backend running?`
    }
  })

  async function run(useExplain = explain) {
    if (loading) return
    loading = true
    error = null
    try {
      // Skip context/explain while scrubbing (current-state context is anachronistic on a past bar).
      const scrubbing = asOfBar != null
      result = await getAnalysis(symbol, timeframe, scrubbing ? false : useExplain, !scrubbing, asOfBar, 5000, explanationStyle)
    } catch (e: any) {
      error = e.message
      result = null
    } finally {
      loading = false
    }
    if (result) loadTrades()
  }

  // Auto-refresh: poll every REFRESH_MS while `auto` is on. NEVER calls Claude (explain=false),
  // so it can't silently burn API credits.
  $effect(() => {
    if (!auto) return
    const id = setInterval(() => run(false), REFRESH_MS)
    return () => clearInterval(id)
  })

  const conf = $derived(result?.confluence)
  // Verdict as a COUNT of categories, never a percentage: "2 of 4 categories agree · 1 opposes".
  // The 0–1 confidence stays in the API/facts for internal use; it is not displayed.
  const catCount = $derived.by(() => {
    const votes = Object.values(conf?.categories ?? {})
    const bias = conf?.bias
    const opposite = bias === 'bullish' ? 'bearish' : bias === 'bearish' ? 'bullish' : null
    return {
      total: votes.length,
      agree: conf?.agreeing_categories ?? 0,
      oppose: opposite ? votes.filter((v) => v === opposite).length : 0,
      neutral: votes.filter((v) => v === 'neutral').length,
      bullish: votes.filter((v) => v === 'bullish').length,
      bearish: votes.filter((v) => v === 'bearish').length,
    }
  })

  // ---- paper-trading simulator (per-pair; live spot fills server-side) ----
  let tradeAmount = $state(500)
  let trades = $state<Trade[]>([])
  let tradePnl = $state<TradePnl | null>(null)
  let position = $state<Position | null>(null)
  let tradeMsg = $state<string | null>(null)
  let tradeBusy = $state(false)

  async function loadTrades() {
    if (!symbol) return
    try {
      const st = await getTrades(symbol)
      trades = st.trades
      tradePnl = st.pnl
      position = await getPosition(symbol, result?.market?.last_close ?? null)
    } catch { /* trades are non-critical — never block the analysis view */ }
  }

  async function doTrade(side: 'buy' | 'sell') {
    if (tradeBusy || !(tradeAmount > 0)) return
    tradeBusy = true
    tradeMsg = null
    try {
      // "Whatever is on screen" — the current verdict (+ explanation if it was fetched). No Claude call.
      const snapshot = result ? {
        bias: conf?.bias, confidence: conf?.confidence,
        agreeing_categories: conf?.agreeing_categories, explanation: result.explanation,
      } : null
      const r = await postTrade({
        symbol, side, amount_usd: tradeAmount, timeframe,
        last_close: result?.market?.last_close ?? null, snapshot,
      })
      trades = r.trades
      tradePnl = r.pnl
      tradeMsg = r.result.action === 'closed'
        ? `Closed — realized ${fmtUsd(r.result.realized_pnl)}`
        : `Opened ${side === 'buy' ? 'LONG' : 'SHORT'} @ ${r.result.price.toLocaleString()}`
      position = await getPosition(symbol, result?.market?.last_close ?? null)
    } catch (e: any) {
      tradeMsg = e.message?.replace(/^\d+:\s*/, '') ?? 'trade failed'
    } finally {
      tradeBusy = false
    }
  }

  async function undoTrade(id: number) {
    try { await deleteTrade(id) } catch { /* ignore */ }
    await loadTrades()
  }

  const fmtUsd = (x: number | null | undefined) =>
    x == null ? '—' : `${x < 0 ? '-' : '+'}$${Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
  const fmtTime = (secs: number) => new Date(secs * 1000).toLocaleString()

  const fmtLevel = (x: any) => (x ? `${x.price.toLocaleString()} (${x.touches} touches)` : '—')
</script>

<main>
  <h1>🧙 Trading Wizard</h1>
  <p class="tag">Reads the chart, explains its reasoning — not financial advice.</p>

  <!-- Persistent no-edge disclosure (ROADMAP A2). Shown on every view; the summary line is always
       visible, the evidence opens underneath. Numbers are from the documented runs (PROGRESS.md /
       CLAUDE.md) — update them here if the tests are re-run. -->
  <details class="disclosure">
    <summary>Tested: no predictive edge. This tool is for reading charts, not forecasting them.
      <span class="more">What was tested</span></summary>
    <div class="evidence">
      <p>Several tests asked one question: <b>does the engine's read tell you where price goes
        next?</b> All said no, so treat every verdict here as a description of the chart, not odds.</p>
      <ul>
        <li><b>Backtest</b> (look-ahead-safe replay, BTC/USDT 1h, 24 bars ahead): when categories
          aligned, price moved the implied way in <b>51.3% of 429 cases</b>, about a coin flip.</li>
        <li><b>Across coins and time</b> (BTC, ETH, SOL, XRP; first half vs second half of the history):
          results ranged from about 40% to 61% and did not hold from one half to the other.</li>
        <li><b>Machine learning</b> (walk-forward on BTC/USDT 1h, 3,545 out-of-sample predictions):
          accuracy 52.2% vs 51.5% for always guessing the more common direction; AUC 0.51, where 0.50
          is guessing. Its confidence was meaningless: when it said 91%, it was right 51% of the time.</li>
        <li><b>Funding rates</b> (a common "crowded trade" signal): no contrarian edge found.</li>
      </ul>
      <p class="muted">What the tool is good for: seeing structure clearly (trend, levels, patterns),
        learning what each signal means, and checking your own reads against what happened.</p>
    </div>
  </details>

  <nav class="views">
    <button class:active={view === 'analysis'} onclick={() => (view = 'analysis')}>Analysis</button>
    <button class:active={view === 'risk'} onclick={() => (view = 'risk')}>Risk calculator</button>
  </nav>

  {#if view === 'analysis'}
  <div class="controls">
    <select bind:value={symbol} onchange={() => { asOfBar = null; trades = []; position = null; tradePnl = null; tradeMsg = null }}>
      {#each pairs as p}<option value={p.symbol}>{p.label} ({p.symbol})</option>{/each}
    </select>
    <select bind:value={timeframe} onchange={() => (asOfBar = null)}>
      {#each timeframes as t}<option value={t}>{t}</option>{/each}
    </select>
    <label class="explain"><input type="checkbox" bind:checked={explain} /> explain (uses API credit)</label>
    {#if explain}
      <select class="mode" bind:value={explanationStyle} title="explanation length">
        <option value="brief">brief</option>
        <option value="teaching">teaching</option>
      </select>
    {/if}
    <label class="explain"><input type="checkbox" bind:checked={auto} /> auto-refresh (30s)</label>
    <button onclick={() => run()} disabled={loading}>{loading ? 'Analyzing…' : 'Analyze'}</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if result}
    <!-- Neutral styling on purpose: green/red + a percentage read as odds to a beginner. -->
    <div class="verdict">
      <span>Bias: <b>{conf?.bias}</b></span>
      {#if conf?.bias === 'bullish' || conf?.bias === 'bearish'}
        <span><b>{catCount.agree} of {catCount.total}</b> categories agree{catCount.oppose
          ? ` · ${catCount.oppose} ${catCount.oppose === 1 ? 'opposes' : 'oppose'}` : ''}{catCount.neutral
          ? ` · ${catCount.neutral} neutral` : ''}</span>
      {:else}
        <span>categories: {catCount.bullish} bullish · {catCount.bearish} bearish · {catCount.neutral} neutral</span>
      {/if}
      {#if conf?.triggered}<span class="flag">categories aligned</span>{/if}
    </div>

    {#if result.base_rate}
      <p class="track">
        📊 Track record: {result.base_rate.bias} setups like this were right
        <b>{(result.base_rate.win_rate * 100).toFixed(0)}%</b> of the time
        ({result.base_rate.n} past cases, {result.base_rate.horizon}-bar horizon).
        <b>A base rate, not a prediction.</b>
      </p>
    {/if}

    <!-- Paper-trading simulator: log a simulated Buy/Sell, see the position + PnL. Fills are live
         spot prices but no slippage/fees are modelled — it's your discipline, not a real account. -->
    <section class="trade panel">
      <div class="trade-head">
        <h3>Paper trade <span class="muted">— simulated, not advice</span></h3>
        {#if position && !position.flat}
          <span class="pos-badge {position.side === 'buy' ? 'bull' : 'bear'}">
            {position.side === 'buy' ? 'LONG' : 'SHORT'} ${position.amount_usd?.toLocaleString()} @ {position.entry?.toLocaleString()}
            · <b class={(position.unrealized_pnl ?? 0) >= 0 ? 'bullish' : 'bearish'}>
              {fmtUsd(position.unrealized_pnl)} ({position.unrealized_pct}%)</b>
          </span>
        {:else}
          <span class="pos-badge flat">Flat</span>
        {/if}
      </div>
      <div class="trade-row">
        <label>$ <input type="number" min="1" step="1" bind:value={tradeAmount} /></label>
        <button class="buy" onclick={() => doTrade('buy')}
                disabled={tradeBusy || (position != null && !position.flat && position.side === 'buy')}>
          {position && !position.flat && position.side === 'sell' ? 'Buy (close short)' : 'Buy'}
        </button>
        <button class="sell" onclick={() => doTrade('sell')}
                disabled={tradeBusy || (position != null && !position.flat && position.side === 'sell')}>
          {position && !position.flat && position.side === 'buy' ? 'Sell (close long)' : 'Sell'}
        </button>
        {#if tradeMsg}<span class="trade-msg">{tradeMsg}</span>{/if}
      </div>
      {#if tradePnl && tradePnl.closed}
        <div class="trade-summary">
          Record: <b>{tradePnl.wins}/{tradePnl.closed}</b> wins ·
          realized <b class={tradePnl.realized_total >= 0 ? 'bullish' : 'bearish'}>{fmtUsd(tradePnl.realized_total)}</b>
          <span class="muted">(paper, {tradePnl.closed} closed)</span>
        </div>
      {/if}
      {#if trades.length}
        <div class="trade-log">
          {#each [...trades].reverse().slice(0, 8) as t (t.id)}
            <div class="log-entry">
              <div class="log-row">
                <span class="log-side {t.side === 'buy' ? 'bull' : 'bear'}">{t.side}</span>
                <span class="log-amt">${t.amount_usd.toLocaleString()}</span>
                <span class="log-px">@ {t.price.toLocaleString()}</span>
                {#if t.status === 'closed'}
                  <span class="log-exit">→ {t.exit_price?.toLocaleString()}
                    <b class={(t.realized_pnl ?? 0) >= 0 ? 'bullish' : 'bearish'}>{fmtUsd(t.realized_pnl)}</b></span>
                {:else}
                  <span class="log-open">open</span>
                {/if}
                <span class="log-time">{fmtTime(t.opened_at)}</span>
                <button class="log-undo" title="undo (delete this paper trade)" onclick={() => undoTrade(t.id)}>✕</button>
              </div>
              <!-- The read you had when you traded — "whatever was on screen": verdict always,
                   Claude's write-up only if explain was ticked. This is the journaling payoff. -->
              {#if t.snapshot?.bias}
                <div class="log-snap">
                  read: <b>{t.snapshot.bias}</b>
                  {#if t.snapshot.agreeing_categories != null}· {t.snapshot.agreeing_categories} categories agreed{/if}
                  {#if t.snapshot.explanation}
                    <details><summary>explanation</summary><pre>{t.snapshot.explanation}</pre></details>
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <!-- Research controls: scrub back through history + choose which overlays/panes to draw. -->
    <div class="research">
      <div class="scrub">
        <button class="mini" onclick={() => stepScrub(-1)} title="step back (←)">‹</button>
        <input type="range" min="0" max={scrubMax} value={scrubValue}
               oninput={(e) => scrubTo(+e.currentTarget.value)} onkeydown={onScrubKey}
               aria-label="scrub through history" />
        <button class="mini" onclick={() => stepScrub(1)} title="step forward (→)">›</button>
        <span class="scrub-label">
          {#if asOfBar == null}bar {scrubMax} · <b>live</b>{:else}bar {asOfBar} / {scrubMax}{/if}
        </span>
        {#if asOfBar != null}<button class="mini live" onclick={goLive}>⤒ live</button>{/if}
      </div>
      <details class="toggles">
        <summary>overlays &amp; panes</summary>
        <div class="toggle-grid">
          <div><span class="grp">overlays</span>
            {#each OVERLAY_KEYS as k}
              <label><input type="checkbox" bind:checked={toggles[k]} /> {k}</label>
            {/each}
          </div>
          <div><span class="grp">panes</span>
            {#each PANE_KEYS as k}
              <label><input type="checkbox" bind:checked={toggles[k]} /> {k}</label>
            {/each}
          </div>
        </div>
      </details>
    </div>

    {#if result.chart.overlays.patterns.length}
      <div class="patterns">
        {#each result.chart.overlays.patterns as p}
          <span class="pchip {p.state}">{p.type} · {p.state}</span>
        {/each}
      </div>
    {/if}

    <PriceChart data={result.chart} {toggles} {trades} />

    <div class="panels">
      <section class="panel">
        <h3>Confluence by category</h3>
        {#each Object.entries(result.confluence.categories ?? {}) as [cat, dir]}
          <div class="row"><span>{cat}</span><b class={dir}>{dir}</b></div>
        {/each}
      </section>

      <section class="panel">
        <h3>Key levels</h3>
        <div class="row"><span>Resistance</span><b>{fmtLevel(result.support_resistance?.nearest_resistance)}</b></div>
        <div class="row"><span>Price</span><b>{result.market.last_close.toLocaleString()}</b></div>
        <div class="row"><span>Support</span><b>{fmtLevel(result.support_resistance?.nearest_support)}</b></div>
        {#if result.round_number}
          <div class="row"><span>Round #</span><b>{result.round_number.nearest.toLocaleString()}{result.round_number.is_near ? ' · at it' : ''}</b></div>
        {/if}
        {#if result.fibonacci}
          <div class="row"><span>Fib ({result.fibonacci.direction})</span><b>{Object.entries(result.fibonacci.key_levels).map(([k, v]) => `${(+k * 100).toFixed(0)}%:${v}`).join('  ')}</b></div>
        {/if}
      </section>

      <section class="panel">
        <h3>Momentum & volatility</h3>
        <div class="row"><span>RSI</span><b>{result.momentum.rsi ?? '—'} ({result.momentum.rsi_zone})</b></div>
        <div class="row"><span>MACD</span><b>{result.momentum.macd_state}</b></div>
        {#if result.momentum.stochastic_zone}
          <div class="row"><span>Stochastic</span><b>{result.momentum.stochastic_k} ({result.momentum.stochastic_zone})</b></div>
        {/if}
        {#if result.volatility}
          <div class="row"><span>ADX</span><b>{result.volatility.adx ?? '—'} ({result.volatility.regime ?? '—'})</b></div>
          <div class="row"><span>Bollinger</span><b>{result.volatility.bollinger_position ?? '—'}</b></div>
          <div class="row"><span>ATR</span><b>{result.volatility.atr_pct ?? '—'}%</b></div>
        {/if}
        {#if result.divergence}<div class="row"><span>Divergence</span><b class={result.divergence.kind}>{result.divergence.kind}</b></div>{/if}
        {#if result.candlestick}<div class="row"><span>Candlestick</span><b class={result.candlestick.direction}>{result.candlestick.pattern}</b></div>{/if}
      </section>

      <section class="panel">
        <h3>Market context</h3>
        {#if result.market_adaptation}
          <div class="row"><span>Type</span><b>{result.market_adaptation.asset_class} · {result.market_adaptation.volume_type} vol</b></div>
          {#if result.market_adaptation.active_session}<div class="row"><span>Session</span><b>{result.market_adaptation.active_session}</b></div>{/if}
          {#if result.market_adaptation.weekend_gap}<div class="row"><span>Gap</span><b>weekend gap</b></div>{/if}
        {/if}
        {#if result.context?.fear_greed}
          <div class="row"><span>Fear &amp; Greed</span><b>{result.context.fear_greed.value} ({result.context.fear_greed.label})</b></div>
        {/if}
        {#if result.context?.fundamentals}
          <div class="row"><span>Market cap</span><b>${(result.context.fundamentals.market_cap / 1e9).toFixed(1)}B</b></div>
          <div class="row"><span>24h change</span><b>{result.context.fundamentals.change_24h_pct}%</b></div>
          <div class="row"><span>From ATH</span><b>{result.context.fundamentals.ath_change_pct}%</b></div>
        {/if}
        {#if result.derivatives?.funding}
          <div class="row"><span>Funding</span><b>{result.derivatives.funding.state}</b></div>
        {/if}
        {#if result.derivatives?.open_interest}
          <div class="row"><span>Open interest</span><b>{result.derivatives.open_interest.amount.toLocaleString()}</b></div>
        {/if}
        {#if !result.context?.fear_greed && !result.context?.fundamentals && !result.derivatives}
          <div class="row"><span class="muted">no extra context (crypto-only / needs keys)</span></div>
        {/if}
      </section>
    </div>

    {#if result.explanation}
      <section class="panel"><h2>Explanation</h2><pre>{result.explanation}</pre></section>
    {:else}
      <p class="hint">Tick “explain” and Analyze again for Claude’s plain-language write-up.</p>
    {/if}
  {:else if !error}
    <p class="hint">Pick a pair and timeframe, then press Analyze.</p>
  {/if}
  {:else}
    <RiskCalculator {symbol} {timeframe} />
  {/if}
</main>

<style>
  :global(body) { margin: 0; background: #0e1117; color: #c9d1d9;
    font: 15px/1.5 -apple-system, system-ui, sans-serif; }
  main { max-width: 1000px; margin: 0 auto; padding: 24px; }
  h1 { margin: 0 0 4px; }
  .tag { color: #8b949e; margin: 0 0 8px; }
  .disclosure { color: #8b949e; font-size: 13px; margin: 0 0 18px; }
  .disclosure summary { cursor: pointer; }
  .disclosure .more { text-decoration: underline; margin-left: 6px; }
  .disclosure .evidence { margin-top: 8px; padding: 10px 14px; border: 1px solid #30363d;
    border-radius: 8px; color: #c9d1d9; line-height: 1.5; }
  .disclosure .evidence ul { margin: 6px 0; padding-left: 20px; }
  .disclosure .evidence .muted { color: #8b949e; }
  .views { display: flex; gap: 8px; margin-bottom: 18px; }
  .views button { background: #161b22; border: 1px solid #30363d; font-weight: 500; }
  .views button.active { background: #238636; border-color: #238636; }
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
  select, button { background: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 12px; font-size: 14px; }
  button { background: #238636; border-color: #238636; cursor: pointer; font-weight: 600; }
  button:disabled { opacity: 0.6; cursor: default; }
  .explain { color: #8b949e; font-size: 13px; }
  .error { color: #f85149; }
  .hint { color: #8b949e; }
  .verdict { display: flex; gap: 18px; align-items: center; flex-wrap: wrap;
    padding: 10px 14px; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 12px; }
  .flag { border: 1px solid #484f58; color: #c9d1d9; padding: 2px 8px; border-radius: 999px; font-size: 12px; }
  .track { color: #8b949e; font-size: 13px; margin: 0 0 12px; }
  .panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 14px 0; }
  .panel h3 { margin: 0 0 8px; font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: .04em; }
  .row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; font-size: 14px; border-bottom: 1px solid #161b22; }
  .row span { color: #8b949e; }
  .row .muted { font-size: 12px; }
  .row b.bullish { color: #26a641; }
  .row b.bearish { color: #f85149; }
  .row b.neutral { color: #8b949e; }

  /* Mobile: stack the controls, full-width thumb-sized targets, tighter padding. */
  @media (max-width: 640px) {
    main { padding: 14px; }
    h1 { font-size: 22px; }
    .controls { flex-direction: column; align-items: stretch; }
    .controls select, .controls button { width: 100%; padding: 12px; font-size: 16px; }
    .verdict { gap: 10px; }
    .panels { grid-template-columns: 1fr; }
  }
  .panel { border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-top: 14px; }
  .panel h2 { margin: 0 0 8px; font-size: 16px; }
  pre { white-space: pre-wrap; margin: 0; color: #c9d1d9; }

  /* Paper-trading simulator */
  .trade .muted { text-transform: none; letter-spacing: 0; color: #6e7681; font-weight: 400; }
  .trade-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .pos-badge { font-size: 13px; padding: 3px 10px; border-radius: 999px; border: 1px solid #30363d; }
  .pos-badge.bull { border-color: #26a641; }
  .pos-badge.bear { border-color: #f85149; }
  .pos-badge.flat { color: #8b949e; }
  .trade b.bullish { color: #26a641; }
  .trade b.bearish { color: #f85149; }
  .trade-row { display: flex; align-items: center; gap: 10px; margin: 12px 0 4px; flex-wrap: wrap; }
  .trade-row label { color: #8b949e; font-size: 14px; }
  .trade-row input { width: 110px; padding: 8px; background: #0d1117; border: 1px solid #30363d;
    border-radius: 6px; color: #c9d1d9; font-size: 15px; }
  .trade-row button { padding: 8px 20px; border: none; border-radius: 6px; color: #fff;
    font-weight: 600; font-size: 14px; cursor: pointer; }
  .trade-row button.buy { background: #238636; }
  .trade-row button.sell { background: #b62324; }
  .trade-row button:disabled { opacity: .4; cursor: not-allowed; }
  .trade-msg { color: #8b949e; font-size: 13px; }
  .trade-summary { font-size: 13px; color: #8b949e; margin: 6px 0; }
  .trade-log { margin-top: 8px; border-top: 1px solid #21262d; }
  .log-entry { border-bottom: 1px solid #161b22; padding: 5px 0; }
  .log-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
  .log-snap { font-size: 12px; color: #8b949e; margin: 3px 0 0 44px; }
  .log-snap details { display: inline-block; margin-left: 6px; }
  .log-snap summary { cursor: pointer; color: #58a6ff; }
  .log-snap pre { white-space: pre-wrap; margin: 6px 0 0; color: #c9d1d9; font-size: 12px; }
  .log-side { text-transform: uppercase; font-weight: 600; width: 34px; }
  .log-side.bull { color: #26a641; }
  .log-side.bear { color: #f85149; }
  .log-time { margin-left: auto; color: #6e7681; font-size: 12px; }
  .log-open { color: #d29922; }
  .log-undo { background: none; border: none; color: #6e7681; cursor: pointer; font-size: 13px; padding: 0 4px; }
  .log-undo:hover { color: #f85149; }

  /* Research controls: scrub + toggles */
  .research { display: flex; justify-content: space-between; align-items: center; gap: 12px;
    flex-wrap: wrap; margin: 6px 0 4px; }
  .scrub { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 240px; }
  .scrub input[type=range] { flex: 1; accent-color: #58a6ff; }
  .scrub-label { color: #8b949e; font-size: 13px; white-space: nowrap; }
  .mini { padding: 2px 9px; font-size: 13px; background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; color: #c9d1d9; cursor: pointer; }
  .mini.live { border-color: #238636; }
  .toggles { color: #8b949e; font-size: 13px; }
  .toggles summary { cursor: pointer; }
  .toggle-grid { display: flex; gap: 20px; margin-top: 8px; }
  .toggle-grid .grp { display: block; text-transform: uppercase; letter-spacing: .04em;
    font-size: 11px; color: #6e7681; margin-bottom: 4px; }
  .toggle-grid label { display: block; padding: 1px 0; text-transform: capitalize; }
  .patterns { display: flex; gap: 6px; flex-wrap: wrap; margin: 4px 0 8px; }
  .pchip { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid #30363d; }
  .pchip.confirmed { border-color: #26a641; color: #26a641; }
  .pchip.failed { border-color: #6e7681; color: #6e7681; }
  .pchip.forming { border-color: #d29922; color: #d29922; }
</style>
