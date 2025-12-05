from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6 import QtWidgets

from app.config.settings import SettingsLoader
from app.security.auth import AuthService
from app.security.audit import AuditLogger, AuditAction
from app.security.tamper import verify_executable
from app.storage.db import Database
from app.ui.app_state import AppState
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import AppBootstrap, MainWindow


def main() -> None:
    settings = SettingsLoader.load()
    db = Database(settings.db_path)
    auth = AuthService(db)
    audit = AuditLogger(db)

    tamper_result = verify_executable(settings)
    if not tamper_result.ok:
        for err in tamper_result.errors:
            print("[SECURITY]", err)
        sys.exit(1)

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
        ok, role, message = auth.authenticate(username, password)
        if ok:
            audit.log(username, AuditAction.LOGIN_SUCCESS.value, details="GUI login")
            break
        login.show_error(message or "Invalid credentials")
        audit.log(username or "unknown", AuditAction.LOGIN_FAILURE.value, details=message or "GUI login failure")

    app_state = AppState()
    bootstrap = AppBootstrap(db)
    engine, thresholds = bootstrap.build_risk_engine()
    window = MainWindow(
        db=db,
        audit=audit,
        auth=auth,
        username=username,
        role=role or "ANALYST",
        session_timeout_minutes=settings.session_timeout_minutes,
        tamper_warnings=tamper_result.warnings,
        settings=settings,
        app_state=app_state,
    )
    worker = bootstrap.start_simulation(engine, thresholds)
    window.attach_simulation(worker)
    window.show()
    exit_code = app.exec()
    worker.requestInterruption()
    worker.wait(2000)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
