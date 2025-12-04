from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .domain import RiskDomain, RiskIndicator
from .risk_engine import RiskThresholds


class ConfigNotFoundWarning(UserWarning):
    pass


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_indicators_config(path: str | Path) -> List[RiskIndicator]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    data = _read_json(file_path)
    indicators: List[RiskIndicator] = []
    for item in data:
        domain_name = item["domain"].upper()
        domain = RiskDomain[domain_name]
        indicators.append(
            RiskIndicator(
                code=item["code"],
                description=item.get("description", ""),
                domain=domain,
                weight=float(item.get("weight", 0.0)),
            )
        )
    return indicators


def load_thresholds_config(path: str | Path) -> RiskThresholds:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    data = _read_json(file_path)
    return RiskThresholds(low=float(data.get("low", 30.0)), medium=float(data.get("medium", 60.0)))


def safe_load_indicators(*, path: str | Path, fallback: Iterable[RiskIndicator]) -> List[RiskIndicator]:
    try:
        return load_indicators_config(path)
    except FileNotFoundError:
        return list(fallback)


def safe_load_thresholds(*, path: str | Path, fallback: RiskThresholds) -> RiskThresholds:
    try:
        return load_thresholds_config(path)
    except FileNotFoundError:
        return fallback
