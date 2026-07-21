"""Fee-model billing: a project pays a fixed fee; the tracker answers whether
the effective wage (fee / billable hours) is still healthy."""

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
    project = store.add_project("P", employer="Client", fee=240)
    store.insert_session(_session(project, 0, 3600, "auto-file"))
    guessed = store.insert_session(_session(project, 3600, 7200, "inferred"))

    row = store.totals_between(0, 7200)["by_project_id"][project]
    assert row["tracked_seconds"] == 7200
    assert row["billable_seconds"] == 3600
    assert row["eff_rate"] == 240              # 240 € over 1 confirmed hour

    store.set_session_project(guessed, project)
    row = store.totals_between(0, 7200)["by_project_id"][project]
    assert row["billable_seconds"] == 7200
    assert row["eff_rate"] == 120              # fee is fixed; more hours = lower wage


def test_non_billable_session_stays_tracked(store):
    project = store.add_project("P", fee=500)
    session_id = store.insert_session(_session(project, 0, 3600, "auto-rule"))

    store.set_session_billable(session_id, False)
    summary = store.totals_between(0, 3600)
    row = summary["by_project_id"][project]

    assert row["tracked_seconds"] == 3600
    assert row["billable_seconds"] == 0
    assert row["eff_rate"] is None
    assert summary["tracked_seconds"] == 3600
    assert summary["billable_seconds"] == 0


def test_effective_rate_uses_lifetime_hours_not_the_period(store):
    project = store.add_project("P", fee=800)
    day = 86400
    store.insert_session(_session(project, 0, 4 * 3600))            # day 1: 4 h
    store.insert_session(_session(project, day, day + 4 * 3600))    # day 2: 4 h

    row = store.totals_between(day, 2 * day)["by_project_id"][project]

    assert row["billable_hours"] == 4          # this period's slice
    assert row["lifetime_billable_hours"] == 8
    assert row["eff_rate"] == 100              # 800 € over all 8 h ever spent


def test_no_fee_or_no_billable_time_means_no_rate(store):
    project = store.add_project("P")
    store.insert_session(_session(project, 0, 3600))
    assert store.totals_between(0, 3600)["by_project_id"][project]["eff_rate"] is None

    fee_only = store.add_project("Q", fee=100)
    store.insert_session(_session(fee_only, 0, 3600, "inferred"))
    assert store.totals_between(0, 3600)["by_project_id"][fee_only]["eff_rate"] is None


def test_report_csv_rows_match_shared_aggregation(store):
    project = store.add_project("P", employer="Client", fee=80)
    store.insert_session(_session(project, 0, 3600, "auto-file"))
    store.insert_session(_session(project, 3600, 5400, "inferred"))

    rows = store.totals_between(0, 5400)["rows"]

    assert list(report_csv_rows(rows)) == [
        REPORT_CSV_HEADER,
        ["P", "Client", "1.50", "1.00", "80", "80.00"],
    ]
