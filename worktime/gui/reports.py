"""Reports view — per-project totals, the effective-wage gauge, CSV export."""

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import db
from ..reporting import coverage_line, report_csv_rows
from ..timeutil import PERIODS, period_bounds


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
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Project", "Employer", "Tracked", "Billable", "Fee", "€/h"]
        )
        self.table.horizontalHeaderItem(5).setToolTip(
            "Effective wage: fee ÷ all billable hours the project ever took")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        v.addWidget(self.table)
        foot = QHBoxLayout()
        self.coverage = QLabel(); self.coverage.setObjectName("muted")
        self.coverage.setToolTip("Share of tracked time by attribution: automatic "
                                 "(file / rule / title), confirmed by you, guessed, unknown")
        foot.addWidget(self.coverage); foot.addStretch()
        self.total = QLabel(); self.total.setObjectName("big")
        foot.addWidget(self.total)
        v.addLayout(foot)

    def _summary(self):
        start, end = period_bounds(self.period.currentText())
        return db.totals_between(start, end)

    def refresh(self, *_):
        summary = self._summary()
        rows = summary["rows"]
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = [
                row["project_name"],
                row["employer"],
                f"{row['tracked_hours']:.2f}",
                f"{row['billable_hours']:.2f}",
                f"{row['fee']:g} €" if row["fee"] else "—",
                f"{row['eff_rate']:.0f}" if row["eff_rate"] else "—",
            ]
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val); item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
        self.coverage.setText(coverage_line(summary))
        self.total.setText(
            f"Tracked {summary['tracked_seconds'] / 3600:.1f} h · "
            f"billable {summary['billable_seconds'] / 3600:.1f} h")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "worktime.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerows(report_csv_rows(self._summary()["rows"]))
        QMessageBox.information(self, "Exported", f"Saved to {path}")
