"""Review view — the core loop: see tracked time, assign unknowns, make rules."""

import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import db
from ..attribution import url_domain
from ..timeutil import PERIODS, fmt_hm, fmt_hms, period_bounds
from .theme import dot, project_color
from .widgets import ProjectRail, TimelineWidget


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

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["When", "Duration", "Activity", "How", "Project", "Bill", ""]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)   # room for the dropdown
        self.table.setSelectionMode(QTableWidget.NoSelection)
        hd = self.table.horizontalHeader()
        for col, mode in {0: QHeaderView.Fixed, 1: QHeaderView.Fixed, 2: QHeaderView.Stretch,
                          3: QHeaderView.Fixed, 4: QHeaderView.Fixed, 5: QHeaderView.Fixed,
                          6: QHeaderView.Fixed}.items():
            hd.setSectionResizeMode(col, mode)
        for col, wpx in {0: 96, 1: 80, 3: 64, 4: 200, 5: 64, 6: 120}.items():
            self.table.setColumnWidth(col, wpx)
        rv.addWidget(self.table)
        h.addWidget(right, 1)

    def update_timeline(self):
        start, end = period_bounds("Today")
        sessions = db.sessions_between(start, end)
        pcolor = {p["id"]: project_color(p) for p in db.list_projects()}
        total = db.totals_between(start, end)["tracked_seconds"]
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

            bill_cell = QWidget(); bh = QHBoxLayout(bill_cell)
            bh.setContentsMargins(2, 2, 2, 2); bh.setAlignment(Qt.AlignCenter)
            bill = QCheckBox()
            bill.setToolTip("Include this entry in billable totals")
            bill.setEnabled(s["project_id"] is not None)
            bill.setChecked(db.session_is_billable(s))
            bill.toggled.connect(lambda checked, sid=s["id"]: self._billable(sid, checked))
            bh.addWidget(bill)
            self.table.setCellWidget(r, 5, bill_cell)

            acts = QWidget(); ah = QHBoxLayout(acts); ah.setContentsMargins(2, 2, 2, 2); ah.setSpacing(4)
            rule_b = QPushButton("rule"); rule_b.setObjectName("mini")
            rule_b.setToolTip("Make a rule (app / site / title) → the assigned project")
            rule_b.clicked.connect(lambda _c=False, s=s, cb=combo: self._rule_menu(s, cb))
            del_b = QPushButton("✕"); del_b.setObjectName("mini"); del_b.setFixedWidth(28)
            del_b.setToolTip("Remove this entry (cleanup — does not make a rule)")
            del_b.clicked.connect(lambda _c=False, sid=s["id"]: self._delete(sid))
            ah.addWidget(rule_b); ah.addWidget(del_b)
            self.table.setCellWidget(r, 6, acts)

    def _assign(self, session_id, combo):
        db.set_session_project(session_id, combo.currentData())
        self.refresh()

    def _billable(self, session_id, checked):
        db.set_session_billable(session_id, checked)
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
