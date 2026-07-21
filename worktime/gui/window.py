"""Main window: status cards, nav, and the four stacked views."""

from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import db
from ..timeutil import fmt_hm, period_bounds
from .projects import ProjectsView
from .reports import ReportsView
from .review import ReviewView
from .rules import RulesView
from .theme import metric_card


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
        summary = db.totals_between(start, end)
        self.today_val.setText(fmt_hm(summary["tracked_seconds"]))
        self.bill_val.setText(fmt_hm(summary["billable_seconds"]))
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
