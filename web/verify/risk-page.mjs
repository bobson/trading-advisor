// Browser-verifies the Feature 9 Risk-calculator page: the nav toggle switches to it, the page
// renders (position size, ruin %, Kelly, and the risk×win-rate table), and editing an input
// fires a /risk request with the updated params. Serves the built app + a mock backend (same
// origin, records the query it receives). Real math is already unit-tested; this checks the UI.
import http from 'http'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(__dirname, '..', 'dist')
const risk = JSON.parse(fs.readFileSync(path.join(__dirname, 'canned_risk.json'), 'utf8'))
const measured = JSON.parse(fs.readFileSync(path.join(__dirname, 'canned_measured.json'), 'utf8'))
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }
let lastRiskQuery = ''

const server = http.createServer((req, res) => {
  const [url, qs] = req.url.split('?')
  const json = (o) => { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)) }
  if (url === '/pairs') return json([{ symbol: 'BTC/USDT', asset_class: 'crypto', label: 'Bitcoin' }])
  if (url === '/timeframes') return json(['1h', '1d'])
  if (url === '/risk') { lastRiskQuery = qs || ''; return json(risk) }
  if (url === '/risk/measured') return json(measured)
  const file = path.join(dist, url === '/' ? 'index.html' : url)
  fs.readFile(file, (e, b) => {
    if (e) { res.writeHead(404); return res.end('nf') }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }); res.end(b)
  })
})
await new Promise((r) => server.listen(8140, r))

const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1100, height: 1300 })
const errs = []
page.on('pageerror', (e) => errs.push(e.message))
await page.goto('http://127.0.0.1:8140/', { waitUntil: 'networkidle0' })

const out = {}
// switch to the Risk calculator view
await page.evaluate(() => [...document.querySelectorAll('nav.views button')].find((b) => /risk/i.test(b.textContent)).click())
await page.waitForFunction("document.querySelector('.risk h2') && document.querySelector('table.ruin')", { timeout: 5000 })
await new Promise((r) => setTimeout(r, 300))

out.headingShown = await page.$eval('.risk h2', (el) => el.textContent.includes('Risk of ruin'))
out.ruinShown = await page.$$eval('.card .big', (els) => els.some((e) => /%/.test(e.textContent)))
out.positionUnits = await page.$eval('.card .big', (el) => el.textContent).catch(() => '')
out.tableCells = await page.$$eval('table.ruin td', (els) => els.length)   // expect 36 (6×6)

// edit the win-rate input -> a new /risk request should carry the changed win_rate
const winInput = (await page.$$('.grid-in input'))[4]  // account, entry, stop, risk, WIN, payoff
await winInput.click({ clickCount: 3 })
await winInput.type('60')
await new Promise((r) => setTimeout(r, 400))
out.refetchedWinRate = new URLSearchParams(lastRiskQuery).get('win_rate')  // expect '0.6'

// "use measured" button pulls a measured win rate + note
await page.evaluate(() => [...document.querySelectorAll('.row-btn button')].find((b) => /measured/i.test(b.textContent)).click())
await new Promise((r) => setTimeout(r, 300))
out.measuredNoteShown = await page.$eval('.row-btn .note', (el) => el.textContent).catch(() => '')

await page.screenshot({ path: path.join(__dirname, 'risk-page.png') })
out.pageErrors = errs

const pass = out.headingShown && out.ruinShown && out.tableCells === 36 &&
  out.refetchedWinRate === '0.6' && /backtest|52%/.test(out.measuredNoteShown) && errs.length === 0
console.log(JSON.stringify(out, null, 2))
console.log(pass ? 'PASS' : 'FAIL')
await browser.close(); server.close()
