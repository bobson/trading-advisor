<script lang="ts">
  // Pattern scanner: every pair × the chosen timeframes, patterns worth a look NOW — fresh breakouts,
  // patterns about to break out, and ones still in play — each with how that pattern type has done
  // historically (counts; a % only with 20+ cases). What happened before, not odds for this one.
  import { getScan, qualityText, recordText, type ScanResult, type ScanRow } from './api'

  let { onOpen }: { onOpen?: (symbol: string, timeframe: string) => void } = $props()

  const ALL_TFS = ['1d', '4h', '1h']
  let tfs = $state<string[]>(['1d'])
  let result = $state<ScanResult | null>(null)
  let loading = $state(false)
  let error = $state<string | null>(null)

  async function scan() {
    loading = true; error = null
    try { result = await getScan(tfs) } catch (e: any) { error = e.message }
    finally { loading = false }
  }
  $effect(() => { tfs; scan() })

  const group = (life: string) => (result?.rows ?? []).filter((r) => r.lifecycle === life)
  const stage = (r: ScanRow) =>
    r.lifecycle === 'fresh' ? `broke out ${r.bars_since_breakout === 0 ? 'on the last candle' : `${r.bars_since_breakout} candle${r.bars_since_breakout === 1 ? '' : 's'} ago`}`
    : r.lifecycle === 'in_play' ? `broke out ${r.bars_since_breakout} candles ago — still in play`
    : r.distance_atr == null ? 'forming' : `forming — ${r.distance_atr} ATR from the breakout`
  const dirText = (d: string) => (d === 'neutral' ? 'either way' : d)
  const fmt = (x: number | null) => (x == null ? '—' : Math.abs(x) >= 100 ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : x.toString())
  const SECTIONS = [
    ['fresh', 'Fresh breakouts', 'broke out in the last few candles'],
    ['forming', 'About to break out', 'closest to the breakout level first'],
    ['in_play', 'Still in play', 'broke out earlier, no target or failure yet'],
  ]
</script>

<section class="scanner">
  <h2>🔎 Pattern scanner</h2>
  <p class="tag">Every pair, the patterns worth a look right now. Beside each: how that pattern type has
    done in this app's history after a breakout — the past, not odds for this one.</p>
  <div class="controls">
    {#each ALL_TFS as t}
      <label><input type="checkbox" value={t} bind:group={tfs} /> {t}</label>
    {/each}
    <button onclick={scan} disabled={loading || !tfs.length}>{loading ? 'Scanning…' : 'Scan again'}</button>
    {#if result}<span class="muted small">{result.markets} charts scanned {new Date(result.scanned_at * 1000).toLocaleTimeString()}</span>{/if}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading && !result}<p class="muted">Scanning every pair — the first scan refreshes candles and can take ~20 s…</p>{/if}

  {#if result}
    {#each SECTIONS as [life, title, hint]}
      {@const rows = group(life)}
      <h3>{title} <span class="muted small">({rows.length}) — {hint}</span></h3>
      {#if rows.length}
        <div class="rows">
          {#each rows as r}
            <div class="row {life}">
              <div class="main">
                <b>{r.symbol}</b> <span class="tf">{r.timeframe}</span> · <b>{r.type}</b>
                <span class="dir">({dirText(r.direction)})</span> · {stage(r)}
              </div>
              <div class="levels muted small">
                {`breakout ${fmt(r.breakout_level)} · invalidation ${fmt(r.invalidation_level)}`
                 + (r.target != null ? ` · target ${fmt(r.target)}` : '') + ` · last close ${fmt(r.last_close)}`}
              </div>
              <div class="record small">History: {recordText(r.record)}</div>
              <div class="record small muted">This one's {qualityText(r.quality_band)}</div>
              <button class="open" onclick={() => onOpen?.(r.symbol, r.timeframe)}>open chart ▶</button>
            </div>
          {/each}
        </div>
      {:else}<p class="muted small">None right now.</p>{/if}
    {/each}
    {#if result.skipped.length}
      <p class="muted small">Skipped: {result.skipped.map((s) => `${s.symbol} ${s.timeframe}`).join(', ')} (no data).</p>
    {/if}
  {/if}
</section>

<style>
  .scanner { max-width: 1000px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 8px; }
  .controls label { color: #c9d1d9; font-size: 14px; display: inline-flex; gap: 5px; align-items: center; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; cursor: pointer; }
  button:disabled { opacity: .6; cursor: default; }
  h3 { margin: 16px 0 6px; font-size: 15px; }
  .rows { display: flex; flex-direction: column; gap: 8px; }
  .row { position: relative; border: 1px solid #30363d; border-radius: 8px; padding: 10px 110px 10px 12px; }
  .row.fresh { border-left: 3px solid #c9d1d9; }
  .main { font-size: 14px; }
  .tf { color: #8b949e; }
  .dir { color: #8b949e; }
  .levels { margin-top: 2px; }
  .record { margin-top: 4px; color: #c9d1d9; }
  .open { position: absolute; right: 10px; top: 10px; }
  @media (max-width: 640px) { .row { padding-right: 12px; } .open { position: static; margin-top: 8px; } }
</style>
