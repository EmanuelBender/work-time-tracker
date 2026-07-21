import pytest

from worktime import config, db
from worktime.reporting import REPORT_CSV_HEADER, report_csv_rows


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def _session(project_id, start, end, confidence="auto-file", billable=None):
    s = {
        "project_id": project_id,
        "app_bundle": "com.test",
        "app_name": "Test",
        "start_ts": start,
        "end_ts": end,
        "confidence": confidence,
    }
    if billable is not None:
        s["billable"] = billable
    return s


def test_inferred_time_is_not_billable_until_confirmed(store):
    project = store.add_project("P", employer="Client", hourly_rate=60, currency="EUR")
    store.insert_session(_session(project, 0, 3600, "auto-file"))
    guessed = store.insert_session(_session(project, 3600, 7200, "inferred"))

    summary = store.totals_between(0, 7200)
    row = summary["by_project_id"][project]

    assert row["tracked_seconds"] == 7200
    assert row["billable_seconds"] == 3600
    assert row["amount"] == 60
    assert summary["billable_amount"] == 60

    store.set_session_project(guessed, project)
    summary = store.totals_between(0, 7200)
    row = summary["by_project_id"][project]

    assert row["billable_seconds"] == 7200
    assert row["amount"] == 120


def test_non_billable_session_stays_tracked(store):
    project = store.add_project("P", hourly_rate=90)
    session_id = store.insert_session(_session(project, 0, 3600, "auto-rule"))

    store.set_session_billable(session_id, False)
    summary = store.totals_between(0, 3600)
    row = summary["by_project_id"][project]

    assert row["tracked_seconds"] == 3600
    assert row["billable_seconds"] == 0
    assert row["amount"] == 0
    assert summary["tracked_seconds"] == 3600
    assert summary["billable_amount"] == 0


def test_amount_uses_project_rate_and_currency(store):
    project = store.add_project("P", hourly_rate=80, currency="EUR")
    store.insert_session(_session(project, 0, 1800, "manual"))

    row = store.totals_between(0, 1800)["by_project_id"][project]

    assert row["billable_hours"] == 0.5
    assert row["amount"] == 40
    assert row["currency"] == "EUR"


def test_rounding_applies_to_project_period_total_not_each_session(store):
    project = store.add_project("P", hourly_rate=60)
    for i in range(3):
        store.insert_session(_session(project, i * 250, (i + 1) * 250, "auto-file"))

    raw = store.totals_between(0, 750)["by_project_id"][project]
    rounded = store.totals_between(0, 750, rounding_minutes=15)["by_project_id"][project]

    assert raw["billable_seconds"] == 750
    assert raw["amount"] == 12.5
    assert rounded["billable_seconds"] == 900
    assert rounded["amount"] == 15


def test_report_csv_rows_match_shared_aggregation(store):
    project = store.add_project("P", employer="Client", hourly_rate=80, currency="EUR")
    store.insert_session(_session(project, 0, 3600, "auto-file"))
    store.insert_session(_session(project, 3600, 5400, "inferred"))

    rows = store.totals_between(0, 5400)["rows"]

    assert list(report_csv_rows(rows)) == [
        REPORT_CSV_HEADER,
        ["P", "Client", "1.50", "1.00", "80", "80.00", "EUR"],
    ]
