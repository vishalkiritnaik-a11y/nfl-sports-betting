"""Pre-kickoff gate (stdlib only, runs in seconds).

GitHub Actions cannot schedule a job at each kickoff, so a 10-minute cron calls
this script. It answers: is any game kicking off in the next ~65 minutes that
has not already had its pre-game refresh? If so the full pipeline runs once for
that kickoff slot (all games sharing the kickoff time are refreshed together).

Writes `run=true|false` and `slot=<kickoff ISO>` to $GITHUB_OUTPUT.
Usage: python -m nfledge.gate [--now 2026-10-11T16:00:00Z]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
STATE = Path(__file__).resolve().parents[2] / "data" / "last_run.json"
ET = ZoneInfo("America/New_York")
ISO = "%Y-%m-%dT%H:%M:%SZ"

# Fire when kickoff is 35-65 minutes away. With a 10-minute cron the first eligible
# tick lands ~55-65 minutes before kickoff; the wide lower bound absorbs GitHub's
# scheduler delays so a late tick still refreshes before the game.
WINDOW_START = timedelta(minutes=65)
WINDOW_END = timedelta(minutes=35)


def kickoffs(text: str, now: datetime) -> list[datetime]:
    out = set()
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("home_score") not in ("", None, "NA"):
            continue
        try:
            local = datetime.strptime(f"{r['gameday']} {r['gametime'] or '13:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        except ValueError:
            continue
        k = local.astimezone(timezone.utc)
        if now - timedelta(hours=1) < k < now + timedelta(days=2):
            out.add(k)
    return sorted(out)


def decide(ks: list[datetime], now: datetime, done: set[str]) -> str | None:
    for k in ks:
        slot = k.strftime(ISO)
        if k - WINDOW_START <= now <= k - WINDOW_END and slot not in done:
            return slot
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now")
    a = ap.parse_args()
    now = datetime.strptime(a.now, ISO).replace(tzinfo=timezone.utc) if a.now else datetime.now(timezone.utc)
    with urllib.request.urlopen(SCHEDULE_URL, timeout=60) as r:
        text = r.read().decode()
    done = set()
    if STATE.exists():
        done = set(json.loads(STATE.read_text()).get("pregame_refreshed", []))
    ks = kickoffs(text, now)
    slot = decide(ks, now, done)
    nxt = next((k.strftime(ISO) for k in ks if k > now), None)
    print(f"now={now.strftime(ISO)} next_kickoff={nxt} run={'true' if slot else 'false'} slot={slot or ''}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"run={'true' if slot else 'false'}\nslot={slot or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
