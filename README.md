# Trading Wizard — a visual trading advisor

A web app that analyzes **crypto and forex** candles, draws the chart structure it finds, flags
higher-confidence setups when independent signals agree, and **explains its reasoning in plain
language** (via Claude). It shows an honest track record on every setup.

**What it is NOT:** it does not place trades and does not predict the future. Out-of-sample and
machine-learning testing both confirmed it has **no predictive edge** — its value is *clarity and
learning*, not prophecy. **Not financial advice.**

See [`ROADMAP.md`](ROADMAP.md) for the full phased roadmap,
[`CLAUDE.md`](CLAUDE.md) for the architecture at a glance, and [`DEPLOY.md`](DEPLOY.md) for
hosting it live.

## Tech stack

- **Backend:** Python — FastAPI, pandas, numpy, scipy, ccxt (market data), pandas-ta-classic
  (indicators), scikit-learn (ML eval), Anthropic Claude (explanations)
- **Frontend:** Svelte 5 + TypeScript + Vite, TradingView lightweight-charts
- **Data:** Binance (crypto, public), Twelve Data (forex), plus the context APIs below
- **Deploy:** uvicorn behind Caddy/nginx (auto-HTTPS); CI via GitHub Actions

## Technical analysis (the deterministic engine)

- **Trend:** moving averages (SMA) + crossover, **ADX** (trend strength / regime), trend
  classification (higher-highs/lower-lows + MA slope)
- **Momentum:** RSI, MACD (line/signal/histogram), Stochastic, **RSI divergence**
- **Volatility:** ATR, Bollinger Bands (+%B)
- **Volume:** volume vs its moving average, OBV
- **Structure:** swing-point detection (the foundation), support/resistance clustering,
  trendlines (least-squares fit), Fibonacci retracement, round-number (psychological) levels
- **Patterns:** candlestick — doji, hammer, **shooting star**, bullish/bearish engulfing;
  chart — double top/bottom, head & shoulders (+ inverse), triangles
- **Multi-timeframe:** higher-timeframe (4h/1d) trend gates the base-timeframe read
- **Confluence engine:** groups signals into independent categories (trend / momentum /
  structure / volume / volatility) into a **0–1 confidence score** (correlated signals collapse
  instead of double-counting)

## Fundamental & context analysis (background for the AI — context, not prediction)

- **Sentiment:** crypto Fear & Greed index (alternative.me)
- **Crypto fundamentals:** market cap, circulating supply, 24h volume, distance from all-time
  high, 24h change (CoinGecko)
- **Macro:** high-impact economic calendar events (Finnhub)
- **News:** recent headlines (Finnhub)
- **Positioning/derivatives:** perpetual funding rate + open interest (Binance) — crypto only
- **Market adaptation:** real vs tick volume, forex sessions, weekend gaps

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # add ANTHROPIC_API_KEY (only needed for Claude explanations)
```

Optional keys in `.env` unlock extra features (all degrade gracefully without them):
`FINNHUB_API_KEY` (news + calendar), `TWELVEDATA_API_KEY` (forex), `WEBHOOK_URL` (alerts).

## Usage

```bash
python scripts/download_data.py          # cache candles for the pair in config.yaml

python scripts/serve.py                  # run the API  -> http://127.0.0.1:8000/docs
cd web && npm install && npm run dev     # run the UI   -> http://localhost:5173

python scripts/analyze.py                # CLI: annotated chart + explanation in outputs/
python scripts/analyze.py --timeframes 1h,4h,1d   # cross-timeframe synthesis
python scripts/backtest.py               # forward-return backtest
python scripts/backtest_suite.py         # out-of-sample backtest across coins + time halves
python scripts/watch.py                  # scan a watchlist, alert on flagged setups (cron-able)
python scripts/ml_eval.py                # walk-forward ML evaluation (verdict: no edge)
```

Behavior is configured in [`config.yaml`](config.yaml) (symbols, timeframe, detector
sensitivity, model, alerts, …). `data/` (cached candles) and `outputs/` are gitignored.

## Tests

~198 tests run offline (network-marked tests are separate); GitHub Actions runs `ruff` + the
offline suite on every push.

```bash
pytest                     # all tests (needs network for the @network ones)
pytest -m "not network"    # offline suite (what CI runs)
```

Coverage includes: every detector (swings, S/R, trendlines, trend, Fibonacci, indicators,
candlestick & chart patterns, divergence, round numbers); the confluence scoring; **look-ahead
safety guards** (backtest, multi-timeframe, and ML features all prove mutating future bars never
changes the past — no data leakage); a snapshot regression test; API auth + rate-limit tests;
context/derivatives/forex tests (injected HTTP, no network); and the ML harness — including
*honesty tests* proving the walk-forward model **finds a planted signal but reports ~50% on pure
noise**, so its "no edge" verdict is trustworthy.
