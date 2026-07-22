"""SQLite storage: projects, sessions, rules — with versioned migrations.

Billing model: a project is paid a fixed fee (EUR), not by the hour. Tracked
time exists to answer one question — is the fee still a healthy effective
hourly wage (fee / billable hours), or is the project eating too much time?
"""

import os
import sqlite3
import time
from contextlib import contextmanager

from . import config

BILLABLE_CONFIDENCES = {"auto-file", "auto-rule", "auto-title", "manual"}
_BILLABLE_SQL = ", ".join(f"'{c}'" for c in sorted(BILLABLE_CONFIDENCES))

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    employer    TEXT,
    fee         REAL,                       -- fixed project price (EUR)
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
    confidence  TEXT NOT NULL,              -- auto-file | auto-rule | auto-title | manual | inferred | unassigned
    billable    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,              -- app | url_domain | title_contains
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


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:                # commit on success, rollback on error
            yield conn
    finally:
        conn.close()


# --- schema lifecycle -------------------------------------------------------
def _migrate_v1(conn):
    """Project-fee model + legacy cleanup.

    Folds the write-never projects.folder column into project_folders, replaces
    hourly_rate/currency with a fixed EUR fee (rates were wages-in, fees are a
    different quantity — values are not carried over), drops the never-used
    sessions.note, collapses the phone/contact rule kinds into title_contains
    (identical behaviour), and normalizes billable flags written before the
    confidence-aware default existed.
    """
    conn.execute(
        "INSERT INTO project_folders (project_id, path)"
        " SELECT id, folder FROM projects WHERE folder IS NOT NULL")
    conn.execute("ALTER TABLE projects DROP COLUMN folder")
    conn.execute("ALTER TABLE projects ADD COLUMN fee REAL")
    conn.execute("ALTER TABLE projects DROP COLUMN hourly_rate")
    conn.execute("ALTER TABLE projects DROP COLUMN currency")
    conn.execute("ALTER TABLE sessions DROP COLUMN note")
    conn.execute(
        "UPDATE rules SET kind = 'title_contains' WHERE kind IN ('phone', 'contact')")
    conn.execute(
        "UPDATE sessions SET billable = 0 WHERE billable = 1 AND (project_id IS NULL"
        " OR confidence NOT IN ('auto-file', 'auto-rule', 'manual'))")


MIGRATIONS = [_migrate_v1]      # index i migrates user_version i -> i+1


def _backup(conn, version):
    """One-time safety copy before a migration rewrites billing data."""
    dest = sqlite3.connect(f"{config.DB_PATH}.v{version}.bak")
    try:
        conn.backup(dest)
    finally:
        dest.close()


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with _conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")   # concurrent tracker-write / GUI-read
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        fresh = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
        ).fetchone() is None
        if fresh:
            conn.executescript(SCHEMA)
        elif version < SCHEMA_VERSION:
            _backup(conn, version)
            for step in MIGRATIONS[version:SCHEMA_VERSION]:
                step(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# --- projects ---------------------------------------------------------------
def add_project(name, folder=None, employer=None, fee=None, color=None):
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, employer, fee, color, created_ts)"
            " VALUES (?,?,?,?,?)",
            (name, employer, fee, color, time.time()),
        )
        pid = cur.lastrowid
    if folder:
        add_project_folder(pid, folder)
    return pid


def list_projects():
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY name")]


def update_project(project_id, name, employer, fee, color):
    with _conn() as conn:
        conn.execute(
            "UPDATE projects SET name=?, employer=?, fee=?, color=? WHERE id=?",
            (name, employer, fee, color, project_id))


def delete_project(project_id):
    """Deletes the project; its sessions become Unassigned (FK SET NULL)."""
    with _conn() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# --- project folders (a project can own several) ----------------------------
def add_project_folder(project_id, path):
    path = os.path.abspath(os.path.expanduser(path))
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO project_folders (project_id, path) VALUES (?, ?)",
            (project_id, path),
        )
        return cur.lastrowid


def list_project_folders(project_id):
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, path FROM project_folders WHERE project_id = ? ORDER BY path",
            (project_id,))]


def all_project_folders():
    """[{path, project_id}] across every project — used by attribution."""
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT path, project_id FROM project_folders")]


def delete_project_folder(folder_id):
    with _conn() as conn:
        conn.execute("DELETE FROM project_folders WHERE id = ?", (folder_id,))


# --- rules ------------------------------------------------------------------
def add_rule(project_id, kind, pattern):
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO rules (project_id, kind, pattern, created_ts) VALUES (?,?,?,?)",
            (project_id, kind, pattern.lower(), time.time()),
        )
        return cur.lastrowid


def list_rules():
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT r.*, p.name AS project_name FROM rules r"
            " LEFT JOIN projects p ON p.id = r.project_id ORDER BY r.id")]


def delete_rule(rule_id):
    with _conn() as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


# --- sessions ---------------------------------------------------------------
def session_is_billable(session):
    return (
        bool(session.get("billable"))
        and session.get("project_id") is not None
        and session.get("confidence") in BILLABLE_CONFIDENCES
    )


def _default_billable(confidence, project_id):
    return int(project_id is not None and confidence in BILLABLE_CONFIDENCES)


def insert_session(s):
    confidence = s.get("confidence", "unassigned")
    project_id = s.get("project_id")
    billable = s.get("billable")
    if billable is None:
        billable = _default_billable(confidence, project_id)
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (project_id, app_bundle, app_name, title, file_path, url,"
            " start_ts, end_ts, confidence, billable) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, s.get("app_bundle"), s.get("app_name"), s.get("title"),
             s.get("file_path"), s.get("url"), s["start_ts"], s["end_ts"],
             confidence, int(bool(billable))),
        )
        return cur.lastrowid


def set_session_project(session_id, project_id, confidence="manual"):
    """Assign (or re-assign) a session to a project — used by the Review tab."""
    if project_id is None:
        confidence = "unassigned"
    billable = _default_billable(confidence, project_id)
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET project_id = ?, confidence = ?, billable = ? WHERE id = ?",
            (project_id, confidence, billable, session_id),
        )


def set_session_billable(session_id, billable):
    """Toggle invoice inclusion; checking a guessed row confirms its project."""
    with _conn() as conn:
        if billable:
            conn.execute(
                "UPDATE sessions SET "
                "billable = CASE WHEN project_id IS NULL THEN 0 ELSE 1 END, "
                "confidence = CASE "
                "  WHEN project_id IS NOT NULL "
                f"   AND confidence NOT IN ({_BILLABLE_SQL}) THEN 'manual' "
                "  ELSE confidence END "
                "WHERE id = ?",
                (session_id,),
            )
        else:
            conn.execute("UPDATE sessions SET billable = 0 WHERE id = ?", (session_id,))


def delete_session(session_id):
    """Remove a tracked entry entirely (cleanup of unrelated activity)."""
    with _conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def assign_unassigned_by_app(app_bundle, project_id):
    """When a rule is created, sweep up earlier unassigned entries of that app.
    Returns how many were re-assigned."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE sessions SET project_id = ?, confidence = 'auto-rule', billable = 1 "
            "WHERE project_id IS NULL AND app_bundle = ?",
            (project_id, app_bundle),
        )
        return cur.rowcount


def sessions_between(start_ts, end_ts):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT s.*, p.name AS project_name FROM sessions s"
            " LEFT JOIN projects p ON p.id = s.project_id"
            " WHERE s.start_ts >= ? AND s.start_ts < ? ORDER BY s.start_ts",
            (start_ts, end_ts),
        )
        return [dict(r) for r in rows]


def totals_between(start_ts, end_ts):
    """Per-project period totals plus each project's lifetime effective rate.

    Tracked time counts every session; billable time only confirmed,
    invoice-safe ones — guessed/unassigned time stays visible but never
    changes the numbers until the user confirms it. eff_rate is
    fee / *lifetime* billable hours (a fixed fee spreads over all the time a
    project ever took, not just this period's slice).
    """
    placeholders = ",".join("?" * len(BILLABLE_CONFIDENCES))
    with _conn() as conn:
        projects = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM projects")}
        lifetime = {r["project_id"]: r["secs"] for r in conn.execute(
            "SELECT project_id, SUM(end_ts - start_ts) AS secs FROM sessions"
            " WHERE billable = 1 AND project_id IS NOT NULL"
            f"  AND confidence IN ({placeholders}) GROUP BY project_id",
            tuple(BILLABLE_CONFIDENCES))}
        by_project = {}
        confidence_seconds = {}
        for row in conn.execute(
                "SELECT * FROM sessions WHERE start_ts >= ? AND start_ts < ?",
                (start_ts, end_ts)):
            s = dict(row)
            pid = s["project_id"]
            p = projects.get(pid)
            entry = by_project.setdefault(pid, {
                "project_id": pid,
                "project_name": p["name"] if p else "Unassigned",
                "employer": (p["employer"] if p else "") or "",
                "fee": p["fee"] if p and p["fee"] else None,
                "color": p["color"] if p else None,
                "tracked_seconds": 0.0,
                "billable_seconds": 0.0,
            })
            seconds = max(0.0, s["end_ts"] - s["start_ts"])
            entry["tracked_seconds"] += seconds
            confidence_seconds[s["confidence"]] = (
                confidence_seconds.get(s["confidence"], 0.0) + seconds)
            if session_is_billable(s):
                entry["billable_seconds"] += seconds

    for pid, entry in by_project.items():
        entry["tracked_hours"] = entry["tracked_seconds"] / 3600.0
        entry["billable_hours"] = entry["billable_seconds"] / 3600.0
        life_hours = lifetime.get(pid, 0.0) / 3600.0
        entry["lifetime_billable_hours"] = life_hours
        fee = entry["fee"]
        entry["eff_rate"] = round(fee / life_hours, 2) if fee and life_hours else None

    rows = sorted(by_project.values(), key=lambda r: -r["tracked_seconds"])
    return {
        "tracked_seconds": sum(r["tracked_seconds"] for r in rows),
        "billable_seconds": sum(r["billable_seconds"] for r in rows),
        "confidence_seconds": confidence_seconds,
        "rows": rows,
        "by_project_id": {r["project_id"]: r for r in rows},
    }
