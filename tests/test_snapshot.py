"""Phase 20 — snapshot regression: build_facts on a FIXED real-data slice must not drift.

This guards against silent detector drift when a threshold or detector is tuned. It is the
regression guard for facts-only phases (where the backtest is trivially unchanged).

If this test fails: READ THE DIFF and confirm the change was intended BEFORE regenerating —
a snapshot you blindly regenerate guards nothing. To regenerate after an intended change:

    python -c "import json,pandas as pd; \
from src.config import load_config; from src.indicators.features import add_features; \
from src.structure.swings import find_swings; from src.advisor.facts import build_facts; \
df=pd.read_csv('tests/fixtures/btc_1h_sample.csv',index_col='timestamp',parse_dates=['timestamp']); \
df.index=pd.to_datetime(df.index,utc=True); cfg=load_config(); \
facts=build_facts(add_features(df,cfg),find_swings(df,cfg.structure.swing_sensitivity),cfg); \
open('tests/fixtures/expected_facts.json','w').write(json.dumps(facts,indent=2,sort_keys=True))"
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.advisor.facts import build_facts
from src.config import load_config
from src.indicators.features import add_features
from src.structure.swings import find_swings

FIXTURES = Path(__file__).parent / "fixtures"


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="timestamp", parse_dates=["timestamp"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def test_facts_snapshot_is_stable():
    cfg = load_config()
    df = _load(FIXTURES / "btc_1h_sample.csv")
    feat = add_features(df, cfg)
    swings = find_swings(df, cfg.structure.swing_sensitivity)
    facts = build_facts(feat, swings, cfg)

    expected = json.loads((FIXTURES / "expected_facts.json").read_text())
    # Round-trip through json so any tuple/np types match the file's parsed form; dict == is
    # order-independent, and pytest prints the differing key on failure.
    assert json.loads(json.dumps(facts)) == expected
