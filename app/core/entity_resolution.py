from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from app.domain import Customer


def normalize(text: str) -> str:
    return re.sub(r"\W+", "", text or "").lower()


def deduplicate(customers: Iterable[Customer]) -> Tuple[List[Customer], Dict[str, str]]:
    seen: Dict[str, Customer] = {}
    mapping: Dict[str, str] = {}
    for cust in customers:
        key = normalize(cust.name) or cust.customer_id.lower()
        if key in seen:
            mapping[cust.id] = seen[key].id
        else:
            seen[key] = cust
            mapping[cust.id] = cust.id
    return list(seen.values()), mapping


def bucket_by_country(customers: Iterable[Customer]) -> Dict[str, List[Customer]]:
    buckets: Dict[str, List[Customer]] = defaultdict(list)
    for cust in customers:
        buckets[cust.country.upper()].append(cust)
    return buckets
