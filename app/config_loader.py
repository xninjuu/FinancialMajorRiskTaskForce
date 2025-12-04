from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .runtime_paths import resolve_config_path

from .domain import RiskDomain, RiskIndicator
from .risk_engine import RiskThresholds


class ConfigNotFoundWarning(UserWarning):
    pass


class ConfigValidationError(ValueError):
    pass


@dataclass
class IndicatorConfig:
    code: str
    description: str
    domain: RiskDomain
    weight: float

    @classmethod
    def from_dict(cls, data: dict) -> "IndicatorConfig":
        missing = [field for field in ("code", "description", "domain", "weight") if field not in data]
        if missing:
            raise ConfigValidationError(f"Missing indicator fields: {', '.join(missing)}")
        try:
            domain = RiskDomain[data["domain"].upper()]
        except KeyError as exc:
            raise ConfigValidationError(f"Invalid domain: {data['domain']}") from exc
        weight = float(data["weight"])
        if weight <= 0:
            raise ConfigValidationError("Indicator weight must be positive")
        return cls(
            code=str(data["code"]),
            description=str(data["description"]),
            domain=domain,
            weight=weight,
        )


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_indicators_config(path: str | Path | None) -> List[RiskIndicator]:
    if path is None:
        raise FileNotFoundError("indicators config not found")
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    data = _read_json(file_path)
    if not isinstance(data, list):
        raise ConfigValidationError("indicators.json must contain a list")
    indicators: List[RiskIndicator] = []
    for item in data:
        cfg = IndicatorConfig.from_dict(item)
        indicators.append(
            RiskIndicator(
                code=cfg.code,
                description=cfg.description,
                domain=cfg.domain,
                weight=cfg.weight,
            )
        )
    return indicators


def load_thresholds_config(path: str | Path | None) -> RiskThresholds:
    if path is None:
        raise FileNotFoundError("threshold config not found")
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    data = _read_json(file_path)
    if "low" not in data or "medium" not in data:
        raise ConfigValidationError("thresholds.json requires 'low' and 'medium'")
    low = float(data.get("low", 30.0))
    medium = float(data.get("medium", 60.0))
    if low <= 0 or medium <= 0 or medium <= low:
        raise ConfigValidationError("Thresholds must be positive and medium > low")
    return RiskThresholds(low=low, medium=medium)


def safe_load_indicators(*, path: str | Path | None, fallback: Iterable[RiskIndicator]) -> List[RiskIndicator]:
    try:
        return load_indicators_config(path)
    except FileNotFoundError:
        print("[CONFIG] indicators.json not found – using embedded defaults.")
        return list(fallback)
    except ConfigValidationError as exc:
        raise SystemExit(f"Invalid indicators config: {exc}")


def safe_load_thresholds(*, path: str | Path | None, fallback: RiskThresholds) -> RiskThresholds:
    try:
        return load_thresholds_config(path)
    except FileNotFoundError:
        print("[CONFIG] thresholds.json not found – using embedded defaults.")
        return fallback
    except ConfigValidationError as exc:
        raise SystemExit(f"Invalid thresholds config: {exc}")


def resolve_indicator_path() -> Path | None:
    return resolve_config_path("indicators.json")


def resolve_threshold_path() -> Path | None:
    return resolve_config_path("thresholds.json")
