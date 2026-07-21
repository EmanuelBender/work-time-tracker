"""Projects view — add/edit/remove projects and their folders."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import db
from .theme import PALETTE, project_color

FEE_TOOLTIP = "Fixed project price — the wage gauge divides it by billable hours"


class EditProjectDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit project")
        self._color = project_color(project)
        form = QFormLayout(self)
        self.name = QLineEdit(project["name"])
        self.employer = QLineEdit(project["employer"] or "")
        self.fee = QDoubleSpinBox(maximum=1_000_000, suffix=" €")
        self.fee.setToolTip(FEE_TOOLTIP)
        self.fee.setValue(project["fee"] or 0)
        sw = QWidget(); sh = QHBoxLayout(sw); sh.setContentsMargins(0, 0, 0, 0); sh.setSpacing(6)
        self._swatches = []
        for c in PALETTE:
            b = QPushButton(); b.setFixedSize(22, 22)
            b.clicked.connect(lambda _x=False, col=c: self._pick(col))
            sh.addWidget(b); self._swatches.append((b, c))
        sh.addStretch()
        form.addRow("Name", self.name)
        form.addRow("Employer", self.employer)
        form.addRow("Fee", self.fee)
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
                "fee": self.fee.value() or None,
                "color": self._color}


class ProjectsView(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(12, 12, 12, 12)

        form = QHBoxLayout()
        self.name = QLineEdit(placeholderText="Project name"); self.name.setMinimumWidth(150)
        self.employer = QLineEdit(placeholderText="Employer"); self.employer.setMinimumWidth(130)
        self.fee = QDoubleSpinBox(maximum=1_000_000, suffix=" €"); self.fee.setMinimumWidth(100)
        self.fee.setToolTip(FEE_TOOLTIP)
        self.folder = QLineEdit(placeholderText="First folder (optional)…"); self.folder.setReadOnly(True)
        pick = QPushButton("Choose…", clicked=self._pick)
        add = QPushButton("Add", clicked=self._add); add.setObjectName("accent")
        form.addWidget(self.name); form.addWidget(self.employer); form.addWidget(self.fee)
        form.addWidget(self.folder, 1); form.addWidget(pick); form.addWidget(add)
        v.addLayout(form)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Project", "Employer", "Fee", "Folders"])
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
                       employer=self.employer.text().strip() or None, fee=self.fee.value() or None)
        self.name.clear(); self.employer.clear(); self.folder.clear(); self.fee.setValue(0)
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
            db.update_project(pid, v["name"], v["employer"], v["fee"], v["color"])
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
        db.delete_project_folder(it.data(Qt.UserRole))
        self.refresh(); self._load_folders()

    def refresh(self):
        projects = db.list_projects()
        self._project_ids = [p["id"] for p in projects]
        self.table.setRowCount(len(projects))
        for r, p in enumerate(projects):
            n = len(db.list_project_folders(p["id"]))
            fee = f"{p['fee']:g} €" if p["fee"] else "—"
            for c, val in enumerate([p["name"], p["employer"] or "—", fee,
                                     f"{n} folder{'s' if n != 1 else ''}"]):
                item = QTableWidgetItem(str(val)); item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
