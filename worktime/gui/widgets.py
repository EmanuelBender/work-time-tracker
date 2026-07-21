"""Reusable widgets: the project rail and the day-timeline strip."""

import datetime
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget,
)

from .. import db
from ..timeutil import fmt_hm, fmt_hms, period_bounds
from .theme import dot, project_color


class ProjectRail(QFrame):
    """Left rail: projects with colour + today hours."""

    def __init__(self, on_add):
        super().__init__()
        self.setObjectName("rail")
        self.setFixedWidth(208)
        self.v = QVBoxLayout(self); self.v.setContentsMargins(12, 12, 12, 12); self.v.setSpacing(4)
        head = QLabel("Projects"); head.setObjectName("h")
        self.v.addWidget(head)
        self.rows = QVBoxLayout(); self.rows.setSpacing(2)
        self.v.addLayout(self.rows)
        self.v.addStretch()
        add = QPushButton("  Add project"); add.setObjectName("accent"); add.clicked.connect(on_add)
        self.v.addWidget(add)

    def refresh(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().setParent(None)   # remove immediately (no ghosts)
        start, end = period_bounds("Today")
        summary = db.totals_between(start, end)
        for p in db.list_projects():
            row = summary["by_project_id"].get(p["id"])
            self.rows.addWidget(self._row(project_color(p), p["name"],
                                          row["tracked_seconds"] if row else 0))
        unassigned = summary["by_project_id"].get(None)
        if unassigned:
            self.rows.addWidget(self._row("#888780", "Unassigned",
                                          unassigned["tracked_seconds"], muted=True))

    def _row(self, color, name, seconds, muted=False):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(4, 5, 4, 5); h.setSpacing(8)
        h.addWidget(dot(color, 9))
        lbl = QLabel(name); lbl.setObjectName("muted" if muted else "")
        h.addWidget(lbl, 1)
        t = QLabel(fmt_hm(seconds)); t.setObjectName("muted")
        h.addWidget(t)
        return w


class TimelineWidget(QWidget):
    """A glanceable strip of today's tracked time: colour-coded blocks laid out
    on an hour axis, with a live 'now' marker. Hover a block for details."""

    TOP, BOT, ML, MR = 12, 48, 16, 16     # block band + side margins

    def __init__(self):
        super().__init__()
        self.setFixedHeight(80)
        self.setMouseTracking(True)
        self._sessions = []
        self._pcolor = {}
        self._segments = []

    def set_data(self, sessions, pcolor):
        self._sessions, self._pcolor = sessions, pcolor
        self.update()

    def _bounds(self):
        now = time.time()
        starts = [s["start_ts"] for s in self._sessions]
        ends = [s["end_ts"] for s in self._sessions] + [now]
        lo = (min(starts) if starts else now - 3600)
        hi = max(ends)
        lo -= lo % 3600                                   # floor to the hour
        hi += (3600 - hi % 3600) % 3600                   # ceil to the hour
        if hi - lo < 3 * 3600:                            # keep a readable span
            hi = lo + 3 * 3600
        return lo, hi

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x0, x1 = self.ML, self.width() - self.MR
        tw = max(1, x1 - x0)
        lo, hi = self._bounds()
        span = max(1.0, hi - lo)

        def X(t):
            return x0 + (t - lo) / span * tw

        p.setPen(Qt.NoPen); p.setBrush(QColor("#20242b"))
        p.drawRoundedRect(QRectF(x0, self.TOP, tw, self.BOT - self.TOP), 7, 7)

        hours = int((hi - lo) // 3600)
        step = max(1, round(hours / max(1.0, tw / 64)))
        f = p.font(); f.setPixelSize(11); p.setFont(f)
        n, h = 0, int(lo)
        while h <= hi + 1:
            x = X(h)
            p.setPen(QColor("#2c313a"))
            p.drawLine(int(x), self.TOP, int(x), self.BOT)
            if n % step == 0:
                p.setPen(QColor("#7e848f"))
                p.drawText(QRectF(x - 18, self.BOT + 4, 36, 14), Qt.AlignCenter,
                           datetime.datetime.fromtimestamp(h).strftime("%H"))
            h += 3600; n += 1

        self._segments = []
        for s in self._sessions:
            bx0, bx1 = X(s["start_ts"]), X(s["end_ts"])
            if bx1 - bx0 < 3:
                bx1 = bx0 + 3
            color = self._pcolor.get(s["project_id"], "#5a5d62")
            p.setPen(Qt.NoPen); p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(bx0, self.TOP + 4, bx1 - bx0, self.BOT - self.TOP - 8), 3, 3)
            self._segments.append((bx0, bx1, s))

        if not self._sessions:
            p.setPen(QColor("#7e848f"))
            p.drawText(QRectF(x0, self.TOP, tw, self.BOT - self.TOP),
                       Qt.AlignCenter, "No activity tracked yet today")

        nx = X(time.time())
        p.setPen(QColor("#5a96f2")); p.setBrush(QColor("#5a96f2"))
        p.drawLine(int(nx), self.TOP - 3, int(nx), self.BOT + 2)
        p.drawEllipse(QRectF(nx - 3, self.TOP - 6, 6, 6))

    def mouseMoveEvent(self, event):
        x, y = event.position().x(), event.position().y()
        if self.TOP <= y <= self.BOT:
            for bx0, bx1, s in self._segments:
                if bx0 - 2 <= x <= bx1 + 2:
                    a = datetime.datetime.fromtimestamp(s["start_ts"]).strftime("%H:%M")
                    b = datetime.datetime.fromtimestamp(s["end_ts"]).strftime("%H:%M")
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"{s['project_name'] or 'Unassigned'}\n{s['app_name']}  ·  "
                        f"{a}–{b}  ({fmt_hms(s['end_ts'] - s['start_ts'])})", self)
                    return
        QToolTip.hideText()
