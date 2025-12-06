import json
from pathlib import Path

import pytest

from app import config_loader
from app.domain import RiskDomain


def test_indicator_validation(tmp_path: Path):
    path = tmp_path / "indicators.json"
    path.write_text(json.dumps([{"code": "X", "description": "", "domain": "MONEY_LAUNDERING", "weight": 1}]))
    indicators = config_loader.load_indicators_config(path)
    assert indicators[0].domain == RiskDomain.MONEY_LAUNDERING


def test_indicator_validation_error(tmp_path: Path):
    path = tmp_path / "indicators.json"
    path.write_text(json.dumps([{"code": "X", "description": "", "domain": "INVALID", "weight": 1}]))
    with pytest.raises(config_loader.ConfigValidationError):
        config_loader.load_indicators_config(path)


def test_threshold_validation(tmp_path: Path):
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps({"low": 10, "medium": 20}))
    thresholds = config_loader.load_thresholds_config(path)
    assert thresholds.low == 10
    assert thresholds.medium == 20
