// Verifies the MULTI-PANE component behavior (sync + clamp together): panning works and syncs
// all panes, no zoom at any drag, the right edge is a bounded gap, the left edge is a hard stop,
// dragging a SUB-pane is corrected via the round-trip, and there are no console-error loops.
import puppeteer from 'puppeteer-core'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1000, height: 700 })
let consoleErrors = 0
page.on('console', (m) => { if (m.type() === 'error') consoleErrors++ })
const pageErrors = []
page.on('pageerror', (e) => pageErrors.push(e.message))

await page.goto('file://' + path.join(__dirname, 'harness-multi.html'))
await page.waitForFunction('window.__ready === true', { timeout: 8000 })

const N = await page.evaluate(() => window.__N)
const OFF = await page.evaluate(() => window.__RIGHT_OFFSET)
const mainRange = () => page.evaluate(() => { const r = window.__main.timeScale().getVisibleLogicalRange(); return { from: r.from, to: r.to } })
// how far each pane's visible TIME range agrees (max abs diff of the `to` edge across panes)
const syncSkewSec = () => page.evaluate(() => {
  const tos = window.__charts.map((c) => c.timeScale().getVisibleRange()?.to).filter((x) => x != null)
  return Math.max(...tos) - Math.min(...tos)
})
const drag = async (x1, y, x2) => { await page.mouse.move(x1, y); await page.mouse.down(); for (let i = 1; i <= 20; i++) await page.mouse.move(x1 + ((x2 - x1) * i) / 20, y); await page.mouse.up(); await new Promise((r) => setTimeout(r, 40)) }

await page.evaluate(() => window.__main.timeScale().setVisibleLogicalRange({ from: 120, to: 180 }))
await new Promise((r) => setTimeout(r, 60))
const r0 = await mainRange(); const w0 = r0.to - r0.from

await drag(520, 200, 300); const r1 = await mainRange()
const out = {}
out.panWorks = Math.abs(r1.from - r0.from) > 1
out.panNoZoom = Math.abs((r1.to - r1.from) - w0) < 1
out.syncSkewBars_afterPan = +((await syncSkewSec()) / 86400).toFixed(2)

for (let k = 0; k < 8; k++) await drag(720, 200, 150)       // slam RIGHT on the main
const rR = await mainRange()
out.rightNoZoom = Math.abs((rR.to - rR.from) - w0) < 1
out.rightGap_bars = +(rR.to - (N - 1)).toFixed(1)

for (let k = 0; k < 6; k++) await drag(720, 480, 150)       // slam RIGHT on a SUB-pane (y in sub2)
const rSub = await mainRange()
out.subDragBounded_gap_bars = +(rSub.to - (N - 1)).toFixed(1)

for (let k = 0; k < 14; k++) await drag(150, 200, 850)      // slam LEFT
const rL = await mainRange()
out.leftStop_from = +rL.from.toFixed(1)
out.leftNoZoom = Math.abs((rL.to - rL.from) - w0) < 1

await page.evaluate(() => window.__main.timeScale().setVisibleLogicalRange({ from: 0, to: window.__N - 1 + window.__RIGHT_OFFSET }))
await new Promise((r) => setTimeout(r, 200))
await page.screenshot({ path: path.join(__dirname, 'chart-multi.png') })

out.consoleErrors = consoleErrors
out.pageErrors = pageErrors
const pass = out.panWorks && out.panNoZoom && out.rightNoZoom && out.leftNoZoom &&
  out.rightGap_bars >= OFF - 2 && out.rightGap_bars <= OFF + 3 &&
  out.subDragBounded_gap_bars <= OFF + 3 && out.leftStop_from <= 1.5 &&
  Math.abs(out.syncSkewBars_afterPan) < 1.5 && out.consoleErrors === 0 && pageErrors.length === 0
console.log(JSON.stringify(out, null, 2))
console.log(pass ? 'PASS' : 'FAIL')
await browser.close()
