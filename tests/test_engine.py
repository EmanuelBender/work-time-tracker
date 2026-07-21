"""Regression tests for the detection engine (no GUI, no macOS APIs).

Run:  ./.venv/bin/python -m pytest -q
"""

import datetime
import time

import pytest

from worktime import attribution, config, db
from worktime.tracker import Tracker, _day_slices


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def _act(bundle="com.x", app="X", file=None, url=None, title=None, idle=0.0):
    return {"pid": 123, "app_bundle": bundle, "app_name": app, "title": title,
            "file_path": file, "url": url, "idle_seconds": idle}


def _resolve(store, activity):
    return attribution.resolve(activity, store.list_projects(),
                               store.list_rules(), store.all_project_folders())


# --- attribution -----------------------------------------------------------
def test_folder_match(store):
    pid = store.add_project("P", folder="/work/p")
    project_id, conf, _ = _resolve(store, _act(file="/work/p/song.logicx"))
    assert project_id == pid and conf == "auto-file"


def test_longest_prefix_wins(store):
    store.add_project("A", folder="/work")
    b = store.add_project("B", folder="/work/sub")
    assert _resolve(store, _act(file="/work/sub/x.txt"))[0] == b


def test_second_folder_of_project_matches(store):
    p = store.add_project("P", folder="/work/a")
    store.add_project_folder(p, "/other/b")
    assert _resolve(store, _act(file="/other/b/x.psd"))[0] == p


def test_url_domain_rule(store):
    p = store.add_project("P")
    store.add_rule(p, "url_domain", "docs.google.com")
    pid, conf, _ = _resolve(store, _act(bundle="com.apple.Safari", url="https://docs.google.com/x"))
    assert pid == p and conf == "auto-rule"


def test_title_contains_rule(store):
    p = store.add_project("P")
    store.add_rule(p, "title_contains", "aufnahmen")
    assert _resolve(store, _act(bundle="com.apple.mail", title="Re: Aufnahmen"))[0] == p


def test_unassigned_when_nothing_matches(store):
    store.add_project("P", folder="/work/p")
    pid, conf, _ = _resolve(store, _act(file="/elsewhere/x"))
    assert pid is None and conf == "unassigned"


# --- tracker: inference + idle ---------------------------------------------
class _Fake:
    def __init__(self, items):
        self.items, self.i = items, 0

    def sample(self):
        a = self.items[min(self.i, len(self.items) - 1)]
        self.i += 1
        return a


def test_inference_follows_active_project(store, monkeypatch):
    monkeypatch.setattr(config, "MIN_SESSION", 0)
    p = store.add_project("P", folder="/work/p")
    tr = Tracker()
    tr.detector = _Fake([_act(bundle="com.apple.logic10", file="/work/p/s.logicx"),
                         _act(bundle="com.soundly", app="Soundly")])
    tr._tick()
    assert tr._context_project_id == p
    tr._tick()
    assert tr._current["project_id"] == p and tr._current["confidence"] == "inferred"


def test_idle_clears_context(store, monkeypatch):
    monkeypatch.setattr(config, "MIN_SESSION", 0)
    store.add_project("P", folder="/work/p")
    tr = Tracker()
    tr.detector = _Fake([_act(bundle="com.apple.logic10", file="/work/p/s.logicx"),
                         _act(bundle="com.soundly", app="Soundly", idle=99999),
                         _act(bundle="com.soundly", app="Soundly")])
    tr._tick(); tr._tick()                       # work, then walk away
    assert tr._context_project_id is None
    tr._tick()                                   # back, no context -> unassigned
    assert tr._current["project_id"] is None


def test_tick_gap_is_never_billed(store, monkeypatch):
    """Sleep/wake: an open session must end at the last live sample, not
    absorb the hours in between."""
    monkeypatch.setattr(config, "MIN_SESSION", 0)
    store.add_project("P", folder="/work/p")
    tr = Tracker()
    tr.detector = _Fake([_act(bundle="com.apple.logic10", file="/work/p/s.logicx")] * 2)
    tr._tick()
    last_seen = time.time() - 7200                     # 2h of silence (sleep)
    tr._current["start_ts"] = last_seen - 600
    tr._current["last_ts"] = last_seen
    tr._tick()
    closed = store.sessions_between(0, 2 ** 31)
    assert len(closed) == 1
    assert closed[0]["end_ts"] == pytest.approx(last_seen)
    assert tr._current["start_ts"] == pytest.approx(time.time(), abs=5)


def test_tick_gap_clears_inference_context(store, monkeypatch):
    monkeypatch.setattr(config, "MIN_SESSION", 0)
    store.add_project("P", folder="/work/p")
    tr = Tracker()
    tr.detector = _Fake([_act(bundle="com.apple.logic10", file="/work/p/s.logicx"),
                         _act(bundle="com.soundly", app="Soundly")])
    tr._tick()
    tr._current["last_ts"] = time.time() - 7200
    tr._tick()                                         # back after sleep, no signal
    assert tr._current["confidence"] == "unassigned"


def test_sessions_split_at_midnight(store, monkeypatch):
    monkeypatch.setattr(config, "MIN_SESSION", 0)
    midnight = datetime.datetime.combine(
        datetime.date.today(), datetime.time.min).timestamp()
    tr = Tracker()
    tr._current = {"key": ("k",), "start_ts": midnight - 3600, "last_ts": midnight + 1800,
                   "project_id": None, "confidence": "unassigned", "activity": _act()}
    tr._close_current(time.time())
    spans = [(r["start_ts"], r["end_ts"]) for r in store.sessions_between(0, 2 ** 31)]
    assert spans == [(midnight - 3600, midnight), (midnight, midnight + 1800)]


def test_day_slices_within_one_day_is_untouched():
    noon = datetime.datetime.combine(
        datetime.date.today(), datetime.time(12)).timestamp()
    assert _day_slices(noon, noon + 3600) == [(noon, noon + 3600)]


def test_min_session_drops_short(store, monkeypatch):
    monkeypatch.setattr(config, "MIN_SESSION", 30)
    store.add_project("P", folder="/work/p")
    tr = Tracker()
    tr.detector = _Fake([_act()])
    tr._tick()
    tr._close_current(time.time())               # ~0s -> dropped
    assert store.sessions_between(0, 2 ** 31) == []


# --- db crud ---------------------------------------------------------------
def test_project_update_and_folders(store):
    p = store.add_project("P", folder="/a", fee=10)
    store.add_project_folder(p, "/b")
    assert len(store.list_project_folders(p)) == 2
    store.update_project(p, "P2", "Emp", 99, "#ffffff")
    got = store.list_projects()[0]
    assert (got["name"], got["fee"], got["color"]) == ("P2", 99, "#ffffff")
    store.delete_project(p)
    assert store.list_projects() == []
