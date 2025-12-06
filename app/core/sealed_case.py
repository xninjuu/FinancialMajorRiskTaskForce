from __future__ import annotations

import hashlib
import json
from typing import Iterable, Tuple

from app.storage.db import Database


def _merkle_root(leaves: Iterable[str]) -> str:
    layer = [hashlib.sha256(leaf.encode("utf-8")).hexdigest() for leaf in leaves]
    if not layer:
        return hashlib.sha256(b"empty").hexdigest()
    while len(layer) > 1:
        paired = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            paired.append(hashlib.sha256((left + right).encode("utf-8")).hexdigest())
        layer = paired
    return layer[0]


def seal_case(db: Database, case_id: str, *, sealed_by: str, seal_reason: str | None = None) -> Tuple[str, str]:
    case = db.get_case(case_id)
    alerts = db.alerts_for_case(case_id)
    notes = db.case_notes(case_id)
    payload = {
        "case": dict(case) if case else {},
        "alerts": [dict(a) for a in alerts],
        "notes": [note.__dict__ for note in notes],
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    leaves = [digest] + [json.dumps(a, sort_keys=True) for a in alerts]
    merkle_root = _merkle_root(leaves)
    db.seal_case(case_id, digest, sealed_by=sealed_by, merkle_root=merkle_root, seal_reason=seal_reason)
    return case_id, merkle_root


def verify_seal(db: Database, case_id: str) -> bool:
    record = db.sealed_case(case_id)
    if not record:
        return False
    case = db.get_case(case_id)
    alerts = db.alerts_for_case(case_id)
    notes = db.case_notes(case_id)
    payload = {
        "case": dict(case) if case else {},
        "alerts": [dict(a) for a in alerts],
        "notes": [note.__dict__ for note in notes],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    leaves = [digest] + [json.dumps(a, sort_keys=True) for a in alerts]
    recomputed_root = _merkle_root(leaves)
    return recomputed_root == record["merkle_root"]
