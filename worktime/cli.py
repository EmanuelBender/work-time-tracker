"""Command-line interface — headless use, setup, and testing without the menu bar.

    python -m worktime.cli add-project "Last Christmas" \
        --folder "/Volumes/4TB HighSpeed/Logic/Pandoras Play/Last Christmas" \
        --employer "Pandoras Play" --rate 80
    python -m worktime.cli list-projects
    python -m worktime.cli add-rule --project 1 --kind app --pattern com.tlphn.Telephone
    python -m worktime.cli run            # start tracking (Ctrl-C to stop)
    python -m worktime.cli today          # today's sessions + per-project totals
"""

import argparse
import datetime
import threading
import time

from . import config, db
from .tracker import Tracker


def _fmt(seconds):
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _day_bounds(day=None):
    d = day or datetime.date.today()
    start = datetime.datetime(d.year, d.month, d.day).timestamp()
    return start, start + 86400


def cmd_add_project(a):
    pid = db.add_project(a.name, folder=a.folder, employer=a.employer,
                         hourly_rate=a.rate, currency=a.currency)
    print(f"added project #{pid}: {a.name}")


def cmd_list_projects(a):
    for p in db.list_projects():
        rate = f"{p['hourly_rate']:g} {p['currency']}/h" if p["hourly_rate"] else "no rate"
        folders = [f["path"] for f in db.list_project_folders(p["id"])] or ["(rule-only)"]
        print(f"#{p['id']:>3}  {p['name']:<24} {rate:<14} {folders[0]}")
        for extra in folders[1:]:
            print(f"{'':>35}{extra}")


def cmd_add_rule(a):
    rid = db.add_rule(a.project, a.kind, a.pattern)
    print(f"added rule #{rid}: {a.kind}={a.pattern} -> project #{a.project}")


def cmd_today(a):
    start, end = _day_bounds()
    rows = db.sessions_between(start, end)
    totals = {}
    for s in rows:
        name = s["project_name"] or "Unassigned"
        dur = s["end_ts"] - s["start_ts"]
        totals[name] = totals.get(name, 0) + dur
        t = datetime.datetime.fromtimestamp(s["start_ts"]).strftime("%H:%M")
        detail = s["file_path"] or s["title"] or ""
        print(f"{t}  {_fmt(dur)}  {name:<20} {s['app_name']:<14} {detail}")
    print("-" * 60)
    for name, secs in sorted(totals.items(), key=lambda x: -x[1]):
        print(f"{_fmt(secs):>12}  {name}")


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

    ap = sub.add_parser("add-project"); ap.set_defaults(func=cmd_add_project)
    ap.add_argument("name")
    ap.add_argument("--folder")
    ap.add_argument("--employer")
    ap.add_argument("--rate", type=float)
    ap.add_argument("--currency", default="EUR")

    sub.add_parser("list-projects").set_defaults(func=cmd_list_projects)

    ar = sub.add_parser("add-rule"); ar.set_defaults(func=cmd_add_rule)
    ar.add_argument("--project", type=int, required=True)
    ar.add_argument("--kind", required=True,
                    choices=["app", "url_domain", "title_contains", "phone", "contact"])
    ar.add_argument("--pattern", required=True)

    sub.add_parser("today").set_defaults(func=cmd_today)
    sub.add_parser("run").set_defaults(func=cmd_run)

    args = p.parse_args()
    db.init_db()
    args.func(args)


if __name__ == "__main__":
    main()
