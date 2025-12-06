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
    device_fingerprint: str | None = None


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
    device_id: str | None = None
    card_present: bool | None = None


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
    priority: str = "Normal"


class CaseStatus(Enum):
    OPEN = auto()
    IN_REVIEW = auto()
    ESCALATED = auto()
    CLOSED = auto()


class CaseLabel(Enum):
    SAR_FILED = auto()
    NO_SAR = auto()
    FALSE_POSITIVE = auto()
    MONITOR = auto()


@dataclass
class CaseNote:
    author: str
    message: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Case:
    id: str
    alerts: List[Alert] = field(default_factory=list)
    status: CaseStatus = CaseStatus.OPEN
    label: CaseLabel | None = None
    priority: str = "Normal"
    band: str | None = None
    policy_triggers: List[str] = field(default_factory=list)
    policy_explanations: List[str] = field(default_factory=list)
    assignee: str | None = None
    policy_flag: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    notes: List[CaseNote] = field(default_factory=list)

    def add_alert(self, alert: Alert) -> None:
        self.alerts.append(alert)
        alert.case_id = self.id
        self.updated_at = datetime.utcnow()

    def add_note(self, note: CaseNote) -> None:
        self.notes.append(note)
        self.updated_at = datetime.utcnow()

    @property
    def customer_id(self) -> Optional[str]:
        if self.alerts:
            return self.alerts[0].transaction.account_id
        return None


class TaskStatus(Enum):
    OPEN = auto()
    IN_PROGRESS = auto()
    REVIEW = auto()
    DONE = auto()


@dataclass
class Task:
    id: str
    title: str
    created_by: str
    assignee: str
    priority: str = "Normal"
    status: TaskStatus = TaskStatus.OPEN
    related_case_id: str | None = None
    related_alert_id: str | None = None
    due_at: datetime | None = None
    description: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
