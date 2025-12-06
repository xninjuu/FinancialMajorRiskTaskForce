from __future__ import annotations

import time
from typing import Dict, List

from app.domain import EvaluatedIndicator, Transaction
from app.risk_engine import RiskScoringEngine


def profile_rules(engine: RiskScoringEngine, tx: Transaction) -> Dict[str, float]:
    timings: Dict[str, float] = {}
    start = time.perf_counter()
    score, evaluated = engine.score_transaction(tx, history=[])
    total = time.perf_counter() - start
    for eval_ind in evaluated:
        timings[eval_ind.indicator.code] = total / max(len(evaluated), 1)
    timings["_total"] = total
    return timings
