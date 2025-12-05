from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

PILL_COLORS = {
    "alert": "#ef4444",
    "warning": "#f7a400",
    "success": "#21d4fd",
    "info": "#8ab4f8",
    "neutral": "#4b5563",
}


def apply_dark_palette(widget: QtWidgets.QWidget) -> None:
    base_style = """
    QWidget { background-color: #1b1d23; color: #e5e7eb; }
    QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
        background-color: #23262d;
        border: 1px solid #2f3340;
        border-radius: 6px;
        padding: 6px;
    }
    QTableWidget::item { padding: 4px; }
    QPushButton {
        background-color: #23262d;
        border: 1px solid #2f3340;
        border-radius: 8px;
        padding: 8px 12px;
    }
    QPushButton:hover { border-color: #21d4fd; }
    QHeaderView::section {
        background-color: #23262d;
        padding: 6px;
        border: 0px;
    }
    QScrollBar:vertical { background: #1b1d23; width: 12px; }
    """
    widget.setStyleSheet(base_style)


def _style_pill(label: QtWidgets.QLabel, state: str) -> None:
    color = PILL_COLORS.get(state, PILL_COLORS["neutral"])
    label.setStyleSheet(
        f"padding:4px 10px; border-radius:10px; background:{color}; color:#0b0c10; font-weight:700;"
    )


def create_pill(text: str, state: str = "neutral") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setAlignment(QtCore.Qt.AlignCenter)
    _style_pill(label, state)
    return label


def update_pill(label: QtWidgets.QLabel, text: str, state: str) -> None:
    label.setText(text)
    _style_pill(label, state)


def create_header_pill(text: str, state: str = "info") -> QtWidgets.QLabel:
    label = create_pill(text, state)
    label.setFixedHeight(26)
    return label


class SectionCard(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setStyleSheet(
            "QWidget#sectionCard { background-color: #23262d; border: 1px solid #2c2f36; border-radius: 10px; }"
        )

