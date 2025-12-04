from __future__ import annotations

import asyncio
import itertools
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from .auth import SecurityBootstrap
from .case_management import CaseManagementService
from .config_loader import (
    resolve_indicator_path,
    resolve_threshold_path,
    safe_load_indicators,
    safe_load_thresholds,
)
from .domain import Alert, CaseNote, CaseStatus, Transaction
from .ingestion import TransactionIngestionService, sample_accounts, sample_customers
from .news_service import NewsService, sample_news
from .persistence import PersistenceLayer
from .risk_engine import RiskScoringEngine, RiskThresholds, default_indicators
from .runtime_paths import resolve_runtime_file
from .web import DashboardServer


class RealTimeOrchestrator:
    def __init__(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        security = SecurityBootstrap()
        session = security.provision_internal_operator()
        self.session_manager = security.session_manager
        self.registry = security.registry
        self.audit = security.audit

        db_path = os.getenv("CODEX_DB_PATH")
        if not db_path:
            db_path = str(resolve_runtime_file("codex.db"))
        self.persistence = PersistenceLayer(db_path=db_path)

        self.customers = sample_customers()
        self.accounts = sample_accounts(self.customers)
        self.customer_index = {c.id: c for c in self.customers}
        self.account_index = {a.id: a for a in self.accounts}
        self.ingestion = TransactionIngestionService(self.customers, self.accounts)
        indicator_config = safe_load_indicators(
            path=resolve_indicator_path(),
            fallback=default_indicators(),
        )
        thresholds = safe_load_thresholds(
            path=resolve_threshold_path(),
            fallback=RiskThresholds(),
        )
        self.risk_engine = RiskScoringEngine(
            indicator_config,
            thresholds=thresholds,
            customers=self.customer_index,
            accounts=self.account_index,
        )
        self.case_manager = CaseManagementService(persistence=self.persistence)
        self.news_service = NewsService(sample_news())
        self.recent_transactions: List[Transaction] = []
        self.alerts: Dict[str, Alert] = {}
        self.total_processed = 0
        self.recent_scores: List[float] = []
        self.alert_history: List[Alert] = []
        self.medium_flags = 0
        self.session = session
        dashboard_port = int(os.getenv("CODEX_DASHBOARD_PORT", "8000"))
        dash_user = os.getenv("CODEX_DASHBOARD_USER", "codex_internal")
        dash_pass = os.getenv("CODEX_DASHBOARD_PASSWORD")
        dash_pass_hash = os.getenv(
            "CODEX_DASHBOARD_PASSWORD_HASH",
            "f0e6d40e24da418d26dc3a542354a32403f56ac3c86730c6815e4506c5d89e51",
        )
        if dash_pass:
            dash_pass_hash = None
        self.dashboard_server = DashboardServer(
            self.persistence,
            user=dash_user,
            password=dash_pass,
            password_hash=dash_pass_hash,
            port=dashboard_port,
        )

    async def start(self) -> None:
        self._guard_internal_access()
        self.dashboard_server.start()
        await asyncio.gather(
            self._run_transactions(),
            self._run_news_ticker(),
        )

    async def _run_transactions(self) -> None:
        async for tx in self.ingestion.stream_transactions(delay_seconds=1.0):
            self.session_manager.ensure_active_session()
            self.registry.require(self.session, "realtime_stream")
            self.persistence.record_transaction(tx)
            history = self.persistence.recent_transactions(tx.account_id, window=timedelta(hours=6))
            self.recent_transactions = (self.recent_transactions + [tx])[-200:]
            score, evaluated = self.risk_engine.score_transaction(tx, history=history)
            self.registry.require(self.session, "risk_engine")
            risk_level = self.risk_engine.thresholds.level(score)
            print(f"[TX] {tx.id} {tx.amount:.2f} {tx.currency} {tx.counterparty_country} via {tx.channel} -> Score {score:.1f} ({risk_level})")
            self.recent_scores.append(score)
            self.recent_scores = self.recent_scores[-200:]
            if risk_level == "High":
                alert = Alert(
                    id=f"alert-{len(self.alerts)+1}",
                    transaction=tx,
                    score=score,
                    evaluated_indicators=evaluated,
                    created_at=datetime.utcnow(),
                    priority="High" if risk_level == "High" else "Normal",
                )
                self.alerts[alert.id] = alert
                self.alert_history.append(alert)
                self.alert_history = self.alert_history[-10:]
                case = self.case_manager.attach_alert(alert)
                alert.case_id = case.id
                self.registry.require(self.session, "case_management")
                self.persistence.record_alert(alert, risk_level)
                print(f"  -> ALERT {alert.id} assigned to {case.id} ({len(case.alerts)} alerts)")
            elif risk_level == "Medium":
                print("  -> Flagged for review (Medium risk)")
                self.medium_flags += 1

            self.total_processed += 1

            if self.total_processed % 8 == 0:
                self._print_dashboard()

    async def _run_news_ticker(self) -> None:
        async for news in self.news_service.stream_news(delay_seconds=5.0):
            self.registry.require(self.session, "news_feed")
            print(f"[NEWS] {news.title} ({news.source})")

    def _print_dashboard(self) -> None:
        open_cases = [c for c in self.case_manager.summary() if c.status != "Closed"]
        high_risk = len(self.alerts)
        print("\n==== Echtzeit-Dashboard ====")
        print(f"Verarbeitete Transaktionen: {self.total_processed}")
        print(f"Alerts gesamt: {high_risk} | Flags (Medium): {self.medium_flags}")
        print(f"Offene Cases: {len(open_cases)}")
        print(
            "Access Policy: INTERNAL ONLY | angemeldet als "
            f"{self.session.user.email} ({self.session.user.role})"
        )
        print(
            f"Security: Session TTL active (expires in {self._session_seconds_remaining()}s); "
            f"Audit events: {len(self.audit.events)}"
        )
        self._print_case_statuses()
        self._print_score_window()
        self._print_domain_breakdown()
        self._print_recent_alerts()
        print("Top-Axiome (Hits):")
        top_indicators = self._aggregate_indicator_hits()
        for code, count in top_indicators.items():
            print(f"- {code}: {count}")
        print("==========================\n")

    def _guard_internal_access(self) -> None:
        self.session_manager.require_internal_access()
        print("[ACCESS] Internal-only runtime verified.")

    def _session_seconds_remaining(self) -> int:
        session = self.session_manager.ensure_active_session()
        expires_at = session.issued_at + timedelta(seconds=session.ttl_seconds)
        delta = expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def _aggregate_indicator_hits(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for alert in self.alerts.values():
            for hit in alert.evaluated_indicators:
                if hit.is_hit:
                    counts[hit.indicator.code] = counts.get(hit.indicator.code, 0) + 1
        return counts

    def _print_domain_breakdown(self) -> None:
        domain_counts: Dict[str, int] = {}
        for alert in self.alerts.values():
            for hit in alert.evaluated_indicators:
                if hit.is_hit:
                    domain = hit.indicator.domain.name
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if not domain_counts:
            print("Domain-Breakdown: (noch keine Treffer)")
            return
        print("Domain-Breakdown:")
        for domain, count in domain_counts.items():
            print(f"- {domain}: {count}")

    def _print_recent_alerts(self) -> None:
        if not self.alert_history:
            print("Letzte Alerts: (keine)")
            return
        print("Letzte Alerts (max 3):")
        for alert in self.alert_history[-3:]:
            hits = [h for h in alert.evaluated_indicators if h.is_hit]
            rationales = ", ".join(
                f"{hit.indicator.code} ({hit.explanation or 'Hit'})" for hit in hits[:2]
            )
            print(
                f"- {alert.id} Score {alert.score:.1f} [{alert.transaction.counterparty_country} -> {alert.transaction.channel}] {rationales}"
            )

    def _print_case_statuses(self) -> None:
        statuses: Dict[str, int] = {s.name: 0 for s in CaseStatus}
        for case in self.case_manager.summary():
            statuses[case.status.name] = statuses.get(case.status.name, 0) + 1
        print(
            "Case-Status: "
            + ", ".join([f"{status} {count}" for status, count in statuses.items() if count])
        )

    def _print_score_window(self) -> None:
        if not self.recent_scores:
            print("Scores: noch keine Daten")
            return
        latest = self.recent_scores[-1]
        avg = sum(self.recent_scores) / len(self.recent_scores)
        high_share = sum(1 for s in self.recent_scores if s >= self.risk_engine.thresholds.medium) / len(
            self.recent_scores
        )
        print(f"Score-Fenster (200 TX): aktuell {latest:.1f}, Mittel {avg:.1f}, High-Share {high_share:.0%}")


def main() -> None:
    orchestrator = RealTimeOrchestrator()
    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        print("Beende Echtzeit-Simulation…")
    except Exception as exc:  # pragma: no cover - safety for PyInstaller runtime
        print(f"Unerwarteter Fehler: {exc}")
    finally:
        if os.getenv("CODEX_HOLD_ON_EXIT", "1") != "0":
            try:
                input("Server gestoppt. ENTER zum Schließen…")
            except EOFError:
                pass


if __name__ == "__main__":
    main()
