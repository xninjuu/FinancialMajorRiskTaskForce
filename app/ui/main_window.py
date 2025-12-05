from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.config_loader import safe_load_indicators, safe_load_thresholds, resolve_indicator_path, resolve_threshold_path
from app.config.settings import AppSettings
from app.core.baseline_engine import BaselineEngine
from app.core.entity_resolution import deduplicate
from app.core.event_correlation import CorrelationEngine
from app.core.export_bridge import export_case_json
from app.core.exporter import export_case_bundle
from app.core.kyc_risk import evaluate_customer
from app.core.sealed_case import seal_case, verify_seal
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
    DENSITY_STYLES,
    SectionCard,
    apply_table_density,
    apply_theme,
    create_header_pill,
    create_pill,
    create_section_header,
    rich_cell,
    update_pill,
)
from app.ui.login_dialog import LoginDialog
from app.runtime_paths import resolve_runtime_file


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
        self.base_font = self.font()
        self.theme = self._load_pref("ui.theme", "dark")
        self.table_density = self._load_pref("ui.table_density", "Comfortable")
        self.font_scale = int(self._load_pref("ui.font_scale", "100"))

        self.setWindowTitle("FMR TaskForce Codex - Desktop")
        self.resize(1200, 800)

        apply_theme(self, self.theme)
        self._apply_font_scale()

        self.container = QtWidgets.QWidget()
        self.setCentralWidget(self.container)
        root_layout = QtWidgets.QHBoxLayout(self.container)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.nav_list = QtWidgets.QListWidget()
        self.nav_list.setFixedWidth(220)
        self.nav_list.setObjectName("navList")
        self.nav_list.setStyleSheet(
            "QListWidget#navList { background:#1b1d23; color:#e5e7eb; border-right:1px solid #2c2f36; }"
        )
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

        self._apply_table_density_all()
        completer = QtWidgets.QCompleter(self.db.list_evidence_tags())
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.evidence_tags.setCompleter(completer)
        self._build_status_bar()
        self._register_shortcuts()

        self.nav_list.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.nav_list.setCurrentRow(0)

        self._activity_timer = QtCore.QTimer(self)
        self._activity_timer.timeout.connect(self._check_session_timeout)
        self._activity_timer.start(30_000)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_all)
        self._refresh_timer.start(5_000)

        self.installEventFilter(self)

    def _build_status_bar(self) -> None:
        bar = QtWidgets.QStatusBar()
        self.setStatusBar(bar)
        secure_state = "Secure" if self.settings and self.settings.secure_mode else "Standard"
        self.status_secure = QtWidgets.QLabel(f"Mode: {secure_state}")
        self.status_role = QtWidgets.QLabel(f"Role: {self.role}")
        expected = self.settings.expected_exe_hash if self.settings else None
        self.status_hash = QtWidgets.QLabel(f"Hash: {expected or 'n/a'}")
        bar.addPermanentWidget(self.status_secure)
        bar.addPermanentWidget(self.status_role)
        bar.addPermanentWidget(self.status_hash)

    def _apply_font_scale(self) -> None:
        font = QtGui.QFont(self.base_font)
        font.setPointSizeF(font.pointSizeF() * (self.font_scale / 100))
        self.setFont(font)

    def _apply_table_density_all(self) -> None:
        tables = [
            getattr(self, name)
            for name in [
                "alert_table",
                "case_table",
                "case_timeline_table",
                "case_alerts_table",
                "customer_table",
                "kyc_table",
                "evidence_table",
                "cluster_table",
                "actor_table",
                "audit_table",
                "timeline_table",
            ]
            if hasattr(self, name)
        ]
        for table in tables:
            apply_table_density(table, self.table_density)

    def _change_theme(self, theme: str) -> None:
        self.theme = theme
        self._save_pref("ui.theme", theme)
        apply_theme(self, theme)

    def _change_font_scale(self, value: int) -> None:
        self.font_scale = value
        self._save_pref("ui.font_scale", str(value))
        self._apply_font_scale()

    def _change_density(self, mode: str) -> None:
        self.table_density = mode
        self._save_pref("ui.table_density", mode)
        self._apply_table_density_all()

    def _save_pref(self, key: str, value: str) -> None:
        try:
            self.db.set_user_pref(self.username, key, value)
        except Exception:
            return

    def _load_pref(self, key: str, default: str) -> str:
        try:
            return self.db.get_user_pref(self.username, key, default) or default
        except Exception:
            return default

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
        layout.addWidget(create_section_header("Alert Triage", accent="#21d4fd"))
        controls = QtWidgets.QHBoxLayout()
        self.alert_refresh_btn = QtWidgets.QPushButton("Refresh")
        self.alert_triage_toggle = QtWidgets.QCheckBox("Triage Mode")
        self.alert_density_combo = QtWidgets.QComboBox()
        self.alert_density_combo.addItems(DENSITY_STYLES.keys())
        self.alert_density_combo.setCurrentText(self.table_density)
        controls.addWidget(self.alert_refresh_btn)
        controls.addWidget(self.alert_triage_toggle)
        controls.addWidget(QtWidgets.QLabel("Density"))
        controls.addWidget(self.alert_density_combo)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.alert_table = QtWidgets.QTableWidget(0, 6)
        self.alert_table.setHorizontalHeaderLabels(["Created", "Account", "Score", "Level", "Domain", "Case"])
        self.alert_table.horizontalHeader().setStretchLastSection(True)
        self.alert_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.alert_table)

        self.alert_refresh_btn.clicked.connect(self._load_alerts)
        self.alert_density_combo.currentTextChanged.connect(self._change_density)
        self.alert_triage_toggle.toggled.connect(self._toggle_triage_mode)
        return page

    def _build_cases(self) -> QtWidgets.QWidget:
        page = SectionCard()
        outer = QtWidgets.QVBoxLayout(page)
        outer.addWidget(create_section_header("Case Workspace", accent="#21d4fd"))

        controls = QtWidgets.QHBoxLayout()
        self.case_refresh_btn = QtWidgets.QPushButton("Refresh")
        self.case_close_btn = QtWidgets.QPushButton("Close Case")
        self.case_timeline_btn = QtWidgets.QPushButton("Open Timeline")
        self.case_export_btn = QtWidgets.QPushButton("Forensic Export")
        self.case_panel_toggle = QtWidgets.QPushButton("Toggle Details")
        self.case_redacted = QtWidgets.QCheckBox("Redacted")
        self.case_watermark = QtWidgets.QLineEdit()
        self.case_watermark.setPlaceholderText("Watermark")
        controls.addWidget(self.case_refresh_btn)
        controls.addWidget(self.case_close_btn)
        controls.addWidget(self.case_timeline_btn)
        controls.addWidget(self.case_export_btn)
        controls.addWidget(self.case_panel_toggle)
        controls.addWidget(self.case_redacted)
        controls.addWidget(self.case_watermark)
        controls.addStretch(1)
        outer.addLayout(controls)

        splitter = QtWidgets.QSplitter()
        splitter.setHandleWidth(6)
        self.case_splitter = splitter

        left_panel = SectionCard()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.addWidget(create_section_header("Cases", accent="#8ab4f8"))
        self.case_table = QtWidgets.QTableWidget(0, 5)
        self.case_table.setHorizontalHeaderLabels(["Case ID", "Status", "Priority", "Created", "Updated"])
        self.case_table.horizontalHeader().setStretchLastSection(True)
        self.case_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        left_layout.addWidget(self.case_table)

        left_layout.addWidget(create_section_header("Case Timeline", accent="#f7a400"))
        self.case_timeline_table = QtWidgets.QTableWidget(0, 3)
        self.case_timeline_table.setHorizontalHeaderLabels(["Timestamp", "Type", "Summary"])
        self.case_timeline_table.horizontalHeader().setStretchLastSection(True)
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

        right_layout.addWidget(create_section_header("Related Alerts", accent="#ef4444"))
        self.case_alerts_table = QtWidgets.QTableWidget(0, 4)
        self.case_alerts_table.setHorizontalHeaderLabels(["Alert", "Score", "Level", "Domain"])
        self.case_alerts_table.horizontalHeader().setStretchLastSection(True)
        self.case_alerts_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        right_layout.addWidget(self.case_alerts_table)

        right_layout.addWidget(create_section_header("Case Narrative & Notes", accent="#8ab4f8"))
        self.case_notes = QtWidgets.QTextEdit()
        self.case_notes.setPlaceholderText("Add note (ENTER to save)")
        self.case_notes.setMaximumHeight(140)
        right_layout.addWidget(self.case_notes)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter)

        self.case_refresh_btn.clicked.connect(self._load_cases)
        self.case_close_btn.clicked.connect(self._close_selected_case)
        self.case_timeline_btn.clicked.connect(self._open_timeline)
        self.case_export_btn.clicked.connect(self._export_case)
        self.case_panel_toggle.clicked.connect(self._toggle_case_detail_panel)
        self.case_notes.installEventFilter(self)
        self.case_table.itemSelectionChanged.connect(self._load_case_details)
        splitter.splitterMoved.connect(self._persist_case_split)
        self._restore_case_split()

        return page

    def _build_timeline(self) -> QtWidgets.QWidget:
        page = SectionCard()
        layout = QtWidgets.QVBoxLayout(page)
        self.timeline_case_input = QtWidgets.QLineEdit()
        self.timeline_case_input.setPlaceholderText("Case ID")
        self.timeline_refresh = QtWidgets.QPushButton("Load Timeline")
        self.timeline_zoom = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.timeline_zoom.setRange(10, 200)
        self.timeline_zoom.setValue(50)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.timeline_case_input)
        top.addWidget(self.timeline_refresh)
        top.addWidget(QtWidgets.QLabel("Events"))
        top.addWidget(self.timeline_zoom)
        layout.addLayout(top)
        self.timeline_table = QtWidgets.QTableWidget(0, 3)
        self.timeline_table.setHorizontalHeaderLabels(["Timestamp", "Type", "Description"])
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.timeline_table)
        self.timeline_refresh.clicked.connect(self._load_timeline_tab)
        self.timeline_zoom.valueChanged.connect(self._load_timeline_tab)
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
        self.evidence_type = QtWidgets.QComboBox()
        self.evidence_type.addItems(["document", "screenshot", "note", "export"])
        self.evidence_tags = QtWidgets.QLineEdit()
        self.evidence_tags.setPlaceholderText("tags (comma separated)")
        self.evidence_filter_type = QtWidgets.QComboBox()
        self.evidence_filter_type.addItems(["any", "document", "screenshot", "note", "export"])
        self.evidence_filter_importance = QtWidgets.QComboBox()
        self.evidence_filter_importance.addItems(["any", "low", "medium", "high"])
        self.evidence_importance = QtWidgets.QComboBox()
        self.evidence_importance.addItems(["low", "medium", "high"])
        self.evidence_add_btn = QtWidgets.QPushButton("Add Evidence")
        self.evidence_seal_btn = QtWidgets.QPushButton("Seal Case")
        self.evidence_verify_btn = QtWidgets.QPushButton("Verify Seal")
        self.evidence_seal_reason = QtWidgets.QComboBox()
        self.evidence_seal_reason.addItems(["closure", "legal_hold", "regulatory_export"])
        controls.addWidget(self.evidence_case_input)
        controls.addWidget(self.evidence_type)
        controls.addWidget(self.evidence_importance)
        controls.addWidget(self.evidence_tags)
        controls.addWidget(self.evidence_filter_type)
        controls.addWidget(self.evidence_filter_importance)
        controls.addWidget(self.evidence_seal_reason)
        controls.addWidget(self.evidence_add_btn)
        controls.addWidget(self.evidence_seal_btn)
        controls.addWidget(self.evidence_verify_btn)
        layout.addLayout(controls)
        self.evidence_table = QtWidgets.QTableWidget(0, 10)
        self.evidence_table.setHorizontalHeaderLabels(
            [
                "File",
                "Hash",
                "Added By",
                "Sealed",
                "Created",
                "Type",
                "Tags",
                "Importance",
                "Preview",
                "OCR",
            ]
        )
        self.evidence_table.horizontalHeader().setStretchLastSection(True)
        self.seal_metadata_label = QtWidgets.QLabel("Seal metadata: n/a")
        layout.addWidget(self.evidence_table)
        layout.addWidget(self.seal_metadata_label)
        self.evidence_add_btn.clicked.connect(self._add_evidence)
        self.evidence_seal_btn.clicked.connect(self._seal_case)
        self.evidence_verify_btn.clicked.connect(self._verify_seal)
        self.evidence_filter_type.currentTextChanged.connect(self._load_evidence_table)
        self.evidence_filter_importance.currentTextChanged.connect(self._load_evidence_table)
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
        controls = QtWidgets.QHBoxLayout()
        self.network_view = NetworkView(self.db)
        self.network_focus = QtWidgets.QLineEdit()
        self.network_focus.setPlaceholderText("Account ID or country to focus")
        focus_btn = QtWidgets.QPushButton("Focus")
        focus_btn.clicked.connect(lambda: self.network_view.set_focus(self.network_focus.text().strip()))
        clear_btn = QtWidgets.QPushButton("Clear Focus")
        clear_btn.clicked.connect(lambda: self.network_view.set_focus(None))
        export_png_btn = QtWidgets.QPushButton("Export PNG")
        export_svg_btn = QtWidgets.QPushButton("Export SVG")
        export_png_btn.clicked.connect(self._export_graph_png)
        export_svg_btn.clicked.connect(self._export_graph_svg)
        controls.addWidget(self.network_focus)
        controls.addWidget(focus_btn)
        controls.addWidget(clear_btn)
        controls.addWidget(export_png_btn)
        controls.addWidget(export_svg_btn)
        layout.addLayout(controls)
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
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.theme)
        layout.addRow("Theme", self.theme_combo)
        self.font_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.font_slider.setRange(80, 120)
        self.font_slider.setValue(self.font_scale)
        layout.addRow("Font scale (%)", self.font_slider)
        self.density_combo = QtWidgets.QComboBox()
        self.density_combo.addItems(DENSITY_STYLES.keys())
        self.density_combo.setCurrentText(self.table_density)
        layout.addRow("Table density", self.density_combo)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        self.font_slider.valueChanged.connect(self._change_font_scale)
        self.density_combo.currentTextChanged.connect(self._change_density)
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
            risk_color = self._risk_color(row["risk_level"])
            cells = [
                rich_cell(row["created_at"], accent_color=risk_color),
                rich_cell(row["transaction_id"], accent_color=None),
                rich_cell(f"{row['score']:.1f}", accent_color=risk_color),
                create_pill(row["risk_level"], self._risk_state(row["risk_level"])),
                rich_cell(row["domain"], accent_color=None, tags=[row["domain"]]),
                rich_cell(row["case_id"] or "", accent_color=None),
            ]
            for col, value in enumerate(cells):
                if isinstance(value, QtWidgets.QWidget):
                    self.alert_table.setCellWidget(idx, col, value)
                else:
                    self.alert_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))
        apply_table_density(self.alert_table, self.table_density)

    def _toggle_triage_mode(self, checked: bool) -> None:
        mode = "Compact" if checked else self.table_density
        self.alert_table.setAlternatingRowColors(checked)
        apply_table_density(self.alert_table, mode)

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
                    accent = self._risk_color("High" if row["status"] == "ESCALATED" else "Medium") if col == 0 else None
                    self.case_table.setCellWidget(idx, col, rich_cell(str(value), accent_color=accent))
        if rows:
            self.case_table.selectRow(0)
            self._load_case_details()
        apply_table_density(self.case_table, self.table_density)

    def _toggle_case_detail_panel(self) -> None:
        if not hasattr(self, "case_splitter"):
            return
        detail = self.case_splitter.widget(1)
        detail.setVisible(not detail.isVisible())
        self._save_pref("ui.case_detail_visible", "1" if detail.isVisible() else "0")
        if detail.isVisible():
            self._restore_case_split()

    def _persist_case_split(self) -> None:
        if not hasattr(self, "case_splitter"):
            return
        sizes = self.case_splitter.sizes()
        self._save_pref("ui.case_split_sizes", ",".join(str(s) for s in sizes))

    def _restore_case_split(self) -> None:
        pref = self._load_pref("ui.case_split_sizes", "")
        if pref and hasattr(self, "case_splitter"):
            try:
                sizes = [int(val) for val in pref.split(",") if val]
                if sizes:
                    self.case_splitter.setSizes(sizes)
            except Exception:
                pass
        visible = self._load_pref("ui.case_detail_visible", "1") == "1"
        self.case_splitter.widget(1).setVisible(visible)

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

    def _risk_color(self, level: str) -> str:
        return {"High": "#ef4444", "Medium": "#f7a400", "Low": "#10b981"}.get(level, "#4b5563")

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
        seal_record = self.db.sealed_case(case_id)
        seal_dict = dict(seal_record) if seal_record else None
        if seal_dict:
            self.seal_metadata_label.setText(
                f"Seal: {seal_dict.get('sealed_by')} @ {seal_dict.get('sealed_at')} | reason {seal_dict.get('seal_reason') or 'n/a'} | merkle {seal_dict.get('merkle_root')}"
            )
        else:
            self.seal_metadata_label.setText("Seal metadata: none")
        rows = [dict(r) for r in list_evidence(self.db, case_id)]
        filtered: list[dict] = []
        type_filter = self.evidence_filter_type.currentText()
        importance_filter = self.evidence_filter_importance.currentText()
        for row in rows:
            if type_filter != "any" and row.get("evidence_type") != type_filter:
                continue
            if importance_filter != "any" and row.get("importance") != importance_filter:
                continue
            filtered.append(row)
        self.evidence_table.setRowCount(len(filtered))
        for idx, row in enumerate(filtered):
            values = [
                row["filename"],
                row["hash"],
                row["added_by"],
                "Yes" if row["sealed"] else "No",
                row["created_at"],
                row.get("evidence_type"),
                row.get("tags"),
                row.get("importance"),
            ]
            for col, value in enumerate(values):
                self.evidence_table.setItem(idx, col, QtWidgets.QTableWidgetItem(str(value)))
            preview_col = 8
            ocr_col = 9
            preview_path = row.get("preview_path")
            if preview_path:
                pixmap = QtGui.QPixmap(str(preview_path))
                if not pixmap.isNull():
                    label = QtWidgets.QLabel()
                    label.setPixmap(pixmap.scaled(96, 96, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
                    self.evidence_table.setCellWidget(idx, preview_col, label)
                else:
                    self.evidence_table.setItem(idx, preview_col, QtWidgets.QTableWidgetItem("-"))
            else:
                self.evidence_table.setItem(idx, preview_col, QtWidgets.QTableWidgetItem("-"))
            ocr_value = "yes" if (row.get("ocr_text")) else "no"
            self.evidence_table.setItem(idx, ocr_col, QtWidgets.QTableWidgetItem(ocr_value))

    def _load_timeline_tab(self):
        case_id = sanitize_text(self.timeline_case_input.text(), max_length=128)
        if not case_id:
            return
        limit = max(5, int(self.timeline_zoom.value()))
        events = self.db.case_timeline(case_id, limit=limit)
        self.timeline_table.setRowCount(len(events))
        for idx, event in enumerate(events):
            accent = self._risk_color(event.get("risk_level") or "")
            self.timeline_table.setCellWidget(idx, 0, rich_cell(str(event.get("timestamp")), accent_color=accent))
            self.timeline_table.setItem(idx, 1, QtWidgets.QTableWidgetItem(str(event.get("type"))))
            self.timeline_table.setCellWidget(idx, 2, rich_cell(str(event.get("description")), accent_color=None))

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
            redacted = self.case_redacted.isChecked()
            watermark = sanitize_text(self.case_watermark.text(), max_length=64) or None
            path, hash_value = export_case_bundle(
                self.db,
                case_id,
                self.settings.exports_dir,
                redacted=redacted,
                watermark=watermark,
            )
            json_path = export_case_json(self.db, case_id, self.settings.exports_dir)
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                f"Case exported to {path}\nJSON: {json_path}\nSHA256: {hash_value}",
            )
            self.audit.log(self.username, AuditAction.SETTINGS_CHANGE.value, target=case_id, details="Forensic export")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))

    def _export_graph_png(self) -> None:
        target = resolve_runtime_file("graph_view.png")
        try:
            self.network_view.export_png(str(target))
            QtWidgets.QMessageBox.information(self, "Graph export", f"Graph saved to {target}")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Graph export", str(exc))

    def _export_graph_svg(self) -> None:
        target = resolve_runtime_file("graph_view.svg")
        try:
            self.network_view.export_svg(str(target))
            QtWidgets.QMessageBox.information(self, "Graph export", f"Graph saved to {target}")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Graph export", str(exc))

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
            tags = [t.strip() for t in self.evidence_tags.text().split(",") if t.strip()]
            filename, digest = add_evidence(
                self.db,
                case_id,
                Path(path),
                self.username,
                evidence_type=self.evidence_type.currentText(),
                tags=tags,
                importance=self.evidence_importance.currentText(),
            )
            QtWidgets.QMessageBox.information(self, "Evidence stored", f"{filename}\nSHA256: {digest}")
            self.audit.log(self.username, AuditAction.EVIDENCE_ADDED.value, target=case_id, details=filename)
            self._load_evidence_table()
            completer = QtWidgets.QCompleter(self.db.list_evidence_tags())
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.evidence_tags.setCompleter(completer)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Evidence", str(exc))

    def _seal_case(self):
        case_id = sanitize_text(self.evidence_case_input.text(), max_length=128)
        if not case_id:
            return
        try:
            _, merkle = seal_case(
                self.db,
                case_id,
                sealed_by=self.username,
                seal_reason=self.evidence_seal_reason.currentText(),
            )
            QtWidgets.QMessageBox.information(self, "Case sealed", f"Merkle root: {merkle}")
            self.audit.log(self.username, AuditAction.CASE_SEALED.value, target=case_id, details="sealed")
            self._load_evidence_table()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Seal", str(exc))

    def _verify_seal(self):
        case_id = sanitize_text(self.evidence_case_input.text(), max_length=128)
        if not case_id:
            return
        ok = verify_seal(self.db, case_id)
        message = "Seal intact" if ok else "Seal mismatch"
        QtWidgets.QMessageBox.information(self, "Verify seal", message)
        self.audit.log(self.username, AuditAction.CASE_SEALED.value, target=case_id, details=message)
        self._load_evidence_table()

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

    def _register_shortcuts(self) -> None:
        palette_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)
        palette_shortcut.activated.connect(self._open_command_palette)

    def _open_command_palette(self) -> None:
        commands = {
            "Open case by ID": self._prompt_open_case,
            "Lock session": self._lock_session,
            "Refresh alerts": self._load_alerts,
            "Run correlation": lambda: self.correlations.correlate([]),
        }
        item, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Command Palette",
            "Select action",
            list(commands.keys()),
            0,
            False,
        )
        if ok and item in commands:
            commands[item]()

    def _prompt_open_case(self) -> None:
        case_id, ok = QtWidgets.QInputDialog.getText(self, "Open case", "Case ID")
        if ok and case_id:
            self.evidence_case_input.setText(case_id)
            self.timeline_case_input.setText(case_id)
            self._load_case_details_by_id(case_id)

    def _load_case_details_by_id(self, case_id: str) -> None:
        for row in range(self.case_table.rowCount()):
            if self.case_table.item(row, 0).text() == case_id:
                self.case_table.setCurrentCell(row, 0)
                self._load_case_details()
                return


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
