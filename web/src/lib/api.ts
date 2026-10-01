// Typed client for the Phase-24 API. Keep these types in step with src/service/serialize.py.
const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://127.0.0.1:8000'

export interface Pair { symbol: string; asset_class: string; label: string }
export interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number | null }
// A4: support/resistance ZONES — a band (lower..upper) around a centre (`price`).
export interface Level {
  price: number; lower: number; upper: number; role: string; touches: number
  bars_since_touch: number; strength: number; stale: boolean
}
export interface SwingMarker { time: number; price: number; kind: string }
export interface Fib { direction: string; levels: Record<string, number> }
export interface Marker { time: number; bias: string }
export interface PatternPoint { time: number; price: number }
export interface Pattern {
  type: string; direction: string; state: string; quality: number | null
  points: PatternPoint[]; lines: PatternPoint[][]
  breakout_level: number | null; invalidation_level: number | null; target: number | null
  lifecycle?: string                 // forming | fresh | in_play | completed | expired | failed
  bars_since_state_change?: number | null
  state_time?: number | null         // the breakout (or failure) candle
  target_hit_time?: number | null    // the candle that reached the target (completed patterns)
  record?: PatternRecord | null      // measured history of this pattern type (encyclopedia)
  quality_band?: QualityBand | null  // B5: the raw quality score calibrated into low/medium/high
}
export interface Divergence { kind: string; reason: string; times: number[] }
export interface CandlePattern { time: number; direction: string; label: string }
// 1- and 2-candle patterns (facts-only). `level` = what the wick tagged, as of that candle (or null).
export interface Candle12 { time: number; label: string; code: string; direction: string; level: string | null }
export interface Point { time: number; value: number }
export interface Indicators {
  volume_ma: Point[]; rsi: Point[]; adx: Point[]; atr: Point[]
  macd: { line: Point[]; signal: Point[]; hist: Point[] }
}
export interface MovingAverage { key: string; period: number; values: Point[] }
export interface ChartData {
  candles: Candle[]
  price_precision: number
  min_move: number
  total_bars: number
  indicators: Indicators
  mas: MovingAverage[]
  overlays: {
    levels: Level[]; swings: SwingMarker[]; fibonacci: Fib | null; marker: Marker | null
    patterns: Pattern[]; divergence: Divergence | null; candle_patterns: CandlePattern[]
    trendlines?: TrendLine[]
    candles_12?: { all: Candle12[]; at_level: Candle12[]; last: Candle12 | null; level_window: number }
    regime?: { time: number; label: string }[]   // TEMP: Feature-6 eyeball strip
  }
}
// Which overlays/sub-panes are drawn (persisted to localStorage; see App.svelte).
export interface TrendLine {
  kind: 'support' | 'resistance'; direction: 'rising' | 'falling' | 'flat'
  anchors: { time: number; price: number }[]; points: { time: number; price: number }[]
}

export interface PanelToggles {
  trendlines: boolean; candles_all: boolean; levels: boolean; fib: boolean; swings: boolean; patterns: boolean; marker: boolean; ma: boolean
  volume: boolean; rsi: boolean; macd: boolean; adx: boolean; atr: boolean
}
export interface Confluence {
  bias: string; triggered: boolean; confidence: number; agreeing_categories: number
  categories?: Record<string, string>
}
export interface BaseRate { bias: string; win_rate: number; n: number; horizon: number }
// ROADMAP A3: Layer 1's situation tier (it sets the explanation's template + word budget).
export interface Situation {
  tier: 'no_setup' | 'notable' | 'confirmed' | 'mtf_synthesis'
  reasons: string[]; word_budget: number; template: string
}

// ROADMAP R1: the risk around a read, never its direction. active null = can't be judged here.
export interface CautionEntry {
  code: string; label: string; active: boolean | null; detail: string; value: unknown; status: string
  record?: string            // R3: what held-back history said (live path only)
}
// R3: active conditions shown as cautions; the rest of the active ones are plain information.
export const CAUTION_STATUSES = ['helps', 'by_construction', 'sizing', 'unmeasured']
export const CAUTION_TAG: Record<string, string> = {
  helps: 'measured', by_construction: 'arithmetic', sizing: 'sizing', unmeasured: 'not yet measured',
  no_effect: 'no measured effect', insufficient: 'too little history', forward_only: 'untested',
}
export interface Analysis {
  market: { symbol: string; timeframe: string; last_close: number }
  caution?: CautionEntry[]
  // ROADMAP C1: the explanation checked against the facts (null when there's no explanation)
  verification?: {
    ok: boolean; issues: string[]; retried: boolean; fallback: boolean; notice: string | null
    hard: { check: string; detail: string }[]; soft: { check: string; detail: string }[]
    first_attempt_hard: { check: string; detail: string }[]
  } | null
  exits?: { noise_floor_atr: number | null; typical_run_atr: number | null; noise_floor_price: number | null
            typical_run_price: number | null; n: number; winners: number; text: string } | null
  confluence: Confluence
  situation?: Situation
  base_rate: BaseRate | null
  explanation: string | null
  chart: ChartData
  as_of_bar: number | null
  bar_index?: number          // the bar this payload was actually computed at (B1)
  [k: string]: any
}

// --- Feature 9: risk of ruin & position sizing ---
export interface RiskResult {
  inputs: Record<string, number>
  ruin: {
    analytic: number
    monte_carlo: { prob: number; ci_low: number; ci_high: number; unresolved: number; n_paths: number }
  }
  kelly: { edge: number; full: number; half: number; quarter: number; has_edge: boolean }
  kelly_drawdowns: Record<string, { fraction: number; median_drawdown: number; p90_drawdown: number }>
  table: { payoff_ratio: number; win_rates: number[]; drawdown: number; target: number; rows: { risk_fraction: number; ruin: number[] }[] }
  position?: { risk_amount: number; stop_distance: number; stop_distance_pct: number; units: number; position_value: number; leverage: number }
  position_error?: string
}
export interface MeasuredStats {
  win_rate: number | null; win_rate_ci: [number, number] | null
  payoff_ratio: number | null; n: number; source: string; thin: boolean
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(API_BASE + path, {
    method,
    headers: body !== undefined ? { 'content-type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

export const getRisk = (p: {
  win_rate: number; payoff_ratio: number; risk_fraction: number; account: number; entry?: number; stop?: number
}) => {
  const q = new URLSearchParams({
    win_rate: String(p.win_rate), payoff_ratio: String(p.payoff_ratio),
    risk_fraction: String(p.risk_fraction), account: String(p.account),
  })
  if (p.entry != null) q.set('entry', String(p.entry))
  if (p.stop != null) q.set('stop', String(p.stop))
  return get<RiskResult>('/risk?' + q.toString())
}
export const getMeasured = (symbol: string, timeframe: string) =>
  get<MeasuredStats>(`/risk/measured?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`)

// A7: the calculator's default win rate — a coin flip minus this instrument's trading costs.
export interface CoinFlip {
  win_rate: number; fair_win_rate: number; cost_pct: number; risk_pct: number; cost_in_r: number
  payoff_ratio: number; horizon_bars: number; source: string
}
export const getCoinFlip = (symbol: string, timeframe: string, entry: number, stop: number, payoff: number) =>
  get<CoinFlip>(`/risk/coin_flip?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}` +
    `&entry=${entry}&stop=${stop}&payoff_ratio=${payoff}`)

// ROADMAP R4: is a stop inside the noise floor of this market/timeframe?
export interface NoiseFloor {
  atr: number; last_close: number; stop_atr: number; timeframe: string; measured: boolean
  inside?: boolean; noise_floor_atr?: number; typical_run_atr?: number | null
  winners_beyond_stop_in_10?: number | null; n?: number; winners?: number; stable?: boolean | null
}
export const getNoiseFloor = (symbol: string, timeframe: string, entry: number, stop: number) =>
  get<NoiseFloor>(`/risk/noise_floor?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&entry=${entry}&stop=${stop}`)

// --- Paper-trading simulator ---
export interface Trade {
  id: number; symbol: string; timeframe: string | null; side: string
  amount_usd: number; price: number; entry_source: string | null; units: number
  opened_at: number; status: string; closed_at: number | null; exit_price: number | null
  exit_source: string | null; realized_pnl: number | null
  snapshot: Record<string, any>; note: string | null
}
export interface TradePnl { closed: number; wins: number; realized_total: number; win_rate: number | null }
export interface TradeState { trades: Trade[]; pnl: TradePnl }
export interface Position {
  flat: boolean; id?: number; side?: string; amount_usd?: number; entry?: number
  units?: number; price?: number; unrealized_pnl?: number; unrealized_pct?: number; price_source?: string
}

export const getTrades = (symbol: string) =>
  get<TradeState>(`/trades?symbol=${encodeURIComponent(symbol)}`)
export const getPosition = (symbol: string, lastClose?: number | null) =>
  get<Position>(`/trades/position?symbol=${encodeURIComponent(symbol)}` +
    (lastClose != null ? `&last_close=${lastClose}` : ''))
export const postTrade = (body: {
  symbol: string; side: string; amount_usd: number
  timeframe?: string; last_close?: number | null; snapshot?: Record<string, any> | null
}) => send<{ result: any } & TradeState>('POST', '/trades', body)
export const deleteTrade = (id: number) => send<{ deleted: number }>('DELETE', `/trades/${id}`)

// A7: random-entry baseline — the range of total P&L luck alone produces with your exposure.
export interface TradeBaseline {
  n_trades: number; n_runs: number; timeframe?: string; history_bars?: number; note?: string
  total_p05?: number; total_p50?: number; total_p95?: number
  wins_p05?: number; wins_p50?: number; wins_p95?: number
  your_total?: number; your_percentile?: number; inside_luck_band?: boolean
}
export const getTradesBaseline = (symbol: string) =>
  get<TradeBaseline>(`/trades/baseline?symbol=${encodeURIComponent(symbol)}`)

export const getPairs = () => get<Pair[]>('/pairs')
export const getTimeframes = () => get<string[]>('/timeframes')
// limit = candles returned. Default 5000 (the API cap) so the chart holds the FULL history and
// you can pan all the way back, not just the last 500 bars.
export const getAnalysis = (
  symbol: string, timeframe: string, explain = false, context = true,
  asOfBar: number | null = null, limit = 5000, explanationStyle = 'brief',
) =>
  get<Analysis>(
    `/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&explain=${explain}` +
      `&context=${context}&limit=${limit}&explanation_style=${explanationStyle}` +
      (asOfBar != null ? `&as_of_bar=${asOfBar}` : ''),
  )

// --- ROADMAP B1: detector gold set (your own labels) ---
export interface GoldPattern { type: string; points: { time: number; price: number }[] }
export interface GoldZone { lower: number; upper: number; role: 'support' | 'resistance' }
export interface GoldLabels { patterns: GoldPattern[]; zones: GoldZone[]; nothing: boolean; note?: string }
export interface GoldRow {
  id: number; symbol: string; timeframe: string; bar: number; bar_time: number | null
  labels: GoldLabels; created_at: number; updated_at: number
}
export interface GoldSummary {
  charts: number; patterns: number; by_type: Record<string, number>; zones: number; nothing: number
  by_symbol_tf: Record<string, number>
}
export const getLabelTypes = () =>
  get<{ detector_types: string[]; extra_types: string[]; zone_roles: string[] }>('/labels/types')
export const getLabels = () => get<{ labels: GoldRow[]; summary: GoldSummary }>('/labels')
export const getLabel = (symbol: string, timeframe: string, bar: number) =>
  get<{ label: GoldRow | null }>(`/labels/one?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&bar=${bar}`)
export const putLabel = (body: { symbol: string; timeframe: string; bar: number; bar_time: number | null; labels: GoldLabels }) =>
  send<{ label: GoldRow; summary: GoldSummary }>('PUT', '/labels', body)
export const deleteLabel = (id: number) => send<{ deleted: number; summary: GoldSummary }>('DELETE', `/labels/${id}`)

// --- ROADMAP B3: Empirical Pattern Encyclopedia ---
export interface EncRow {
  pattern_type: string; timeframe: string; symbol: string; regime: string; split: string
  sample_size: number; insufficient_data: boolean
  seen_forming: number; decided_n: number; pending_breakout_n: number
  confirmed_n: number; invalidated_n: number; confirmation_rate: number | null
  judged_n: number; pending_outcome_n: number
  target_n: number; target_hit_n: number; follow_through_rate: number | null
  failed_n: number; failure_rate: number | null
  move_n: number; move_atr_median: number | null; move_atr_q1: number | null; move_atr_q3: number | null
  resolved_n: number; bars_to_resolution_median: number | null
  built_at: number
  quality_cuts?: [number, number] | null   // B5 band boundaries (split='all' rows)
  examples?: { symbol: string; timeframe: string; bar: number; direction: string; outcome: string; move_atr: number | null }[]
}
export interface EncIndex { built_at: number | null; params: Record<string, number>; types: EncRow[] }
export interface Textbook { shape: string | null; trigger: string | null; claims: string[]; source: string }
export interface EncPage {
  pattern_type: string; rows: EncRow[]; textbook: Textbook | null
  detector_precision: Record<string, { precision: number | null; n: number; status: string }>
  quality_meaning?: Record<string, string>   // B5, per timeframe, decided by Layer 1
}
export const getEncyclopedia = () => get<EncIndex>('/encyclopedia')
export const getEncyclopediaPage = (t: string) => get<EncPage>(`/encyclopedia/${encodeURIComponent(t)}`)

// --- Pattern scanner (every pair × timeframes) + the record beside each find ---
export interface PatternRecord {
  sample_size: number; judged_n: number; target_n: number; target_hit_n: number
  follow_through_rate: number | null; failed_n: number; failure_rate: number | null; move_atr_median: number | null
}
export interface ScanRow {
  symbol: string; timeframe: string; type: string; direction: string; lifecycle: string
  bars_since_breakout: number | null; breakout_level: number | null; invalidation_level: number | null
  target: number | null; last_close: number; distance_atr: number | null; quality: number
  last_time: number; record: PatternRecord | null; quality_band: QualityBand | null
}
export interface ScanResult { rows: ScanRow[]; skipped: { symbol: string; timeframe: string; reason: string }[]; markets: number; scanned_at: number }
export const getScan = (timeframes: string[]) => get<ScanResult>(`/scan?timeframes=${timeframes.join(',')}`)

// "target 35 of 85 (41%) · failed 46 of 85 (54%)" — a % only with 20+ judged cases.
// ROADMAP B5 — quality as a calibrated band: low/medium/high = bottom/middle/top third of this
// pattern type's past scores, with what the patterns in that band did. Never the raw 0.62.
export interface QualityBand extends PatternRecord {
  band: 'low' | 'medium' | 'high'; cuts: [number, number]; raw: number
  decided_n: number | null; confirmed_n: number | null; confirmation_rate: number | null
  meaning: string
}
export function qualityText(q: QualityBand | null | undefined): string {
  if (!q) return 'quality: not calibrated yet'
  const [lo, hi] = q.cuts
  const range = { low: `score below ${lo}`, medium: `score ${lo}–${hi}`, high: `score ${hi} and up` }[q.band]
  return `quality ${q.band} band (${range}) — in that band ${recordText(q)}`
}

export function recordText(r: PatternRecord | null | undefined): string {
  if (!r) return 'no history yet (rebuild the encyclopedia)'
  const part = (label: string, n: number, d: number, rate: number | null) =>
    d === 0 ? `${label}: no cases` : `${label} ${n} of ${d}` + (rate != null && d >= 20 ? ` (${Math.round(rate * 100)}%)` : ' — too few to rate')
  return `${part('reached target', r.target_hit_n, r.target_n, r.follow_through_rate)} · ${part('failed', r.failed_n, r.judged_n, r.failure_rate)}`
}

// --- ROADMAP A8: the morning report (forward record) ---
export interface ForwardRead {
  id: number; symbol: string; timeframe: string; bar_time: number; price: number
  tier: string; bias: string; aligned: number; agreeing: number
  read_kind: 'directional' | 'range'; direction: string | null
  invalidation: number | null; next_level: number | null; near_above: number | null; near_below: number | null
  range_low: number | null; range_high: number | null; source_above: string; source_below: string
  horizon: number; rule_version: number; outcome: string | null; run_date: string; resolved_run_date: string | null
  baseline_direction: string | null; baseline_outcome: string | null
  engine_commit: string; engine_dirty: number; facts_hash: string
  patterns: { type: string; direction: string; lifecycle: string | null }[]
  caution: Record<string, boolean | null> | null   // R2: flags frozen at the read; null = not recorded
}
export interface CautionSplitRow {
  rule_version: number; read_kind: 'directional' | 'range'; code: string; label: string; cant_judge: number
  flagged: { engine: ScoreSide; baseline: ScoreSide | null }
  not_flagged: { engine: ScoreSide; baseline: ScoreSide | null }
}
export interface ScoreSide { n: number; counts: Record<string, number>; rate: number | null }
export interface ScoreRow {
  rule_version: number; timeframe: string; tier: string; read_kind: string
  engine: ScoreSide; baseline: ScoreSide | null
}
export interface MorningRun {
  run_date: string; status: string; trigger: string | null; started_at: number | null; finished_at: number | null
  attempts: number; new_reads: number; resolved: number
  skipped: { symbol: string; timeframe: string; reason: string }[] | string | null; engine_commit: string | null
  attempt_log?: MorningAttempt[]
}
export interface MorningAttempt {
  attempt: number; trigger: string; started_at: number; finished_at: number; status: string
  new_reads: number; resolved: number; engine_commit: string
  skipped: { symbol: string; timeframe: string; reason: string }[]
}
export interface MorningReport {
  run_date: string | null; run: MorningRun | null; runs: MorningRun[]; gaps: string[]; first_run: string | null
  review: ForwardRead[]; grid: ForwardRead[]; syntheses: { symbol: string; text: string; model: string }[]
  pending: Record<string, number>; scoreboard: ScoreRow[]
  watchlist: { symbols: string[]; timeframes: string[]; horizons: Record<string, number> }
  next_run: string; schedule: string; rule: { version: number; text: string }
  caution_split?: { rows: CautionSplitRow[]; not_recorded: number }
  caution_labels?: Record<string, string>
  caution_status?: Record<string, string>     // R3: what held-back history said per condition
}
export const getMorning = (date?: string) => get<MorningReport>(`/morning${date ? `?date=${date}` : ''}`)
export const runMorning = () => send<{ started: boolean }>('POST', '/morning/run')

// --- ROADMAP D1: the prediction journal (YOUR calls) ---
export interface JournalEntry {
  id: number; created_at: number; source: string; symbol: string; timeframe: string
  bar_time: number; price: number; direction: 'up' | 'down'; confidence: number; invalidation: number
  horizon_value: number; horizon_unit: string; end_time: number; note: string | null
  verdict_visible: boolean; explanation_visible: boolean
  engine: { bias: string; tier: string; aligned: boolean; patterns: string[]; regime: string } | null
  outcome: 'correct' | 'incorrect' | 'invalidated' | null; resolved_at: number | null; end_close: number | null
}
export interface JournalGroup {
  n: number; hits: number; invalidated: number; accuracy: number | null; brier: number | null
  mean_confidence?: number; overconfidence: number | null
}
export interface JournalStats {
  overall: JournalGroup; baseline_brier: number; pending: number; min_n: number
  curve: { bin: string; n: number; hits: number; mean_confidence: number | null; rate: number | null }[]
  by_timeframe: Record<string, JournalGroup>; by_source: Record<string, JournalGroup>
  by_regime: Record<string, JournalGroup>; by_pattern: Record<string, JournalGroup>; by_view: Record<string, JournalGroup>
}
export interface JournalPage {
  entries: JournalEntry[]; stats: JournalStats; delete_window_s: number; now: number
  rule: { version: number; text: string }
}
export interface JournalIn {
  symbol: string; timeframe: string; direction: 'up' | 'down'; confidence: number; invalidation: number
  horizon_value: number; horizon_unit: string; note: string; source: 'analysis' | 'morning'
  verdict_visible: boolean; explanation_visible: boolean
}
export const getJournal = () => get<JournalPage>('/journal')
export const getJournalPrice = (symbol: string, timeframe: string) =>
  get<{ bar_time: number; price: number }>(`/journal/price?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`)
export const postJournal = (body: JournalIn) => send<JournalEntry>('POST', '/journal', body)
export const deleteJournal = (id: number) => send<{ deleted: number }>('DELETE', `/journal/${id}`)

// --- ROADMAP D6: blind training ---
export interface TrainingOptions { types: Record<string, number>; regimes: Record<string, number>; timeframes: Record<string, number>; total: number }
export interface TrainingSetup { id: number; symbol: string; timeframe: string; as_of_bar: number; bar_time: number; price: number; horizon_bars: number }
export interface TrainingReveal {
  entry: JournalEntry; reveal_bar: number; end_time: number
  setup: { type: string; direction: string; regime: string; outcome: string; move_atr: number | null
           breakout: number | null; invalidation: number | null; target: number | null }
  engine: { bias: string; tier: string; agreeing: number; total: number; cautions: string[]
            patterns: { type: string; state: string; lifecycle: string | null }[] }
  record: PatternRecord | null
}
const qs = (o: Record<string, string | undefined>) =>
  Object.entries(o).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join('&')
export const getTrainingOptions = () => get<TrainingOptions>('/training/options')
export const getTrainingNext = (f: { type?: string; regime?: string; timeframe?: string }) =>
  get<{ setup: TrainingSetup | null }>(`/training/next?${qs(f)}`)
export const postTrainingAnswer = (body: { setup_id: number; direction: 'up' | 'down'; confidence: number; invalidation: number; note: string }) =>
  send<TrainingReveal>('POST', '/training/answer', body)

// --- ROADMAP D2: pre-registered experiments ---
export interface Experiment {
  id: number; created_at: number; question: string; hypothesis: string; script: string; params: Record<string, unknown>
  metric: string; direction: string; threshold: number; baseline: number | null; predicted_pass: number
  predicted_value: number | null; supersedes: number | null; superseded: boolean; hash: string
  ran_at: number | null; value: number | null; n: number | null; passed: number | null; p_value: number | null
  variations: number | null; corrected_alpha: number | null; passed_corrected: number | null; engine_commit: string | null
}
export interface ExperimentsPage {
  experiments: Experiment[]
  questions: Record<string, { registered: number; ran: number; passed: number; passed_corrected: number }>
  summary: { registered: number; ran: number; never_ran: number; passed: number; misses: number; prediction_hits: number; prediction_n: number }
}
export const getExperiments = () => get<ExperimentsPage>('/experiments')

// --- ROADMAP D5: declared rules + discipline review ---
export interface TradingRules {
  account_size?: number; max_position_pct?: number; max_open_positions?: number; required_regimes?: string[]
  min_categories_aligned?: number; allowed_symbols?: string[]; max_per_week?: number; cooling_off_hours?: number
}
export interface RuleVersion { version: number; created_at: number; rules: TradingRules; note: string }
export interface DisciplineOutcome { n: number; judged: number; wins: number; win_rate: number | null; pnl_total: number | null }
export interface DisciplineSide { followed: DisciplineOutcome; broke: DisciplineOutcome; by_rule: Record<string, DisciplineOutcome>; unchecked: number }
export interface Decision {
  kind: 'trade' | 'call'; id: number; t: number; symbol: string; size: number | null; outcome: string | null
  pnl: number | null; regime: string | null; agreeing: number | null; rule_version: number | null
  violations: { rule: string; detail: string }[]; cant_check: string[]; followed: boolean
}
export interface DisciplinePage {
  rules: RuleVersion | null; versions: RuleVersion[]; decisions: Decision[]
  compare: { trade: DisciplineSide; call: DisciplineSide }
  observations: { t: number | null; kind: string; text: string; week?: string }[]
  weekly: { week: string; trades: number; calls: number; broke: number; rules_broken: string[]; judged: number; wins: number; observations: string[] }[]
  labels: Record<string, string>; min_n: number
}
export const getDiscipline = () => get<DisciplinePage>('/discipline')
export const postRules = (body: TradingRules & { note: string }) => send<RuleVersion>('POST', '/rules', body)
