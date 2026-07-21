"""Headless dev CLI. Projects and rules are managed in the GUI.

    python -m worktime.cli run      # start tracking in the terminal (Ctrl-C to stop)
    python -m worktime.cli today    # today's sessions + per-project totals
"""

import argparse
import datetime
import threading
import time

from . import config, db
from .timeutil import fmt_hms, period_bounds
from .tracker import Tracker


def cmd_today(a):
    start, end = period_bounds("Today")
    for s in db.sessions_between(start, end):
        t = datetime.datetime.fromtimestamp(s["start_ts"]).strftime("%H:%M")
        detail = s["file_path"] or s["title"] or ""
        print(f"{t}  {fmt_hms(s['end_ts'] - s['start_ts'])}  "
              f"{(s['project_name'] or 'Unassigned'):<20} {s['app_name']:<14} {detail}")
    print("-" * 60)
    for r in db.totals_between(start, end)["rows"]:
        print(f"{fmt_hms(r['tracked_seconds']):>12}  {r['project_name']}")


def cmd_run(a):
    t = Tracker()
    print(f"tracking… (Ctrl-C to stop)   db={config.DB_PATH}")
    th = threading.Thread(target=t.run, daemon=True)
    th.start()
    try:
        while True:
            time.sleep(2)
            print("\r  " + t.last_status.ljust(60), end="", flush=True)
    except KeyboardInterrupt:
        t.stop()
        th.join(timeout=3)
        print("\nstopped.")


def main():
    p = argparse.ArgumentParser(prog="worktime")
    sub = p.add_subparsers(required=True)
    sub.add_parser("today").set_defaults(func=cmd_today)
    sub.add_parser("run").set_defaults(func=cmd_run)
    args = p.parse_args()
    db.init_db()
    args.func(args)


if __name__ == "__main__":
    main()
