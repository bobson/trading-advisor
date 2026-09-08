<script lang="ts">
  import { onMount } from 'svelte'
  import { createChart, type IChartApi, type ISeriesApi, type IPriceLine } from 'lightweight-charts'
  import type { ChartData } from './api'

  let { data }: { data: ChartData | null } = $props()

  let el: HTMLDivElement
  let chart: IChartApi | null = null
  let series: ISeriesApi<'Candlestick'> | null = null
  let priceLines: IPriceLine[] = []

  onMount(() => {
    chart = createChart(el, {
      height: 460,
      layout: { background: { color: '#0e1117' }, textColor: '#c9d1d9' },
      grid: { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } },
      timeScale: { timeVisible: true, borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
    })
    series = chart.addCandlestickSeries({
      upColor: '#26a641', downColor: '#f85149',
      borderVisible: false, wickUpColor: '#26a641', wickDownColor: '#f85149',
    })
    render()
    const ro = new ResizeObserver(() => chart?.applyOptions({ width: el.clientWidth }))
    ro.observe(el)
    return () => { ro.disconnect(); chart?.remove(); chart = null }
  })

  // Re-render whenever `data` changes.
  $effect(() => { data; render() })

  function render() {
    if (!chart || !series || !data) return
    series.setData(data.candles as any)

    // Redraw horizontal levels: clear the old price lines first (v4 has no clear-all).
    for (const pl of priceLines) series.removePriceLine(pl)
    priceLines = []

    for (const lv of data.overlays.levels) {
      priceLines.push(series.createPriceLine({
        price: lv.price,
        color: lv.role === 'support' ? '#26a641' : '#f85149',
        lineWidth: 1, lineStyle: 0,
        axisLabelVisible: true, title: `${lv.role} (${lv.touches})`,
      } as any))
    }
    const fib = data.overlays.fibonacci
    if (fib) {
      for (const [ratio, price] of Object.entries(fib.levels)) {
        priceLines.push(series.createPriceLine({
          price, color: '#8b949e', lineWidth: 1, lineStyle: 2,
          axisLabelVisible: true, title: `fib ${(Number(ratio) * 100).toFixed(1)}%`,
        } as any))
      }
    }

    // Swing pivots + the confluence marker (arrow colored by bias) on the last bar.
    const markers = data.overlays.swings.map((s) => ({
      time: s.time as any,
      position: s.kind === 'high' ? 'aboveBar' : 'belowBar',
      color: '#8b949e', shape: 'circle',
    }))
    const m = data.overlays.marker
    if (m) {
      markers.push({
        time: m.time as any,
        position: m.bias === 'bullish' ? 'belowBar' : 'aboveBar',
        color: m.bias === 'bullish' ? '#26a641' : '#f85149',
        shape: m.bias === 'bullish' ? 'arrowUp' : 'arrowDown',
      } as any)
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number))
    series.setMarkers(markers as any)
    chart.timeScale().fitContent()
  }
</script>

<div bind:this={el} style="width:100%"></div>
