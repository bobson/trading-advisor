"""ROADMAP A8 — when the morning report runs. 08:00 Europe/Skopje, daylight-saving aware.

The real trigger is a systemd timer on the droplet (`deploy/trading-wizard-morning.timer`,
`OnCalendar=*-*-* 08:00:00 Europe/Skopje`, `Persistent=false` so a missed morning is a gap, never
a late catch-up). These functions give the SAME answers in Python: the run date a moment belongs
to (the local Skopje date, so a manual run at 00:30 local isn't filed under yesterday's UTC date)
and the next scheduled run — used by the report page, the `--wait` mode and the tests.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def run_date(now_utc: datetime, tz: str = "Europe/Skopje") -> date:
    """The local calendar date of `now_utc` in `tz` — the key of a morning's run."""
    return now_utc.astimezone(ZoneInfo(tz)).date()


def next_run(now_utc: datetime, tz: str = "Europe/Skopje", at: str = "08:00") -> datetime:
    """The next local `at` in `tz` strictly after `now_utc`, returned in UTC. Building the local
    wall-clock time with the zone (not adding a fixed UTC offset) is what makes it DST-aware:
    08:00 Skopje is 06:00 UTC in summer and 07:00 UTC in winter."""
    z = ZoneInfo(tz)
    hh, mm = (int(x) for x in at.split(":"))
    local = now_utc.astimezone(z)
    candidate = datetime.combine(local.date(), time(hh, mm), tzinfo=z)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), time(hh, mm), tzinfo=z)
    return candidate.astimezone(timezone.utc)
