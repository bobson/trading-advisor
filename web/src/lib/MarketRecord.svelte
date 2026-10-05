<script lang="ts">
  // Simplification pass 1 — the morning record for the market + timeframe on screen: this morning's
  // frozen read, whether the engine's read of the last CLOSED candle has changed since, the last
  // judged read (✓/✗ and why), and the record here vs a coin flip. Shown beside the live read, never
  // fed into it. Read-only — no run, no Claude call.
  import { getMorningMarket, type MarketBox } from './api'
  import { mark, outcomeSentence, readSentence, summarySentence, whySentence } from './forwardText'

  let { symbol, timeframe, refreshKey, onOpenMorning }: {
    symbol: string; timeframe: string; refreshKey: string; onOpenMorning?: () => void
  } = $props()

  let box = $state<MarketBox | null>(null)
  let failed = $state(false)
  $effect(() => {
    refreshKey
    const s = symbol, tf = timeframe
    getMorningMarket(s, tf)
      .then((b) => { if (s === symbol && tf === timeframe) { box = b; failed = false } })
      .catch(() => { failed = true; box = null })
  })

  const TIER: Record<string, string> = { confirmed: 'confirmed setup', notable: 'notable', no_setup: 'no setup' }
  const label = (kind: string, dir: string | null, tier: string) =>
    kind === 'directional' ? `${dir === 'bullish' ? '▲ up' : '▼ down'} (${TIER[tier] ?? tier})` : 'no setup'
  const changed = $derived(box?.latest && box.now
    ? box.now.read_kind !== box.latest.read_kind || box.now.direction !== box.latest.direction : null)
</script>

{#if box && (box.latest || box.last_judged)}
  <section class="mrec">
    <div class="head"><b>☀️ Morning record</b> <span class="muted">— {symbol} {timeframe}</span>
      {#if onOpenMorning}<button class="mini" onclick={onOpenMorning}>full report</button>{/if}</div>

    {#if box.latest}
      {@const r = box.latest}
      <p><span class="k">Morning read</span> <span class="muted">{r.run_date}</span> — {readSentence(r)}.
        {#if r.outcome}<br /><span class="muted">→ price {outcomeSentence(r)}.</span>{:else}<span class="muted"> Judged after {r.horizon} candles.</span>{/if}</p>
      {#if box.now}
        <p><span class="k">Since then</span>
          {#if box.now.new_candles === 0}no new closed candle — the read is unchanged.
          {:else}{box.now.new_candles} new closed candle{box.now.new_candles > 1 ? 's' : ''}; the engine's read now is
            <b>{label(box.now.read_kind, box.now.direction, box.now.tier)}</b>
            {#if changed}<span class="chg">— changed from {label(r.read_kind, r.direction, r.tier)}</span>{:else}<span class="muted">— same as the morning</span>{/if}.
          {/if}</p>
      {/if}
    {/if}

    {#if box.last_judged && box.last_judged.id !== box.latest?.id}
      {@const j = box.last_judged}
      {@const why = whySentence(j, box.caution_labels, box.caution_status)}
      <p><span class="k">Last judged</span> <span class="mark {mark(j) === '✓' ? 'good' : mark(j) === '✗' ? 'bad' : ''}">{mark(j)}</span>
        <span class="muted">{j.run_date}</span> — {readSentence(j)} → price {outcomeSentence(j)}.
        {#if why}<br /><span class="why">{mark(j) === '✗' ? 'Why it may have gone wrong: ' : ''}{why}</span>{/if}</p>
    {/if}

    <p class="muted small"><span class="k">Record here</span> {summarySentence(box.summary)}
      {#if box.pending}{box.pending} waiting to be judged.{/if}</p>
  </section>
{:else if box}
  <p class="muted small mnone">☀️ No morning read for {symbol} {timeframe} yet{failed ? '' : ' — the 08:00 run reads only the morning watchlist (config.yaml)'}.</p>
{/if}

<style>
  .mrec { border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; margin: 0 0 12px; font-size: 14px; }
  .mrec p { margin: 6px 0 0; }
  .head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .k { color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; margin-right: 4px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .mark { font-weight: 700; }
  .mark.good { color: #3fb950; }
  .mark.bad { color: #f85149; }
  .why { color: #d29922; }
  .chg { color: #d29922; }
  .mnone { margin: 0 0 12px; }
  button.mini { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; font-size: 11px; padding: 1px 6px; cursor: pointer; margin-left: auto; }
</style>
