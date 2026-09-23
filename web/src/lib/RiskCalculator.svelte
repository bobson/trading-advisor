<script lang="ts">
  import { getRisk, getMeasured, getCoinFlip, type RiskResult } from './api'

  let { symbol = 'BTC/USDT', timeframe = '1h' }: { symbol?: string; timeframe?: string } = $props()

  // Inputs (percent-facing where natural; converted to fractions for the API).
  let account = $state(10_000)
  let entry = $state(100)
  let stop = $state(96)
  let riskPct = $state(1) // % of account risked per trade
  let winPct = $state(50)
  // A7: where the win rate came from. Default = a cost-adjusted coin flip (the testing found no
  // edge); 'backtest' only when explicitly chosen; 'manual' once the user types their own.
  let winSource = $state<'coin' | 'backtest' | 'manual'>('coin')
  let coinNote = $state<string | null>(null)
  let payoff = $state(1.5)

  let result = $state<RiskResult | null>(null)
  let error = $state<string | null>(null)
  let measuredNote = $state<string | null>(null)
  let timer: any = null

  function scheduleFetch() {
    clearTimeout(timer)
    timer = setTimeout(fetchRisk, 200)
  }
  async function fetchRisk() {
    try {
      result = await getRisk({
        win_rate: winPct / 100, payoff_ratio: payoff, risk_fraction: riskPct / 100,
        account, entry, stop,
      })
      error = null
    } catch (e: any) {
      error = e.message
    }
  }
  $effect(() => { winPct; payoff; riskPct; account; entry; stop; scheduleFetch() })

  // Default win rate: coin flip minus this instrument's round-trip costs (in units of the risk).
  async function useCoinFlip() {
    if (!(entry > 0 && stop > 0 && entry !== stop && payoff > 0)) return
    try {
      const c = await getCoinFlip(symbol, timeframe, entry, stop, payoff)
      if (winSource !== 'coin') return          // user switched away while this was in flight
      winPct = Math.round(c.win_rate * 1000) / 10
      coinNote = `Coin flip, cost-adjusted: with no edge, a ${payoff}:1 target is hit before the stop ` +
        `${(c.fair_win_rate * 100).toFixed(1)}% of the time; ${symbol} costs of ${c.cost_pct}% round trip ` +
        `(${c.cost_in_r}× your risk, ${c.horizon_bars}-bar hold on ${timeframe}) bring it to ${winPct}% — ` +
        `an expected loss of exactly those costs per trade.`
      measuredNote = null
    } catch (e: any) { coinNote = e.message }
  }
  $effect(() => { symbol; timeframe; entry; stop; payoff; if (winSource === 'coin') useCoinFlip() })
  function chooseCoin() { winSource = 'coin'; useCoinFlip() }

  async function useMeasured() {
    try {
      const m = await getMeasured(symbol, timeframe)
      if (m.win_rate == null) { measuredNote = `No backtest win rate for ${symbol} yet (run the backtest).`; return }
      winSource = 'backtest'
      coinNote = null
      winPct = Math.round(m.win_rate * 1000) / 10
      const ci = m.win_rate_ci ? ` (95% CI ${(m.win_rate_ci[0] * 100).toFixed(0)}–${(m.win_rate_ci[1] * 100).toFixed(0)}%)` : ''
      const thin = m.thin ? ' — THIN SAMPLE, treat as a wide range' : ''
      measuredNote = `Backtest — no edge found: ${(m.win_rate * 100).toFixed(0)}% over ${m.n} cases${ci}${thin}, ` +
        'about a coin flip before costs. ' +
        (m.payoff_ratio == null ? 'Payoff ratio not measured yet — set it yourself.' : '')
    } catch (e: any) { measuredNote = e.message }
  }

  const pct = (x: number) => `${(x * 100).toFixed(1)}%`
  const ruinClass = (p: number) => (p >= 0.5 ? 'bad' : p >= 0.2 ? 'warn' : 'ok')
  const heat = (p: number) => `background:rgba(${Math.round(248 * p + 38 * (1 - p))},${Math.round(81 * p + 134 * (1 - p))},${Math.round(73 * p + 54 * (1 - p))},0.85)`
</script>

<section class="risk">
  <h2>🩹 Risk of ruin & position sizing</h2>
  <p class="tag">The math of survival. Risk too much at too low a win rate and ruin is certain
    regardless of how good the analysis is. These numbers are meant to sober, not reassure.</p>

  <div class="grid-in">
    <label>Account $<input type="number" bind:value={account} min="1" /></label>
    <label>Entry <input type="number" bind:value={entry} step="0.01" /></label>
    <label>Stop <input type="number" bind:value={stop} step="0.01" /></label>
    <label>Risk %/trade <input type="number" bind:value={riskPct} min="0.05" max="99" step="0.05" /></label>
    <label>Win rate % <input type="number" bind:value={winPct} min="1" max="99" step="0.1"
      oninput={() => { winSource = 'manual'; coinNote = null; measuredNote = null }} /></label>
    <label>Payoff (win/loss) <input type="number" bind:value={payoff} min="0.1" step="0.1" /></label>
  </div>
  <div class="row-btn">
    <span class="src-label">Win rate source:</span>
    <button class:active={winSource === 'coin'} onclick={chooseCoin}>Coin flip, cost-adjusted (default)</button>
    <button class:active={winSource === 'backtest'} onclick={useMeasured}>Backtest — no edge found</button>
    {#if winSource === 'manual'}<span class="note">Your own number — the testing found no edge to justify more than the coin flip.</span>{/if}
  </div>
  {#if coinNote && winSource === 'coin'}<p class="note src-note">{coinNote}</p>{/if}
  {#if measuredNote && winSource === 'backtest'}<p class="note src-note">{measuredNote}</p>{/if}

  {#if error}<p class="error">{error}</p>{/if}

  {#if result}
    <div class="cards">
      <div class="card">
        <h3>Position size</h3>
        {#if result.position}
          <div class="big">{result.position.units.toLocaleString()} units</div>
          <div class="line">Position value <b>${result.position.position_value.toLocaleString()}</b> ({result.position.leverage}× account)</div>
          <div class="line">Risk if stopped <b>${result.position.risk_amount.toLocaleString()}</b> · stop {result.position.stop_distance_pct}% away</div>
        {:else}
          <div class="line bad">{result.position_error ?? 'enter entry & stop'}</div>
        {/if}
      </div>

      <div class="card">
        <h3>Risk of ruin <span class="sub">(hit −{(result.inputs.drawdown * 100).toFixed(0)}% before doubling)</span></h3>
        <div class="big {ruinClass(result.ruin.analytic)}">{pct(result.ruin.analytic)}</div>
        <div class="line">Monte Carlo {pct(result.ruin.monte_carlo.prob)}
          (95% CI {pct(result.ruin.monte_carlo.ci_low)}–{pct(result.ruin.monte_carlo.ci_high)})</div>
        <div class="line muted">analytic diffusion + {result.ruin.monte_carlo.n_paths.toLocaleString()} simulated paths</div>
      </div>

      <div class="card">
        <h3>Kelly sizing</h3>
        {#if result.kelly.has_edge}
          {#each ['full', 'half', 'quarter'] as k}
            <div class="line"><span class="klabel">{k} Kelly</span>
              risk <b>{pct(result.kelly[k as 'full'])}</b>
              <span class="muted">→ median drawdown {pct(result.kelly_drawdowns[k].median_drawdown)}</span></div>
          {/each}
          <div class="line muted">full Kelly is growth-optimal and unbearable; practitioners use ¼.</div>
        {:else}
          <div class="line bad">No edge (payoff × win rate ≤ loss rate) — Kelly says don't bet.</div>
        {/if}
      </div>
    </div>

    <h3 class="tbl-h">P(−{(result.table.drawdown * 100).toFixed(0)}% drawdown before doubling) — risk/trade × win rate, at {result.table.payoff_ratio}:1 payoff</h3>
    <table class="ruin">
      <thead><tr><th>risk ↓ / win →</th>{#each result.table.win_rates as w}<th>{(w * 100).toFixed(0)}%</th>{/each}</tr></thead>
      <tbody>
        {#each result.table.rows as row}
          <tr><th>{(row.risk_fraction * 100).toFixed(2)}%</th>
            {#each row.ruin as p}<td style={heat(p)}>{(p * 100).toFixed(0)}</td>{/each}</tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .risk { max-width: 900px; }
  .tag { color: #8b949e; margin: 0 0 14px; }
  .grid-in { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
  .grid-in label { display: flex; flex-direction: column; font-size: 12px; color: #8b949e; gap: 4px; }
  input { background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 8px; font-size: 15px; }
  .row-btn { display: flex; gap: 10px; align-items: center; margin: 10px 0; flex-wrap: wrap; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 7px 12px; cursor: pointer; }
  .note { color: #8b949e; font-size: 12px; }
  .src-label { color: #8b949e; font-size: 12px; }
  .row-btn button.active { border-color: #8b949e; background: #30363d; font-weight: 600; }
  .src-note { margin: 0 0 10px; }
  .error { color: #f85149; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 14px 0; }
  .card { border: 1px solid #30363d; border-radius: 8px; padding: 14px; }
  .card h3 { margin: 0 0 8px; font-size: 14px; }
  .sub { color: #8b949e; font-weight: normal; font-size: 12px; }
  .big { font-size: 26px; font-weight: 700; margin: 4px 0; }
  .big.ok { color: #26a641; } .big.warn { color: #d29922; } .big.bad { color: #f85149; }
  .line { font-size: 13px; padding: 2px 0; }
  .line.bad { color: #f85149; }
  .muted { color: #8b949e; }
  .klabel { display: inline-block; width: 80px; text-transform: capitalize; color: #8b949e; }
  .tbl-h { font-size: 13px; color: #8b949e; margin: 18px 0 8px; }
  table.ruin { border-collapse: collapse; width: 100%; font-size: 13px; }
  table.ruin th { color: #8b949e; padding: 5px 8px; font-weight: 600; text-align: center; }
  table.ruin td { text-align: center; padding: 6px 8px; color: #0e1117; font-weight: 700; }
  table.ruin tbody th { text-align: right; }
</style>
