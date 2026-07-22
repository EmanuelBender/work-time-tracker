# WorktimeTracker

A lean macOS menu-bar app that automatically tracks time per freelance project,
by detecting which project folder's documents you're working in (plus
rule-based attribution for email, calls, browser, and AI tools).

Freelance work here is paid a **fixed fee per project**, so the money question
the app answers is: *is this project still paying a healthy effective wage
(fee ÷ hours it actually takes), or is it eating too much time?*

See [PLAN.md](PLAN.md) for the full design and phased roadmap.

## Status

Detection engine, SQLite store (versioned migrations, daily backups),
attribution, and the sampling state machine are built and validated against
real apps (Logic Pro, Mail, Safari, Telephone, Claude/Codex). The UI is a
**PySide6** app — a native menu-bar item plus **Review / Projects / Reports /
Rules** views. Review-and-assign is the core: track everything, then assign
unknowns with a click.

Accuracy model (v0.3.0): playback counts as work (listening passes, video
review, calls — via power assertions, capped), project names/folder basenames
auto-match window titles (Terminal/agent sessions, Blender, mail subjects),
inference expires after 30 min, and off-computer work is added as manual
blocks. Reports show each project's fee, effective €/h coloured against your
target rate, and an attribution-coverage line that tells you how much time
attributed itself. `cli.py` is a dev tool only.

## Setup

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Grant **Accessibility** permission to whatever runs it (your Terminal, for now):
System Settings → Privacy & Security → Accessibility.

## Use

Launch the app (menu-bar item + Review / Projects / Reports / Rules windows —
register projects and folders, assign time, and create rules here):

```sh
./.venv/bin/python -m worktime.gui
```

Headless dev use: `python -m worktime.cli run` tracks in the terminal
(Ctrl-C to stop); `python -m worktime.cli today` prints today's sessions and
per-project totals.

The GUI is also available as a reviewed Start/Quit control in Manu Control
Center. A single-instance lock prevents duplicate trackers. Control Center may
quit only the process it launched; an exact externally launched instance is
observed without being adopted or stopped. Accessibility permission remains a
local prerequisite for activity detection.

Data lives at `~/Library/Application Support/WorktimeTracker/worktime.db`
(override with the `WORKTIME_DB` env var).

## Layout

| File | Role |
|---|---|
| `worktime/detector.py` | Live frontmost-app + document + idle detection |
| `worktime/attribution.py` | Resolve an activity to a project (file match / rule) |
| `worktime/tracker.py` | Sampling state machine → Session rows |
| `worktime/db.py` | SQLite schema, migrations + storage |
| `worktime/timeutil.py` | Duration formatting + period bounds (shared) |
| `worktime/reporting.py` | CSV report rows (headless) |
| `worktime/cli.py` | Headless dev CLI (`run`, `today`) |
| `worktime/statusbar.py` | Native menu-bar item (NSStatusItem) |
| `worktime/gui/` | PySide6 GUI package: theme, widgets, one module per view |
