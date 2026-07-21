"""SQLite storage: projects, sessions, rules."""

import math
import os
import sqlite3
import time

from . import config

BILLABLE_CONFIDENCES = {"auto-file", "auto-rule", "manual"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    folder      TEXT,                       -- absolute path; NULL = rule-only project
    employer    TEXT,
    hourly_rate REAL,
    currency    TEXT DEFAULT 'EUR',
    color       TEXT,
    created_ts  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    app_bundle  TEXT,
    app_name    TEXT,
    title       TEXT,
    file_path   TEXT,
    url         TEXT,
    start_ts    REAL NOT NULL,
    end_ts      REAL NOT NULL,
    confidence  TEXT NOT NULL,              -- auto-file | auto-rule | manual | inferred | unassigned
    billable    INTEGER NOT NULL DEFAULT 1,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,              -- app | url_domain | title_contains | phone | contact
    pattern     TEXT NOT NULL,
    created_ts  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_ts);
"""


def connect():
    config.support_dir()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")   # concurrent tracker-write / GUI-read
        conn.executescript(SCHEMA)


# --- projects ---------------------------------------------------------------
def add_project(name, folder=None, employer=None, hourly_rate=None,
                currency="EUR", color=None):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, folder, employer, hourly_rate, currency, color, created_ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, None, employer, hourly_rate, currency, color, time.time()),
        )
        pid = cur.lastrowid
    if folder:
        add_project_folder(pid, folder)
    return pid


def list_projects():
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY name")]


def update_project(project_id, name, employer, hourly_rate, color, currency=None):
    with connect() as conn:
        if currency is None:
            conn.execute(
                "UPDATE projects SET name=?, employer=?, hourly_rate=?, color=? WHERE id=?",
                (name, employer, hourly_rate, color, project_id))
        else:
            conn.execute(
                "UPDATE projects SET name=?, employer=?, hourly_rate=?, color=?, currency=? WHERE id=?",
                (name, employer, hourly_rate, color, currency, project_id))


# --- project folders (a project can own several) ----------------------------
def add_project_folder(project_id, path):
    path = os.path.abspath(os.path.expanduser(path))
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO project_folders (project_id, path) VALUES (?, ?)",
            (project_id, path),
        )
        return cur.lastrowid


def list_project_folders(project_id):
    """Folders for one project (includes any legacy projects.folder value)."""
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, path FROM project_folders WHERE project_id = ? ORDER BY path",
            (project_id,))]
        legacy = conn.execute(
            "SELECT folder FROM projects WHERE id = ? AND folder IS NOT NULL",
            (project_id,)).fetchone()
        if legacy and legacy["folder"]:
            rows.append({"id": None, "path": legacy["folder"]})
    return rows


def all_project_folders():
    """[{path, project_id}] across every project — used by attribution."""
    with connect() as conn:
        out = [dict(r) for r in conn.execute(
            "SELECT path, project_id FROM project_folders")]
        for r in conn.execute(
                "SELECT folder AS path, id AS project_id FROM projects WHERE folder IS NOT NULL"):
            out.append(dict(r))
    return out


def delete_project_folder(folder_id):
    with connect() as conn:
        conn.execute("DELETE FROM project_folders WHERE id = ?", (folder_id,))


# --- rules ------------------------------------------------------------------
def add_rule(project_id, kind, pattern):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO rules (project_id, kind, pattern, created_ts) VALUES (?,?,?,?)",
            (project_id, kind, pattern.lower(), time.time()),
        )
        return cur.lastrowid


def list_rules():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT r.*, p.name AS project_name FROM rules r"
            " LEFT JOIN projects p ON p.id = r.project_id ORDER BY r.id")]


def delete_rule(rule_id):
    with connect() as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


def delete_project(project_id):
    """Deletes the project; its sessions become Unassigned (FK SET NULL)."""
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# --- sessions ---------------------------------------------------------------
def session_is_billable(session):
    return (
        bool(session.get("billable"))
        and session.get("project_id") is not None
        and session.get("confidence") in BILLABLE_CONFIDENCES
    )


def _default_billable(confidence, project_id):
    return int(project_id is not None and confidence in BILLABLE_CONFIDENCES)


def _round_seconds(seconds, rounding_minutes):
    if not rounding_minutes:
        return seconds
    step = int(rounding_minutes) * 60
    if step <= 0:
        return seconds
    return math.floor(seconds / step + 0.5) * step


def insert_session(s):
    confidence = s.get("confidence", "unassigned")
    project_id = s.get("project_id")
    billable = s.get("billable")
    if billable is None:
        billable = _default_billable(confidence, project_id)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (project_id, app_bundle, app_name, title, file_path, url,"
            " start_ts, end_ts, confidence, billable, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, s.get("app_bundle"), s.get("app_name"), s.get("title"),
             s.get("file_path"), s.get("url"), s["start_ts"], s["end_ts"],
             confidence, int(bool(billable)), s.get("note")),
        )
        return cur.lastrowid


def set_session_project(session_id, project_id, confidence="manual"):
    """Assign (or re-assign) a session to a project — used by the Review tab."""
    if project_id is None:
        confidence = "unassigned"
    billable = _default_billable(confidence, project_id)
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET project_id = ?, confidence = ?, billable = ? WHERE id = ?",
            (project_id, confidence, billable, session_id),
        )


def set_session_billable(session_id, billable):
    """Toggle invoice inclusion; checking a guessed row confirms its project."""
    with connect() as conn:
        if billable:
            conn.execute(
                "UPDATE sessions SET "
                "billable = CASE WHEN project_id IS NULL THEN 0 ELSE 1 END, "
                "confidence = CASE "
                "  WHEN project_id IS NOT NULL "
                "   AND confidence NOT IN ('auto-file', 'auto-rule', 'manual') THEN 'manual' "
                "  ELSE confidence END "
                "WHERE id = ?",
                (session_id,),
            )
        else:
            conn.execute("UPDATE sessions SET billable = 0 WHERE id = ?", (session_id,))


def delete_session(session_id):
    """Remove a tracked entry entirely (cleanup of unrelated activity)."""
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def assign_unassigned_by_app(app_bundle, project_id):
    """When a rule is created, sweep up earlier unassigned entries of that app.
    Returns how many were re-assigned."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE sessions SET project_id = ?, confidence = 'auto-rule', billable = 1 "
            "WHERE project_id IS NULL AND app_bundle = ?",
            (project_id, app_bundle),
        )
        return cur.rowcount


def sessions_between(start_ts, end_ts):
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.*, p.name AS project_name FROM sessions s"
            " LEFT JOIN projects p ON p.id = s.project_id"
            " WHERE s.start_ts >= ? AND s.start_ts < ? ORDER BY s.start_ts",
            (start_ts, end_ts),
        )
        return [dict(r) for r in rows]


def totals_between(start_ts, end_ts, rounding_minutes=0):
    """Shared period totals for UI, menu bar, reports, and CSV export.

    Tracked time includes every session. Billable time only includes explicitly
    billable sessions with invoice-safe confidence; guessed/unassigned time stays
    visible but does not affect amounts until the user confirms it.
    """
    with connect() as conn:
        projects = {
            r["id"]: dict(r)
            for r in conn.execute("SELECT * FROM projects")
        }
        rows = conn.execute(
            "SELECT * FROM sessions WHERE start_ts >= ? AND start_ts < ? ORDER BY start_ts",
            (start_ts, end_ts),
        )
        by_project = {}
        for row in rows:
            s = dict(row)
            pid = s["project_id"]
            p = projects.get(pid)
            entry = by_project.setdefault(pid, {
                "project_id": pid,
                "id": pid,
                "project_name": p["name"] if p else "Unassigned",
                "name": p["name"] if p else "Unassigned",
                "employer": (p["employer"] if p else "") or "",
                "rate": p["hourly_rate"] if p and p["hourly_rate"] else None,
                "currency": p["currency"] if p else "EUR",
                "color": p["color"] if p else None,
                "tracked_seconds": 0.0,
                "billable_seconds": 0.0,
            })
            seconds = max(0.0, s["end_ts"] - s["start_ts"])
            entry["tracked_seconds"] += seconds
            if session_is_billable(s):
                entry["billable_seconds"] += seconds

    for entry in by_project.values():
        entry["billable_seconds"] = _round_seconds(entry["billable_seconds"], rounding_minutes)
        entry["tracked_hours"] = entry["tracked_seconds"] / 3600.0
        entry["billable_hours"] = entry["billable_seconds"] / 3600.0
        rate = entry["rate"]
        entry["amount"] = round(entry["billable_hours"] * rate, 2) if rate else None

    rows = sorted(by_project.values(), key=lambda r: -r["tracked_seconds"])
    return {
        "tracked_seconds": sum(r["tracked_seconds"] for r in rows),
        "billable_seconds": sum(r["billable_seconds"] for r in rows),
        "billable_amount": sum(r["amount"] or 0.0 for r in rows),
        "rows": rows,
        "by_project_id": {r["project_id"]: r for r in rows},
    }
