"""The v0 → v1 migration against a real legacy database file."""

import sqlite3

import pytest

from worktime import config, db

LEGACY_SCHEMA = """
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    folder      TEXT,
    employer    TEXT,
    hourly_rate REAL,
    currency    TEXT DEFAULT 'EUR',
    color       TEXT,
    created_ts  REAL NOT NULL
);
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    app_bundle  TEXT, app_name TEXT, title TEXT, file_path TEXT, url TEXT,
    start_ts    REAL NOT NULL,
    end_ts      REAL NOT NULL,
    confidence  TEXT NOT NULL,
    billable    INTEGER NOT NULL DEFAULT 1,
    note        TEXT
);
CREATE TABLE rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    created_ts  REAL NOT NULL
);
CREATE TABLE project_folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path        TEXT NOT NULL
);
CREATE INDEX idx_sessions_start ON sessions(start_ts);
"""


@pytest.fixture
def legacy_path(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setattr(config, "DB_PATH", str(path))
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO projects (id, name, folder, hourly_rate, currency, created_ts)"
        " VALUES (1, 'P', '/work/p', 80, 'EUR', 0)")
    conn.execute(
        "INSERT INTO rules (project_id, kind, pattern, created_ts)"
        " VALUES (1, 'phone', 'fritz', 0)")
    conn.execute(     # pre-billable-fix row: guessed but flagged billable
        "INSERT INTO sessions (project_id, start_ts, end_ts, confidence, billable, note)"
        " VALUES (1, 0, 3600, 'inferred', 1, 'x')")
    conn.execute(
        "INSERT INTO sessions (project_id, start_ts, end_ts, confidence, billable)"
        " VALUES (1, 3600, 7200, 'auto-file', 1)")
    conn.commit()
    conn.close()
    return path


def _columns(path, table):
    with sqlite3.connect(path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_v1_migration_consolidates_legacy_data(legacy_path):
    db.init_db()

    assert _columns(legacy_path, "projects") == {
        "id", "name", "employer", "fee", "color", "created_ts"}
    assert "note" not in _columns(legacy_path, "sessions")

    # legacy folder became a managed project folder
    assert db.all_project_folders() == [{"path": "/work/p", "project_id": 1}]

    # phone rule collapsed into the behaviourally identical title_contains
    assert [r["kind"] for r in db.list_rules()] == ["title_contains"]

    # billable flags normalized: guessed time no longer counts until confirmed
    summary = db.totals_between(0, 7200)
    assert summary["tracked_seconds"] == 7200
    assert summary["billable_seconds"] == 3600

    with sqlite3.connect(legacy_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION

    # a safety copy of the pre-migration file exists
    assert legacy_path.with_name(legacy_path.name + ".v0.bak").exists()


def test_init_db_is_idempotent_after_migration(legacy_path):
    db.init_db()
    db.init_db()      # no error, no double-migration
    assert _columns(legacy_path, "projects") == {
        "id", "name", "employer", "fee", "color", "created_ts"}


def test_fresh_db_starts_at_current_version(tmp_path, monkeypatch):
    path = tmp_path / "fresh.db"
    monkeypatch.setattr(config, "DB_PATH", str(path))
    db.init_db()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert not path.with_name(path.name + ".v0.bak").exists()
