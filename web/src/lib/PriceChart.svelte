<script lang="ts">
  import { onMount } from 'svelte'
  import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'
  import type { ChartData, GoldLabels, PanelToggles, Pattern, Trade } from './api'

  // ROADMAP B1: `labelMode` hides EVERY detector overlay (levels, fib, patterns, trendlines, swings,
  // candle patterns, verdict marker, regime strip), draws the user's own `draft` labels instead, and
  // forwards clicks on the price pane to `onChartClick(time, price)`.
  let { data, toggles, trades = [], labelMode = false, draft = null, pending = null, onChartClick }:
    { data: ChartData | null; toggles: PanelToggles; trades?: Trade[]; labelMode?: boolean
      draft?: GoldLabels | null
      pending?: { kind: string; points: { time: number; price: number }[] } | null
      onChartClick?: (time: number, price: number) => void } = $props()

  let root: HTMLDivElement
  let charts: IChartApi[] = []
  let mainSeries: ISeriesApi<'Candlestick'> | null = null
  let syncing = false

  const isMobile = () => window.innerWidth < 640
  const MAIN_H = () => (isMobile() ? 300 : 380)
  const SUB_H = 110
  const RIGHT_OFFSET = 25   // permanent empty bars after the last candle (clear of the price labels)

  const GRID = { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } }
  const LAYOUT = { background: { color: '#0e1117' }, textColor: '#c9d1d9' }
  // Fixed price-scale width so every pane's left edge lines up under the candles.
  const baseOpts = (h: number, isMain = false) => ({
    height: h, layout: LAYOUT, grid: GRID,
    // Edge behavior (verified in a real headless browser — see verify/). Drag never zooms
    // (axisPressedMouseMove off). Left edge is a hard stop (fixLeftEdge). The right edge is a
    // BOUNDED hard stop applied manually below — fixRightEdge:true would jam the last candle
    // against the price-axis labels (it ignores rightOffset AND trailing whitespace), while
    // fixRightEdge:false alone lets the chart overscroll into empty space (reads as a zoom-out).
    // Only the MAIN pane fixes its left edge; sub-panes are passive followers, otherwise their
    // warm-up-trimmed data clamps the left edge and pushes it back onto the main through the sync.
    timeScale: {
      timeVisible: true, borderColor: '#30363d',
      fixLeftEdge: isMain, fixRightEdge: false, rightOffset: RIGHT_OFFSET,
    },
    rightPriceScale: { borderColor: '#30363d', minimumWidth: 68 },
    // Horizontal DRAG pans the time axis; ZOOM is wheel/pinch only. Axis-drag scaling is off, so
    // dragging (incl. on the time axis) never zooms — that was the "drag = zoom" bug.
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: {
      mouseWheel: true, pinch: true,
      axisPressedMouseMove: { time: false, price: false },
      axisDoubleClickReset: { time: true, price: true },
    },
  })

  // `extra` shallow-merges per section (timeScale / rightPriceScale) over the base options.
  // An empty `label` skips the overlaid pane label (the regime strip carries its own legend).
  function newPane(label: string, h: number, isMain = false, extra: Record<string, any> = {}): IChartApi {
    const wrap = document.createElement('div')
    wrap.className = 'pane'
    if (label) {
      const tag = document.createElement('span')
      tag.className = 'pane-label'; tag.textContent = label
      wrap.appendChild(tag)
    }
    root.appendChild(wrap)
    const base = baseOpts(h, isMain)
    const opts = {
      ...base, ...extra,
      timeScale: { ...base.timeScale, ...(extra.timeScale ?? {}) },
      rightPriceScale: { ...base.rightPriceScale, ...(extra.rightPriceScale ?? {}) },
    }
    const c = createChart(wrap, { ...opts, width: root.clientWidth } as any)
    charts.push(c)
    return c
  }

  function teardown() {
    for (const c of charts) c.remove()
    charts = []; mainSeries = null
    // Also remove the .pane wrapper DIVS (each holds a label span). Removing only the chart
    // instances left stale, empty panes to accumulate across re-renders — their labels stacked
    // into garbled text at the top-left.
    if (root) root.replaceChildren()
  }

  // Sync by LOGICAL (bar-index) range, not time. Every pane is set on the SAME shared index axis
  // (see `axis` in render), so logical sync is exact and can't drift — time-range sync across
  // differing-length series was what made a drag creep into a zoom. A guard stops A->B->A loops.
  function syncTimeScales() {
    for (const src of charts) {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return
        syncing = true
        for (const dst of charts) if (dst !== src) dst.timeScale().setVisibleLogicalRange(range as any)
        syncing = false
      })
    }
  }

  // Regime (Feature 6) -> strip color. Standalone context, not a vote.
  const REGIME_COLORS: Record<string, string> = {
    trending_up: '#26a641', trending_down: '#f85149', ranging: '#8b949e',
    volatile: '#d29922', quiet: '#3b6ea5',
  }
  const regimeColor = (label: string) => REGIME_COLORS[label] ?? '#484f58'
  const regimeText = (label: string) => label.replace('_', ' ')
  const REGIME_H = 22

  const CANDLE_CODES: Record<string, string> = {
    'morning star': 'MS', 'evening star': 'ES',
    'three white soldiers': '3WS', 'three black crows': '3BC',
  }
  const candleCode = (label: string) => CANDLE_CODES[label] ?? label
  // Short names for chart-pattern markers at the breakout candle.
  const PATTERN_ABBR: Record<string, string> = {
    'double top': 'DTop', 'double bottom': 'DBot', 'head and shoulders': 'H&S',
    'inverse head and shoulders': 'iH&S', 'ascending triangle': 'AscTri', 'descending triangle': 'DescTri',
    'symmetric triangle': 'SymTri', 'sideways channel': 'Range', 'ascending channel': 'AscCh',
    'descending channel': 'DescCh', 'falling wedge': 'FWedge', 'rising wedge': 'RWedge',
  }
  const patternAbbr = (t: string) => PATTERN_ABBR[t] ?? t
  // B4: beside a measured target, how often that pattern type reached it ("· hit 35/80").
  const targetRecord = (p: Pattern) => {
    const r = p.record
    return r && r.target_n ? ` (${r.target_hit_n}/${r.target_n})` : ''
  }
  const LIFE_TEXT: Record<string, string> = {
    fresh: '✓ breakout (fresh)', in_play: '✓ breakout (in play)', completed: '✓ breakout (done)',
    expired: '✓ breakout (expired)', failed: '✗ failed',
  }
  // Short tag for the level a 1–2 candle pattern tagged ("support zone 1.14–1.15" -> "sup").
  const levelAbbr = (level: string | null) => {
    if (!level) return ''
    if (level.startsWith('support zone')) return 'sup'
    if (level.startsWith('resistance zone')) return 'res'
    if (level.startsWith('fib')) return 'fib' + level.replace(/[^0-9.]/g, '')
    if (level.includes('trendline')) return 'TL'
    return level
  }

  const patternStyle = (p: Pattern) => {
    // failed, completed and expired are all HISTORY — drawn thin and grey so they don't read as current
    if (p.state === 'failed' || p.lifecycle === 'completed' || p.lifecycle === 'expired')
      return { color: '#6e7681', width: 1, dashed: true }
    if (p.state === 'confirmed')
      return { color: p.direction === 'bearish' ? '#f85149' : '#26a641', width: 2, dashed: false }
    return { color: '#d29922', width: 2, dashed: true } // forming
  }

  onMount(() => {
    render()
    const ro = new ResizeObserver(() => {
      for (const c of charts) c.applyOptions({ width: root.clientWidth })
    })
    ro.observe(root)
    return () => { ro.disconnect(); teardown() }
  })

  // Rebuild whenever the data or the toggles change (simple + robust vs incremental updates).
  // Deep-read the label draft so adding a point re-renders; JSON keeps the dependency simple.
  $effect(() => { data; toggles; trades; labelMode; JSON.stringify(draft); JSON.stringify(pending); render() })

  // Keep the user's zoom/scroll across re-renders of the SAME candles (e.g. each labelling click).
  let savedRange: { key: string; range: any } | null = null
  const dataKey = (d: ChartData) => `${d.candles.length}:${d.candles[d.candles.length - 1]?.time}`

  function render() {
    if (!root) return
    if (charts[0] && data) {
      const r = charts[0].timeScale().getVisibleLogicalRange()
      if (r) savedRange = { key: dataKey(data), range: { from: r.from, to: r.to } }
    }
    teardown()
    if (!data) return
    const prec = data.price_precision ?? 2
    const ov = data.overlays
    const ind = data.indicators

    // ONE shared time axis for every pane: the candle times, then RIGHT_OFFSET future bars as
    // whitespace (the right-hand gap, now real index space). Every series is mapped onto this axis
    // — warm-up holes and the trailing gap become whitespace — so all charts share identical
    // logical indices. That makes logical-range sync exact (no drift -> no zoom) AND lets the view
    // include the gap (setVisibleLogicalRange to the last whitespace index isn't clamped away).
    const cTimes = data.candles.map((k) => k.time)
    const step = cTimes.length > 1 ? cTimes[cTimes.length - 1] - cTimes[cTimes.length - 2] : 86400
    const axis: number[] = cTimes.slice()
    for (let k = 1; k <= RIGHT_OFFSET; k++) axis.push(cTimes[cTimes.length - 1] + k * step)
    const whitespace = axis.slice(cTimes.length).map((t) => ({ time: t }))
    const align = (s: { time: number; value: number }[]) => {
      const m = new Map(s.map((p) => [p.time, p.value]))
      return axis.map((t) => (m.has(t) ? { time: t, value: m.get(t) } : { time: t }))
    }

    // ---- main price pane ----
    const main = newPane('price', MAIN_H(), true)
    const series = main.addCandlestickSeries({
      upColor: '#26a641', downColor: '#f85149',
      borderVisible: false, wickUpColor: '#26a641', wickDownColor: '#f85149',
      priceFormat: { type: 'price', precision: prec, minMove: data.min_move ?? 0.01 },
    })
    series.setData((data.candles as any[]).concat(whitespace))
    mainSeries = series

    // Moving averages overlaid on the price pane (50 = blue, 200 = gold), aligned to the axis.
    if (toggles.ma) for (const ma of data.mas ?? []) {
      const maLine = main.addLineSeries({
        color: ma.key === 'long' ? '#e3b341' : '#58a6ff', lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false,       // no label (user: not needed for MAs)
        crosshairMarkerVisible: false,
      })
      maLine.setData(align(ma.values) as any)
    }

    // Plain-text labels drawn in the pane (no coloured axis tags): S1(8), R2(3), Fib 38, TL, targets.
    const labels: { price: number; text: string; color: string }[] = []

    // Support/resistance ZONES (A4): a shaded band per zone, drawn under the candles, labelled
    // S1/S2… (support, nearest first) and R1/R2… (resistance) with the touch count. Stale zones
    // (no reversal for a long time) are fainter, band and label alike.
    if (!labelMode && toggles.levels && ov.levels.length) {
      series.attachPrimitive(new ZoneBands(ov.levels.map((lv) => ({
        lower: lv.lower, upper: lv.upper,
        color: (lv.role === 'support' ? '#26a641' : '#f85149') + (lv.stale ? '14' : '30'),
      }))) as any)
      const rank = { support: 0, resistance: 0 } as Record<string, number>
      for (const lv of ov.levels) {            // serialize orders each side nearest-first
        rank[lv.role] += 1
        labels.push({ price: lv.price, text: `${lv.role === 'support' ? 'S' : 'R'}${rank[lv.role]}(${lv.touches})`,
          color: (lv.role === 'support' ? '#3fb950' : '#f85149') + (lv.stale ? '99' : '') })
      }
    }

    if (!labelMode && toggles.fib && ov.fibonacci)
      for (const [ratio, price] of Object.entries(ov.fibonacci.levels)) {
        if (![0.382, 0.5, 0.618].includes(Number(ratio))) continue   // key retracements only, less clutter
        series.createPriceLine({ price, color: '#8b949e', lineWidth: 1, lineStyle: 2, axisLabelVisible: false } as any)
        labels.push({ price, text: `Fib ${Math.round(Number(ratio) * 100)}`, color: '#8b949e' })
      }

    // Patterns: draw each ACTUAL boundary (channel/triangle boundaries, neckline, rectangle edges)
    // as a line series, styled by state. The boundaries ARE the breakout/invalidation levels, so we
    // don't also draw horizontal lines for those (that was redundant clutter) — only the projected
    // target gets a single tag.
    const markers: any[] = []
    if (!labelMode && toggles.patterns) for (const p of ov.patterns) {
      const st = patternStyle(p)
      for (const ln of p.lines ?? []) {
        if (ln.length < 2) continue
        const bl = main.addLineSeries({
          color: st.color, lineWidth: st.width as any, lineStyle: st.dashed ? 2 : 0,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        })
        bl.setData(dedupeByTime(ln.map((pt) => ({ time: pt.time, value: pt.price }))) as any)
      }
      // Carry the breakout level forward to the candle that broke it (or failed it), and mark that
      // candle — so "confirmed 2 bars ago" points at something visible.
      const lastPt = Math.max(...p.points.map((q) => q.time))
      if (p.state_time != null && p.breakout_level != null && p.state_time > lastPt) {
        const ext = main.addLineSeries({ color: st.color, lineWidth: 1, lineStyle: 2,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false })
        ext.setData([{ time: lastPt, value: p.breakout_level }, { time: p.state_time, value: p.breakout_level }] as any)
      }
      if (p.state_time != null) {
        const up = p.direction === 'bullish'
        markers.push({ time: p.state_time, position: up ? 'belowBar' : 'aboveBar', color: st.color,
          shape: up ? 'arrowUp' : 'arrowDown', text: `${patternAbbr(p.type)} ${LIFE_TEXT[p.lifecycle ?? p.state] ?? ''}` })
      }
      if (p.target_hit_time != null)
        markers.push({ time: p.target_hit_time, position: p.direction === 'bullish' ? 'aboveBar' : 'belowBar',
          color: st.color, shape: 'circle', text: `${patternAbbr(p.type)} target hit` })
      // Only CURRENT patterns show their target on the price axis; history doesn't need one.
      if (p.target != null && !['completed', 'expired', 'failed'].includes(p.lifecycle ?? p.state))
      {
        series.createPriceLine({ price: p.target, color: st.color, lineWidth: 1, lineStyle: 1, axisLabelVisible: false } as any)
        labels.push({ price: p.target, text: `${patternAbbr(p.type)} target${targetRecord(p)}`, color: st.color })
      }
    }

    // Two-point trendlines: support through two swing lows (teal), resistance through two swing
    // highs (pink), drawn from the older anchor to the last candle — only while unbroken.
    if (!labelMode && toggles.trendlines) for (const tl of ov.trendlines ?? []) {
      const tln = main.addLineSeries({
        color: tl.kind === 'support' ? '#39c5cf' : '#db61a2', lineWidth: 2, lineStyle: 0,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      })
      tln.setData(dedupeByTime(tl.points.map((pt) => ({ time: pt.time, value: pt.price }))) as any)
      const end = tl.points[tl.points.length - 1]
      if (end) labels.push({ price: end.price, text: 'TL', color: tl.kind === 'support' ? '#39c5cf' : '#db61a2' })
    }

    if (!labelMode && toggles.swings) for (const s of ov.swings)
      markers.push({ time: s.time, position: s.kind === 'high' ? 'aboveBar' : 'belowBar',
        color: '#8b949e', shape: 'circle' })

    // Three-candle patterns (morning/evening star, three soldiers/crows) — a labelled square at the
    // confirming candle, green below for bullish / red above for bearish. Grouped under the
    // `patterns` toggle so they can be hidden with the other pattern annotations.
    // Marker text is a SHORT code (full names are in the legend under the pane): the full names
    // ("three white soldiers") overlapped each other and clipped at the left edge when zoomed out.
    const candlePats = toggles.patterns && !labelMode ? (ov.candle_patterns ?? []) : []
    for (const cp of candlePats) {
      const bull = cp.direction === 'bullish'
      markers.push({ time: cp.time, position: bull ? 'belowBar' : 'aboveBar',
        color: bull ? '#26a641' : '#f85149', shape: 'square', text: candleCode(cp.label) })
    }
    // 1–2 candle patterns (facts-only). By default only those whose wick TAGGED a level that
    // favours them (as of that candle) — "H@sup", "BeE@fib61.8" — plus the last closed candle's
    // pattern (the one the candlestick vote reads). The study toggle adds every other one, faded.
    const c12 = ov.candles_12
    const c12Drawn: { code: string; label: string }[] = []
    if (c12 && !labelMode) {
      const atTimes = new Set(c12.at_level.map((c) => c.time))
      const col = (d: string, faded = false) =>
        (d === 'bullish' ? '#26a641' : d === 'bearish' ? '#f85149' : '#8b949e') + (faded ? '99' : '')
      const pos = (d: string) => (d === 'bearish' ? 'aboveBar' : 'belowBar')
      const isLast = (t: number) => c12.last?.time === t
      if (toggles.patterns) for (const c of c12.at_level) {
        markers.push({ time: c.time, position: pos(c.direction), color: col(c.direction), shape: 'circle',
          text: `${c.code}@${levelAbbr(c.level)}${isLast(c.time) ? ' (last)' : ''}` })
        c12Drawn.push(c)
      }
      if (toggles.candles_all) for (const c of c12.all) {
        if (atTimes.has(c.time)) continue
        markers.push({ time: c.time, position: pos(c.direction), color: col(c.direction, true), shape: 'circle',
          text: c.code + (isLast(c.time) ? ' (last)' : '') })
        c12Drawn.push(c)
      }
      const last = c12.last
      if (toggles.patterns && last && !atTimes.has(last.time) && !toggles.candles_all) {
        markers.push({ time: last.time, position: pos(last.direction), color: col(last.direction), shape: 'circle',
          text: `${last.code} (last)` })
        c12Drawn.push(last)
      }
    }

    if (!labelMode && toggles.marker && ov.marker)
      markers.push({ time: ov.marker.time,
        position: ov.marker.bias === 'bullish' ? 'belowBar' : 'aboveBar',
        color: '#8b949e',   // neutral: the verdict marker must not read as a green/red call
        shape: ov.marker.bias === 'bullish' ? 'arrowUp' : 'arrowDown' })

    // Paper trades: green ▲ (buy) / red ▼ (sell) at the candle whose bar contains the trade time.
    // A close is the OPPOSITE action, so a closed long draws a buy at entry AND a sell at close
    // ("green when I bought, red when I sold"). Trades before the loaded window are skipped.
    // A trade after the last loaded candle (e.g. while scrubbed back in history) is NOT snapped onto
    // that candle — it didn't happen yet at this bar — so it's skipped.
    const lastCandle = cTimes[cTimes.length - 1]
    const snap = (ts: number): number | null => {
      if (ts >= lastCandle + step) return null
      let best: number | null = null
      for (const t of cTimes) { if (t <= ts) best = t; else break }
      return best
    }
    const tradeMarker = (side: string, time: number, amount: number) =>
      side === 'buy'
        ? { time, position: 'belowBar', color: '#26a641', shape: 'arrowUp', text: `Buy $${amount}` }
        : { time, position: 'aboveBar', color: '#f85149', shape: 'arrowDown', text: `Sell $${amount}` }
    for (const tr of labelMode ? [] : trades) {        // labelling: your trades would anchor you too
      const et = snap(tr.opened_at)
      if (et != null) markers.push(tradeMarker(tr.side, et, tr.amount_usd))
      if (tr.status === 'closed' && tr.closed_at != null) {
        const xt = snap(tr.closed_at)
        if (xt != null) markers.push(tradeMarker(tr.side === 'buy' ? 'sell' : 'buy', xt, tr.amount_usd))
      }
    }
    // ---- B1: the user's own labels (purple) + the point/zone being drawn (orange) ----
    if (labelMode && draft) {
      const GOLD = '#a371f7', PEND = '#f0883e'
      if (draft.zones.length)
        series.attachPrimitive(new ZoneBands(draft.zones.map((z) => ({ lower: z.lower, upper: z.upper, color: GOLD + '38' }))) as any)
      for (const z of draft.zones)
        labels.push({ price: (z.lower + z.upper) / 2, text: `your ${z.role === 'support' ? 'S' : 'R'}`, color: GOLD })
      const drawPts = (pts: { time: number; price: number }[], color: string, dashed: boolean, label: string) => {
        const line = main.addLineSeries({ color, lineWidth: 2, lineStyle: dashed ? 2 : 0,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false })
        line.setData(dedupeByTime(pts.map((q) => ({ time: q.time, value: q.price }))) as any)
        pts.forEach((q, i) => markers.push({ time: q.time, position: 'inBar', color, shape: 'circle',
          text: i === 0 ? label : '' }))
      }
      for (const p of draft.patterns) drawPts(p.points, GOLD, false, p.type)
      if (pending?.points.length) {
        if (pending.kind === 'pattern') drawPts(pending.points, PEND, true, 'drawing…')
        else series.createPriceLine({ price: pending.points[0].price, color: PEND, lineWidth: 1,
          lineStyle: 2, axisLabelVisible: true, title: 'zone edge 1' } as any)
      }
    }
    if (labels.length) series.attachPrimitive(new TextLabels(labels) as any)
    markers.sort((a, b) => a.time - b.time)
    series.setMarkers(markers as any)
    if (labelMode && onChartClick) {
      const lastTime = cTimes[cTimes.length - 1]
      main.subscribeClick((param: any) => {
        if (!param?.point || param.time == null || param.time > lastTime) return
        const price = series.coordinateToPrice(param.point.y)
        if (price != null) onChartClick(param.time as number, price as number)
      })
    }

    // ---- regime strip: a solid colored band per candle + an HTML legend row under it ----
    // The strip hides its own time axis and price labels (the old 40px pane spent most of its
    // height on an axis, leaving a sliver of color under an overlapping label). The price scale
    // stays VISIBLE (blank labels) so its width — and the candles above — still line up.
    if (!labelMode && ov.regime && ov.regime.length) {
      const c = newPane('', REGIME_H, false, {
        timeScale: { visible: false },
        rightPriceScale: { ticksVisible: false, borderVisible: false },
        localization: { priceFormatter: () => '' },
        // The TradingView logo covered the left of the 22px strip; attribution stays on the other panes.
        layout: { ...LAYOUT, attributionLogo: false },
        crosshair: { horzLine: { visible: false, labelVisible: false } },
      })
      const strip = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false, base: 0 })
      strip.priceScale().applyOptions({ scaleMargins: { top: 0, bottom: 0 } })
      const regMap = new Map(ov.regime.map((r) => [r.time, r.label]))
      strip.setData(axis.map((t) => (regMap.has(t)
        ? { time: t, value: 1, color: regimeColor(regMap.get(t) as string) } : { time: t })) as any)

      // Legend: "Regime: <label at hovered bar, else latest>" + one swatch per regime.
      const latest = ov.regime[ov.regime.length - 1].label
      const legend = document.createElement('div')
      legend.className = 'chart-legend'
      const cur = document.createElement('span')
      cur.className = 'regime-current'
      const setCur = (label: string, hovered: boolean) => {
        cur.innerHTML = `Regime${hovered ? '' : ' (latest)'}: <b style="color:${regimeColor(label)}">${regimeText(label)}</b>`
      }
      setCur(latest, false)
      legend.appendChild(cur)
      for (const [label, color] of Object.entries(REGIME_COLORS)) {
        const sw = document.createElement('span')
        sw.className = 'legend-swatch'
        sw.innerHTML = `<i style="background:${color}"></i>${regimeText(label)}`
        legend.appendChild(sw)
      }
      c.chartElement().parentElement!.appendChild(legend)
      const onHover = (param: any) => {
        const lbl = param?.time != null ? regMap.get(param.time as number) : undefined
        if (lbl) setCur(lbl, true); else setCur(latest, false)
      }
      main.subscribeCrosshairMove(onHover)
      c.subscribeCrosshairMove(onHover)
    }

    // Candle-pattern legend (full names for the short marker codes) — below the regime strip,
    // so the strip stays directly under the candles.
    if (candlePats.length || c12Drawn.length) {
      const legend = document.createElement('div')
      legend.className = 'chart-legend'
      const swatch = (dir: string) => dir === 'bullish' ? '#26a641' : dir === 'bearish' ? '#f85149' : '#8b949e'
      const three = [...new Map(candlePats.map((cp) => [cp.label, cp.direction])).entries()]
        .map(([label, dir]) => ({ code: candleCode(label), label, dir }))
      const twelve = [...new Map(c12Drawn.map((c: any) => [c.label, c])).values()]
        .map((c: any) => ({ code: c.code, label: c.label, dir: c.direction }))
      legend.innerHTML = 'Candle patterns: ' + [...three, ...twelve].map((x) =>
        `<span class="legend-swatch"><i style="background:${swatch(x.dir)}"></i><b>${x.code}</b>&nbsp;${x.label}</span>`).join('')
        + (c12Drawn.length ? '<span class="legend-note">@sup / @res = support / resistance zone, @fib = Fibonacci level, '
          + '@TL = trendline — shown where the wick touched that level as of that candle. (last) = the candle the verdict reads.</span>' : '')
      root.appendChild(legend)
    }

    // ---- sub-panes (all mapped onto `axis`, so their indices match the price pane) ----
    if (toggles.volume) {
      const c = newPane('volume', SUB_H)
      const vol = c.addHistogramSeries({ priceFormat: { type: 'volume' }, priceLineVisible: false })
      const volMap = new Map(data.candles.filter((k) => k.volume != null)
        .map((k) => [k.time, { v: k.volume as number, up: k.close >= k.open }]))
      vol.setData(axis.map((t) => (volMap.has(t)
        ? { time: t, value: volMap.get(t)!.v, color: volMap.get(t)!.up ? '#26a64155' : '#f8514955' }
        : { time: t })) as any)
      const ma = c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      ma.setData(align(ind.volume_ma) as any)
    }

    if (toggles.rsi) {
      const c = newPane('RSI', SUB_H)
      const rsi = c.addLineSeries({ color: '#d29922', lineWidth: 2, priceLineVisible: false })
      rsi.setData(align(ind.rsi) as any)
      for (const [lvl, style] of [[70, 2], [30, 2]] as [number, number][])
        rsi.createPriceLine({ price: lvl, color: '#30363d', lineWidth: 1, lineStyle: style,
          axisLabelVisible: true } as any)
      const d = ov.divergence
      if (d && d.times.length) {
        const byTime = new Map(ind.rsi.map((p) => [p.time, p.value]))
        rsi.setMarkers(d.times.map((t) => ({
          time: t, position: d.kind === 'bearish' ? 'aboveBar' : 'belowBar',
          color: d.kind === 'bearish' ? '#f85149' : '#26a641', shape: 'circle',
          text: `${d.kind} div`,
        })).filter((m) => byTime.has(m.time)) as any)
      }
    }

    if (toggles.macd) {
      const c = newPane('MACD', SUB_H)
      const hist = c.addHistogramSeries({ priceLineVisible: false })
      const histMap = new Map(ind.macd.hist.map((p) => [p.time, p.value]))
      hist.setData(axis.map((t) => (histMap.has(t)
        ? { time: t, value: histMap.get(t)!, color: histMap.get(t)! >= 0 ? '#26a64188' : '#f8514988' }
        : { time: t })) as any)
      c.addLineSeries({ color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(align(ind.macd.line) as any)
      c.addLineSeries({ color: '#d29922', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        .setData(align(ind.macd.signal) as any)
    }

    if (toggles.adx) {
      const c = newPane('ADX', SUB_H)
      const adx = c.addLineSeries({ color: '#a371f7', lineWidth: 2, priceLineVisible: false })
      adx.setData(align(ind.adx) as any)
      adx.createPriceLine({ price: 25, color: '#30363d', lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title: 'trend' } as any)
    }

    if (toggles.atr) {
      const c = newPane('ATR', SUB_H)
      c.addLineSeries({ color: '#ec8e2c', lineWidth: 2, priceLineVisible: false })
        .setData(align(ind.atr) as any)
    }

    syncTimeScales()
    // Bounded right stop (snap-back). While you actively drag, the right edge can rubber-band into
    // empty space — lightweight-charts overrides an in-scroll correction, so a hard stop mid-drag
    // isn't possible — but crucially the WIDTH is preserved, so it never becomes a zoom. Once the
    // scroll settles we snap the last candle back to RIGHT_OFFSET bars from the edge (the gap).
    // Debounced so the correction lands after the drag stops, not fighting it. Clamping the MAIN
    // pane propagates to the sub-panes via the logical-range sync.
    const maxRight = data.candles.length - 1 + RIGHT_OFFSET
    let clamping = false
    let clampTimer: any
    main.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (!r || clamping || r.to <= maxRight) return
      clearTimeout(clampTimer)
      clampTimer = setTimeout(() => {
        const cur = main.timeScale().getVisibleLogicalRange()
        if (!cur || cur.to <= maxRight) return
        clamping = true
        main.timeScale().setVisibleLogicalRange({ from: maxRight - (cur.to - cur.from), to: maxRight })
        clamping = false
      }, 60)
    })
    // Initial view: the most recent ~200 bars with the trailing gap (like a trading chart). NOT
    // the whole history — thousands of bars hit lightweight-charts' minimum bar-spacing and the
    // view collapses/loses the gap. You can still pan all the way back to bar 0 (fixLeftEdge).
    const view = Math.min(data.candles.length, 200)
    if (savedRange && savedRange.key === dataKey(data)) main.timeScale().setVisibleLogicalRange(savedRange.range)
    else main.timeScale().setVisibleLogicalRange({ from: data.candles.length - view, to: maxRight })

    // Opt-in test hook (only when the URL carries ?__verify) so a headless browser can read the
    // real chart's range. No-op in normal use.
    if (typeof location !== 'undefined' && location.search.includes('__verify')) {
      (window as any).__mainChart = main; (window as any).__mainSeries = series
    }
  }

  // Shaded horizontal bands (series primitive): each zone fills lower..upper across the pane.
  class ZoneBands {
    series: any = null
    zones: { lower: number; upper: number; color: string }[]
    constructor(zones: { lower: number; upper: number; color: string }[]) { this.zones = zones }
    attached({ series }: any) { this.series = series }
    detached() { this.series = null }
    updateAllViews() {}
    paneViews() {
      const self = this
      return [{
        zOrder: () => 'bottom',
        renderer: () => ({
          draw: (target: any) => target.useBitmapCoordinateSpace((scope: any) => {
            if (!self.series) return
            const ctx = scope.context
            for (const z of self.zones) {
              const y1 = self.series.priceToCoordinate(z.upper)
              const y2 = self.series.priceToCoordinate(z.lower)
              if (y1 == null || y2 == null) continue
              const top = Math.round(Math.min(y1, y2) * scope.verticalPixelRatio)
              const h = Math.max(1, Math.round(Math.abs(y2 - y1) * scope.verticalPixelRatio))
              ctx.fillStyle = z.color
              ctx.fillRect(0, top, scope.bitmapSize.width, h)
            }
          }),
        }),
      }]
    }
  }

  // Plain-text labels at given prices, right-aligned just inside the price pane, no background. Labels
  // that would overlap are nudged apart vertically so they stay readable.
  class TextLabels {
    series: any = null
    items: { price: number; text: string; color: string }[]
    constructor(items: { price: number; text: string; color: string }[]) { this.items = items }
    attached({ series }: any) { this.series = series }
    detached() { this.series = null }
    updateAllViews() {}
    paneViews() {
      const self = this
      return [{
        zOrder: () => 'top',
        renderer: () => ({
          draw: (target: any) => target.useMediaCoordinateSpace((scope: any) => {
            if (!self.series) return
            const ctx = scope.context
            ctx.font = '11px -apple-system, system-ui, sans-serif'
            ctx.textAlign = 'right'
            ctx.textBaseline = 'bottom'
            const rows = self.items
              .map((it) => ({ ...it, y: self.series.priceToCoordinate(it.price) as number | null }))
              .filter((it) => it.y != null && it.y > 8 && it.y < scope.mediaSize.height)
              .sort((a, b) => (a.y as number) - (b.y as number))
            // Keep >= GAP px between labels: crowded labels form a group spread evenly around the
            // group's mean line position, so each label stays as close to its own line as possible.
            const GAP = 12
            const groups: { ys: number[]; top: number }[] = []
            for (const r of rows) {
              const want = (r.y as number) - 2
              groups.push({ ys: [want], top: want })
              while (groups.length > 1) {
                const g = groups[groups.length - 1], prev = groups[groups.length - 2]
                if (prev.top + prev.ys.length * GAP <= g.top) break
                prev.ys.push(...g.ys); groups.pop()
                const mean = prev.ys.reduce((a, b) => a + b, 0) / prev.ys.length
                prev.top = mean - ((prev.ys.length - 1) * GAP) / 2
              }
            }
            let k = 0
            for (const g of groups) g.ys.forEach((_, j) => {
              const r = rows[k++], x = scope.mediaSize.width - 6, y = g.top + j * GAP
              ctx.lineWidth = 3                    // thin outline in the chart colour, so a line
              ctx.strokeStyle = LAYOUT.background.color // running through stays readable (no box)
              ctx.strokeText(r.text, x, y)
              ctx.fillStyle = r.color
              ctx.fillText(r.text, x, y)
            })
          }),
        }),
      }]
    }
  }

  // lightweight-charts requires strictly-increasing unique times.
  function dedupeByTime<T extends { time: number }>(rows: T[]): T[] {
    const seen = new Set<number>()
    return rows.filter((r) => (seen.has(r.time) ? false : (seen.add(r.time), true)))
      .sort((a, b) => a.time - b.time)
  }
</script>

<div bind:this={root} class="chart-root"></div>

<style>
  .chart-root { width: 100%; }
  .chart-root :global(.pane) { position: relative; margin-bottom: 2px; }
  .chart-root :global(.pane-label) {
    position: absolute; top: 4px; left: 8px; z-index: 3;
    font-size: 11px; letter-spacing: .04em; text-transform: uppercase;
    color: #8b949e; pointer-events: none;
  }
  .chart-root :global(.chart-legend) {
    display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: center;
    padding: 4px 8px 6px; font-size: 12px; color: #8b949e;
  }
  .chart-root :global(.regime-current) { color: #c9d1d9; margin-right: 6px; }
  .chart-root :global(.legend-swatch) { display: inline-flex; align-items: center; gap: 5px; }
  .chart-root :global(.legend-note) { flex-basis: 100%; font-size: 11px; color: #6e7681; }
  .chart-root :global(.legend-swatch i) {
    display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  }
</style>
