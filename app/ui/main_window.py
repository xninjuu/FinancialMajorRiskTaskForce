from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

from PySide6 import QtCore, QtWidgets

from app.config_loader import safe_load_indicators, safe_load_thresholds, resolve_indicator_path, resolve_threshold_path
from app.domain import Alert, Case, CaseNote, CaseStatus, Transaction
from app.risk_engine import RiskScoringEngine, RiskThresholds
from app.core.validation import sanitize_text
from app.security.audit import AuditLogger, AuditAction
from app.security.auth import AuthService
from app.storage.db import Database
from app.test_data import cnp_velocity, make_accounts, make_customers, pep_offshore_transactions, structuring_burst


class SimulationWorker(QtCore.QThread):
    alert_ready = QtCore.Signal(dict)

    def __init__(self, db: Database, engine: RiskScoringEngine, thresholds: RiskThresholds, accounts: Dict[str, str]):
        super().__init__()
        self.db = db
        self.engine = engine
        self.thresholds = thresholds
        self.accounts_map = accounts
        self._tx_cycle = itertools.cycle(self._build_tx_queue())

    def _build_tx_queue(self) -> List[Transaction]:
        customers = make_customers()
        accounts = make_accounts(customers)
        by_id = {acct.id: acct for acct in accounts}
        self.accounts_map.update({acct.id: acct.customer_id for acct in accounts})
        bursts: List[List[Transaction]] = [
            structuring_burst(accounts[0]),
            pep_offshore_transactions(accounts[1]),
            cnp_velocity(accounts[0]),
        ]
        merged: List[Transaction] = []
        for seq in bursts:
            merged.extend(seq)
        return merged

    def run(self) -> None:
        for tx in self._tx_cycle:
            if self.isInterruptionRequested():
                break
            history = self.db.recent_transactions(tx.account_id, window=timedelta(days=7))
            score, evaluated = self.engine.score_transaction(tx, history)
            risk_level = self.thresholds.level(score)
            self.db.record_transaction(tx)
            alert = Alert(
                id=str(uuid.uuid4()),
                transaction=tx,
                score=score,
                evaluated_indicators=evaluated,
                created_at=datetime.utcnow(),
            )
            if risk_level != "Low":
                if risk_level == "High":
                    case = Case(id=str(uuid.uuid4()), alerts=[alert], status=CaseStatus.OPEN, priority="High")
                    alert.case_id = case.id
                    self.db.record_case(case)
                self.db.record_alert(alert, risk_level)
                self.alert_ready.emit(
                    {
                        "id": alert.id,
                        "score": score,
                        "risk_level": risk_level,
                        "account_id": tx.account_id,
                        "domain": evaluated[0].indicator.domain.name if evaluated else "UNKNOWN",
                        "created_at": alert.created_at,
                    }
                )
            self.msleep(900)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, db: Database, audit: AuditLogger, auth: AuthService, username: str, role: str, session_timeout_minutes: int = 15):
        super().__init__()
        self.db = db
        self.audit = audit
        self.auth = auth
        self.username = username
        self.role = role
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.last_activity = datetime.utcnow()

        self.setWindowTitle("FMR TaskForce Codex - Desktop")
        self.resize(1200, 800)

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_tab = QtWidgets.QWidget()
        self.alerts_tab = QtWidgets.QWidget()
        self.cases_tab = QtWidgets.QWidget()
        self.customers_tab = QtWidgets.QWidget()
        self.security_tab = QtWidgets.QWidget()
        self.settings_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.alerts_tab, "Alerts")
        self.tabs.addTab(self.cases_tab, "Cases")
        self.tabs.addTab(self.customers_tab, "Customers / Accounts")
        self.tabs.addTab(self.security_tab, "Security / Audit")
        self.tabs.addTab(self.settings_tab, "Settings")

        self._build_dashboard()
        self._build_alerts()
        self._build_cases()
        self._build_customers()
        self._build_security()
        self._build_settings()

        self._activity_timer = QtCore.QTimer(self)
        self._activity_timer.timeout.connect(self._check_session_timeout)
        self._activity_timer.start(30_000)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_all)
        self._refresh_timer.start(5_000)

        self.installEventFilter(self)

    # region UI builders
    def _build_dashboard(self):
        layout = QtWidgets.QVBoxLayout()
        self.kpi_alerts = QtWidgets.QLabel("Alerts: 0")
        self.kpi_cases = QtWidgets.QLabel("Open Cases: 0")
        self.kpi_high = QtWidgets.QLabel("High Alerts (24h): 0")
        for lbl in (self.kpi_alerts, self.kpi_cases, self.kpi_high):
            lbl.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(self.kpi_alerts)
        layout.addWidget(self.kpi_cases)
        layout.addWidget(self.kpi_high)
        layout.addStretch(1)
        self.dashboard_tab.setLayout(layout)

    def _build_alerts(self):
        layout = QtWidgets.QVBoxLayout()
        controls = QtWidgets.QHBoxLayout()
        self.alert_refresh_btn = QtWidgets.QPushButton("Refresh")
        controls.addWidget(self.alert_refresh_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.alert_table = QtWidgets.QTableWidget(0, 6)
        self.alert_table.setHorizontalHeaderLabels(["Created", "Account", "Score", "Level", "Domain", "Case"])
        self.alert_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.alert_table)

        self.alert_refresh_btn.clicked.connect(self._load_alerts)
        self.alerts_tab.setLayout(layout)

    def _build_cases(self):
        layout = QtWidgets.QVBoxLayout()
        controls = QtWidgets.QHBoxLayout()
        self.case_refresh_btn = QtWidgets.QPushButton("Refresh")
        self.case_close_btn = QtWidgets.QPushButton("Close Case")
        controls.addWidget(self.case_refresh_btn)
        controls.addWidget(self.case_close_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.case_table = QtWidgets.QTableWidget(0, 5)
        self.case_table.setHorizontalHeaderLabels(["Case ID", "Status", "Priority", "Created", "Updated"])
        self.case_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.case_table)

        self.case_notes = QtWidgets.QTextEdit()
        self.case_notes.setPlaceholderText("Add note (ENTER to save)")
        self.case_notes.setMaximumHeight(100)
        layout.addWidget(self.case_notes)

        self.case_refresh_btn.clicked.connect(self._load_cases)
        self.case_close_btn.clicked.connect(self._close_selected_case)
        self.case_notes.installEventFilter(self)

        self.cases_tab.setLayout(layout)

    def _build_customers(self):
        layout = QtWidgets.QVBoxLayout()
        self.customer_table = QtWidgets.QTableWidget(0, 4)
        self.customer_table.setHorizontalHeaderLabels(["Customer", "Country", "PEP", "Annual Income"])
        self.customer_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.customer_table)
        self.customers_tab.setLayout(layout)

    def _build_security(self):
        layout = QtWidgets.QVBoxLayout()
        self.audit_table = QtWidgets.QTableWidget(0, 4)
        self.audit_table.setHorizontalHeaderLabels(["Timestamp", "User", "Action", "Target"])
        self.audit_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.audit_table)
        self.security_tab.setLayout(layout)

    def _build_settings(self):
        layout = QtWidgets.QFormLayout()
        self.role_label = QtWidgets.QLabel(self.role)
        layout.addRow("Current role", self.role_label)
        self.settings_tab.setLayout(layout)

    # endregion

    def attach_simulation(self, worker: SimulationWorker):
        worker.alert_ready.connect(lambda _: self.refresh_all())
        worker.start()

    def refresh_all(self):
        self._load_dashboard()
        self._load_alerts()
        self._load_cases()
        self._load_customers()
        self._load_audit()

    def _load_dashboard(self):
        alerts = self.db.list_alerts(limit=200)
        cases = self.db.list_cases()
        high_24h = [a for a in alerts if a["risk_level"] == "High" and datetime.fromisoformat(a["created_at"]) >= datetime.utcnow() - timedelta(hours=24)]
        self.kpi_alerts.setText(f"Alerts: {len(alerts)}")
        self.kpi_cases.setText(f"Open Cases: {len([c for c in cases if c['status'] != 'CLOSED'])}")
        self.kpi_high.setText(f"High Alerts (24h): {len(high_24h)}")

    def _load_alerts(self):
        rows = self.db.list_alerts(limit=200)
        self.alert_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            values = [
                row["created_at"],
                row["transaction_id"],
                f"{row['score']:.1f}",
                row["risk_level"],
                row["domain"],
                row["case_id"] or "",
            ]
            for col, value in enumerate(values):
                self.alert_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_cases(self):
        rows = self.db.list_cases()
        self.case_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            values = [row["id"], row["status"], row["priority"], row["created_at"], row["updated_at"]]
            for col, value in enumerate(values):
                self.case_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_customers(self):
        customers = make_customers()
        self.customer_table.setRowCount(len(customers))
        for idx, c in enumerate(customers):
            values = [c.name, c.country, "Yes" if c.is_pep else "No", f"{c.annual_declared_income:,.0f}"]
            for col, value in enumerate(values):
                self.customer_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_audit(self):
        rows = self.audit.recent(limit=200)
        self.audit_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            values = [row["timestamp"], row["username"], row["action"], row.get("target") or ""]
            for col, value in enumerate(values):
                self.audit_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _close_selected_case(self):
        if self.role not in {"LEAD", "ADMIN"}:
            QtWidgets.QMessageBox.warning(self, "Access denied", "Only LEAD or ADMIN can close cases.")
            return
        row = self.case_table.currentRow()
        if row < 0:
            return
        case_id = self.case_table.item(row, 0).text()
        self.db.update_case_status(case_id, status="CLOSED")
        self.audit.log(self.username, AuditAction.CASE_STATUS_CHANGE.value, target=case_id, details="Closed from UI")
        note_text = sanitize_text(self.case_notes.toPlainText(), max_length=500, allow_newlines=False)
        if note_text:
            self.db.attach_note(case_id, CaseNote(author=self.username, message=note_text, created_at=datetime.utcnow()))
            self.audit.log(self.username, AuditAction.CASE_NOTE_ADDED.value, target=case_id, details=note_text[:120])
            self.case_notes.clear()
        self.refresh_all()

    def eventFilter(self, source, event):
        if event.type() in {QtCore.QEvent.MouseButtonPress, QtCore.QEvent.KeyPress}:
            self.last_activity = datetime.utcnow()
        if source is self.case_notes and event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Return:
            self._close_selected_case()
            return True
        return super().eventFilter(source, event)

    def _check_session_timeout(self):
        if datetime.utcnow() - self.last_activity > self.session_timeout:
            QtWidgets.QMessageBox.information(self, "Session locked", "Inactivity timeout. Please re-authenticate.")
            self._lock_session()

    def _lock_session(self):
        from app.ui.login_dialog import LoginDialog

        dialog = LoginDialog(self)
        self.audit.log(self.username, AuditAction.SESSION_LOCK.value, details="User-initiated lock or timeout")
        while True:
            if dialog.exec() == QtWidgets.QDialog.Rejected:
                QtWidgets.QMessageBox.warning(self, "Locked", "Application locked. Close and restart if you cannot log in.")
                continue
            username, password = dialog.credentials()
            ok, role, message = self.auth.authenticate(username, password)
            if ok:
                self.username = username
                self.role = role or self.role
                self.last_activity = datetime.utcnow()
                self.audit.log(username, "LOGIN_SUCCESS", details="Unlocked session")
                self.role_label.setText(self.role)
                break
            dialog.show_error(message or "Invalid credentials")
            self.audit.log(username or "unknown", "LOGIN_FAILURE", details=message or "Unlock failed")


class AppBootstrap:
    def __init__(self, db: Database):
        self.db = db

    def build_risk_engine(self) -> tuple[RiskScoringEngine, RiskThresholds]:
        from app.risk_engine import default_indicators, RiskThresholds

        indicators = safe_load_indicators(path=resolve_indicator_path(), fallback=default_indicators())
        thresholds = safe_load_thresholds(path=resolve_threshold_path(), fallback=RiskThresholds())
        customers = {c.id: c for c in make_customers()}
        accounts = {a.id: a for a in make_accounts(customers.values())}
        engine = RiskScoringEngine(indicators=indicators, thresholds=thresholds, customers=customers, accounts=accounts)
        return engine, thresholds

    def start_simulation(self, engine: RiskScoringEngine, thresholds: RiskThresholds) -> SimulationWorker:
        accounts_map: Dict[str, str] = {}
        worker = SimulationWorker(db=self.db, engine=engine, thresholds=thresholds, accounts=accounts_map)
        return worker
