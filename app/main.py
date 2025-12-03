from __future__ import annotations

import asyncio
import itertools
from datetime import datetime
from typing import Dict, List

from .case_management import CaseManagementService
from .domain import Alert, Transaction
from .ingestion import TransactionIngestionService, sample_accounts, sample_customers
from .news_service import NewsService, sample_news
from .risk_engine import RiskScoringEngine, RiskThresholds, default_indicators


class RealTimeOrchestrator:
    def __init__(self) -> None:
        self.customers = sample_customers()
        self.accounts = sample_accounts(self.customers)
        self.ingestion = TransactionIngestionService(self.customers, self.accounts)
        self.risk_engine = RiskScoringEngine(default_indicators(), thresholds=RiskThresholds())
        self.case_manager = CaseManagementService()
        self.news_service = NewsService(sample_news())
        self.recent_transactions: List[Transaction] = []
        self.alerts: Dict[str, Alert] = {}

    async def start(self) -> None:
        await asyncio.gather(
            self._run_transactions(),
            self._run_news_ticker(),
        )

    async def _run_transactions(self) -> None:
        async for tx in self.ingestion.stream_transactions(delay_seconds=1.0):
            self.recent_transactions.append(tx)
            self.recent_transactions = self.recent_transactions[-200:]
            score, evaluated = self.risk_engine.score_transaction(tx, history=self.recent_transactions)
            risk_level = self.risk_engine.thresholds.level(score)
            print(f"[TX] {tx.id} {tx.amount:.2f} {tx.currency} {tx.counterparty_country} via {tx.channel} -> Score {score:.1f} ({risk_level})")
            if risk_level == "High":
                alert = Alert(
                    id=f"alert-{len(self.alerts)+1}",
                    transaction=tx,
                    score=score,
                    evaluated_indicators=evaluated,
                    created_at=datetime.utcnow(),
                )
                self.alerts[alert.id] = alert
                case = self.case_manager.attach_alert(alert)
                print(f"  -> ALERT {alert.id} assigned to {case.id} ({len(case.alerts)} alerts)")
            elif risk_level == "Medium":
                print("  -> Flagged for review (Medium risk)")

            if len(self.alerts) % 5 == 0 and self.alerts:
                self._print_dashboard()

    async def _run_news_ticker(self) -> None:
        async for news in self.news_service.stream_news(delay_seconds=5.0):
            print(f"[NEWS] {news.title} ({news.source})")

    def _print_dashboard(self) -> None:
        open_cases = [c for c in self.case_manager.summary() if c.status != "Closed"]
        high_risk = len(self.alerts)
        print("\n==== Echtzeit-Dashboard ====")
        print(f"Alerts gesamt: {high_risk}")
        print(f"Offene Cases: {len(open_cases)}")
        print("Top-Axiome (Hits):")
        top_indicators = self._aggregate_indicator_hits()
        for code, count in top_indicators.items():
            print(f"- {code}: {count}")
        print("==========================\n")

    def _aggregate_indicator_hits(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for alert in self.alerts.values():
            for hit in alert.evaluated_indicators:
                if hit.is_hit:
                    counts[hit.indicator.code] = counts.get(hit.indicator.code, 0) + 1
        return counts


def main() -> None:
    orchestrator = RealTimeOrchestrator()
    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        print("Beende Echtzeit-Simulation…")


if __name__ == "__main__":
    main()
