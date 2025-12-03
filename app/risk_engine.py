from __future__ import annotations

import math

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from .domain import Account, Customer, EvaluatedIndicator, RiskDomain, RiskIndicator, Transaction


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
    def __init__(
        self,
        indicators: Iterable[RiskIndicator],
        thresholds: RiskThresholds | None = None,
        customers: Dict[str, Customer] | None = None,
        accounts: Dict[str, Account] | None = None,
    ) -> None:
        self.indicators = list(indicators)
        self.thresholds = thresholds or RiskThresholds()
        self.customers = customers or {}
        self.accounts = accounts or {}

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

    def _rule_aml_high_risk_sector(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.merchant_category in {"crypto", "luxury"}

    def _rule_aml_pep_high_value(self, tx: Transaction, _: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        return bool(customer and customer.is_pep and tx.amount >= 5000)

    def _rule_aml_structuring(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(minutes=30)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.is_credit == tx.is_credit]
        high_frequency = len(relevant) >= 5
        under_threshold = tx.amount < 9500
        return high_frequency and under_threshold

    def _rule_aml_amount_vs_income(self, tx: Transaction, history: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        if not customer:
            return False
        rolling_window = datetime.utcnow() - timedelta(hours=4)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= rolling_window]
        total_flow = sum(h.amount for h in relevant)
        return total_flow > customer.annual_declared_income / 6

    def _rule_aml_repeated_offshore(self, tx: Transaction, history: List[Transaction]) -> bool:
        offshore = {"PA", "KY", "VG", "MT"}
        window_start = datetime.utcnow() - timedelta(hours=1)
        relevant = [
            h
            for h in history
            if h.account_id == tx.account_id
            and h.counterparty_country.upper() in offshore
            and h.timestamp >= window_start
        ]
        return tx.counterparty_country.upper() in offshore and len(relevant) >= 2 and tx.amount >= 5000

    def _rule_fraud_unusual_device_channel(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.channel.lower() in {"unknown_device", "tor", "anonymous_proxy"}

    def _rule_fraud_velocity_spending(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(minutes=10)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start]
        return len(relevant) >= 4 and sum(h.amount for h in relevant) > 20000

    def _rule_fraud_device_channel_mix(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(hours=2)
        recent = [h.channel for h in history if h.account_id == tx.account_id and h.timestamp >= window_start]
        return len(set(recent + [tx.channel])) >= 3

    def _rule_tf_conflict_region(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.counterparty_country.upper() in {"RU", "UA", "IR", "SY"}

    def _rule_tf_ngo_conflict_donation(self, tx: Transaction, _: List[Transaction]) -> bool:
        return "donation" in (tx.purpose or "").lower() and tx.counterparty_country.upper() in {"SY", "IR", "AF", "UA"}

    def _rule_tax_low_tax_jurisdiction(self, tx: Transaction, _: List[Transaction]) -> bool:
        return tx.counterparty_country.upper() in {"PA", "KY", "VG", "MT"}

    def _rule_tax_income_mismatch(self, tx: Transaction, history: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        if not customer:
            return False
        last_24h = datetime.utcnow() - timedelta(hours=24)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= last_24h]
        rolling = sum(h.amount for h in relevant)
        return rolling > (customer.annual_declared_income / 12) * 1.5


def default_indicators() -> List[RiskIndicator]:
    return [
        RiskIndicator(
            code="AML_HIGH_RISK_COUNTRY",
            description="Gegenpartei in Hochrisiko- oder sanktioniertem Land",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=15.0,
        ),
        RiskIndicator(
            code="AML_HIGH_RISK_SECTOR",
            description="Transaktion in Hochrisiko-Branche (z.B. Crypto, Luxus)",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=9.0,
        ),
        RiskIndicator(
            code="AML_PEP_HIGH_VALUE",
            description="PEP-Kunde mit hoher Transaktion",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=18.0,
        ),
        RiskIndicator(
            code="AML_STRUCTURING",
            description="Viele kleine Transaktionen im 30-Minuten-Fenster",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=20.0,
        ),
        RiskIndicator(
            code="AML_AMOUNT_VS_INCOME",
            description="Transaktionsvolumen überrollt Einkommen",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=16.0,
        ),
        RiskIndicator(
            code="AML_REPEATED_OFFSHORE",
            description="Mehrere Offshore-Zahlungen in kurzer Zeit",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=12.0,
        ),
        RiskIndicator(
            code="FRAUD_UNUSUAL_DEVICE_CHANNEL",
            description="Ungewohntes oder anonymes Gerät/Kanal",
            domain=RiskDomain.FRAUD,
            weight=10.0,
        ),
        RiskIndicator(
            code="FRAUD_VELOCITY_SPENDING",
            description="Hohe Frequenz/Volumen in kurzer Zeit",
            domain=RiskDomain.FRAUD,
            weight=14.0,
        ),
        RiskIndicator(
            code="FRAUD_DEVICE_CHANNEL_MIX",
            description="Viele unterschiedliche Geräte/Kanäle in kurzer Zeit",
            domain=RiskDomain.FRAUD,
            weight=9.5,
        ),
        RiskIndicator(
            code="TF_CONFLICT_REGION",
            description="Zahlung in Konflikt-/TF-Risikoregion",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=12.5,
        ),
        RiskIndicator(
            code="TF_NGO_CONFLICT_DONATION",
            description="NGO-Spende in Konflikt- oder TF-Risikoregion",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=13.5,
        ),
        RiskIndicator(
            code="TAX_LOW_TAX_JURISDICTION",
            description="Zahlung in niedrigbesteuerndes Offshore-Territorium",
            domain=RiskDomain.TAX_EVASION,
            weight=8.0,
        ),
        RiskIndicator(
            code="TAX_INCOME_MISMATCH",
            description="Rollierender Cashflow übersteigt Einkommen signifikant",
            domain=RiskDomain.TAX_EVASION,
            weight=13.0,
        ),
    ]
