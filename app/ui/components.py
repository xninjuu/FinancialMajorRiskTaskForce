from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

THEME_TOKENS = {
    "dark": {
        "bg": "#1b1d23",
        "card": "#23262d",
        "border": "#2c2f36",
        "accent": "#21d4fd",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
    },
    "light": {
        "bg": "#f7f8fb",
        "card": "#ffffff",
        "border": "#d1d5db",
        "accent": "#2563eb",
        "text": "#111827",
        "muted": "#4b5563",
    },
}

PILL_COLORS = {
    "alert": "#ef4444",
    "warning": "#f7a400",
    "success": "#21d4fd",
    "info": "#8ab4f8",
    "neutral": "#4b5563",
}


def apply_theme(widget: QtWidgets.QWidget, theme: str = "dark") -> None:
    tokens = THEME_TOKENS.get(theme, THEME_TOKENS["dark"])
    base_style = f"""
    QWidget {{ background-color: {tokens['bg']}; color: {tokens['text']}; }}
    QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {{
        background-color: {tokens['card']};
        border: 1px solid {tokens['border']};
        border-radius: 6px;
        padding: 6px;
    }}
    QTableWidget::item {{ padding: 6px; }}
    QPushButton {{
        background-color: {tokens['card']};
        border: 1px solid {tokens['border']};
        border-radius: 8px;
        padding: 8px 12px;
    }}
    QPushButton:hover {{ border-color: {tokens['accent']}; }}
    QHeaderView::section {{
        background-color: {tokens['card']};
        padding: 8px;
        border: 0px;
    }}
    QScrollBar:vertical {{ background: {tokens['bg']}; width: 12px; }}
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


def create_section_header(text: str, *, accent: str = "#21d4fd", icon: QtGui.QIcon | None = None) -> QtWidgets.QWidget:
    wrapper = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 6)
    if icon:
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(icon.pixmap(18, 18))
        layout.addWidget(icon_label)
    label = QtWidgets.QLabel(text)
    label.setStyleSheet(f"font-weight:700; font-size:15px; border-bottom: 2px solid {accent}; padding-bottom: 4px;")
    layout.addWidget(label)
    layout.addStretch(1)
    return wrapper


class SectionCard(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setStyleSheet(
            "QWidget#sectionCard { background-color: #23262d; border: 1px solid #2c2f36; border-radius: 10px; }"
        )


DENSITY_STYLES = {
    "Compact": {"row_height": 22, "padding": "2px 4px", "font": "12px"},
    "Comfortable": {"row_height": 28, "padding": "6px", "font": "13px"},
    "Expanded": {"row_height": 34, "padding": "10px 8px", "font": "14px"},
}


def apply_table_density(table: QtWidgets.QTableWidget, mode: str = "Comfortable") -> None:
    style = DENSITY_STYLES.get(mode, DENSITY_STYLES["Comfortable"])
    table.setStyleSheet(
        f"QTableWidget::item {{ padding: {style['padding']}; font-size: {style['font']}; }}"
        f"QHeaderView::section {{ padding: {style['padding']}; font-size: {style['font']}; }}"
    )
    for row in range(table.rowCount()):
        table.setRowHeight(row, style["row_height"])


def rich_cell(text: str, *, accent_color: str | None = None, tags: list[str] | None = None) -> QtWidgets.QWidget:
    wrapper = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    if accent_color:
        accent = QtWidgets.QFrame()
        accent.setFixedWidth(6)
        accent.setStyleSheet(f"background:{accent_color}; border-radius: 3px;")
        layout.addWidget(accent)
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    layout.addWidget(label, 1)
    if tags:
        tags_layout = QtWidgets.QHBoxLayout()
        tags_layout.setSpacing(4)
        for tag in tags:
            tag_lbl = create_pill(tag, "neutral")
            tag_lbl.setFixedHeight(18)
            tags_layout.addWidget(tag_lbl)
        layout.addLayout(tags_layout)
    return wrapper

