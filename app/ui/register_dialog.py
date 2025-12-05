from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from app.security.auth import AuthService


class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, auth: AuthService, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.setWindowTitle("Neues Konto anlegen")
        self.setModal(True)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("analyst_demo")
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("Mind. 12 Zeichen")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.confirm_input = QtWidgets.QLineEdit()
        self.confirm_input.setPlaceholderText("Passwort bestätigen")
        self.confirm_input.setEchoMode(QtWidgets.QLineEdit.Password)

        form = QtWidgets.QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Passwort", self.password_input)
        form.addRow("Bestätigung", self.confirm_input)

        self.info = QtWidgets.QLabel(
            "Analysten-Konten nutzen die vordefinierte Rolle ANALYST. Admins nutzen weiterhin den gesicherten Bootstrap.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        self.error = QtWidgets.QLabel("")
        self.error.setStyleSheet("color: #ff6b6b;")

        self.submit_btn = QtWidgets.QPushButton("Konto anlegen")
        self.submit_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogOkButton))
        self.cancel_btn = QtWidgets.QPushButton("Abbrechen")

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.submit_btn)

        card = QtWidgets.QFrame()
        card.setStyleSheet(
            """
            QFrame {background-color: #1f2330; border: 1px solid #2d3242; border-radius: 10px;}
            QLineEdit {padding: 8px; border-radius: 6px; border: 1px solid #3a4154; color: #e5e7eb; background: #0f121a;}
            QLabel {color: #e5e7eb;}
            QPushButton {padding: 8px 14px; border-radius: 6px; background: #2563eb; color: white;}
            QPushButton:hover {background: #1d4ed8;}
            QPushButton:disabled {background: #475569;}
            """
        )
        layout = QtWidgets.QVBoxLayout(card)
        title = QtWidgets.QLabel("Registrierung")
        title.setFont(QtGui.QFont("Segoe UI", 14, QtGui.QFont.Bold))
        subtitle = QtWidgets.QLabel("Lokales Konto für sichere Analysen anlegen")
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(self.error)
        layout.addLayout(btns)

        outer = QtWidgets.QVBoxLayout()
        outer.addWidget(card)
        self.setLayout(outer)

        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn.clicked.connect(self.reject)

    def _on_submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()
        if password != confirm:
            self.error.setText("Passwörter stimmen nicht überein")
            return
        ok, message = self.auth.register_user(username=username, password=password, role="ANALYST")
        if not ok:
            self.error.setText(message)
            return
        QtWidgets.QMessageBox.information(self, "Konto erstellt", f"Konto {username} wurde angelegt.")
        self.accept()
