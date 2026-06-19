"""PySide6 desktop GUI — dark theme, the real product surface.

Layout: a persistent status bar (what's tracking now + today's totals), a left
project rail with colours and live hours, and three views — Review (assign
unknowns), Projects (manage projects + their folders), Reports (totals + CSV).

The detection engine (detector / tracker / attribution / db) is unchanged.

    python -m worktime.gui
"""

import csv
import datetime
import threading
import time
import urllib.parse

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QStackedWidget, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QToolTip, QVBoxLayout, QWidget,
)

from . import db
from .detector import accessibility_ok
from .log import get_logger
from .tracker import Tracker

log = get_logger("gui")

PERIODS = ["Today", "Last 7 days", "This month"]
PALETTE = ["#8B7FE8", "#2FB89B", "#E8825A", "#5A9CF8", "#E06A98", "#E0A23B", "#8BBF4E"]

QSS = """
QMainWindow, QDialog { background: #16181c; }
QWidget { color: #e8eaed; font-family: "SF Pro Text", "Helvetica Neue"; font-size: 13px; }

QLabel#muted { color: #969ba4; }
QLabel#h { color: #7e848f; font-size: 11px; }
QLabel#big { font-size: 22px; font-weight: 500; color: #f4f6f8; }
QLabel#now { font-size: 14px; color: #cfd3da; }

QFrame#card {
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.085);
    border-radius: 12px;
}
QFrame#rail {
    background: rgba(255, 255, 255, 0.022);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}

QTableWidget { background: transparent; border: none; gridline-color: transparent; }
QTableView { background: transparent; }
QHeaderView { background: transparent; }
QTableWidget::item { padding: 6px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
QHeaderView::section {
    background: transparent; color: #7e848f; border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10); padding: 8px 4px; font-weight: 500;
}
QTableCornerButton::section { background: transparent; border: none; }

QPushButton {
    background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px; padding: 7px 14px; color: #e8eaed;
}
QPushButton:hover { background: rgba(255, 255, 255, 0.11); }
QPushButton:pressed { background: rgba(255, 255, 255, 0.04); }
QPushButton:disabled { color: #5b616b; background: rgba(255, 255, 255, 0.03); }
QPushButton#nav {
    background: transparent; border: none; color: #969ba4; padding: 7px 16px; border-radius: 8px;
}
QPushButton#nav:hover { color: #e8eaed; background: rgba(255, 255, 255, 0.05); }
QPushButton#nav:checked { background: rgba(95, 145, 240, 0.20); color: #93b7ff; }
QPushButton#accent { background: #4d8df0; border: 1px solid #5f9bf2; color: #ffffff; }
QPushButton#accent:hover { background: #5b97f2; }
QPushButton#mini { padding: 4px 9px; border-radius: 6px; font-size: 12px; }

QComboBox, QLineEdit, QDoubleSpinBox {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px; padding: 6px 9px; color: #e8eaed; selection-background-color: #4d8df0;
}
QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover { border-color: rgba(95, 145, 240, 0.55); }
QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus { border-color: #4d8df0; }
QComboBox::drop-down { border: none; width: 16px; }
QComboBox QAbstractItemView {
    background: #22252b; border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 8px;
    selection-background-color: #4d8df0; outline: none; padding: 4px;
}
QListWidget {
    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px; padding: 4px;
}
QListWidget::item { padding: 5px 6px; border-radius: 6px; }
QListWidget::item:selected { background: rgba(95, 145, 240, 0.20); color: #e8eaed; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.16); border-radius: 5px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.28); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: rgba(255, 255, 255, 0.16); border-radius: 5px; min-width: 26px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QToolTip {
    background: #22252b; color: #e8eaed; border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px; padding: 6px 9px;
}
QMenu { background: #22252b; border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 10px; padding: 5px; }
QMenu::item { padding: 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: rgba(95, 145, 240, 0.22); }
"""


def fmt_hm(seconds):
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}"


def fmt_hms(seconds):
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def project_color(project):
    return project.get("color") or PALETTE[(project["id"] or 0) % len(PALETTE)]


def url_domain(url):
    if not url:
        return ""
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def period_bounds(period):
    today = datetime.date.today()
    if period == "Last 7 days":
        start = today - datetime.timedelta(days=6)
    elif period == "This month":
        start = today.replace(day=1)
    else:
        start = today
    s = datetime.datetime(start.year, start.month, start.day).timestamp()
    e = datetime.datetime(today.year, today.month, today.day).timestamp() + 86400
    return s, e


def dot(color, size=10):
    d = QLabel()
    d.setFixedSize(size, size)
    d.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return d


def _icon_pixmap(text=""):
    # Height must match the macOS menu-bar icon target (~18pt) so the system
    # doesn't downscale a wide pixmap and shrink the text. Rendered at 2x.
    dpr, h = 2, 19
    w = 17 + (8 * len(text) if text else 1)
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpr, dpr)                    # draw in logical coordinates
    pen = p.pen(); pen.setColor(QColor("#000")); pen.setWidthF(1.3); p.setPen(pen)
    p.drawEllipse(2, 4, 12, 12)
    p.drawLine(8, 10, 8, 6)
    p.drawLine(8, 10, 11, 11)
    if text:
        f = QFont(); f.setPixelSize(13); f.setWeight(QFont.Medium); p.setFont(f)
        p.drawText(17, 14, text)
    p.end()
    return pm


def menu_icon(text=""):
    icon = QIcon(_icon_pixmap(text))
    icon.setIsMask(True)
    return icon


def metric_card(label):
    card = QFrame(); card.setObjectName("card")
    v = QVBoxLayout(card); v.setContentsMargins(14, 8, 14, 8); v.setSpacing(0)
    cap = QLabel(label); cap.setObjectName("h")
    val = QLabel("—"); val.setObjectName("big"); val.setAlignment(Qt.AlignRight)
    v.addWidget(cap); v.addWidget(val)
    return card, val


# --------------------------------------------------------------------------- #
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
        secs = {}
        for s in db.sessions_between(start, end):
            secs[s["project_id"]] = secs.get(s["project_id"], 0) + (s["end_ts"] - s["start_ts"])
        for p in db.list_projects():
            self.rows.addWidget(self._row(project_color(p), p["name"], secs.get(p["id"], 0)))
        if secs.get(None):
            self.rows.addWidget(self._row("#888780", "Unassigned", secs[None], muted=True))

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


class ReviewView(QWidget):
    def __init__(self, on_add_project):
        super().__init__()
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        self.rail = ProjectRail(on_add_project)
        h.addWidget(self.rail)

        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(12, 10, 12, 12)

        self.timeline_head = QLabel("Today"); self.timeline_head.setObjectName("h")
        rv.addWidget(self.timeline_head)
        self.timeline = TimelineWidget()
        rv.addWidget(self.timeline)

        bar = QHBoxLayout()
        self.period = QComboBox(); self.period.addItems(PERIODS)
        self.period.currentTextChanged.connect(self.refresh)
        bar.addWidget(QLabel("List:")); bar.addWidget(self.period); bar.addStretch()
        bar.addWidget(QPushButton("Refresh", clicked=self.refresh))
        rv.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["When", "Duration", "Activity", "How", "Project", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)   # room for the dropdown
        self.table.setSelectionMode(QTableWidget.NoSelection)
        hd = self.table.horizontalHeader()
        for col, mode in {0: QHeaderView.Fixed, 1: QHeaderView.Fixed, 2: QHeaderView.Stretch,
                          3: QHeaderView.Fixed, 4: QHeaderView.Fixed, 5: QHeaderView.Fixed}.items():
            hd.setSectionResizeMode(col, mode)
        for col, wpx in {0: 96, 1: 80, 3: 64, 4: 200, 5: 120}.items():
            self.table.setColumnWidth(col, wpx)
        rv.addWidget(self.table)
        h.addWidget(right, 1)

    def update_timeline(self):
        start, end = period_bounds("Today")
        sessions = db.sessions_between(start, end)
        pcolor = {p["id"]: project_color(p) for p in db.list_projects()}
        total = sum(s["end_ts"] - s["start_ts"] for s in sessions)
        self.timeline.set_data(sessions, pcolor)
        self.timeline_head.setText(f"Today · {fmt_hm(total)} tracked")

    def refresh(self, *_):
        self.rail.refresh()
        self.update_timeline()
        start, end = period_bounds(self.period.currentText())
        rows = list(reversed(db.sessions_between(start, end)))   # newest first
        projects = db.list_projects()
        pcolor = {p["id"]: project_color(p) for p in projects}
        self.table.setRowCount(len(rows))
        for r, s in enumerate(rows):
            when = datetime.datetime.fromtimestamp(s["start_ts"]).strftime("%a %H:%M")
            detail = s["file_path"].split("/")[-1] if s["file_path"] else (s["title"] or "")
            dom = url_domain(s["url"])
            if dom and dom not in (detail or ""):
                detail = f"{detail}  ·  {dom}" if detail else dom
            activity = f"{s['app_name'] or ''}"
            if detail:
                activity += f"   ·   {detail}"
            tag = {"auto-file": "auto", "auto-rule": "rule", "manual": "you",
                   "inferred": "guess", "unassigned": "new"}.get(s["confidence"], s["confidence"])
            needs_review = s["project_id"] is None or s["confidence"] == "inferred"
            for c, val in enumerate([when, fmt_hms(s["end_ts"] - s["start_ts"]), activity, tag]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if c == 3 and needs_review:
                    item.setForeground(QColor("#E0A23B"))
                self.table.setItem(r, c, item)

            cell = QWidget(); ch = QHBoxLayout(cell); ch.setContentsMargins(4, 2, 4, 2); ch.setSpacing(6)
            ch.addWidget(dot(pcolor.get(s["project_id"], "#5a5d62"), 9))
            combo = QComboBox(); combo.setMinimumWidth(160)
            combo.addItem("Assign…", None)
            for p in projects:
                combo.addItem(p["name"], p["id"])
            idx = combo.findData(s["project_id"]); combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.currentIndexChanged.connect(
                lambda _i, sid=s["id"], cb=combo: self._assign(sid, cb))
            ch.addWidget(combo)
            self.table.setCellWidget(r, 4, cell)

            acts = QWidget(); ah = QHBoxLayout(acts); ah.setContentsMargins(2, 2, 2, 2); ah.setSpacing(4)
            rule_b = QPushButton("rule"); rule_b.setObjectName("mini")
            rule_b.setToolTip("Make a rule (app / site / title) → the assigned project")
            rule_b.clicked.connect(lambda _c=False, s=s, cb=combo: self._rule_menu(s, cb))
            del_b = QPushButton("✕"); del_b.setObjectName("mini"); del_b.setFixedWidth(28)
            del_b.setToolTip("Remove this entry (cleanup — does not make a rule)")
            del_b.clicked.connect(lambda _c=False, sid=s["id"]: self._delete(sid))
            ah.addWidget(rule_b); ah.addWidget(del_b)
            self.table.setCellWidget(r, 5, acts)

    def _assign(self, session_id, combo):
        db.set_session_project(session_id, combo.currentData())
        self.refresh()

    def _delete(self, session_id):
        db.delete_session(session_id)
        self.refresh()

    def _rule_menu(self, session, combo):
        pid = combo.currentData()
        if pid is None:
            QMessageBox.information(self, "Assign first", "Assign this row to a project first.")
            return
        menu = QMenu(self)
        if session["app_bundle"]:
            menu.addAction(f"Always: app “{session['app_name']}” → this project",
                           lambda: self._add_rule(pid, "app", session["app_bundle"]))
        dom = url_domain(session["url"])
        if dom:
            menu.addAction(f"Always: site “{dom}” → this project",
                           lambda: self._add_rule(pid, "url_domain", dom))
        if session["title"]:
            menu.addAction("Always: title contains…",
                           lambda: self._title_rule(pid, session))
        if not menu.actions():
            QMessageBox.information(self, "No rule possible", "Nothing on this row to base a rule on.")
            return
        menu.exec(QCursor.pos())

    def _add_rule(self, pid, kind, pattern):
        db.add_rule(pid, kind, pattern)
        n = db.assign_unassigned_by_app(pattern, pid) if kind == "app" else 0
        self.refresh()
        extra = f" {n} earlier entr{'y' if n == 1 else 'ies'} assigned." if n else ""
        QMessageBox.information(self, "Rule created", f"Rule added — {kind}: {pattern}.{extra}")

    def _title_rule(self, pid, session):
        text, ok = QInputDialog.getText(
            self, "Title contains",
            "Attribute to this project when the window title contains:",
            text=session["title"] or "")
        if ok and text.strip():
            self._add_rule(pid, "title_contains", text.strip())


class EditProjectDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit project")
        self._color = project_color(project)
        form = QFormLayout(self)
        self.name = QLineEdit(project["name"])
        self.employer = QLineEdit(project["employer"] or "")
        self.rate = QDoubleSpinBox(maximum=10000, suffix=" /h")
        self.rate.setValue(project["hourly_rate"] or 0)
        sw = QWidget(); sh = QHBoxLayout(sw); sh.setContentsMargins(0, 0, 0, 0); sh.setSpacing(6)
        self._swatches = []
        for c in PALETTE:
            b = QPushButton(); b.setFixedSize(22, 22)
            b.clicked.connect(lambda _x=False, col=c: self._pick(col))
            sh.addWidget(b); self._swatches.append((b, c))
        sh.addStretch()
        form.addRow("Name", self.name)
        form.addRow("Employer", self.employer)
        form.addRow("Rate", self.rate)
        form.addRow("Colour", sw)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)
        self._paint()

    def _pick(self, col):
        self._color = col; self._paint()

    def _paint(self):
        for b, c in self._swatches:
            border = "#ffffff" if c == self._color else "transparent"
            b.setStyleSheet(f"background:{c}; border-radius:11px; border:2px solid {border};")

    def values(self):
        return {"name": self.name.text().strip(),
                "employer": self.employer.text().strip() or None,
                "hourly_rate": self.rate.value() or None,
                "color": self._color}


class ProjectsView(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(12, 12, 12, 12)

        form = QHBoxLayout()
        self.name = QLineEdit(placeholderText="Project name"); self.name.setMinimumWidth(150)
        self.employer = QLineEdit(placeholderText="Employer"); self.employer.setMinimumWidth(130)
        self.rate = QDoubleSpinBox(maximum=10000, suffix=" /h"); self.rate.setMinimumWidth(90)
        self.folder = QLineEdit(placeholderText="First folder (optional)…"); self.folder.setReadOnly(True)
        pick = QPushButton("Choose…", clicked=self._pick)
        add = QPushButton("Add", clicked=self._add); add.setObjectName("accent")
        form.addWidget(self.name); form.addWidget(self.employer); form.addWidget(self.rate)
        form.addWidget(self.folder, 1); form.addWidget(pick); form.addWidget(add)
        v.addLayout(form)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Project", "Employer", "Rate", "Folders"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        v.addWidget(self.table)

        delrow = QHBoxLayout(); delrow.addStretch()
        self.editp = QPushButton("Edit selected project…", clicked=self._edit_project)
        self.editp.setEnabled(False); delrow.addWidget(self.editp)
        self.delp = QPushButton("Remove selected project", clicked=self._delete_project)
        self.delp.setEnabled(False); delrow.addWidget(self.delp)
        v.addLayout(delrow)

        fhead = QHBoxLayout()
        self.flabel = QLabel("Folders — select a project"); self.flabel.setObjectName("h")
        self.addf = QPushButton("Add folder…", clicked=self._add_folder); self.addf.setEnabled(False)
        self.rmf = QPushButton("Remove", clicked=self._remove_folder); self.rmf.setEnabled(False)
        fhead.addWidget(self.flabel); fhead.addStretch(); fhead.addWidget(self.addf); fhead.addWidget(self.rmf)
        v.addLayout(fhead)
        self.folders = QListWidget(); self.folders.setMaximumHeight(140)
        v.addWidget(self.folders)
        self._project_ids = []
        self.table.itemSelectionChanged.connect(self._load_folders)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder")
        if d:
            self.folder.setText(d)

    def _add(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Missing name", "Give the project a name.")
            return
        db.add_project(self.name.text().strip(), folder=self.folder.text().strip() or None,
                       employer=self.employer.text().strip() or None, hourly_rate=self.rate.value() or None)
        self.name.clear(); self.employer.clear(); self.folder.clear(); self.rate.setValue(0)
        self.refresh()

    def _selected_project(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            r = self.table.currentRow()
        else:
            r = rows[0].row()
        if 0 <= r < len(self._project_ids):
            return self._project_ids[r]
        return None

    def _edit_project(self):
        pid = self._selected_project()
        if pid is None:
            return
        p = next((x for x in db.list_projects() if x["id"] == pid), None)
        if not p:
            return
        dlg = EditProjectDialog(p, self)
        if dlg.exec():
            v = dlg.values()
            if not v["name"]:
                QMessageBox.warning(self, "Missing name", "Name can't be empty.")
                return
            db.update_project(pid, v["name"], v["employer"], v["hourly_rate"], v["color"])
            self.refresh()

    def _delete_project(self):
        pid = self._selected_project()
        if pid is None:
            return
        name = next((p["name"] for p in db.list_projects() if p["id"] == pid), "")
        if QMessageBox.question(self, "Remove project",
                                f"Remove “{name}”? Its tracked time becomes Unassigned.") \
                != QMessageBox.Yes:
            return
        db.delete_project(pid)
        self.refresh(); self._load_folders()

    def _load_folders(self):
        pid = self._selected_project()
        self.folders.clear()
        self.addf.setEnabled(pid is not None)
        self.rmf.setEnabled(pid is not None)
        self.delp.setEnabled(pid is not None)
        self.editp.setEnabled(pid is not None)
        if pid is None:
            self.flabel.setText("Folders — select a project"); return
        name = next((p["name"] for p in db.list_projects() if p["id"] == pid), "")
        self.flabel.setText(f"Folders for {name}")
        for f in db.list_project_folders(pid):
            it = QListWidgetItem(f["path"]); it.setData(Qt.UserRole, f["id"])
            self.folders.addItem(it)

    def _add_folder(self):
        pid = self._selected_project()
        if pid is None:
            return
        d = QFileDialog.getExistingDirectory(self, "Add folder to project")
        if d:
            db.add_project_folder(pid, d)
            self.refresh(); self._load_folders()

    def _remove_folder(self):
        it = self.folders.currentItem()
        if not it:
            return
        fid = it.data(Qt.UserRole)
        if fid is None:
            QMessageBox.information(self, "Legacy folder", "Re-add it as a managed folder to remove it.")
            return
        db.delete_project_folder(fid)
        self.refresh(); self._load_folders()

    def refresh(self):
        projects = db.list_projects()
        self._project_ids = [p["id"] for p in projects]
        self.table.setRowCount(len(projects))
        for r, p in enumerate(projects):
            n = len(db.list_project_folders(p["id"]))
            rate = f"{p['hourly_rate']:g} {p['currency']}" if p["hourly_rate"] else "—"
            for c, val in enumerate([p["name"], p["employer"] or "—", rate,
                                     f"{n} folder{'s' if n != 1 else ''}"]):
                item = QTableWidgetItem(str(val)); item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)


class ReportsView(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(12, 12, 12, 12)
        bar = QHBoxLayout()
        self.period = QComboBox(); self.period.addItems(PERIODS)
        self.period.currentTextChanged.connect(self.refresh)
        bar.addWidget(QLabel("Period:")); bar.addWidget(self.period); bar.addStretch()
        exp = QPushButton("Export CSV", clicked=self._export); exp.setObjectName("accent")
        bar.addWidget(exp)
        v.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Project", "Employer", "Hours", "Rate", "Amount"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        v.addWidget(self.table)
        self.total = QLabel(); self.total.setObjectName("big")
        v.addWidget(self.total, alignment=Qt.AlignRight)

    def _rows(self):
        start, end = period_bounds(self.period.currentText())
        by_id = {p["id"]: p for p in db.list_projects()}
        agg = {}
        for s in db.sessions_between(start, end):
            agg[s["project_id"]] = agg.get(s["project_id"], 0.0) + (s["end_ts"] - s["start_ts"])
        out = []
        for pid, secs in agg.items():
            p = by_id.get(pid)
            name = p["name"] if p else "Unassigned"
            rate = p["hourly_rate"] if p and p["hourly_rate"] else None
            hours = secs / 3600.0
            amount = round(hours * rate, 2) if rate else None
            out.append((name, (p["employer"] if p else "") or "", hours, rate, amount,
                        p["currency"] if p else "EUR"))
        out.sort(key=lambda x: -x[2])
        return out

    def refresh(self, *_):
        rows = self._rows(); self.table.setRowCount(len(rows)); grand = 0.0
        for r, (name, employer, hours, rate, amount, cur) in enumerate(rows):
            cells = [name, employer, f"{hours:.2f}", f"{rate:g}" if rate else "—",
                     f"{amount:.2f} {cur}" if amount is not None else "—"]
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val); item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
            if amount:
                grand += amount
        self.total.setText(f"Total billable: {grand:.2f}")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "worktime.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Project", "Employer", "Hours", "Rate", "Amount", "Currency"])
            for name, employer, hours, rate, amount, cur in self._rows():
                w.writerow([name, employer, f"{hours:.2f}", rate or "",
                            amount if amount is not None else "", cur])
        QMessageBox.information(self, "Exported", f"Saved to {path}")


class RulesView(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(12, 12, 12, 12)
        cap = QLabel("Rules auto-attribute an app to a project. Delete any that are wrong "
                     "(e.g. an app you use across several projects).")
        cap.setObjectName("h"); v.addWidget(cap)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["App / pattern", "Kind", "Project", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        v.addWidget(self.table)

    def refresh(self, *_):
        rules = db.list_rules()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            for c, val in enumerate([rule["pattern"], rule["kind"], rule["project_name"] or "—"]):
                it = QTableWidgetItem(str(val)); it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
            btn = QPushButton("Delete")
            btn.clicked.connect(lambda _c=False, rid=rule["id"]: self._del(rid))
            self.table.setCellWidget(r, 3, btn)

    def _del(self, rule_id):
        db.delete_rule(rule_id); self.refresh()


# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.setWindowTitle("WorktimeTracker")
        self.resize(1120, 700)
        self.setMinimumSize(940, 560)
        central = QWidget(); root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        status = QWidget(); sh = QHBoxLayout(status); sh.setContentsMargins(18, 14, 18, 8)
        self.now = QLabel("Starting…"); self.now.setObjectName("now")
        sh.addWidget(self.now); sh.addStretch()
        today_card, self.today_val = metric_card("Today")
        bill_card, self.bill_val = metric_card("Billable today")
        sh.addWidget(today_card); sh.addSpacing(8); sh.addWidget(bill_card)
        root.addWidget(status)

        nav = QHBoxLayout(); nav.setContentsMargins(12, 6, 12, 6); nav.setSpacing(4)
        self.stack = QStackedWidget()
        self.review = ReviewView(self._goto_projects)
        self.projects = ProjectsView()
        self.reports = ReportsView()
        self.rules = RulesView()
        self._views = [self.review, self.projects, self.reports, self.rules]
        for w in self._views:
            self.stack.addWidget(w)
        group = QButtonGroup(self)
        for i, label in enumerate(["Review", "Projects", "Reports", "Rules"]):
            b = QPushButton(label); b.setObjectName("nav"); b.setCheckable(True)
            b.clicked.connect(lambda _c=False, idx=i: self._switch(idx))
            group.addButton(b, i); nav.addWidget(b)
            if i == 0:
                b.setChecked(True)
        self._nav = group
        nav.addStretch()
        navw = QWidget(); navw.setLayout(nav); root.addWidget(navw)
        divider = QFrame(); divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,0.06);")
        root.addWidget(divider)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.refresh_all()

    def _switch(self, idx):
        self.stack.setCurrentIndex(idx)
        self._views[idx].refresh()

    def _goto_projects(self):
        self._nav.button(1).setChecked(True)
        self._switch(1)

    def _update_status(self):
        start, end = period_bounds("Today")
        rows = db.sessions_between(start, end)
        by_id = {p["id"]: p for p in db.list_projects()}
        total = sum(s["end_ts"] - s["start_ts"] for s in rows)
        billable = 0.0
        for s in rows:
            p = by_id.get(s["project_id"])
            if p and p["hourly_rate"]:
                billable += (s["end_ts"] - s["start_ts"]) / 3600.0 * p["hourly_rate"]
        self.today_val.setText(fmt_hm(total))
        self.bill_val.setText(f"€{billable:.0f}")
        if self.tracker.current_project:
            self.now.setText(f"●  Now:  {self.tracker.current_app}  →  {self.tracker.current_project}")
        else:
            self.now.setText("○  Idle")
        self.review.rail.refresh()
        self.review.update_timeline()      # live 'now' marker + new blocks (no table rebuild)

    def refresh_all(self):
        self.stack.currentWidget().refresh()
        self._update_status()

    def refresh_live(self):
        # timer-driven: update live bits only. Don't rebuild the interactive
        # Review/Projects tables under the user's cursor; Reports is safe.
        self._update_status()
        if self.stack.currentWidget() is self.reports:
            self.reports.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.stack.currentWidget().refresh()


def main():
    db.init_db()
    log.info("app starting; accessibility granted=%s", accessibility_ok())
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    app.setQuitOnLastWindowClosed(False)

    tracker = Tracker()
    threading.Thread(target=tracker.run, daemon=True).start()
    app.aboutToQuit.connect(tracker.stop)

    window = MainWindow(tracker)

    tray = QSystemTrayIcon(menu_icon())
    menu = QMenu()
    act_now = QAction("…"); act_now.setEnabled(False)
    act_today = QAction("Today: 0:00"); act_today.setEnabled(False)
    act_open = QAction("Open WorktimeTracker")
    act_open.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    act_quit = QAction("Quit"); act_quit.triggered.connect(app.quit)
    menu.addAction(act_now); menu.addAction(act_today); menu.addSeparator()
    menu.addAction(act_open); menu.addSeparator(); menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (window.show(), window.raise_(), window.activateWindow())
        if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    def tick():
        start, end = period_bounds("Today")
        secs = sum(s["end_ts"] - s["start_ts"] for s in db.sessions_between(start, end))
        tray.setIcon(menu_icon(fmt_hm(secs) if secs else ""))
        proj = tracker.current_project
        act_now.setText(f"▶ {tracker.current_app} → {proj}" if proj else "○ Idle")
        act_today.setText(f"Today: {fmt_hm(secs)}")
        tray.setToolTip(f"{proj or 'Idle'} — today {fmt_hm(secs)}")
        if window.isVisible():
            window.refresh_live()

    timer = QTimer(); timer.timeout.connect(tick); timer.start(5000)
    tick()

    if not accessibility_ok():
        QMessageBox.warning(window, "Accessibility needed",
                            "Grant access in System Settings → Privacy & Security → "
                            "Accessibility (to whatever launches this), then relaunch.")
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
