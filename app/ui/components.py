from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from PySide6 import QtCore, QtGui, QtWidgets

ThemeName = Literal["dark", "light"]
PillState = Literal["alert", "warning", "success", "info", "neutral"]
DensityMode = Literal["Compact", "Comfortable", "Expanded"]


@dataclass(frozen=True)
class ThemeTokens:
    bg: str
    card: str
    border: str
    accent: str
    text: str
    muted: str


tokens_dark = ThemeTokens(
    bg="#1b1d23",
    card="#23262d",
    border="#2c2f36",
    accent="#21d4fd",
    text="#e5e7eb",
    muted="#9ca3af",
)

tokens_light = ThemeTokens(
    bg="#f7f8fb",
    card="#ffffff",
    border="#d1d5db",
    accent="#2563eb",
    text="#111827",
    muted="#4b5563",
)

THEME_TOKENS: dict[ThemeName, ThemeTokens] = {
    "dark": tokens_dark,
    "light": tokens_light,
}

PILL_COLORS: dict[PillState, str] = {
    "alert": "#ef4444",
    "warning": "#f7a400",
    "success": "#21d4fd",
    "info": "#8ab4f8",
    "neutral": "#4b5563",
}

CURRENT_THEME: ThemeName = "dark"


def _get_tokens(theme: ThemeName | None = None) -> ThemeTokens:
    if theme is None:
        return THEME_TOKENS.get(CURRENT_THEME, tokens_dark)
    return THEME_TOKENS.get(theme, tokens_dark)


def _build_base_style(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        background-color: {tokens.bg};
        color: {tokens.text};
    }}

    QWidget#sectionCard {{
        background-color: {tokens.card};
        border: 1px solid {tokens.border};
        border-radius: 10px;
    }}

    QLineEdit, QTextEdit, QPlainTextEdit,
    QTableWidget, QListWidget, QComboBox {{
        background-color: {tokens.card};
        border: 1px solid {tokens.border};
        border-radius: 6px;
        padding: 6px;
    }}

    QTableWidget::item, QTreeWidget::item {{
        padding: 6px;
    }}

    QPushButton {{
        background-color: {tokens.card};
        border: 1px solid {tokens.border};
        border-radius: 8px;
        padding: 8px 12px;
    }}

    QPushButton:hover {{
        border-color: {tokens.accent};
    }}

    QHeaderView::section {{
        background-color: {tokens.card};
        padding: 8px;
        border: 0px;
    }}

    QScrollBar:vertical {{
        background: {tokens.bg};
        width: 12px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {tokens.border};
        min-height: 20px;
        border-radius: 6px;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
        width: 0;
    }}
    """


def apply_theme(widget: QtWidgets.QWidget, theme: ThemeName = "dark") -> None:
    global CURRENT_THEME
    CURRENT_THEME = theme
    tokens = _get_tokens(theme)

    palette = widget.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(tokens.bg))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(tokens.card))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(tokens.bg))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(tokens.card))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(tokens.accent))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#0b0c10"))

    widget.setPalette(palette)
    widget.setAutoFillBackground(True)
    widget.setStyleSheet(_build_base_style(tokens))


def apply_theme_to_app(app: QtWidgets.QApplication, theme: ThemeName = "dark") -> None:
    global CURRENT_THEME
    CURRENT_THEME = theme
    tokens = _get_tokens(theme)

    palette = app.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(tokens.bg))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(tokens.card))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(tokens.bg))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(tokens.card))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(tokens.text))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(tokens.accent))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#0b0c10"))

    app.setPalette(palette)
    app.setStyleSheet(_build_base_style(tokens))


def _style_pill(label: QtWidgets.QLabel, state: PillState) -> None:
    color = PILL_COLORS.get(state, PILL_COLORS["neutral"])
    label.setStyleSheet(
        "padding: 4px 10px;"
        "border-radius: 10px;"
        f"background: {color};"
        "color: #0b0c10;"
        "font-weight: 700;"
        "font-size: 11px;"
    )


def create_pill(text: str, state: PillState = "neutral") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setAlignment(QtCore.Qt.AlignCenter)
    label.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
    _style_pill(label, state)
    return label


def update_pill(label: QtWidgets.QLabel, text: str, state: PillState) -> None:
    label.setText(text)
    _style_pill(label, state)


def create_header_pill(text: str, state: PillState = "info") -> QtWidgets.QLabel:
    label = create_pill(text, state)
    label.setFixedHeight(26)
    return label


def create_section_header(
    text: str,
    *,
    accent: Optional[str] = None,
    icon: Optional[QtGui.QIcon] = None,
) -> QtWidgets.QWidget:
    tokens = _get_tokens()
    accent_color = accent or tokens.accent

    wrapper = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 6)
    layout.setSpacing(6)

    if icon:
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(icon.pixmap(18, 18))
        icon_label.setFixedSize(18, 18)
        layout.addWidget(icon_label)

    label = QtWidgets.QLabel(text)
    label.setStyleSheet(
        f"font-weight: 700; font-size: 15px; "
        f"border-bottom: 2px solid {accent_color}; padding-bottom: 4px;"
    )
    layout.addWidget(label)
    layout.addStretch(1)
    return wrapper


class SectionCard(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)


DENSITY_STYLES: dict[DensityMode, dict[str, str | int]] = {
    "Compact": {"row_height": 22, "padding": "2px 4px", "font": "12px"},
    "Comfortable": {"row_height": 28, "padding": "6px", "font": "13px"},
    "Expanded": {"row_height": 34, "padding": "10px 8px", "font": "14px"},
}


def apply_table_density(
    table: QtWidgets.QTableWidget | QtWidgets.QTableView,
    mode: DensityMode = "Comfortable",
) -> None:
    style = DENSITY_STYLES.get(mode, DENSITY_STYLES["Comfortable"])

    table.setStyleSheet(
        f"QTableView::item, QTableWidget::item {{"
        f" padding: {style['padding']}; font-size: {style['font']}; }}"
        f"QHeaderView::section {{"
        f" padding: {style['padding']}; font-size: {style['font']}; }}"
    )

    row_height = int(style["row_height"])
    if isinstance(table, QtWidgets.QTableWidget):
        for row in range(table.rowCount()):
            table.setRowHeight(row, row_height)
    else:
        model = table.model()
        if model is not None:
            for row in range(model.rowCount()):
                table.setRowHeight(row, row_height)


def rich_cell(
    text: str,
    *,
    accent_color: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> QtWidgets.QWidget:
    wrapper = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    if accent_color:
        accent = QtWidgets.QFrame()
        accent.setFixedWidth(6)
        accent.setStyleSheet(f"background: {accent_color}; border-radius: 3px;")
        layout.addWidget(accent)

    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
    layout.addWidget(label, 1)

    if tags:
        tags_layout = QtWidgets.QHBoxLayout()
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(4)
        for tag in tags:
            tag_lbl = create_pill(tag, "neutral")
            tag_lbl.setFixedHeight(18)
            tags_layout.addWidget(tag_lbl)
        tags_layout.addStretch(1)
        layout.addLayout(tags_layout)

    return wrapper
