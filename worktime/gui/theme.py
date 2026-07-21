"""Dark glass-inspired theme: stylesheet, palette, and small styled helpers."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

PALETTE = ["#8B7FE8", "#2FB89B", "#E8825A", "#5A9CF8", "#E06A98", "#E0A23B", "#8BBF4E"]

QSS = """
QMainWindow, QDialog { background: #16181c; }
QWidget { color: #e8eaed; font-size: 13px; }

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


def project_color(project):
    pid = project.get("id", project.get("project_id", 0))
    return project.get("color") or PALETTE[(pid or 0) % len(PALETTE)]


def dot(color, size=10):
    d = QLabel()
    d.setFixedSize(size, size)
    d.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return d


def metric_card(label):
    card = QFrame(); card.setObjectName("card")
    v = QVBoxLayout(card); v.setContentsMargins(14, 8, 14, 8); v.setSpacing(0)
    cap = QLabel(label); cap.setObjectName("h")
    val = QLabel("—"); val.setObjectName("big"); val.setAlignment(Qt.AlignRight)
    v.addWidget(cap); v.addWidget(val)
    return card, val
