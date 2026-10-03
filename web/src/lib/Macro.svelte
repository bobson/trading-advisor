<script lang="ts">
  // ROADMAP D3: the macro backdrop — conditions, never direction. The calendar and headlines come
  // from public feeds (cached); the driver line is a measured CO-MOVEMENT, not a cause.
  import { getMacro, type MacroEvent, type MacroHeadline, type MacroPage } from './api'

  let { symbol: initial = 'BTC/USDT', pairs = [] }: { symbol?: string; pairs?: { symbol: string }[] } = $props()
  // svelte-ignore state_referenced_locally
  let symbol = $state(initial)            // starts on the app's market, then independent
  let page = $state<MacroPage | null>(null)
  let error = $state<string | null>(null)
  let tab = $state<'market' | 'central_bank' | 'commodity' | 'all'>('market')
  let showLow = $state(false)

  $effect(() => { const s = symbol; page = null; error = null; getMacro(s).then((p) => (page = p)).catch((e) => (error = e.message)) })

  const local = (ts: number) => new Date(ts * 1000).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const ago = (ts: number | null) => ts == null ? '' : `${Math.max(1, Math.round((Date.now() / 1000 - ts) / 60))} min ago`
  function events(p: MacroPage): MacroEvent[] {
    let ev = p.calendar.events.filter((e) => showLow || ['High', 'Medium', 'Holiday'].includes(e.impact))
    if (tab === 'market') ev = ev.filter((e) => p.currencies.includes(e.currency))
    else if (tab !== 'all') ev = ev.filter((e) => e.kind === tab)
    return ev
  }
  const soon = (e: MacroEvent, now: number) => e.ts >= now && e.ts - now <= 6 * 3600
  const past = (e: MacroEvent, now: number) => e.ts < now
  const headlineGroups = (p: MacroPage): { title: string; list: MacroHeadline[] }[] =>
    [{ title: `About ${p.symbol}`, list: p.headlines.for_symbol }, { title: 'Latest overall', list: p.headlines.all.slice(0, 12) }]
  const cell = (p: MacroPage, a: string, b: string) => a === b ? null : p.correlation.pairs.find((x) => (x.a === a && x.b === b) || (x.a === b && x.b === a))?.rho ?? null
</script>

<section class="macro">
  <h2>🌍 Macro context</h2>
  <p class="tag">The backdrop around a market: scheduled events, headlines, what it has been moving with, and which of
    your markets are really one bet. Conditions, never direction.</p>
  <label class="pick">market <select bind:value={symbol}>
    {#each (pairs.length ? pairs.map((x) => x.symbol) : [symbol]) as s}<option>{s}</option>{/each}</select></label>
  {#if error}<p class="error">{error}</p>{/if}
  {#if !page && !error}<p class="muted">Loading the calendar and headlines…</p>{/if}

  {#if page}
    {@const p = page}
    <div class="two">
      <div class="box">
        <h3>What moves {p.symbol}</h3>
        <p class="small muted">Conventionally (convention, not measured): {p.drivers.conventional.join('; ')}.</p>
        <p><b>Measured co-movement:</b> {p.drivers.text}</p>
        <p class="small muted">{p.drivers.items.map((i) => `${i.proxy}: ${i.rho == null ? '—' : (i.rho > 0 ? '+' : '') + i.rho.toFixed(2)} (${i.n} days)`).join(' · ')}</p>
      </div>
      <div class="box">
        <h3>Your markets as bets <span class="muted small">daily returns, last {p.correlation.window} days</span></h3>
        {#if p.correlation.warnings.length}
          <ul class="warn">{#each p.correlation.warnings as w}<li>{w.text}</li>{/each}</ul>
        {:else}<p class="small">No pair moved together above {p.correlation.threshold}.</p>{/if}
        <div class="tablewrap"><table class="corr">
          <thead><tr><th></th>{#each p.correlation.symbols as s}<th>{s.split('/')[0]}</th>{/each}</tr></thead>
          <tbody>{#each p.correlation.symbols as a}<tr><th>{a.split('/')[0]}</th>
            {#each p.correlation.symbols as b}{@const r = cell(p, a, b)}
              <td class:hi={r != null && r >= p.correlation.threshold}>{a === b ? '—' : r == null ? '·' : r.toFixed(2)}</td>{/each}</tr>{/each}</tbody>
        </table></div>
      </div>
    </div>

    <h3>Calendar <span class="muted small">{p.calendar.source}{p.calendar.stale ? ' · stale copy' : ''} · {p.calendar.note}</span></h3>
    <div class="tabs">
      <button class:on={tab === 'market'} onclick={() => (tab = 'market')}>{p.symbol} ({p.currencies.join(', ')})</button>
      <button class:on={tab === 'central_bank'} onclick={() => (tab = 'central_bank')}>Central banks</button>
      <button class:on={tab === 'commodity'} onclick={() => (tab = 'commodity')}>Commodities</button>
      <button class:on={tab === 'all'} onclick={() => (tab = 'all')}>All</button>
      <label class="small"><input type="checkbox" bind:checked={showLow} /> low impact too</label>
    </div>
    {#if events(p).length}
      <div class="tablewrap"><table>
        <thead><tr><th>when (your time)</th><th></th><th>event</th><th>impact</th><th>consensus</th><th>previous</th></tr></thead>
        <tbody>{#each events(p) as e}
          <tr class:soon={soon(e, p.now)} class:past={past(e, p.now)}>
            <td>{local(e.ts)}{soon(e, p.now) ? ' · soon' : ''}</td><td>{e.currency}</td><td>{e.title}</td>
            <td class="imp {e.impact.toLowerCase()}">{e.impact}</td><td>{e.forecast ?? '—'}</td><td>{e.previous ?? '—'}</td></tr>
        {/each}</tbody>
      </table></div>
    {:else}<p class="muted small">No events in this view this week.</p>{/if}

    <h3>Headlines <span class="muted small">headline and link only · {p.headlines.stale ? 'stale copy · ' : ''}updated {ago(p.headlines.fetched_at)}</span></h3>
    <p class="small muted">Shown here only, never given to the explanation: headlines often carry directional wording.</p>
    {#each headlineGroups(p) as g}
      <h4>{g.title}</h4>
      {#if g.list.length}
        <ul class="news">{#each g.list as h}<li><a href={h.link} target="_blank" rel="noopener noreferrer">{h.headline}</a>
          <span class="muted small"> — {h.source}{h.ts ? `, ${ago(h.ts)}` : ''}</span></li>{/each}</ul>
      {:else}<p class="muted small">none right now</p>{/if}
    {/each}
  {/if}
</section>

<style>
  .macro { max-width: 1100px; }
  .tag { color: #8b949e; margin: 0 0 10px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .pick { color: #c9d1d9; font-size: 14px; }
  select { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px; font-size: 14px; }
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin: 12px 0; }
  .box { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; font-size: 14px; }
  h3 { margin: 16px 0 6px; font-size: 15px; }
  .box h3 { margin-top: 0; }
  h4 { margin: 10px 0 4px; font-size: 13px; color: #8b949e; }
  .warn { margin: 0 0 8px; padding-left: 18px; color: #d29922; font-size: 13px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 6px; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 13px; }
  button.on { border-color: #58a6ff; color: #58a6ff; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #161b22; }
  th { color: #8b949e; font-weight: 500; }
  table.corr td { text-align: center; }
  td.hi { color: #d29922; font-weight: 600; }
  tr.soon td { color: #d29922; }
  tr.past td { color: #6e7681; }
  .imp.high { color: #f85149; }
  .imp.medium { color: #d29922; }
  .news { margin: 0; padding-left: 18px; font-size: 14px; }
  .news a { color: #c9d1d9; }
</style>
