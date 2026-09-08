// Typed client for the Phase-24 API. Keep these types in step with src/service/serialize.py.
const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export interface Pair { symbol: string; asset_class: string; label: string }
export interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number | null }
export interface Level { price: number; role: string; touches: number }
export interface SwingMarker { time: number; price: number; kind: string }
export interface Fib { direction: string; levels: Record<string, number> }
export interface Marker { time: number; bias: string }
export interface ChartData {
  candles: Candle[]
  overlays: { levels: Level[]; swings: SwingMarker[]; fibonacci: Fib | null; marker: Marker | null }
}
export interface Confluence { bias: string; triggered: boolean; confidence: number; agreeing_categories: number }
export interface Analysis {
  market: { symbol: string; timeframe: string; last_close: number }
  confluence: Confluence
  explanation: string | null
  chart: ChartData
  [k: string]: any
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

export const getPairs = () => get<Pair[]>('/pairs')
export const getTimeframes = () => get<string[]>('/timeframes')
export const getAnalysis = (symbol: string, timeframe: string, explain = false) =>
  get<Analysis>(`/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&explain=${explain}`)
