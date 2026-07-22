"""Offscreen GUI smoke: the views build and populate, the dialogs compute."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from worktime import config, db
from worktime.timeutil import period_bounds


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


class _FakeTracker:
    current_app = "Logic Pro"
    current_project = "Demo"


def test_window_builds_and_populates(app, store):
    start, _ = period_bounds("Today")
    p = store.add_project("Demo", folder="/tmp/demo", employer="Client", fee=1200)
    store.insert_session({"project_id": p, "app_bundle": "com.apple.logic10",
                          "app_name": "Logic Pro", "start_ts": start + 60,
                          "end_ts": start + 3660, "confidence": "auto-file"})
    from worktime.gui.window import MainWindow
    w = MainWindow(_FakeTracker())
    for i in range(4):
        w._switch(i)
    w.refresh_live()
    assert w.review.table.rowCount() == 1
    assert w.reports.table.item(0, 4).text() == "1200 €"
    assert "auto" in w.reports.coverage.text()


def test_session_dialog_add_block(app, store):
    p = store.add_project("Demo")
    from worktime.gui.session_dialog import SessionDialog
    dlg = SessionDialog(projects=db.list_projects())
    dlg.description.setText("client call")
    dlg.minutes.setValue(90)
    block = dlg.block()
    assert block["project_id"] == p
    assert block["app_name"] == "client call"
    assert block["confidence"] == "manual"
    assert block["end_ts"] - block["start_ts"] == 90 * 60


def test_session_dialog_edit_times_prefills_span(app):
    from worktime.gui.session_dialog import SessionDialog
    now = time.time()
    dlg = SessionDialog(session={"start_ts": now - 3600, "end_ts": now - 1800})
    assert dlg.project is None          # edit mode: times only
    start_ts, end_ts = dlg.span()
    assert end_ts - start_ts == 30 * 60
