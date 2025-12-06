from datetime import datetime, timedelta

from app.domain import RiskIndicator, RiskDomain, Transaction
from app.risk_engine import RiskScoringEngine, RiskThresholds


def test_structuring_indicator_triggers():
    indicator = RiskIndicator(
        code="AML_STRUCTURING",
        description="",
        domain=RiskDomain.MONEY_LAUNDERING,
        weight=10.0,
    )
    engine = RiskScoringEngine([indicator])
    now = datetime.utcnow()
    history = [
        Transaction(
            id=str(i),
            account_id="acc-1",
            timestamp=now - timedelta(minutes=5 * i),
            amount=9000,
            currency="EUR",
            counterparty_country="DE",
            channel="branch",
            is_credit=True,
        )
        for i in range(5)
    ]
    tx = Transaction(
        id="tx-final",
        account_id="acc-1",
        timestamp=now,
        amount=9100,
        currency="EUR",
        counterparty_country="DE",
        channel="branch",
        is_credit=True,
    )
    score, evaluated = engine.score_transaction(tx, history=history)
    assert score > 0
    assert evaluated[0].is_hit


def test_threshold_levels():
    thresholds = RiskThresholds(low=10, medium=20)
    assert thresholds.level(5) == "Low"
    assert thresholds.level(15) == "Medium"
    assert thresholds.level(25) == "High"
