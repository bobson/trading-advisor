"""ROADMAP A8 — run the morning report once (the systemd timer calls this at 08:00 Europe/Skopje).

    python scripts/morning_report.py                    # manual trigger
    python scripts/morning_report.py --trigger schedule # what the timer runs
    python scripts/morning_report.py --db /tmp/scratch.db   # a scratch DB (never test into the record)

Review first, then read, then (if `morning_report.synthesis`) one Claude synthesis per symbol.
Running twice in a day adds nothing new; a second run only retries markets that failed.
A file lock next to the DB stops two runs overlapping (timer + "run now" button).
"""

from __future__ import annotations

import argparse
import fcntl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.forward.record import connect, run_morning  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/wizard.db")
    ap.add_argument("--trigger", default="manual", choices=["manual", "schedule", "api"])
    args = ap.parse_args()

    lock_path = Path(f"{args.db}.morning.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another morning run is in progress — not starting a second one.")
            return 2
        cfg = load_config()
        conn = connect(args.db)
        try:
            out = run_morning(cfg, conn, trigger=args.trigger)
        finally:
            conn.close()
    print(f"Morning run {out['run_date']}: {out['status']} — {out['new_reads']} new reads, "
          f"{out['resolved']} resolved, engine {out['engine']['commit']}{' (dirty)' if out['engine']['dirty'] else ''}")
    for g in out["gaps"]:
        print(f"  gap recorded: {g}")
    for s in out["skipped"]:
        print(f"  skipped {s['symbol']} {s['timeframe']}: {s['reason']}")
    return 0 if out["status"] != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
