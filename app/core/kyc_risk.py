from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.domain import Customer


HIGH_RISK_JURISDICTIONS = {"IR", "KP", "AF", "SY"}
MEDIUM_RISK_JURISDICTIONS = {"TR", "AE", "RU"}


@dataclass
class KYCDimension:
    name: str
    score: int
    rationale: str


@dataclass
class KYCRiskProfile:
    total_score: int
    level: str
    dimensions: List[KYCDimension]


def _level(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def evaluate_customer(customer: Customer) -> KYCRiskProfile:
    dimensions: List[KYCDimension] = []

    base = 10
    dimensions.append(KYCDimension("Baseline", base, "Default baseline score"))

    if customer.is_pep:
        dimensions.append(KYCDimension("PEP", 40, "Customer flagged as Politically Exposed Person"))
    if customer.country in HIGH_RISK_JURISDICTIONS:
        dimensions.append(KYCDimension("Jurisdiction", 30, f"High-risk country {customer.country}"))
    elif customer.country in MEDIUM_RISK_JURISDICTIONS:
        dimensions.append(KYCDimension("Jurisdiction", 15, f"Medium-risk country {customer.country}"))
    else:
        dimensions.append(KYCDimension("Jurisdiction", 5, "Standard jurisdiction"))

    if customer.annual_declared_income <= 0:
        dimensions.append(KYCDimension("Income", 20, "Missing or zero declared income"))
    elif customer.annual_declared_income < 35_000:
        dimensions.append(KYCDimension("Income", 10, "Low declared income"))

    total = sum(d.score for d in dimensions)
    return KYCRiskProfile(total_score=total, level=_level(total), dimensions=dimensions)
