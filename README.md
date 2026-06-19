# WorktimeTracker

A lean macOS menu-bar app that automatically tracks billable time per freelance
project, by detecting which project folder's documents you're working in (plus
rule-based attribution for email, calls, browser, and AI tools).

See [PLAN.md](PLAN.md) for the full design and phased roadmap.

## Status

**Phase 1.5 — GUI (current).** Detection engine, SQLite store, attribution, and
the sampling state machine are built and validated against real apps (Logic Pro,
Mail, Safari, Telephone, Claude/Codex). The UI is a **PySide6** app — a menu-bar
item plus **Review / Projects / Reports** windows. Review-and-assign is the core:
track everything, then assign unknowns with a click. `cli.py` is a dev tool only.

## Setup

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Grant **Accessibility** permission to whatever runs it (your Terminal, for now):
System Settings → Privacy & Security → Accessibility.

## Use

Register a project (folder = one project):

```sh
./.venv/bin/python -m worktime.cli add-project "Last Christmas" \
    --folder "/Volumes/4TB HighSpeed/Logic/Pandoras Play/Last Christmas" \
    --employer "Pandoras Play" --rate 80
```

Add a rule for non-file work (e.g. calls via Telephone → this project):

```sh
./.venv/bin/python -m worktime.cli add-rule --project 1 --kind app \
    --pattern com.tlphn.Telephone
```

Track (headless), then review today's totals:

```sh
./.venv/bin/python -m worktime.cli run       # Ctrl-C to stop
./.venv/bin/python -m worktime.cli today
```

Or — the normal way — launch the GUI (menu-bar item + Review / Projects /
Reports windows; register projects and assign time here instead of the CLI):

```sh
./.venv/bin/python -m worktime.gui
```

Data lives at `~/Library/Application Support/WorktimeTracker/worktime.db`
(override with the `WORKTIME_DB` env var).

## Layout

| File | Role |
|---|---|
| `worktime/detector.py` | Live frontmost-app + document + idle detection |
| `worktime/attribution.py` | Resolve an activity to a project (file match / rule) |
| `worktime/tracker.py` | Sampling state machine → Session rows |
| `worktime/db.py` | SQLite schema + storage |
| `worktime/cli.py` | Headless CLI (setup, run, reports) |
| `worktime/gui.py` | PySide6 GUI: menu-bar item + Review / Projects / Reports |
| `detect_probe.py` | Standalone detection spike (diagnostics) |
