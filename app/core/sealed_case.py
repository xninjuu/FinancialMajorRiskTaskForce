from __future__ import annotations

import hashlib
import json
from typing import Tuple

from app.storage.db import Database


def seal_case(db: Database, case_id: str, *, sealed_by: str) -> Tuple[str, str]:
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
    db.seal_case(case_id, digest, sealed_by=sealed_by)
    return case_id, digest
