"""Add a manual work block, or edit an existing session's times.

Off-computer project time (calls, meetings, studio sessions) is real work
under the fixed-fee model — a manual block records it after the fact, so the
effective-wage gauge sees the whole cost of a project, not just screen time.
"""

import datetime

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QSpinBox, QTimeEdit,
)


class SessionDialog(QDialog):
    """Add mode (project + description + when) or edit-times mode (when only)."""

    def __init__(self, projects=None, session=None, parent=None):
        super().__init__(parent)
        editing = session is not None
        self.setWindowTitle("Edit times" if editing else "Add work block")
        form = QFormLayout(self)

        self.project = self.description = None
        if not editing:
            self.project = QComboBox()
            for p in projects:
                self.project.addItem(p["name"], p["id"])
            self.description = QLineEdit(placeholderText="e.g. client call, studio session")
            form.addRow("Project", self.project)
            form.addRow("What", self.description)

        start_dt = (datetime.datetime.fromtimestamp(session["start_ts"]) if editing
                    else datetime.datetime.now() - datetime.timedelta(hours=1))
        minutes = (int((session["end_ts"] - session["start_ts"]) // 60) if editing
                   else 60)
        self.date = QDateEdit(QDate(start_dt.year, start_dt.month, start_dt.day))
        self.date.setCalendarPopup(True)
        self.start = QTimeEdit(QTime(start_dt.hour, start_dt.minute))
        self.minutes = QSpinBox(minimum=1, maximum=24 * 60, value=max(1, minutes))
        self.minutes.setSuffix(" min")
        form.addRow("Date", self.date)
        form.addRow("Start", self.start)
        form.addRow("Duration", self.minutes)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def span(self):
        """(start_ts, end_ts) from the date / start / duration fields."""
        d, t = self.date.date(), self.start.time()
        start = datetime.datetime(
            d.year(), d.month(), d.day(), t.hour(), t.minute()).timestamp()
        return start, start + self.minutes.value() * 60

    def block(self):
        """Session dict for a new manual block (add mode)."""
        start_ts, end_ts = self.span()
        return {
            "project_id": self.project.currentData(),
            "app_name": self.description.text().strip() or "Work block",
            "start_ts": start_ts,
            "end_ts": end_ts,
            "confidence": "manual",
        }
