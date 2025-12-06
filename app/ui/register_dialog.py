from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.security.auth import AuthService


class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, auth: AuthService, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.auth = auth

        self.setWindowTitle("Neues Konto anlegen")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("analyst_demo")

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("Mind. 12 Zeichen")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)

        self.confirm_input = QtWidgets.QLineEdit()
        self.confirm_input.setPlaceholderText("Passwort bestätigen")
        self.confirm_input.setEchoMode(QtWidgets.QLineEdit.Password)

        user_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogInfoView)
        lock_icon = self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)

        self._add_leading_icon(self.username_input, user_icon)
        self._add_leading_icon(self.password_input, lock_icon)
        self._add_leading_icon(self.confirm_input, lock_icon)

        self._pass_toggle = QtWidgets.QToolButton()
        self._pass_toggle.setCheckable(True)
        self._pass_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._pass_toggle.setToolTip("Passwort anzeigen")
        self._pass_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))

        self._confirm_toggle = QtWidgets.QToolButton()
        self._confirm_toggle.setCheckable(True)
        self._confirm_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._confirm_toggle.setToolTip("Passwort anzeigen")
        self._confirm_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))

        self._add_trailing_widget(self.password_input, self._pass_toggle)
        self._add_trailing_widget(self.confirm_input, self._confirm_toggle)

        self._pass_toggle.clicked.connect(self._toggle_password_visibility)
        self._confirm_toggle.clicked.connect(self._toggle_confirm_visibility)

        self.info = QtWidgets.QLabel(
            "Analysten-Konten nutzen die vordefinierte Rolle ANALYST.\nAdmins nutzen weiterhin den gesicherten Bootstrap-Mechanismus."
        )
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #cbd5e1; font-size: 11px;")

        self.error = QtWidgets.QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #fca5a5; font-size: 11px;")
        self.error.setVisible(False)

        self.submit_btn = QtWidgets.QPushButton("Konto anlegen")
        self.submit_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOkButton))
        self.submit_btn.setDefault(True)

        self.cancel_btn = QtWidgets.QPushButton("Abbrechen")
        self.cancel_btn.setObjectName("ghost")

        btns = QtWidgets.QHBoxLayout()
        btns.setContentsMargins(0, 8, 0, 0)
        btns.setSpacing(8)
        btns.addStretch(1)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.submit_btn)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form.setFormAlignment(QtCore.Qt.AlignVCenter)
        form.setVerticalSpacing(12)
        form.addRow("Username", self.username_input)
        form.addRow("Passwort", self.password_input)
        form.addRow("Bestätigung", self.confirm_input)

        card = QtWidgets.QFrame()
        card.setObjectName("registerCard")

        title = QtWidgets.QLabel("Registrierung")
        title.setFont(QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold))

        subtitle = QtWidgets.QLabel("Lokales Konto für sichere Analysen anlegen")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")

        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addLayout(header_layout)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(self.error)
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

        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn.clicked.connect(self.reject)

        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.confirm_input.setFocus)
        self.confirm_input.returnPressed.connect(self.submit_btn.click)

    def _set_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def _on_submit(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username:
            self._set_error("Bitte einen Benutzernamen angeben.")
            return

        if password != confirm:
            self._set_error("Passwörter stimmen nicht überein.")
            return

        ok, message = self.auth.register_user(username=username, password=password, role="ANALYST")
        if not ok:
            self._set_error(message)
            return

        self._set_error("")
        QtWidgets.QMessageBox.information(
            self,
            "Konto erstellt",
            f"Konto <b>{username}</b> wurde angelegt.",
        )
        self.accept()

    def _toggle_password_visibility(self) -> None:
        if self._pass_toggle.isChecked():
            self.password_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self._pass_toggle.setToolTip("Passwort ausblenden")
            self._pass_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogNoButton))
        else:
            self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self._pass_toggle.setToolTip("Passwort anzeigen")
            self._pass_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))

    def _toggle_confirm_visibility(self) -> None:
        if self._confirm_toggle.isChecked():
            self.confirm_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self._confirm_toggle.setToolTip("Passwort ausblenden")
            self._confirm_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogNoButton))
        else:
            self.confirm_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self._confirm_toggle.setToolTip("Passwort anzeigen")
            self._confirm_toggle.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #020617; }
            QFrame#registerCard { background-color: #0f172a; border-radius: 16px; border: 1px solid #1e293b; }
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
