// Typed client for the Phase-24 API. Keep these types in step with src/service/serialize.py.
const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://127.0.0.1:8000'

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

export interface Analysis {
  market: { symbol: string; timeframe: string; last_close: number }
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
