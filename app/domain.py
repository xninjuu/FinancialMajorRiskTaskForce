from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional


class RiskDomain(Enum):
    MONEY_LAUNDERING = auto()
    FRAUD = auto()
    TERRORIST_FINANCING = auto()
    TAX_EVASION = auto()


@dataclass
class Customer:
    id: str
    customer_id: str
    name: str
    country: str
    is_pep: bool
    annual_declared_income: float


@dataclass
class Account:
    id: str
    account_number: str
    customer_id: str


@dataclass
class Transaction:
    id: str
    account_id: str
    timestamp: datetime
    amount: float
    currency: str
    counterparty_country: str
    channel: str
    is_credit: bool
    merchant_category: str | None = None
    purpose: str | None = None


@dataclass
class RiskIndicator:
    code: str
    description: str
    domain: RiskDomain
    weight: float


@dataclass
class EvaluatedIndicator:
    indicator: RiskIndicator
    is_hit: bool
    explanation: str | None = None

    @property
    def score_contribution(self) -> float:
        return self.indicator.weight if self.is_hit else 0.0


@dataclass
class Alert:
    id: str
    transaction: Transaction
    score: float
    evaluated_indicators: List[EvaluatedIndicator]
    created_at: datetime
    status: str = "Open"
    case_id: Optional[str] = None


@dataclass
class Case:
    id: str
    alerts: List[Alert] = field(default_factory=list)
    status: str = "Open"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_alert(self, alert: Alert) -> None:
        self.alerts.append(alert)
        alert.case_id = self.id
        self.updated_at = datetime.utcnow()

    @property
    def customer_id(self) -> Optional[str]:
        if self.alerts:
            return self.alerts[0].transaction.account_id
        return None
