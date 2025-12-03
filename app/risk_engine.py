from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from .domain import EvaluatedIndicator, RiskDomain, RiskIndicator, Transaction


@dataclass
class RiskThresholds:
    low: float = 30.0
    medium: float = 60.0

    def level(self, score: float) -> str:
        if score < self.low:
            return "Low"
        if score < self.medium:
            return "Medium"
        return "High"


class RiskScoringEngine:
    def __init__(self, indicators: Iterable[RiskIndicator], thresholds: RiskThresholds | None = None) -> None:
        self.indicators = list(indicators)
        self.thresholds = thresholds or RiskThresholds()

    def score_transaction(self, tx: Transaction, history: List[Transaction] | None = None) -> Tuple[float, List[EvaluatedIndicator]]:
        evaluated: List[EvaluatedIndicator] = []
        history = history or []

        for indicator in self.indicators:
            hit = self._evaluate_indicator(indicator, tx, history)
            evaluated.append(EvaluatedIndicator(indicator=indicator, is_hit=hit))

        raw_score = sum(e.score_contribution for e in evaluated)
        normalized_score = 100.0 / (1.0 + math.exp(-0.1 * (raw_score - 10)))
        return normalized_score, evaluated

    def _evaluate_indicator(self, indicator: RiskIndicator, tx: Transaction, history: List[Transaction]) -> bool:
        evaluator = getattr(self, f"_rule_{indicator.code.lower()}", None)
        if evaluator:
            return evaluator(tx, history)
        return False

    def _rule_aml_high_risk_country(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.counterparty_country.upper() in {"IR", "KP", "AF", "CU", "SY"}

    def _rule_aml_structuring(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(minutes=30)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.is_credit == tx.is_credit]
        high_frequency = len(relevant) >= 5
        under_threshold = tx.amount < 9500
        return high_frequency and under_threshold

    def _rule_fraud_unusual_device_channel(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.channel.lower() in {"unknown_device", "tor", "anonymous_proxy"}

    def _rule_tf_conflict_region(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.counterparty_country.upper() in {"RU", "UA", "IR", "SY"}

    def _rule_tax_low_tax_jurisdiction(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.counterparty_country.upper() in {"PA", "KY", "VG", "MT"}


def default_indicators() -> List[RiskIndicator]:
    return [
        RiskIndicator(
            code="AML_HIGH_RISK_COUNTRY",
            description="Gegenpartei in Hochrisiko- oder sanktioniertem Land",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=15.0,
        ),
        RiskIndicator(
            code="AML_STRUCTURING",
            description="Viele kleine Transaktionen im 30-Minuten-Fenster",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=20.0,
        ),
        RiskIndicator(
            code="FRAUD_UNUSUAL_DEVICE_CHANNEL",
            description="Ungewohntes oder anonymes Gerät/Kanal",
            domain=RiskDomain.FRAUD,
            weight=10.0,
        ),
        RiskIndicator(
            code="TF_CONFLICT_REGION",
            description="Zahlung in Konflikt-/TF-Risikoregion",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=12.5,
        ),
        RiskIndicator(
            code="TAX_LOW_TAX_JURISDICTION",
            description="Zahlung in niedrigbesteuerndes Offshore-Territorium",
            domain=RiskDomain.TAX_EVASION,
            weight=8.0,
        ),
    ]
