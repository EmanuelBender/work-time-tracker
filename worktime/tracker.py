"""The sampling loop: an in-memory state machine that emits Session rows.

Holds the current activity; when the resolved (project, app, file/title) changes
or you go idle, it closes the open session and starts a new one. Only sessions
hit the database — no row-per-tick.
"""

import datetime
import threading
import time

from . import attribution, config, db
from .detector import Detector
from .log import get_logger

log = get_logger("tracker")


def _activity_key(project_id, activity):
    # NB: the window title is intentionally EXCLUDED. It flickers (Logic shows
    # 'Last Christmas - Tracks' / '' / None as focus moves between the arrange
    # window, mixer and plugins), which would fragment a session below the
    # minimum length and drop it. A session's identity is project + app + doc.
    return (project_id, activity.get("app_bundle"), activity.get("file_path"))


def _day_slices(start_ts, end_ts):
    """Split [start_ts, end_ts] at local midnights so daily totals stay exact."""
    slices, cur = [], start_ts
    while True:
        day = datetime.date.fromtimestamp(cur)
        midnight = datetime.datetime.combine(
            day + datetime.timedelta(days=1), datetime.time.min).timestamp()
        if end_ts <= midnight:
            slices.append((cur, end_ts))
            return slices
        slices.append((cur, midnight))
        cur = midnight


class Tracker:
    def __init__(self):
        self.detector = Detector()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._current = None      # open session, or None
        self._manual = None       # {"project_id": ...} while a manual timer runs
        self.last_status = "starting…"
        self.current_app = None       # for the menu bar
        self.current_project = None
        self._context_project_id = None   # last strong project, for inference

    # --- manual timer -------------------------------------------------------
    def start_manual(self, project_id):
        with self._lock:
            self._manual = {"project_id": project_id}

    def stop_manual(self):
        with self._lock:
            self._manual = None

    @property
    def manual_active(self):
        with self._lock:
            return self._manual is not None

    # --- loop ---------------------------------------------------------------
    def run(self):
        db.init_db()
        log.info("tracker started (interval=%ss idle=%ss min=%ss)",
                 config.SAMPLE_INTERVAL, config.IDLE_THRESHOLD, config.MIN_SESSION)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:           # one bad app must not kill the loop
                log.exception("tick failed")
                self.last_status = f"error: {e}"
            self._stop.wait(config.SAMPLE_INTERVAL)
        self._close_current(time.time())
        log.info("tracker stopped")

    def stop(self):
        self._stop.set()

    def _tick(self):
        now = time.time()
        if self._current:
            gap = now - self._current["last_ts"]
            if gap > config.MAX_TICK_GAP:
                # The sampler went silent (sleep, closed lid, suspension). The
                # gap must never be billed: end the session at the last live
                # sample instead of letting last_ts jump across it.
                self._close_current(now)
                if gap >= config.IDLE_THRESHOLD:
                    self._context_project_id = None
        activity = self.detector.sample()
        if activity is None:
            return  # ignored / no frontmost -> leave the current session as-is

        if activity["idle_seconds"] >= config.IDLE_THRESHOLD:
            self._close_current(now)
            self.last_status = "idle"
            self.current_app = self.current_project = None
            self._context_project_id = None   # walking away clears the context
            return

        projects = db.list_projects()
        rules = db.list_rules()
        folders = db.all_project_folders()
        with self._lock:
            manual = self._manual
        if manual:
            project_id, confidence = manual["project_id"], "manual"
        else:
            project_id, confidence, _ = attribution.resolve(activity, projects, rules, folders)

        # Session inference: a confident attribution (open project file, a rule,
        # or a manual timer) becomes the "current context". Activity that has no
        # signal of its own (e.g. Soundly with no project file) is then attributed
        # to that context — so it follows whatever project you're working in,
        # rather than being locked to one. Tagged 'inferred' so it's reviewable.
        if confidence in ("auto-file", "auto-rule", "manual"):
            self._context_project_id = project_id
        elif project_id is None and self._context_project_id is not None:
            project_id, confidence = self._context_project_id, "inferred"

        key = _activity_key(project_id, activity)
        if self._current and self._current["key"] == key:
            self._current["last_ts"] = now
            # keep the best-known title/document for this session (titles flicker)
            a = self._current["activity"]
            if activity.get("file_path"):
                a["file_path"] = activity["file_path"]
            if activity.get("title"):
                a["title"] = activity["title"]
        else:
            self._close_current(now)
            self._current = {
                "key": key, "start_ts": now, "last_ts": now,
                "project_id": project_id, "confidence": confidence,
                "activity": activity,
            }

        pname = next((p["name"] for p in projects if p["id"] == project_id), "Unassigned")
        self.current_app = activity["app_name"]
        self.current_project = pname
        self.last_status = f"{activity['app_name']} → {pname}"

    def _close_current(self, now):
        c, self._current = self._current, None
        if not c:
            return
        if c["last_ts"] - c["start_ts"] < config.MIN_SESSION:
            return  # too short -> drop (quick app flick)
        a = c["activity"]
        log.info("logged %3ds  %-18s [%s]  %s", int(c["last_ts"] - c["start_ts"]),
                 a.get("app_name"), c["confidence"], a.get("file_path") or a.get("title") or "")
        for start_ts, end_ts in _day_slices(c["start_ts"], c["last_ts"]):
            db.insert_session({
                "project_id": c["project_id"],
                "app_bundle": a.get("app_bundle"),
                "app_name": a.get("app_name"),
                "title": a.get("title"),
                "file_path": a.get("file_path"),
                "url": a.get("url"),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "confidence": c["confidence"],
            })
