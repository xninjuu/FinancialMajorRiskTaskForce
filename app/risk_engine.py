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
            hit, explanation = self._evaluate_indicator(indicator, tx, history)
            evaluated.append(EvaluatedIndicator(indicator=indicator, is_hit=hit, explanation=explanation))

        raw_score = sum(e.score_contribution for e in evaluated)
        raw_score += self._correlation_bonus(evaluated)
        normalized_score = 100.0 / (1.0 + math.exp(-0.1 * (raw_score - 10)))
        return normalized_score, evaluated

    def _correlation_bonus(self, evaluated: List[EvaluatedIndicator]) -> float:
        hits = [e for e in evaluated if e.is_hit]
        if len(hits) >= 3:
            return 5.0
        if len(hits) == 2 and any(e.indicator.domain == RiskDomain.TERRORIST_FINANCING for e in hits):
            return 3.0
        return 0.0

    def _evaluate_indicator(self, indicator: RiskIndicator, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        evaluator = getattr(self, f"_rule_{indicator.code.lower()}", None)
        if evaluator:
            result = evaluator(tx, history)
            if isinstance(result, tuple):
                return result
            return bool(result), None
        return False, None

    def _rule_aml_high_risk_country(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = tx.counterparty_country.upper() in {"IR", "KP", "AF", "CU", "SY"}
        return hit, "Gegenpartei in Hochrisikoland" if hit else None

    def _rule_aml_high_risk_sector(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = tx.merchant_category in {"crypto", "luxury"}
        return hit, "Risikobehaftete Branche (Crypto/Luxus)" if hit else None

    def _rule_aml_pep_high_value(self, tx: Transaction, _: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        hit = bool(customer and customer.is_pep and tx.amount >= 5000)
        return hit, "PEP-Kunde mit Hochwert-Transaktion" if hit else None

    def _rule_aml_structuring(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(minutes=30)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.is_credit == tx.is_credit]
        high_frequency = len(relevant) >= 5
        under_threshold = tx.amount < 9500
        hit = high_frequency and under_threshold
        return hit, "Viele kleine Buchungen < 9.5k im 30-Minuten-Fenster" if hit else None

    def _rule_aml_amount_vs_income(self, tx: Transaction, history: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        if not customer:
            return False, None
        rolling_window = datetime.utcnow() - timedelta(hours=4)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= rolling_window]
        total_flow = sum(h.amount for h in relevant)
        hit = total_flow > customer.annual_declared_income / 6
        return hit, "4h Cashflow übersteigt Einkommen / 6" if hit else None

    def _rule_aml_pep_mismatch(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        if not customer or not customer.is_pep:
            return False, None
        last_day = datetime.utcnow() - timedelta(hours=24)
        high_risk_countries = {"IR", "SY", "RU", "UA", "KP"}
        risky = [
            h
            for h in history
            if h.timestamp >= last_day and (h.counterparty_country.upper() in high_risk_countries or h.channel == "tor")
        ]
        hit = len(risky) >= 2 and tx.amount >= 4000
        return hit, "PEP mit Mehrfach-Exposure zu Hochrisiko-Ländern" if hit else None

    def _rule_aml_pep_offshore_layering(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        offshore = {"PA", "KY", "VG", "MT", "IM"}
        if not customer or not customer.is_pep:
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=12)
        offshore_hits = [
            h for h in history if h.timestamp >= window_start and h.counterparty_country.upper() in offshore
        ]
        hit = tx.counterparty_country.upper() in offshore and len(offshore_hits) >= 2
        return hit, "PEP mit gestapelten Offshore-Transfers" if hit else None

    def _rule_aml_round_tripping(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        window_start = datetime.utcnow() - timedelta(hours=6)
        relevant = [h for h in history if h.timestamp >= window_start and h.account_id == tx.account_id]
        matching = [h for h in relevant if abs(h.amount - tx.amount) <= max(200, tx.amount * 0.05)]
        hit = len(matching) >= 3 and any(h.is_credit != tx.is_credit for h in matching)
        return hit, "Rundlauf-Transaktionen mit ähnlichen Beträgen" if hit else None

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
        hit = tx.counterparty_country.upper() in offshore and len(relevant) >= 2 and tx.amount >= 5000
        return hit, "Wiederholte Offshore-Transaktionen >= 5k binnen 1h" if hit else None

    def _rule_aml_cash_intensity(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        if tx.channel != "branch" or not tx.is_credit:
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=6)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.channel == "branch" and h.is_credit]
        total_cash = sum(h.amount for h in relevant) + tx.amount
        hit = total_cash >= 20000
        return hit, "Hohe Cash-Intensität am Schalter binnen 6h" if hit else None

    def _rule_fraud_unusual_device_channel(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = tx.channel.lower() in {"unknown_device", "tor", "anonymous_proxy"}
        return hit, "Unbekanntes/verborgenes Gerät oder Kanal" if hit else None

    def _rule_fraud_velocity_spending(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(minutes=10)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start]
        hit = len(relevant) >= 4 and sum(h.amount for h in relevant) > 20000
        return hit, ">=4 Transaktionen / >20k in 10 Minuten" if hit else None

    def _rule_fraud_device_channel_mix(self, tx: Transaction, history: List[Transaction]) -> bool:
        window_start = datetime.utcnow() - timedelta(hours=2)
        recent = [h.channel for h in history if h.account_id == tx.account_id and h.timestamp >= window_start]
        hit = len(set(recent + [tx.channel])) >= 3
        return hit, "Stark wechselnde Geräte/Kanäle" if hit else None

    def _rule_fraud_device_mismatch(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        account = self.accounts.get(tx.account_id)
        trusted_device = account.device_fingerprint if account else None
        if not trusted_device or not tx.device_id:
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=4)
        recent_devices = {h.device_id for h in history if h.timestamp >= window_start and h.account_id == tx.account_id}
        hit = tx.device_id not in {trusted_device} and len(recent_devices) >= 2
        return hit, "Device-Fingerprint wechselt unerwartet" if hit else None

    def _rule_fraud_card_not_present(self, tx: Transaction, _: List[Transaction]) -> tuple[bool, str | None]:
        if tx.card_present is None:
            return False, None
        hit = not tx.card_present and tx.amount >= 2000 and tx.channel in {"web", "mobile"}
        return hit, "Card-Not-Present Hochwert-Transaktion" if hit else None

    def _rule_fraud_velocity_cnp(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        if tx.card_present:
            return False, None
        window_start = datetime.utcnow() - timedelta(minutes=15)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and not h.card_present]
        hit = len(relevant) >= 3 and sum(h.amount for h in relevant) > 8000
        return hit, "CNP-Velocity > 8k in 15 Minuten" if hit else None

    def _rule_fraud_refund_carousel(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        if tx.is_credit:
            return False, None
        window_start = datetime.utcnow() - timedelta(minutes=20)
        credits = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.is_credit]
        if not credits:
            return False, None
        latest_credit = credits[-1]
        similar_amount = abs(latest_credit.amount - tx.amount) <= latest_credit.amount * 0.15
        hit = similar_amount and "refund" in (tx.purpose or "").lower()
        return hit, "Rückerstattungsmuster kurz nach hohem Kredit" if hit else None

    def _rule_tf_conflict_region(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = tx.counterparty_country.upper() in {"RU", "UA", "IR", "SY"}
        return hit, "Konflikt-/TF-Risikoregion" if hit else None

    def _rule_tf_ngo_conflict_donation(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = "donation" in (tx.purpose or "").lower() and tx.counterparty_country.upper() in {"SY", "IR", "AF", "UA"}
        return hit, "Spende in Konfliktregion" if hit else None

    def _rule_tf_structured_small_donations(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        if not (tx.purpose and "donation" in tx.purpose.lower()):
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=1)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.purpose and "donation" in h.purpose.lower()]
        hit = len(relevant) >= 4 and tx.amount <= 500
        return hit, "Viele Kleinspenden in 60 Minuten" if hit else None

    def _rule_tf_aid_corridor_story(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        keywords = {"aid", "corridor", "ngo", "relief"}
        purpose = (tx.purpose or "").lower()
        if not any(k in purpose for k in keywords):
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=3)
        relevant = [
            h
            for h in history
            if h.account_id == tx.account_id
            and h.timestamp >= window_start
            and any(k in (h.purpose or "").lower() for k in keywords)
            and h.counterparty_country.upper() in {"SY", "IR", "AF", "UA"}
        ]
        hit = len(relevant) >= 3 and 200 <= tx.amount <= 5500
        return hit, "Serielle Hilfszahlungen in Konfliktkorridor (3h)" if hit else None

    def _rule_tf_dual_use_goods(self, tx: Transaction, _: List[Transaction]) -> tuple[bool, str | None]:
        dual_use_categories = {"electronics", "dual_use", "chemicals"}
        hit = tx.merchant_category in dual_use_categories and tx.counterparty_country.upper() in {"IR", "SY", "KP"}
        return hit, "Dual-Use-Güter mit Konflikt-/Sanktionsbezug" if hit else None

    def _rule_tax_low_tax_jurisdiction(self, tx: Transaction, _: List[Transaction]) -> bool:
        hit = tx.counterparty_country.upper() in {"PA", "KY", "VG", "MT"}
        return hit, "Zahlung in Niedrigsteuer-Territorium" if hit else None

    def _rule_tax_income_mismatch(self, tx: Transaction, history: List[Transaction]) -> bool:
        account = self.accounts.get(tx.account_id)
        customer = self.customers.get(account.customer_id) if account else None
        if not customer:
            return False, None
        last_24h = datetime.utcnow() - timedelta(hours=24)
        relevant = [h for h in history if h.account_id == tx.account_id and h.timestamp >= last_24h]
        rolling = sum(h.amount for h in relevant)
        hit = rolling > (customer.annual_declared_income / 12) * 1.5
        return hit, "24h Cashflow > 1.5x Monats-Einkommen" if hit else None

    def _rule_tax_offshore_hopping(self, tx: Transaction, history: List[Transaction]) -> tuple[bool, str | None]:
        offshore = {"PA", "KY", "VG", "MT", "IM"}
        if tx.counterparty_country.upper() not in offshore:
            return False, None
        window_start = datetime.utcnow() - timedelta(hours=6)
        recent_countries = [h.counterparty_country.upper() for h in history if h.account_id == tx.account_id and h.timestamp >= window_start and h.counterparty_country.upper() in offshore]
        hit = len(set(recent_countries + [tx.counterparty_country.upper()])) >= 3 and tx.amount >= 7000
        return hit, "Sprunghafte Offshore-Ketten über mehrere Jurisdiktionen" if hit else None


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
            code="AML_PEP_MISMATCH",
            description="PEP mit mehrfachen Hochrisiko-Exposures",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=14.0,
        ),
        RiskIndicator(
            code="AML_PEP_OFFSHORE_LAYERING",
            description="PEP mit gestapelten Offshore-Transfers",
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
            code="AML_CASH_INTENSITY",
            description="Hohe Cash-Intensität am Schalter",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=11.0,
        ),
        RiskIndicator(
            code="AML_ROUND_TRIPPING",
            description="Rundlauf-Transaktionen mit ähnlichen Beträgen",
            domain=RiskDomain.MONEY_LAUNDERING,
            weight=13.0,
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
            code="FRAUD_DEVICE_MISMATCH",
            description="Device-Fingerprint wechselt unerwartet",
            domain=RiskDomain.FRAUD,
            weight=11.0,
        ),
        RiskIndicator(
            code="FRAUD_CARD_NOT_PRESENT",
            description="Hochwertige Card-Not-Present-Buchung",
            domain=RiskDomain.FRAUD,
            weight=12.0,
        ),
        RiskIndicator(
            code="FRAUD_VELOCITY_CNP",
            description="CNP-Velocity in kurzer Zeit",
            domain=RiskDomain.FRAUD,
            weight=10.0,
        ),
        RiskIndicator(
            code="FRAUD_REFUND_CAROUSEL",
            description="Rückerstattungsmuster nach hohem Kredit",
            domain=RiskDomain.FRAUD,
            weight=12.0,
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
            code="TF_STRUCTURED_SMALL_DONATIONS",
            description="Viele Kleinspenden in kurzer Zeit",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=9.0,
        ),
        RiskIndicator(
            code="TF_AID_CORRIDOR_STORY",
            description="Serielle Hilfszahlungen in Konflikt-NGO-Korridor",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=14.5,
        ),
        RiskIndicator(
            code="TF_DUAL_USE_GOODS",
            description="Dual-Use-Güter mit Konflikt-/Sanktionsbezug",
            domain=RiskDomain.TERRORIST_FINANCING,
            weight=10.5,
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
        RiskIndicator(
            code="TAX_OFFSHORE_HOPPING",
            description="Mehrere Offshore-Jurisdiktionen binnen 6h",
            domain=RiskDomain.TAX_EVASION,
            weight=10.5,
        ),
    ]
