<script lang="ts">
  // ROADMAP A8 — the morning report: the engine's live, forward record. Every morning at 08:00
  // Skopje the reads are frozen; each is judged later against a fixed, versioned rule.
  // Simplification pass 1: the page answers "was it right, why was it wrong, what do the misses have in
  // common" in plain words first; today's reads next; tables and rule text under Details. The results
  // are shown beside the reads, never fed into them. Counts always; a rate only with 20+ cases.
  import { CAUTION_TAG, getMorning, runMorning, type ForwardRead, type MorningReport } from './api'
  import { coinSentence, mark, outcomeSentence, readSentence, summarySentence, whySentence } from './forwardText'
  import JournalForm from './JournalForm.svelte'

  let { onOpen }: { onOpen?: (symbol: string, timeframe: string) => void } = $props()

  let report = $state<MorningReport | null>(null)
  let date = $state<string>('')
  let loading = $state(false)
  let error = $state<string | null>(null)
  let started = $state(false)

  // D1: log my own read before the engine's is revealed (latest morning only; per symbol)
  const HIDE_KEY = 'tw.hideMorning'
  let hideReads = $state((() => { try { return localStorage.getItem(HIDE_KEY) === '1' } catch { return false } })())
  $effect(() => { try { localStorage.setItem(HIDE_KEY, hideReads ? '1' : '0') } catch { /* private mode */ } })
  let revealed = $state<Record<string, boolean>>({})
  let logFor = $state<string | null>(null)
  let logTf = $state('1d')
  const latestDate = $derived(report?.runs.find((r) => r.status !== 'gap')?.run_date ?? null)
  const isLatest = $derived(!!report && report.run_date === latestDate)
  const hidden = (sym: string) => hideReads && isLatest && !revealed[`${report?.run_date}|${sym}`]
  function reveal(sym: string) { revealed = { ...revealed, [`${report?.run_date}|${sym}`]: true } }
  function openLog(sym: string) { logFor = sym; logTf = report?.watchlist.timeframes.at(-1) ?? '1d' }

  async function load() {
    loading = true; error = null
    try { report = await getMorning(date || undefined); if (!date && report.run_date) date = report.run_date }
    catch (e: any) { error = e.message } finally { loading = false }
  }
  $effect(() => { date; load() })

  async function runNow() {
    try { await runMorning(); started = true; setTimeout(() => { started = false; load() }, 60000) }
    catch (e: any) { error = e.message }
  }

  const OUT: Record<string, [string, string]> = {
    followed_through: ['followed through', 'good'], invalidated: ['invalidated', 'bad'],
    expired: ['expired', 'muted'], ambiguous: ['ambiguous', 'muted'], unscorable: ['unscorable', 'muted'],
    correct: ['correct (stayed in range)', 'good'], missed_move: ['missed move', 'bad'],
  }
  const TIER: Record<string, string> = { confirmed: 'confirmed', notable: 'notable', no_setup: 'no setup' }
  const fmt = (x: number | null) => (x == null ? '—' : Math.abs(x) >= 100
    ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Number(x.toPrecision(6)).toString())
  const arrow = (d: string | null) => (d === 'bullish' ? '▲' : d === 'bearish' ? '▼' : '')
  const readText = (r: ForwardRead) => r.read_kind === 'directional'
    ? `${r.direction} — next level ${fmt(r.next_level)}, invalidation ${fmt(r.invalidation)}`
    : `no directional read — range ${fmt(r.range_low)} to ${fmt(r.range_high)}`
  const barDate = (t: number) => new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
  const cell = (sym: string, tf: string) => report?.grid.find((r) => r.symbol === sym && r.timeframe === tf)
  const gridSymbols = $derived([...new Set([...(report?.watchlist.symbols ?? []), ...(report?.grid ?? []).map((r) => r.symbol)])])
  const skipped = $derived(Array.isArray(report?.run?.skipped) ? report!.run!.skipped : [])
  const rate = (r: number | null) => (r == null ? '' : ` · ${Math.round(r * 100)}%`)
  const DIR_OUT = ['followed_through', 'invalidated', 'expired', 'ambiguous']
  // R2: the caution conditions frozen with each read
  const flagsOn = (r: ForwardRead) => Object.entries(r.caution ?? {}).filter(([, v]) => v).map(([k]) => report?.caution_labels?.[k] ?? k)
  const sideText = (x: { engine: { n: number; counts: Record<string, number>; rate: number | null } }, kind: string) =>
    x.engine.n === 0 ? '—' : kind === 'directional'
      ? `${x.engine.counts.followed_through} followed · ${x.engine.counts.invalidated} invalidated · ${x.engine.counts.expired + x.engine.counts.ambiguous} other (${x.engine.n})${rate(x.engine.rate)}`
      : `${x.engine.counts.correct} correct · ${x.engine.counts.missed_move} missed (${x.engine.n})${rate(x.engine.rate)}`
  // pass 1: judged directional reads one by one; no-setup reads summed in one line
  const judgedDir = $derived((report?.review ?? []).filter((r) => r.read_kind === 'directional'))
  const judgedRange = $derived((report?.review ?? []).filter((r) => r.read_kind === 'range'))
  const whyText = (r: ForwardRead) => whySentence(r, report?.caution_labels ?? {}, report?.caution_status ?? {})
  const totals = $derived(report?.summary?.directional.engine.counts)
  const BENIGN = ['already read today', 'no new closed candle since the last read']
  const clock = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const attemptText = (a: { trigger: string; status: string; new_reads: number; resolved: number; skipped: { reason: string }[] }) => {
    const bad = a.skipped.filter((s) => !BENIGN.includes(s.reason)).length
    const what = a.new_reads || a.resolved ? `${a.new_reads} new reads, ${a.resolved} judged` : 'nothing new'
    return `${a.trigger === 'schedule' ? '08:00 timer' : a.trigger === 'api' ? 'Run now button' : 'by hand'} · ${a.status} · ${what}${bad ? ` · ${bad} market(s) failed` : ''}`
  }
</script>

<section class="morning">
  <h2>☀️ Morning report</h2>
  <p class="tag">The engine's live record. Every morning at {report?.schedule ?? '08:00 Europe/Skopje'} it freezes a
    read for each market; each read is judged later by a fixed rule. What happened — not a forecast.</p>

  <div class="controls">
    {#if report?.runs.length}
      <label>morning
        <select bind:value={date}>
          {#each report.runs as r}
            <option value={r.run_date} disabled={r.status === 'gap'}>{r.run_date}{r.status === 'gap' ? ' — missed (gap)' : r.status !== 'ok' ? ` — ${r.status}` : ''}</option>
          {/each}
        </select>
      </label>
    {/if}
    <button onclick={runNow} disabled={started}>{started ? 'Started — refreshing in a minute…' : 'Run now'}</button>
    {#if report}<span class="muted small">next run {new Date(report.next_run).toLocaleString()} · day one: {report.first_run ?? 'not started yet'}</span>{/if}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading && !report}<p class="muted">Loading…</p>{/if}

  {#if report && !report.run_date}
    <p class="muted">No morning has run yet. The first run is day one of the forward record.</p>
  {/if}

  {#if report?.run_date}
    <div class="summary">
      <b>The record so far</b>
      <p>{summarySentence(report.summary)}</p>
    </div>

    <!-- 1. WAS IT RIGHT? -->
    <h3>Judged this morning</h3>
    {#if judgedDir.length}
      {#each judgedDir as r}
        <div class="judged {mark(r) === '✓' ? 'good' : mark(r) === '✗' ? 'bad' : ''}">
          <div class="jhead"><span class="mark">{mark(r)}</span> <b>{r.symbol}</b> {r.timeframe}
            <span class="muted small">· read on {r.run_date}</span>
            {#if onOpen}<button class="mini" onclick={() => onOpen?.(r.symbol, r.timeframe)}>open chart</button>{/if}</div>
          <p>{readSentence(r)} → price {outcomeSentence(r)}.</p>
          {#if whyText(r)}<p class="why">{mark(r) === '✗' ? 'Why it may have gone wrong: ' : ''}{whyText(r)}</p>{/if}
          <p class="muted small">{coinSentence(r)}</p>
        </div>
      {/each}
    {:else if !judgedRange.length}
      <p class="muted small">Nothing was judged this morning. 30m and 1h reads are judged the next morning, 4h after
        about a week, 1d after about a month.</p>
    {/if}
    {#if judgedRange.length}
      {@const ok = judgedRange.filter((r) => r.outcome === 'correct').length}
      <p class="small">No-setup reads judged: <b>{judgedRange.length}</b> — {ok} stayed in their range,
        {judgedRange.length - ok} missed a move. <span class="muted">These ranges are narrow (about 2 ATR), so price
        usually leaves them; a missed move here is common, not a failed call.</span></p>
      <details class="small"><summary>show them</summary>
        <ul class="rlist">{#each judgedRange as r}<li>{mark(r)} <b>{r.symbol}</b> {r.timeframe} — {readSentence(r)} → {outcomeSentence(r)}.</li>{/each}</ul>
      </details>
    {/if}
    {#if Object.keys(report.pending).length}
      <p class="muted small">Waiting to be judged: {Object.entries(report.pending).map(([tf, n]) => `${n} × ${tf}`).join(', ')}</p>
    {/if}

    <!-- 2. WHAT DO THE MISSES HAVE IN COMMON? -->
    <h3>What the misses have in common</h3>
    {#if report.misses_in_common?.length}
      <p class="small muted">All judged directional reads so far: {totals?.invalidated ?? 0} invalidated (misses),
        {totals?.followed_through ?? 0} followed through (hits). A condition matters only if it shows up much more often on
        misses than on hits.</p>
      <ul class="common">
        {#each report.misses_in_common.filter((m) => m.misses_flagged || m.hits_flagged) as m}
          <li><b>{m.label}</b>: on {m.misses_flagged} of {m.misses} misses, and on {m.hits_flagged} of {m.hits} hits.
            {#if report.caution_status?.[m.code]}<span class="muted small">History: {CAUTION_TAG[report.caution_status[m.code]] ?? report.caution_status[m.code]}.</span>{/if}</li>
        {/each}
      </ul>
      {@const never = report.misses_in_common.filter((m) => !m.misses_flagged && !m.hits_flagged)}
      {#if never.length}<p class="muted small">Not flagged on any of them: {never.map((m) => m.label.toLowerCase()).join(', ')}.</p>{/if}
      {#if report.misses_in_common.some((m) => !m.enough)}
        <p class="muted small">Too few to conclude — this needs 20+ misses and 20+ hits. Until then it's a list of what to
          watch, not a finding. A difference that holds up becomes a test to set in advance (Experiments), not a rule
          changed on the spot.</p>
      {/if}
    {:else}
      <p class="muted small">No judged directional read with recorded cautions yet.</p>
    {/if}

    <!-- 2. TODAY'S READS -->
    <h3>Today's reads <span class="muted small">— frozen on {report.run_date}, judged later</span></h3>
    {#if isLatest}
      <p class="small"><label><input type="checkbox" bind:checked={hideReads} /> hide the engine's reads until I've
        logged my own call for that market</label> <span class="muted">— your calls go to the Journal, a separate record
        from the engine's (different bars, different rule).</span></p>
    {/if}
    <div class="tablewrap"><table class="grid">
      <thead><tr><th></th>{#each report.watchlist.timeframes as tf}<th>{tf}</th>{/each}</tr></thead>
      <tbody>
        {#each gridSymbols as sym}
          <tr>
            <th>{sym}
              {#if isLatest}<br /><button class="mini" onclick={() => openLog(sym)}>📝 my call</button>
                {#if hidden(sym)}<button class="mini" onclick={() => reveal(sym)}>reveal</button>{/if}{/if}</th>
            {#each report.watchlist.timeframes as tf}
              {@const r = cell(sym, tf)}
              <td>
                {#if r && hidden(sym)}
                  <span class="muted small">hidden</span>
                {:else if r}
                  <button class="cellbtn" onclick={() => onOpen?.(sym, tf)} title={`${readText(r)} · closed bar ${barDate(r.bar_time)} · engine ${r.engine_commit}`}>
                    <span class="tier {r.tier}">{TIER[r.tier] ?? r.tier}</span>
                    {#if r.read_kind === 'directional'}<span class="dir {r.direction}">{arrow(r.direction)} {r.direction}</span>{/if}
                    <span class="small muted">{fmt(r.price)}</span>
                    {#if flagsOn(r).length}<span class="warn small" title={flagsOn(r).join('\n')}>⚠ {flagsOn(r).length} caution{flagsOn(r).length > 1 ? 's' : ''}</span>{/if}
                  </button>
                {:else}
                  {@const why = skipped.find((s) => s.symbol === sym && s.timeframe === tf)?.reason}
                  <span class="muted small" title={why}>{why ? `skipped — ${why.replace(/^data: /, '').split(' in .env')[0].split(' (')[0]}` : '—'}</span>
                {/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table></div>
    {#if logFor && isLatest}
      <div class="logbox">
        <b>My call on {logFor}</b>
        <label class="small">timeframe <select bind:value={logTf}>{#each report.watchlist.timeframes as tf}<option>{tf}</option>{/each}</select></label>
        <button class="mini" onclick={() => (logFor = null)}>close</button>
        {#key `${logFor}|${logTf}`}
          <JournalForm symbol={logFor} timeframe={logTf} source="morning" lastClose={cell(logFor, logTf)?.price ?? null}
            verdictVisible={!hidden(logFor)} explanationVisible={!hidden(logFor) && report.syntheses.some((x) => x.symbol === logFor)}
            onLogged={() => logFor && reveal(logFor)} />
        {/key}
      </div>
    {/if}
    <p class="muted small">Closed candles only. Forex, gold and oil get no new read when their market was closed.
      Engine {report.grid[0]?.engine_commit ?? report.run?.engine_commit ?? '—'}{report.grid[0]?.engine_dirty ? ' (uncommitted changes)' : ''}.</p>

  {/if}

  {#if report}
  <details class="details">
    <summary>Details — runs, synthesis, scoreboard, caution tables, the rule</summary>
    {#if report.run?.attempt_log?.length}
      <p class="muted small attempts">Runs this morning:
        {#each report.run.attempt_log as a, i}{i ? ' · ' : ' '}<span title={a.skipped.map((s) => `${s.symbol} ${s.timeframe}: ${s.reason}`).join('\n')}>{clock(a.started_at)} {attemptText(a)}</span>{/each}
      </p>
    {/if}
    {#if report.run_date}
    <h3>Cross-timeframe synthesis</h3>
    {#if report.syntheses.length}
      {#each report.syntheses as s}<div class="synth"><b>{s.symbol}</b>{#if hidden(s.symbol)}<p class="muted small">hidden until you log your call or reveal</p>{:else}<p>{s.text}</p>{/if}</div>{/each}
    {:else}
      <p class="muted small">None for this morning (off by default: <code>morning_report.synthesis</code> in config.yaml).</p>
    {/if}
    {/if}
    <!-- SCOREBOARD -->
    <h3>Scoreboard <span class="muted small">— every judged read so far, beside a coin flip scored by the same rule</span></h3>
    {#if report.scoreboard.length}
      <div class="tablewrap"><table>
        <thead><tr><th>rule</th><th>tf</th><th>tier</th><th>reads</th><th>engine</th><th>coin flip (same reads)</th></tr></thead>
        <tbody>
          {#each report.scoreboard as s}
            <tr>
              <td class="muted">v{s.rule_version}</td><td>{s.timeframe}</td><td>{TIER[s.tier] ?? s.tier}</td>
              <td>{s.engine.n}{s.read_kind === 'range' ? ' range' : ''}</td>
              <td>{#if s.read_kind === 'directional'}{DIR_OUT.map((o) => `${s.engine.counts[o]} ${OUT[o][0]}`).join(' · ')}{rate(s.engine.rate)}
                {:else}{s.engine.counts.correct} correct · {s.engine.counts.missed_move} missed{rate(s.engine.rate)}{/if}</td>
              <td class="muted">{#if s.baseline}{DIR_OUT.map((o) => `${s.baseline!.counts[o]} ${OUT[o][0]}`).join(' · ')}{rate(s.baseline.rate)}{:else}—{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table></div>
      <p class="muted small">A % appears only with 20+ reads in a row (followed-through share, or correct share for
        range reads). Overlapping reads aren't independent.</p>
    {:else}
      <p class="muted small">No read has been judged yet.</p>
    {/if}
    <h3>Caution split <span class="muted small">— did reads a caution flagged really go worse? (all timeframes pooled)</span></h3>
    {#if report.caution_split?.rows.length}
      <div class="tablewrap"><table>
        <thead><tr><th>caution</th><th>reads</th><th>when flagged</th><th>when not flagged</th></tr></thead>
        <tbody>
          {#each report.caution_split.rows as c}
            <tr>
              <td>{c.label}{#if report.rule.version !== c.rule_version} <span class="muted">v{c.rule_version}</span>{/if}
                {#if report.caution_status?.[c.code]}<br /><span class="small muted">history: {CAUTION_TAG[report.caution_status[c.code]] ?? report.caution_status[c.code]}</span>{/if}</td>
              <td class="muted">{c.read_kind}</td>
              <td>{sideText(c.flagged, c.read_kind)}{#if c.flagged.baseline && c.flagged.engine.n}<br /><span class="small muted">coin flip: {c.flagged.baseline.counts.followed_through} followed · {c.flagged.baseline.counts.invalidated} invalidated</span>{/if}</td>
              <td>{sideText(c.not_flagged, c.read_kind)}{#if c.not_flagged.baseline && c.not_flagged.engine.n}<br /><span class="small muted">coin flip: {c.not_flagged.baseline.counts.followed_through} followed · {c.not_flagged.baseline.counts.invalidated} invalidated</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table></div>
      <p class="muted small">"history" = what the held-back 30% of past data said (ROADMAP R3); this table is the live
        check of the same conditions. A % appears only with 20+ reads on a side.
        {#if report.caution_split.not_recorded}{report.caution_split.not_recorded} judged read(s) are from before cautions were recorded.{/if}</p>
    {:else}
      <p class="muted small">No judged read with recorded cautions yet{report.caution_split?.not_recorded ? ` (${report.caution_split.not_recorded} judged before cautions were recorded)` : ''}.</p>
    {/if}
    {#if report.gaps.length}<p class="muted small">Missed mornings (gaps, never backfilled): {report.gaps.join(', ')}</p>{/if}
    <h3>How reads are judged — rule v{report.rule.version}</h3><pre>{report.rule.text}</pre>
  </details>
  {/if}
</section>

<style>
  .morning { max-width: 1100px; }
  .tag { color: #8b949e; margin: 0 0 12px; }
  .muted { color: #8b949e; }
  .small { font-size: 12px; }
  .error { color: #f85149; }
  .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 8px; }
  .controls label { display: inline-flex; gap: 6px; align-items: center; color: #c9d1d9; font-size: 14px; }
  select, button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; font-size: 14px; }
  button { cursor: pointer; }
  button:disabled { opacity: .6; cursor: default; }
  h3 { margin: 20px 0 6px; font-size: 15px; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #161b22; vertical-align: top; }
  th { color: #8b949e; font-weight: 500; }
  .grid td { min-width: 110px; }
  .cellbtn { display: flex; flex-direction: column; gap: 2px; align-items: flex-start; width: 100%; padding: 6px 8px; text-align: left; }
  .tier { font-size: 12px; color: #8b949e; }
  .tier.confirmed { color: #c9d1d9; font-weight: 600; }
  .dir.bullish { color: #3fb950; }
  .dir.bearish { color: #f85149; }
  .warn { color: #d29922; }
  button.mini { font-size: 11px; padding: 1px 6px; margin: 3px 3px 0 0; }
  .logbox { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; margin: 10px 0; }
  .logbox label { margin: 0 8px; }
  .chip { border: 1px solid #30363d; border-radius: 10px; padding: 1px 8px; font-size: 12px; white-space: nowrap; }
  .chip.good { color: #3fb950; border-color: #238636; }
  .chip.bad { color: #f85149; border-color: #da3633; }
  .chip.muted { color: #8b949e; }
  .summary { border: 1px solid #30363d; border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
  .summary p { margin: 4px 0 0; }
  .judged { border: 1px solid #30363d; border-left-width: 3px; border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; }
  .judged.good { border-left-color: #238636; }
  .judged.bad { border-left-color: #da3633; }
  .judged p { margin: 4px 0 0; }
  .judged .mark { font-weight: 700; }
  .judged.good .mark { color: #3fb950; }
  .judged.bad .mark { color: #f85149; }
  .judged .why { color: #d29922; }
  .jhead .mini { margin-left: 8px; }
  .common { margin: 6px 0; padding-left: 20px; }
  .common li { margin-bottom: 4px; }
  .rlist { margin: 6px 0; padding-left: 20px; }
  .details { margin-top: 24px; border-top: 1px solid #21262d; padding-top: 10px; }
  .details > summary { cursor: pointer; color: #8b949e; }
  .synth { border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; }
  .synth p { margin: 4px 0 0; white-space: pre-wrap; }
  details { margin-top: 12px; }
  pre { white-space: pre-wrap; font-size: 12px; color: #8b949e; }
  @media (max-width: 640px) { select, button { font-size: 16px; } }
</style>
