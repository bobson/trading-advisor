<script lang="ts">
  import { onMount } from 'svelte'
  import PriceChart from './lib/PriceChart.svelte'
  import { getPairs, getTimeframes, getAnalysis, type Pair, type Analysis, type PanelToggles } from './lib/api'

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
    levels: true, fib: true, swings: true, patterns: true, marker: true,
    volume: true, rsi: true, macd: true, adx: false, atr: false,
  }
  const TOGGLE_KEY = 'tw.toggles'
  function loadToggles(): PanelToggles {
    try { return { ...DEFAULT_TOGGLES, ...JSON.parse(localStorage.getItem(TOGGLE_KEY) || '{}') } }
    catch { return { ...DEFAULT_TOGGLES } }
  }
  let toggles = $state<PanelToggles>(loadToggles())
  $effect(() => { localStorage.setItem(TOGGLE_KEY, JSON.stringify(toggles)) })
  const OVERLAY_KEYS: (keyof PanelToggles)[] = ['levels', 'fib', 'swings', 'patterns', 'marker']
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
  }

  // Auto-refresh: poll every REFRESH_MS while `auto` is on. NEVER calls Claude (explain=false),
  // so it can't silently burn API credits.
  $effect(() => {
    if (!auto) return
    const id = setInterval(() => run(false), REFRESH_MS)
    return () => clearInterval(id)
  })

  const conf = $derived(result?.confluence)

  const fmtLevel = (x: any) => (x ? `${x.price.toLocaleString()} (${x.touches} touches)` : '—')
</script>

<main>
  <h1>🧙 Trading Wizard</h1>
  <p class="tag">Reads the chart, explains its reasoning — not financial advice.</p>

  <div class="controls">
    <select bind:value={symbol} onchange={() => (asOfBar = null)}>
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
    <div class="verdict" class:bull={conf?.bias === 'bullish'} class:bear={conf?.bias === 'bearish'}>
      <span>Bias: <b>{conf?.bias}</b></span>
      <span>confidence <b>{((conf?.confidence ?? 0) * 100).toFixed(0)}%</b></span>
      <span>{conf?.agreeing_categories} categories agree</span>
      {#if conf?.triggered}<span class="flag">SETUP FLAGGED</span>{/if}
    </div>

    {#if result.base_rate}
      <p class="track">
        📊 Track record: {result.base_rate.bias} setups like this were right
        <b>{(result.base_rate.win_rate * 100).toFixed(0)}%</b> of the time
        ({result.base_rate.n} past cases, {result.base_rate.horizon}-bar horizon).
        <b>A base rate, not a prediction.</b>
      </p>
    {/if}

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

    <PriceChart data={result.chart} {toggles} />

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
</main>

<style>
  :global(body) { margin: 0; background: #0e1117; color: #c9d1d9;
    font: 15px/1.5 -apple-system, system-ui, sans-serif; }
  main { max-width: 1000px; margin: 0 auto; padding: 24px; }
  h1 { margin: 0 0 4px; }
  .tag { color: #8b949e; margin: 0 0 20px; }
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
  .verdict.bull { border-color: #26a641; }
  .verdict.bear { border-color: #f85149; }
  .flag { background: #238636; color: #fff; padding: 2px 8px; border-radius: 999px; font-size: 12px; }
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
