from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from app.runtime_paths import resolve_config_path


@dataclass
class Policy:
    id: str
    domain: str
    severity: str
    description: str
    conditions: Dict[str, Any]


@dataclass
class PolicyResult:
    band: str
    triggered_policies: List[str]
    explanations: List[str]


class PolicyEngine:
    def __init__(self, policies: List[Policy]):
        self.policies = policies

    @classmethod
    def from_file(cls, filename: str = "policies.json") -> "PolicyEngine":
        path = resolve_config_path(filename)
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = _default_policies()
        policies = [Policy(**entry) for entry in data]
        return cls(policies)

    def evaluate_case(self, case_row: Any, alerts: List[Any]) -> PolicyResult:
        alerts_data = [dict(a) if not hasattr(a, "get") else a for a in alerts]
        metrics = self._build_metrics(case_row, alerts_data)
        triggered: List[str] = []
        explanations: List[str] = []
        band = "GREEN"
        for policy in self.policies:
            if self._matches(policy, metrics):
                triggered.append(policy.id)
                explanations.append(policy.description)
                band = _max_band(band, policy.severity)
        return PolicyResult(band=band, triggered_policies=triggered, explanations=explanations)

    def _build_metrics(self, case_row: Any, alerts: List[dict]) -> Dict[str, Any]:
        alert_count = len(alerts)
        high_alerts = sum(1 for a in alerts if a.get("risk_level") == "High")
        domains = {a.get("domain") for a in alerts if a.get("domain")}
        max_score = max((float(a.get("score", 0)) for a in alerts), default=0.0)
        band = case_row.get("band") if hasattr(case_row, "get") else case_row["band"] if "band" in case_row.keys() else None
        return {
            "alert_count": alert_count,
            "high_alerts": high_alerts,
            "domains": domains,
            "max_score": max_score,
            "band": band,
        }

    def _matches(self, policy: Policy, metrics: Dict[str, Any]) -> bool:
        conditions = policy.conditions
        if "min_alerts" in conditions and metrics["alert_count"] < conditions["min_alerts"]:
            return False
        if "min_high_alerts" in conditions and metrics["high_alerts"] < conditions["min_high_alerts"]:
            return False
        if "min_score" in conditions and metrics["max_score"] < conditions["min_score"]:
            return False
        domains = conditions.get("domains")
        if domains and not (metrics["domains"] & set(domains)):
            return False
        return True


def _default_policies() -> List[Dict[str, Any]]:
    return [
        {
            "id": "AML_HIGH_SCORE",
            "domain": "AML",
            "severity": "RED",
            "description": "AML high score with strong alert density",
            "conditions": {"min_score": 70, "min_alerts": 2},
        },
        {
            "id": "FRAUD_CARD_PATTERN",
            "domain": "FRAUD",
            "severity": "YELLOW",
            "description": "Fraud velocity pattern detected",
            "conditions": {"domains": ["Fraud"], "min_high_alerts": 1},
        },
        {
            "id": "TF_ROUTE",
            "domain": "TF",
            "severity": "YELLOW",
            "description": "Terrorism financing corridor risk",
            "conditions": {"domains": ["TF"], "min_alerts": 1},
        },
    ]


def _max_band(current: str, new_band: str) -> str:
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    return new_band if order.get(new_band, 0) > order.get(current, 0) else current
