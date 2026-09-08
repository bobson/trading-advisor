<script lang="ts">
  import { onMount } from 'svelte'
  import PriceChart from './lib/PriceChart.svelte'
  import { getPairs, getTimeframes, getAnalysis, type Pair, type Analysis } from './lib/api'

  let pairs = $state<Pair[]>([])
  let timeframes = $state<string[]>([])
  let symbol = $state('BTC/USDT')
  let timeframe = $state('1h')
  let explain = $state(false)
  let loading = $state(false)
  let error = $state<string | null>(null)
  let result = $state<Analysis | null>(null)

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

  async function run() {
    loading = true
    error = null
    try {
      result = await getAnalysis(symbol, timeframe, explain)
    } catch (e: any) {
      error = e.message
      result = null
    } finally {
      loading = false
    }
  }

  const conf = $derived(result?.confluence)
</script>

<main>
  <h1>🧙 Trading Wizard</h1>
  <p class="tag">Reads the chart, explains its reasoning — not financial advice.</p>

  <div class="controls">
    <select bind:value={symbol}>
      {#each pairs as p}<option value={p.symbol}>{p.label} ({p.symbol})</option>{/each}
    </select>
    <select bind:value={timeframe}>
      {#each timeframes as t}<option value={t}>{t}</option>{/each}
    </select>
    <label class="explain"><input type="checkbox" bind:checked={explain} /> explain (uses API credit)</label>
    <button onclick={run} disabled={loading}>{loading ? 'Analyzing…' : 'Analyze'}</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if result}
    <div class="verdict" class:bull={conf?.bias === 'bullish'} class:bear={conf?.bias === 'bearish'}>
      <span>Bias: <b>{conf?.bias}</b></span>
      <span>confidence <b>{((conf?.confidence ?? 0) * 100).toFixed(0)}%</b></span>
      <span>{conf?.agreeing_categories} categories agree</span>
      {#if conf?.triggered}<span class="flag">SETUP FLAGGED</span>{/if}
    </div>

    <PriceChart data={result.chart} />

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
  .panel { border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-top: 14px; }
  .panel h2 { margin: 0 0 8px; font-size: 16px; }
  pre { white-space: pre-wrap; margin: 0; color: #c9d1d9; }
</style>
