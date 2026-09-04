# Trading Advisor

A **visual trading advisor** (Python): it computes chart structure from price data
(trend, support/resistance, trendlines, Fibonacci), flags higher-confidence setups when
several signals agree, and explains its reasoning in plain trading language.

It **does not place trades and does not predict the future.** Its value is clarity and
education. None of this is financial advice.

See [`PLAN.md`](PLAN.md) for the full design and phased build roadmap, and
[`CLAUDE.md`](CLAUDE.md) for the architecture at a glance.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # add ANTHROPIC_API_KEY (only needed for the Phase 7 reasoning layer)
```

## Usage

```bash
# Download and cache ~6 months of candles for the symbol in config.yaml
python scripts/download_data.py
```

Behavior is configured in [`config.yaml`](config.yaml) (symbol, timeframe, detector
sensitivity, model). Downloaded candles are cached under `data/` (gitignored).

## Tests

```bash
pytest                     # all tests
pytest -m "not network"    # skip tests that hit the exchange (offline)
pytest tests/test_exchange.py::test_normalize_empty   # a single test
```
