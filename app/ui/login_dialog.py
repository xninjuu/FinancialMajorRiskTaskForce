from __future__ import annotations

from PySide6 import QtWidgets


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FMR TaskForce - Login")
        self.username_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.message_label = QtWidgets.QLabel("")
        self.message_label.setStyleSheet("color: red;")

        form = QtWidgets.QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)

        self.login_button = QtWidgets.QPushButton("Login")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.login_button)
        btns.addWidget(self.cancel_button)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.message_label)
        layout.addLayout(btns)
        self.setLayout(layout)

        self.login_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def credentials(self):
        return self.username_input.text().strip(), self.password_input.text()

    def show_error(self, message: str):
        self.message_label.setText(message)
