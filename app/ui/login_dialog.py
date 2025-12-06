from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.core.validation import validate_password_policy, validate_username


class LoginDialog(QtWidgets.QDialog):
    REGISTER_CODE = 2

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, *, demo_hint: str | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("FMRTF – Financial Major Risk Task Force")
        self.setModal(True)
        self.setSizeGripEnabled(False)
        self.setMinimumWidth(420)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("admin oder analyst_demo")

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_input.setPlaceholderText("Passwort")

        self._password_toggle = QtWidgets.QToolButton()
        self._password_toggle.setCheckable(True)
        self._password_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._password_toggle.setToolTip("Passwort anzeigen")
        self._password_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self._password_toggle.clicked.connect(self._toggle_password_visibility)

        user_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogInfoView)
        pass_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)

        self._add_leading_icon(self.username_input, user_icon)
        self._add_leading_icon(self.password_input, pass_icon)
        self._add_trailing_widget(self.password_input, self._password_toggle)

        self.message_label = QtWidgets.QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)

        self.login_button = QtWidgets.QPushButton("Anmelden")
        self.login_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOkButton))
        self.login_button.setDefault(True)

        self.register_button = QtWidgets.QPushButton("Registrieren")
        self.register_button.setObjectName("ghost")
        self.register_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))

        self.cancel_button = QtWidgets.QPushButton("Abbrechen")
        self.cancel_button.setObjectName("ghost")

        btns = QtWidgets.QHBoxLayout()
        btns.setContentsMargins(0, 8, 0, 0)
        btns.setSpacing(8)
        btns.addWidget(self.register_button)
        btns.addStretch(1)
        btns.addWidget(self.cancel_button)
        btns.addWidget(self.login_button)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignVCenter)
        form.setVerticalSpacing(12)
        form.addRow("Username", self.username_input)
        form.addRow("Passwort", self.password_input)

        card = QtWidgets.QFrame()
        card.setObjectName("card")

        title = QtWidgets.QLabel("Financial Major Risk Task Force")
        title.setFont(QtGui.QFont("Segoe UI", 18, QtGui.QFont.Bold))

        subtitle = QtWidgets.QLabel("Sicherer Analysten-Zugang")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")

        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        if demo_hint:
            demo = QtWidgets.QLabel(demo_hint)
            demo.setStyleSheet("color: #22d3ee; font-size: 11px;")
            header_layout.addWidget(demo)

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addLayout(header_layout)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addWidget(self.message_label)
        layout.addLayout(btns)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 10)
        shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        card.setGraphicsEffect(shadow)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 26)
        outer.addWidget(card)

        self._apply_styles()

        self.login_button.clicked.connect(self._on_login)
        self.cancel_button.clicked.connect(self.reject)
        self.register_button.clicked.connect(self._on_register)

        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.login_button.click)

    def credentials(self) -> tuple[str, str]:
        return self.username_input.text().strip(), self.password_input.text()

    def show_error(self, message: str) -> None:
        self.message_label.setText(message)
        self.message_label.setStyleSheet("color: #fca5a5; font-size: 11px;")
        self.message_label.setVisible(bool(message))

    def _on_register(self) -> None:
        self.done(self.REGISTER_CODE)

    def _on_login(self) -> None:
        username, password = self.credentials()
        if not validate_username(username):
            self.show_error("Bitte gültigen Benutzernamen eingeben (3–64 Zeichen).")
            return
        ok, reason = validate_password_policy(password)
        if not ok:
            self.show_error(reason)
            return
        self.show_error("")
        self.accept()

    def _toggle_password_visibility(self) -> None:
        if self._password_toggle.isChecked():
            self.password_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self._password_toggle.setToolTip("Passwort ausblenden")
            self._password_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogNoButton))
        else:
            self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self._password_toggle.setToolTip("Passwort anzeigen")
            self._password_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #020617; }
            QFrame#card { background-color: #0f172a; border-radius: 16px; border: 1px solid #1e293b; }
            QLabel { color: #e5e7eb; }
            QLineEdit { padding: 9px 10px; border-radius: 10px; border: 1px solid #1e293b; background: #020617; color: #e5e7eb; selection-background-color: #2563eb; }
            QLineEdit:focus { border-color: #2563eb; }
            QPushButton { padding: 9px 16px; border-radius: 999px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2563eb, stop:1 #21d4fd); color: white; border: none; font-weight: 600; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2b6ff0, stop:1 #38e0ff); }
            QPushButton:pressed { background: #1d4ed8; }
            QPushButton#ghost { background: transparent; color: #cbd5e1; border-radius: 999px; border: 1px solid #334155; font-weight: 500; }
            QPushButton#ghost:hover { background: rgba(148, 163, 184, 0.08); }
            QToolButton { border: none; background: transparent; }
            """
        )

    def _add_leading_icon(self, line_edit: QtWidgets.QLineEdit, icon: QtGui.QIcon) -> None:
        action = QtGui.QAction(icon, "", line_edit)
        line_edit.addAction(action, QtWidgets.QLineEdit.LeadingPosition)

    def _add_trailing_widget(self, line_edit: QtWidgets.QLineEdit, widget: QtWidgets.QWidget) -> None:
        w_action = QtWidgets.QWidgetAction(line_edit)
        w_action.setDefaultWidget(widget)
        line_edit.addAction(w_action, QtWidgets.QLineEdit.TrailingPosition)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self.parent() is None:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(
                    geo.center().x() - self.width() // 2,
                    geo.center().y() - self.height() // 2,
                )
