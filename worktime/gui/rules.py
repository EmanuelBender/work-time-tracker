"""Rules view — see and delete attribution rules (a wrong rule is reversible)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import db


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
