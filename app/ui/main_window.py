from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtCore, QtWidgets

from app.config_loader import safe_load_indicators, safe_load_thresholds, resolve_indicator_path, resolve_threshold_path
from app.config.settings import AppSettings
from app.core.baseline_engine import BaselineEngine
from app.core.entity_resolution import deduplicate
from app.core.event_correlation import CorrelationEngine
from app.core.export_bridge import export_case_json
from app.core.exporter import export_case_bundle
from app.core.kyc_risk import evaluate_customer
from app.core.sealed_case import seal_case
from app.core.secure_clipboard import SecureClipboard
from app.core.validation import sanitize_text, validate_role
from app.core.evidence_locker import add_evidence, list_evidence
from app.domain import Alert, Case, CaseNote, CaseStatus, Transaction
from app.risk_engine import RiskScoringEngine, RiskThresholds
from app.security.audit import AuditLogger, AuditAction
from app.security.auth import AuthService
from app.storage.db import Database
from app.test_data import cnp_velocity, make_accounts, make_customers, pep_offshore_transactions, structuring_burst
from app.ui.case_timeline import CaseTimelineDialog
from app.ui.network_view import NetworkView


class SimulationWorker(QtCore.QThread):
    alert_ready = QtCore.Signal(dict)

    def __init__(self, db: Database, engine: RiskScoringEngine, thresholds: RiskThresholds, accounts: Dict[str, str]):
        super().__init__()
        self.db = db
        self.engine = engine
        self.thresholds = thresholds
        self.accounts_map = accounts
        self._tx_cycle = itertools.cycle(self._build_tx_queue())
        self.correlations = CorrelationEngine(db)

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
                existing_alerts = []
                for row in self.db.list_alerts(limit=25):
                    tx_row = self.db.get_transaction(row["transaction_id"])
                    if not tx_row:
                        continue
                    existing_alerts.append(
                        Alert(
                            id=row["id"],
                            transaction=tx_row,
                            score=row["score"],
                            evaluated_indicators=[],
                            created_at=datetime.fromisoformat(row["created_at"]),
                        )
                    )
                self.correlations.correlate([alert, *existing_alerts])
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
    def __init__(
        self,
        db: Database,
        audit: AuditLogger,
        auth: AuthService,
        username: str,
        role: str,
        session_timeout_minutes: int = 15,
        tamper_warnings: Optional[List[str]] = None,
        settings: Optional[AppSettings] = None,
    ):
        super().__init__()
        self.db = db
        self.audit = audit
        self.auth = auth
        self.username = username
        self.role = role
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.last_activity = datetime.utcnow()
        self.tamper_warnings = tamper_warnings or []
        self.settings = settings
        self.baselines = BaselineEngine(db)
        self.correlations = CorrelationEngine(db)
        self.clipboard = SecureClipboard(self)

        self.setWindowTitle("FMR TaskForce Codex - Desktop")
        self.resize(1200, 800)

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_tab = QtWidgets.QWidget()
        self.alerts_tab = QtWidgets.QWidget()
        self.cases_tab = QtWidgets.QWidget()
        self.timeline_tab = QtWidgets.QWidget()
        self.network_tab = QtWidgets.QWidget()
        self.customers_tab = QtWidgets.QWidget()
        self.kyc_tab = QtWidgets.QWidget()
        self.evidence_tab = QtWidgets.QWidget()
        self.compare_tab = QtWidgets.QWidget()
        self.cluster_tab = QtWidgets.QWidget()
        self.actor_tab = QtWidgets.QWidget()
        self.security_tab = QtWidgets.QWidget()
        self.settings_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.alerts_tab, "Alerts")
        self.tabs.addTab(self.cases_tab, "Cases")
        self.tabs.addTab(self.timeline_tab, "Case Timeline")
        self.tabs.addTab(self.evidence_tab, "Evidence")
        self.tabs.addTab(self.compare_tab, "Compare Cases")
        self.tabs.addTab(self.cluster_tab, "Alert Clusters")
        self.tabs.addTab(self.customers_tab, "Customers / Accounts")
        self.tabs.addTab(self.kyc_tab, "KYC Risk")
        self.tabs.addTab(self.network_tab, "Network")
        self.tabs.addTab(self.actor_tab, "Actors")
        self.tabs.addTab(self.security_tab, "Security / Audit")
        self.tabs.addTab(self.settings_tab, "Settings")

        self._build_dashboard()
        self._build_alerts()
        self._build_cases()
        self._build_timeline()
        self._build_evidence()
        self._build_compare()
        self._build_clusters()
        self._build_customers()
        self._build_kyc()
        self._build_network()
        self._build_actor()
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
        self.case_timeline_btn = QtWidgets.QPushButton("Timeline")
        self.case_export_btn = QtWidgets.QPushButton("Forensic Export")
        controls.addWidget(self.case_refresh_btn)
        controls.addWidget(self.case_close_btn)
        controls.addWidget(self.case_timeline_btn)
        controls.addWidget(self.case_export_btn)
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
        self.case_timeline_btn.clicked.connect(self._open_timeline)
        self.case_export_btn.clicked.connect(self._export_case)
        self.case_notes.installEventFilter(self)

        self.cases_tab.setLayout(layout)

    def _build_timeline(self):
        layout = QtWidgets.QVBoxLayout()
        self.timeline_case_input = QtWidgets.QLineEdit()
        self.timeline_case_input.setPlaceholderText("Case ID")
        self.timeline_refresh = QtWidgets.QPushButton("Load Timeline")
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.timeline_case_input)
        top.addWidget(self.timeline_refresh)
        layout.addLayout(top)
        self.timeline_table = QtWidgets.QTableWidget(0, 3)
        self.timeline_table.setHorizontalHeaderLabels(["Timestamp", "Type", "Description"])
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.timeline_table)
        self.timeline_tab.setLayout(layout)
        self.timeline_refresh.clicked.connect(self._load_timeline_tab)

    def _build_customers(self):
        layout = QtWidgets.QVBoxLayout()
        self.customer_table = QtWidgets.QTableWidget(0, 4)
        self.customer_table.setHorizontalHeaderLabels(["Customer", "Country", "PEP", "Annual Income"])
        self.customer_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.customer_table)
        self.customer_table.itemSelectionChanged.connect(self._load_selected_customer_kyc)
        self.customers_tab.setLayout(layout)

    def _build_kyc(self):
        layout = QtWidgets.QVBoxLayout()
        self.kyc_summary = QtWidgets.QLabel("Select a customer to view KYC risk.")
        self.kyc_table = QtWidgets.QTableWidget(0, 3)
        self.kyc_table.setHorizontalHeaderLabels(["Dimension", "Score", "Rationale"])
        self.kyc_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.kyc_summary)
        layout.addWidget(self.kyc_table)
        self.kyc_tab.setLayout(layout)

    def _build_evidence(self):
        layout = QtWidgets.QVBoxLayout()
        controls = QtWidgets.QHBoxLayout()
        self.evidence_case_input = QtWidgets.QLineEdit()
        self.evidence_case_input.setPlaceholderText("Case ID")
        self.evidence_add_btn = QtWidgets.QPushButton("Add Evidence")
        self.evidence_seal_btn = QtWidgets.QPushButton("Seal Case")
        controls.addWidget(self.evidence_case_input)
        controls.addWidget(self.evidence_add_btn)
        controls.addWidget(self.evidence_seal_btn)
        layout.addLayout(controls)
        self.evidence_table = QtWidgets.QTableWidget(0, 5)
        self.evidence_table.setHorizontalHeaderLabels(["File", "Hash", "Added By", "Sealed", "Created"])
        self.evidence_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.evidence_table)
        self.evidence_tab.setLayout(layout)
        self.evidence_add_btn.clicked.connect(self._add_evidence)
        self.evidence_seal_btn.clicked.connect(self._seal_case)

    def _build_compare(self):
        layout = QtWidgets.QVBoxLayout()
        inputs = QtWidgets.QHBoxLayout()
        self.compare_case_a = QtWidgets.QLineEdit()
        self.compare_case_a.setPlaceholderText("Case A")
        self.compare_case_b = QtWidgets.QLineEdit()
        self.compare_case_b.setPlaceholderText("Case B")
        self.compare_btn = QtWidgets.QPushButton("Compare")
        self.copy_compare_btn = QtWidgets.QPushButton("Copy Summary")
        inputs.addWidget(self.compare_case_a)
        inputs.addWidget(self.compare_case_b)
        inputs.addWidget(self.compare_btn)
        inputs.addWidget(self.copy_compare_btn)
        self.compare_text = QtWidgets.QTextEdit()
        self.compare_text.setReadOnly(True)
        layout.addLayout(inputs)
        layout.addWidget(self.compare_text)
        self.compare_tab.setLayout(layout)
        self.compare_btn.clicked.connect(self._compare_cases)
        self.copy_compare_btn.clicked.connect(self._copy_compare)

    def _build_clusters(self):
        layout = QtWidgets.QVBoxLayout()
        self.cluster_table = QtWidgets.QTableWidget(0, 4)
        self.cluster_table.setHorizontalHeaderLabels(["Domain", "Risk", "Count", "Latest"])
        self.cluster_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.cluster_table)
        self.cluster_tab.setLayout(layout)

    def _build_actor(self):
        layout = QtWidgets.QVBoxLayout()
        self.actor_table = QtWidgets.QTableWidget(0, 4)
        self.actor_table.setHorizontalHeaderLabels(["Customer", "Alerts", "Cases", "Baseline Avg"])
        self.actor_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.actor_table)
        self.actor_tab.setLayout(layout)

    def _build_network(self):
        layout = QtWidgets.QVBoxLayout()
        self.network_view = NetworkView(self.db)
        refresh_btn = QtWidgets.QPushButton("Refresh Graph")
        refresh_btn.clicked.connect(self.network_view.refresh)
        layout.addWidget(refresh_btn)
        layout.addWidget(self.network_view)
        self.network_tab.setLayout(layout)

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
        if self.settings:
            layout.addRow("Secure mode", QtWidgets.QLabel("ON" if self.settings.secure_mode else "OFF"))
            layout.addRow("Expected hash", QtWidgets.QLabel(self.settings.expected_exe_hash or "not set"))
        if self.tamper_warnings:
            warnings_box = QtWidgets.QTextEdit("\n".join(self.tamper_warnings))
            warnings_box.setReadOnly(True)
            warnings_box.setMaximumHeight(120)
            layout.addRow("Security warnings", warnings_box)
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
        self._load_clusters()
        self._load_actor()
        self._load_evidence_table()
        self.network_view.refresh()

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

    def _load_clusters(self):
        rows = self.db.list_alerts(limit=200)
        clusters: Dict[tuple[str, str], list[str]] = {}
        latest: Dict[tuple[str, str], str] = {}
        for row in rows:
            key = (row["domain"], row["risk_level"])
            clusters.setdefault(key, []).append(row["id"])
            latest[key] = row["created_at"]
        self.cluster_table.setRowCount(len(clusters))
        for idx, ((domain, risk), alert_ids) in enumerate(clusters.items()):
            values = [domain, risk, len(alert_ids), latest.get((domain, risk), "")]
            for col, value in enumerate(values):
                self.cluster_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_actor(self):
        customers = make_customers()
        accounts = make_accounts(customers)
        account_to_customer = {a.id: a.customer_id for a in accounts}
        alerts = self.db.list_alerts(limit=300)
        cases = self.db.list_cases()
        counts: Dict[str, Dict[str, int]] = {}
        for alert in alerts:
            tx = self.db.get_transaction(alert["transaction_id"])
            cust_id = account_to_customer.get(tx.account_id, "unknown") if tx else "unknown"
            bucket = counts.setdefault(cust_id, {"alerts": 0, "cases": 0})
            bucket["alerts"] += 1
        for case in cases:
            bucket = counts.setdefault(case["id"], {"alerts": 0, "cases": 0})
            bucket["cases"] += 1
        self.actor_table.setRowCount(len(customers))
        for idx, cust in enumerate(customers):
            baseline = self.baselines.fetch(cust.id)
            stats = counts.get(cust.id, {"alerts": 0, "cases": 0})
            values = [cust.name, stats["alerts"], stats["cases"], f"{(baseline.avg_amount if baseline else 0):.0f}"]
            for col, value in enumerate(values):
                self.actor_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_evidence_table(self):
        case_id = sanitize_text(self.evidence_case_input.text(), max_length=128)
        if not case_id:
            self.evidence_table.setRowCount(0)
            return
        rows = list_evidence(self.db, case_id)
        self.evidence_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            values = [row["filename"], row["hash"], row["added_by"], "Yes" if row["sealed"] else "No", row["created_at"]]
            for col, value in enumerate(values):
                self.evidence_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_timeline_tab(self):
        case_id = sanitize_text(self.timeline_case_input.text(), max_length=128)
        if not case_id:
            return
        events = self.db.case_timeline(case_id)
        self.timeline_table.setRowCount(len(events))
        for idx, event in enumerate(events):
            self.timeline_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(str(event.get("timestamp"))))
            self.timeline_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(str(event.get("type"))))
            self.timeline_table.setItem(idx, 2, QtWidgets.QTableWidgetItem(str(event.get("description"))))

    def _close_selected_case(self):
        if not validate_role(self.role) or self.role not in {"LEAD", "ADMIN"}:
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

    def _open_timeline(self):
        row = self.case_table.currentRow()
        if row < 0:
            return
        case_id = self.case_table.item(row, 0).text()
        dialog = CaseTimelineDialog(self.db, case_id, self)
        dialog.exec()

    def _export_case(self):
        if not self.settings:
            QtWidgets.QMessageBox.warning(self, "Config", "Settings unavailable for export path.")
            return
        row = self.case_table.currentRow()
        if row < 0:
            return
        case_id = self.case_table.item(row, 0).text()
        try:
            path, hash_value = export_case_bundle(self.db, case_id, self.settings.exports_dir)
            json_path = export_case_json(self.db, case_id, self.settings.exports_dir)
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Case exported to {path}\nJSON: {json_path}\nSHA256: {hash_value}",
            )
            self.audit.log(self.username, AuditAction.SETTINGS_CHANGE.value, target=case_id, details="Forensic export")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))

    def _load_selected_customer_kyc(self):
        row = self.customer_table.currentRow()
        if row < 0:
            return
        customers = make_customers()
        if row >= len(customers):
            return
        profile = evaluate_customer(customers[row])
        self.kyc_summary.setText(f"Total: {profile.total_score} ({profile.level})")
        self.kyc_table.setRowCount(len(profile.dimensions))
        for idx, dim in enumerate(profile.dimensions):
            self.kyc_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(dim.name))
            self.kyc_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(str(dim.score)))
            self.kyc_table.setItem(idx, 2, QtWidgets.QTableWidgetItem(dim.rationale))

    def _add_evidence(self):
        case_id = sanitize_text(self.evidence_case_input.text(), max_length=128)
        if not case_id:
            QtWidgets.QMessageBox.warning(self, "Case", "Provide a case ID")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select evidence file")
        if not path:
            return
        try:
            filename, digest = add_evidence(self.db, case_id, Path(path), self.username)
            QtWidgets.QMessageBox.information(self, "Evidence stored", f"{filename}\nSHA256: {digest}")
            self.audit.log(self.username, AuditAction.EVIDENCE_ADDED.value, target=case_id, details=filename)
            self._load_evidence_table()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Evidence", str(exc))

    def _seal_case(self):
        case_id = sanitize_text(self.evidence_case_input.text(), max_length=128)
        if not case_id:
            return
        try:
            _, digest = seal_case(self.db, case_id, sealed_by=self.username)
            QtWidgets.QMessageBox.information(self, "Case sealed", f"Hash: {digest}")
            self.audit.log(self.username, AuditAction.CASE_SEALED.value, target=case_id, details="sealed")
            self._load_evidence_table()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Seal", str(exc))

    def _compare_cases(self):
        case_a = sanitize_text(self.compare_case_a.text(), max_length=128)
        case_b = sanitize_text(self.compare_case_b.text(), max_length=128)
        if not case_a or not case_b:
            return
        alerts_a = {a["id"] for a in self.db.alerts_for_case(case_a)}
        alerts_b = {b["id"] for b in self.db.alerts_for_case(case_b)}
        overlap = alerts_a & alerts_b
        summary = [
            f"Case A alerts: {len(alerts_a)}",
            f"Case B alerts: {len(alerts_b)}",
            f"Overlap: {len(overlap)}",
            f"Shared IDs: {', '.join(sorted(overlap)) if overlap else 'None'}",
        ]
        self.compare_text.setText("\n".join(summary))
        self.audit.log(self.username, AuditAction.SETTINGS_CHANGE.value, target=f"compare:{case_a}:{case_b}", details="case compare")

    def _copy_compare(self):
        self.clipboard.copy(self.compare_text.toPlainText())

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
