from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6 import QtWidgets

from app.config.settings import SettingsLoader
from app.security.auth import AuthService
from app.security.audit import AuditLogger
from app.storage.db import Database
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import AppBootstrap, MainWindow


def main() -> None:
    settings = SettingsLoader.load()
    db = Database(settings.db_path)
    auth = AuthService(db)
    audit = AuditLogger(db)

    generated_password = auth.bootstrap_admin()
    if generated_password:
        print("[SECURITY] Generated initial admin password (store securely):", generated_password)

    app = QtWidgets.QApplication(sys.argv)
    login = LoginDialog()

    while True:
        if login.exec() == QtWidgets.QDialog.Rejected:
            print("Login cancelled")
            sys.exit(1)
        username, password = login.credentials()
        ok, role = auth.authenticate(username, password)
        if ok:
            audit.log(username, "LOGIN_SUCCESS", details="GUI login")
            break
        login.show_error("Invalid credentials")
        audit.log(username or "unknown", "LOGIN_FAILURE", details="GUI login failure")

    bootstrap = AppBootstrap(db)
    engine, thresholds = bootstrap.build_risk_engine()
    window = MainWindow(db=db, audit=audit, auth=auth, username=username, role=role or "ANALYST", session_timeout_minutes=settings.session_timeout_minutes)
    worker = bootstrap.start_simulation(engine, thresholds)
    window.attach_simulation(worker)
    window.show()
    exit_code = app.exec()
    worker.requestInterruption()
    worker.wait(2000)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
