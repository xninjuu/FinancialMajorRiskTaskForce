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
from app.ui.components import (
    apply_dark_palette,
    create_header_pill,
    create_pill,
    update_pill,
    SectionCard,
)


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

        apply_dark_palette(self)

        self.container = QtWidgets.QWidget()
        self.setCentralWidget(self.container)
        root_layout = QtWidgets.QHBoxLayout(self.container)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.nav_list = QtWidgets.QListWidget()
        self.nav_list.setFixedWidth(220)
        self.nav_list.setObjectName("navList")
        self.nav_list.setStyleSheet("QListWidget#navList { background:#1b1d23; color:#e5e7eb; border-right:1px solid #2c2f36; }")
        root_layout.addWidget(self.nav_list)

        content_column = QtWidgets.QVBoxLayout()
        content_column.setSpacing(8)
        root_layout.addLayout(content_column)

        self.header_bar = self._build_header_bar()
        content_column.addWidget(self.header_bar)

        self.content_stack = QtWidgets.QStackedWidget()
        content_column.addWidget(self.content_stack)

        pages: list[tuple[str, QtWidgets.QWidget]] = [
            ("Dashboard", self._build_dashboard()),
            ("Alerts", self._build_alerts()),
            ("Cases", self._build_cases()),
            ("Customers", self._build_customers()),
            ("KYC Risk", self._build_kyc()),
            ("Evidence Locker", self._build_evidence()),
            ("Actor Insights", self._build_actor()),
            ("Graph View", self._build_network()),
            ("Timeline", self._build_timeline()),
            ("Audit", self._build_security()),
            ("Alert Clusters", self._build_clusters()),
            ("Compare Cases", self._build_compare()),
            ("Settings", self._build_settings()),
        ]

        for title, widget in pages:
            self.nav_list.addItem(title)
            self.content_stack.addWidget(widget)

        self.nav_list.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.nav_list.setCurrentRow(0)

        self._activity_timer = QtCore.QTimer(self)
        self._activity_timer.timeout.connect(self._check_session_timeout)
        self._activity_timer.start(30_000)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_all)
        self._refresh_timer.start(5_000)

        self.installEventFilter(self)

    def _build_header_bar(self) -> QtWidgets.QWidget:
        bar = SectionCard()
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        title = QtWidgets.QLabel("FMR TaskForce – Investigator Workspace")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        layout.addWidget(title)

        layout.addStretch(1)

        secure_label = "SECURE MODE" if self.settings and self.settings.secure_mode else "STANDARD MODE"
        secure_state = "success" if self.settings and self.settings.secure_mode else "warning"
        self.secure_pill = create_header_pill(secure_label, secure_state)
        layout.addWidget(self.secure_pill)

        self.role_badge = create_header_pill(self.role or "ANALYST", "info")
        layout.addWidget(self.role_badge)

        if self.tamper_warnings:
            warning_pill = create_header_pill("TAMPER WARNINGS", "alert")
            warning_pill.setToolTip("\n".join(self.tamper_warnings))
            layout.addWidget(warning_pill)

        user_label = QtWidgets.QLabel(f"Signed in as {self.username}")
        layout.addWidget(user_label)
        return bar

    # region UI builders
    def _build_dashboard(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.kpi_alerts = QtWidgets.QLabel("Alerts: 0")
        self.kpi_cases = QtWidgets.QLabel("Open Cases: 0")
        self.kpi_high = QtWidgets.QLabel("High Alerts (24h): 0")
        for lbl in (self.kpi_alerts, self.kpi_cases, self.kpi_high):
            lbl.setStyleSheet("font-size:16px; font-weight:bold;")
        layout.addWidget(self.kpi_alerts)
        layout.addWidget(self.kpi_cases)
        layout.addWidget(self.kpi_high)
        layout.addStretch(1)
        return page

    def _build_alerts(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
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
        return page

    def _build_cases(self) -> QtWidgets.QWidget:
        page = SectionCard()
        outer = QtWidgets.QVBoxLayout(page)

        controls = QtWidgets.QHBoxLayout()
        self.case_refresh_btn = QtWidgets.QPushButton("Refresh")
        self.case_close_btn = QtWidgets.QPushButton("Close Case")
        self.case_timeline_btn = QtWidgets.QPushButton("Open Timeline")
        self.case_export_btn = QtWidgets.QPushButton("Forensic Export")
        controls.addWidget(self.case_refresh_btn)
        controls.addWidget(self.case_close_btn)
        controls.addWidget(self.case_timeline_btn)
        controls.addWidget(self.case_export_btn)
        controls.addStretch(1)
        outer.addLayout(controls)

        splitter = QtWidgets.QSplitter()
        splitter.setHandleWidth(4)

        left_panel = SectionCard()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        self.case_table = QtWidgets.QTableWidget(0, 5)
        self.case_table.setHorizontalHeaderLabels(["Case ID", "Status", "Priority", "Created", "Updated"])
        self.case_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(QtWidgets.QLabel("Cases"))
        left_layout.addWidget(self.case_table)

        self.case_timeline_table = QtWidgets.QTableWidget(0, 3)
        self.case_timeline_table.setHorizontalHeaderLabels(["Timestamp", "Type", "Summary"])
        self.case_timeline_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(QtWidgets.QLabel("Case Timeline"))
        left_layout.addWidget(self.case_timeline_table)

        splitter.addWidget(left_panel)

        right_panel = SectionCard()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        header_row = QtWidgets.QHBoxLayout()
        self.case_title = QtWidgets.QLabel("Select a case")
        self.case_status_pill = create_pill("Unknown", "neutral")
        header_row.addWidget(self.case_title)
        header_row.addStretch(1)
        header_row.addWidget(self.case_status_pill)
        right_layout.addLayout(header_row)

        self.case_alerts_table = QtWidgets.QTableWidget(0, 4)
        self.case_alerts_table.setHorizontalHeaderLabels(["Alert", "Score", "Level", "Domain"])
        self.case_alerts_table.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(QtWidgets.QLabel("Related Alerts"))
        right_layout.addWidget(self.case_alerts_table)

        self.case_notes = QtWidgets.QTextEdit()
        self.case_notes.setPlaceholderText("Add note (ENTER to save)")
        self.case_notes.setMaximumHeight(120)
        right_layout.addWidget(QtWidgets.QLabel("Case Narrative & Notes"))
        right_layout.addWidget(self.case_notes)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter)

        self.case_refresh_btn.clicked.connect(self._load_cases)
        self.case_close_btn.clicked.connect(self._close_selected_case)
        self.case_timeline_btn.clicked.connect(self._open_timeline)
        self.case_export_btn.clicked.connect(self._export_case)
        self.case_notes.installEventFilter(self)
        self.case_table.itemSelectionChanged.connect(self._load_case_details)

        return page

    def _build_timeline(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
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
        self.timeline_refresh.clicked.connect(self._load_timeline_tab)
        return page

    def _build_customers(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.customer_table = QtWidgets.QTableWidget(0, 4)
        self.customer_table.setHorizontalHeaderLabels(["Customer", "Country", "PEP", "Annual Income"])
        self.customer_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.customer_table)
        self.customer_table.itemSelectionChanged.connect(self._load_selected_customer_kyc)
        return page

    def _build_kyc(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.kyc_summary = QtWidgets.QLabel("Select a customer to view KYC risk.")
        self.kyc_table = QtWidgets.QTableWidget(0, 3)
        self.kyc_table.setHorizontalHeaderLabels(["Dimension", "Score", "Rationale"])
        self.kyc_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.kyc_summary)
        layout.addWidget(self.kyc_table)
        return page

    def _build_evidence(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
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
        self.evidence_add_btn.clicked.connect(self._add_evidence)
        self.evidence_seal_btn.clicked.connect(self._seal_case)
        return page

    def _build_compare(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
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
        self.compare_btn.clicked.connect(self._compare_cases)
        self.copy_compare_btn.clicked.connect(self._copy_compare)
        return page

    def _build_clusters(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.cluster_table = QtWidgets.QTableWidget(0, 4)
        self.cluster_table.setHorizontalHeaderLabels(["Domain", "Risk", "Count", "Latest"])
        self.cluster_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.cluster_table)
        return page

    def _build_actor(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.actor_table = QtWidgets.QTableWidget(0, 4)
        self.actor_table.setHorizontalHeaderLabels(["Customer", "Alerts", "Cases", "Baseline Avg"])
        self.actor_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.actor_table)
        return page

    def _build_network(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.network_view = NetworkView(self.db)
        refresh_btn = QtWidgets.QPushButton("Refresh Graph")
        refresh_btn.clicked.connect(self.network_view.refresh)
        layout.addWidget(refresh_btn)
        layout.addWidget(self.network_view)
        return page

    def _build_security(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.audit_table = QtWidgets.QTableWidget(0, 4)
        self.audit_table.setHorizontalHeaderLabels(["Timestamp", "User", "Action", "Target"])
        self.audit_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.audit_table)
        return page

    def _build_settings(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QFormLayout(page)
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
        return page

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
                "",  # pill placeholder
                row["domain"],
                row["case_id"] or "",
            ]
            for col, value in enumerate(values):
                if col == 3:
                    self.alert_table.setCellWidget(
                        idx, col, create_pill(row["risk_level"], self._risk_state(row["risk_level"]))
                    )
                else:
                    self.alert_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_cases(self):
        rows = self.db.list_cases()
        self.case_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            values = [row["id"], row["status"], row["priority"], row["created_at"], row["updated_at"]]
            for col, value in enumerate(values):
                pill_state = self._status_state(row["status"]) if col == 1 else None
                if pill_state:
                    self.case_table.setCellWidget(idx, col, create_pill(str(value), pill_state))
                else:
                    self.case_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))
        if rows:
            self.case_table.selectRow(0)
            self._load_case_details()

    def _load_customers(self):
        customers = make_customers()
        self.customer_table.setRowCount(len(customers))
        for idx, c in enumerate(customers):
            values = [c.name, c.country, "Yes" if c.is_pep else "No", f"{c.annual_declared_income:,.0f}"]
            for col, value in enumerate(values):
                self.customer_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))

    def _load_case_details(self) -> None:
        row = self.case_table.currentRow()
        if row < 0:
            return
        case_id_item = self.case_table.item(row, 0)
        status_widget = self.case_table.cellWidget(row, 1)
        if not case_id_item:
            return
        case_id = case_id_item.text()
        status_text = status_widget.text() if status_widget else self.case_table.item(row, 1).text()
        update_pill(self.case_status_pill, status_text, self._status_state(status_text))
        self.case_title.setText(f"Case {case_id}")

        events = self.db.case_timeline(case_id)
        self.case_timeline_table.setRowCount(len(events))
        for idx, event in enumerate(events):
            self.case_timeline_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(str(event.get("timestamp"))))
            self.case_timeline_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(str(event.get("type"))))
            self.case_timeline_table.setItem(idx, 2, QtWidgets.QTableWidgetItem(str(event.get("description"))))

        alerts = self.db.alerts_for_case(case_id)
        self.case_alerts_table.setRowCount(len(alerts))
        for idx, alert in enumerate(alerts):
            level = alert.get("risk_level") or "Unknown"
            self.case_alerts_table.setItem(idx, 0, QtWidgets.QTableWidgetItem(alert["id"]))
            self.case_alerts_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(f"{alert['score']:.1f}"))
            self.case_alerts_table.setCellWidget(idx, 2, create_pill(level, self._risk_state(level)))
            self.case_alerts_table.setItem(idx, 3, QtWidgets.QTableWidgetItem(alert.get("domain") or ""))

    def _risk_state(self, level: str) -> str:
        mapping = {"High": "alert", "Medium": "warning", "Low": "success"}
        return mapping.get(level, "neutral")

    def _status_state(self, status: str) -> str:
        mapping = {"OPEN": "warning", "IN_REVIEW": "info", "ESCALATED": "alert", "CLOSED": "success"}
        return mapping.get(status, "neutral")

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
                    update_pill(self.role_badge, self.role, "info")
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
