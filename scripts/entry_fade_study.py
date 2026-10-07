"""Experiment (D2, forward-only): on the daily chart, does going AGAINST a textbook entry beat the textbook side?

    # 1. register (once, on the machine that keeps the forward record):
    python scripts/entry_fade_study.py --register \\
        --question "daily: fade textbook entries?" \\
        --hypothesis "On 1d, the mirror of trendline touch / MA pullback / resistance rejection / support bounce wins >= 55% of decisive forward entries" \\
        --metric mirror_win_rate --threshold 0.55 --baseline 0.5 --predict pass --predicted-value 0.58
    # 2. progress at any time (records nothing):
    python scripts/entry_fade_study.py --progress

The morning job records the result by itself once `--min-n` decisive forward entries exist (see
src/research/entry_fade.py). Only entry points frozen at 08:00 count — never the training pool, which is
where the idea came from.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forward.record import connect as fconnect  # noqa: E402
from src.research import prereg  # noqa: E402
from src.research.entry_fade import DEFAULT_TYPES, SCRIPT, live  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", default="1d")
    ap.add_argument("--types", default=",".join(DEFAULT_TYPES))
    ap.add_argument("--min-n", type=int, default=100, help="decisive forward entries before the result is recorded")
    ap.add_argument("--progress", action="store_true", help="show the open experiments' progress and exit")
    prereg.add_args(ap)
    args = ap.parse_args()
    fconnect(args.prereg_db).close()                     # make sure the forward tables exist
    if args.progress:
        conn = prereg.connect(args.prereg_db)
        for e in live(conn) or [None]:
            if e is None:
                print("No open entry_fade experiment — register one first.")
                break
            share = f" ({e['value'] * 100:.0f}%)" if e["value"] is not None else ""
            print(f"Experiment {e['id']}: {e['n']} of {e['min_n']} decisive {e['timeframe']} entries; "
                  f"mirror won {e['mirror']}{share}; {e['judged']} judged in all")
        conn.close()
        return
    params = {"timeframe": args.timeframe, "types": sorted(args.types.split(",")), "min_n": args.min_n}
    if not args.register:
        print("This experiment is recorded by the morning job once it has its sample; use --register or --progress.")
        sys.exit(2)
    prereg.gate(args, SCRIPT, params)                    # registers and exits


if __name__ == "__main__":
    main()
