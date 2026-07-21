"""PySide6 desktop GUI — dark theme, the real product surface.

Layout: a persistent status bar (what's tracking now + today's totals), a left
project rail with colours and live hours, and four views — Review (assign
unknowns), Projects, Reports (totals + effective wage + CSV), Rules.

The detection engine (detector / tracker / attribution / db) is unchanged.

    python -m worktime.gui
"""

import signal
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import config, db
from ..detector import accessibility_ok
from ..instance import InstanceGuard, stop_tracker
from ..log import get_logger
from ..statusbar import StatusBar
from ..timeutil import fmt_hm, period_bounds
from ..tracker import Tracker
from .theme import QSS, project_color
from .window import MainWindow

log = get_logger("gui")


def _short(text, n=22):
    return text if len(text) <= n else text[: n - 1] + "…"


def today_summary():
    """(total_secs, billable_secs, [(name, secs, colour)] biggest-first) for
    today — feeds the menu-bar title and dropdown."""
    start, end = period_bounds("Today")
    summary = db.totals_between(start, end)
    rows = [
        (r["project_name"], r["tracked_seconds"], project_color(r) if r["project_id"] else "#888780")
        for r in summary["rows"]
    ]
    return summary["tracked_seconds"], summary["billable_seconds"], rows


def main():
    app = QApplication.instance() or QApplication([])
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)
    signal.signal(signal.SIGTERM, lambda _signal, _frame: QTimer.singleShot(0, app.quit))

    guard = InstanceGuard()
    if not guard.acquire():
        log.info("app already running; duplicate launch exiting")
        return 0

    tracker = None
    tracker_thread = None
    shutdown_complete = False

    def shutdown():
        nonlocal shutdown_complete
        if shutdown_complete:
            return
        shutdown_complete = True
        if tracker is not None and tracker_thread is not None:
            if not stop_tracker(tracker, tracker_thread, config.SAMPLE_INTERVAL + 1):
                log.warning("tracker thread did not stop before shutdown timeout")
        guard.release()

    try:
        db.init_db()
        log.info("app starting; accessibility granted=%s", accessibility_ok())
        app.setStyleSheet(QSS)
        app.setQuitOnLastWindowClosed(False)

        tracker = Tracker()
        tracker_thread = threading.Thread(target=tracker.run, daemon=True)
        tracker_thread.start()
        app.aboutToQuit.connect(shutdown)

        window = MainWindow(tracker)

        def show_window():
            window.show(); window.raise_(); window.activateWindow()

        statusbar = StatusBar(on_open=show_window, on_quit=app.quit)

        def tick():
            total, billable, rows = today_summary()
            proj, app_name = tracker.current_project, tracker.current_app
            active = bool(proj and proj != "Unassigned")
            title = f"{fmt_hm(total)} · {_short(proj)}" if active else fmt_hm(total)
            now_text = f"{app_name} → {proj}" if proj else None
            now_color = next((c for n, _d, c in rows if n == proj), None) if proj else None
            proj_rows = [(name, fmt_hm(d), color) for name, d, color in rows]
            total_text = f"Total   {fmt_hm(total)}   ·   billable {fmt_hm(billable)}"
            statusbar.update(title, now_text, now_color, proj_rows, total_text)
            if window.isVisible():
                window.refresh_live()

        timer = QTimer(); timer.timeout.connect(tick); timer.start(5000)
        tick()

        if not accessibility_ok():
            QMessageBox.warning(window, "Accessibility needed",
                                "Grant access in System Settings → Privacy & Security → "
                                "Accessibility (to whatever launches this), then relaunch.")
        window.show()
        return app.exec()
    finally:
        shutdown()
