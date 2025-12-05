from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from app.core.validation import validate_password_policy, validate_username


class LoginDialog(QtWidgets.QDialog):
    REGISTER_CODE = 2

    def __init__(self, parent=None, *, demo_hint: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("FMR TaskForce – Sicherer Login")
        self.setModal(True)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("admin oder analyst_demo")
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_input.setPlaceholderText("Passwort")
        self.message_label = QtWidgets.QLabel("")
        self.message_label.setStyleSheet("color: #fca5a5;")

        form = QtWidgets.QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Passwort", self.password_input)

        self.login_button = QtWidgets.QPushButton("Anmelden")
        self.login_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOkButton))
        self.register_button = QtWidgets.QPushButton("Registrieren")
        self.register_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.cancel_button = QtWidgets.QPushButton("Abbrechen")

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.register_button)
        btns.addStretch(1)
        btns.addWidget(self.cancel_button)
        btns.addWidget(self.login_button)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            """
            QDialog {background-color: #0f1117;}
            QFrame#card {background-color: #1b1f2b; border: 1px solid #283045; border-radius: 12px;}
            QLineEdit {padding: 10px; border-radius: 8px; border: 1px solid #2f384f; background: #0f121a; color: #e5e7eb;}
            QLabel {color: #e5e7eb;}
            QPushButton {padding: 9px 14px; border-radius: 8px; background: #2563eb; color: white;}
            QPushButton:hover {background: #1d4ed8;}
            QPushButton#ghost {background: transparent; color: #cbd5e1; border: 1px solid #334155;}
            """
        )
        layout = QtWidgets.QVBoxLayout(card)
        title = QtWidgets.QLabel("FMR TaskForce")
        title.setFont(QtGui.QFont("Segoe UI", 16, QtGui.QFont.Bold))
        subtitle = QtWidgets.QLabel("Sicherer Analysten-Zugang")
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        if demo_hint:
            demo = QtWidgets.QLabel(demo_hint)
            demo.setStyleSheet("color: #22d3ee; font-size: 11px;")
            layout.addWidget(demo)
        layout.addWidget(self.message_label)
        layout.addLayout(btns)

        outer = QtWidgets.QVBoxLayout()
        outer.setContentsMargins(18, 18, 18, 18)
        outer.addWidget(card)
        self.setLayout(outer)

        self.login_button.clicked.connect(self._on_login)
        self.cancel_button.clicked.connect(self.reject)
        self.register_button.clicked.connect(self._on_register)

    def credentials(self):
        return self.username_input.text().strip(), self.password_input.text()

    def show_error(self, message: str):
        self.message_label.setText(message)

    def _on_register(self) -> None:
        self.done(self.REGISTER_CODE)

    def _on_login(self):
        username, password = self.credentials()
        if not validate_username(username):
            self.show_error("Bitte gültigen Benutzernamen eingeben (3-64 Zeichen).")
            return
        ok, reason = validate_password_policy(password)
        if not ok:
            self.show_error(reason)
            return
        self.accept()
