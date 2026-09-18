// Browser-verifies the brief/teaching UI toggle: the mode <select> appears only when `explain`
// is checked, and Analyze sends the chosen `explanation_style` to the API. Serves the built app
// + a mock backend that records the query it received.
import http from 'http'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(__dirname, '..', 'dist')
const canned = JSON.parse(fs.readFileSync(path.join(__dirname, 'canned.json'), 'utf8'))
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
let lastAnalysisQuery = ''

const server = http.createServer((req, res) => {
  const [url, qs] = req.url.split('?')
  const json = (o) => { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)) }
  if (url === '/pairs') return json([{ symbol: 'BTC/USDT', asset_class: 'crypto', label: 'Bitcoin' }])
  if (url === '/timeframes') return json(['1d'])
  if (url === '/analysis') { lastAnalysisQuery = qs || ''; return json(canned) }
  const file = path.join(dist, url === '/' ? 'index.html' : url)
  fs.readFile(file, (err, buf) => {
    if (err) { res.writeHead(404); return res.end('nf') }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }); res.end(buf)
  })
})
await new Promise((r) => server.listen(8123, r))

const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1100, height: 900 })
await page.goto('http://127.0.0.1:8123/', { waitUntil: 'networkidle0' })

const modeVisible = () => page.evaluate(() => !!document.querySelector('select.mode'))
const setChk = (label) => page.evaluate((l) => { const el = [...document.querySelectorAll('label.explain')].find((x) => x.textContent.includes(l)); const c = el.querySelector('input'); if (!c.checked) c.click() }, label)
const analyze = () => page.evaluate(() => [...document.querySelectorAll('button')].find((b) => /analy/i.test(b.textContent)).click())
const q = () => new URLSearchParams(lastAnalysisQuery).get('explanation_style')

const out = {}
out.modeHiddenWhenExplainOff = !(await modeVisible())          // expect true (hidden)
await setChk('explain')
await new Promise((r) => setTimeout(r, 100))
out.modeShownWhenExplainOn = await modeVisible()               // expect true

await page.select('select.mode', 'teaching')
await analyze(); await new Promise((r) => setTimeout(r, 300))
out.sentStyle_afterTeaching = q()                             // expect 'teaching'

await page.select('select.mode', 'brief')
await analyze(); await new Promise((r) => setTimeout(r, 300))
out.sentStyle_afterBrief = q()                               // expect 'brief'

const pass = out.modeHiddenWhenExplainOff && out.modeShownWhenExplainOn &&
  out.sentStyle_afterTeaching === 'teaching' && out.sentStyle_afterBrief === 'brief'
console.log(JSON.stringify(out, null, 2))
console.log(pass ? 'PASS' : 'FAIL')
await browser.close(); server.close()
