from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import AsyncIterator, Iterable, List

from .domain import Account, Customer, Transaction


class TransactionIngestionService:
    def __init__(self, customers: Iterable[Customer], accounts: Iterable[Account]) -> None:
        self.customers = list(customers)
        self.accounts = list(accounts)

    async def stream_transactions(self, *, delay_seconds: float = 1.0) -> AsyncIterator[Transaction]:
        while True:
            tx = self._generate_transaction()
            yield tx
            await asyncio.sleep(delay_seconds)

    def _generate_transaction(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(10, 15000), 2)
        now = datetime.utcnow()
        return Transaction(
            id=str(uuid.uuid4()),
            account_id=account.id,
            timestamp=now,
            amount=amount,
            currency="EUR",
            counterparty_country=random.choice(["DE", "US", "IR", "GB", "MT", "SY", "KY", "FR", "UA"]),
            channel=random.choice(["mobile", "web", "branch", "unknown_device", "tor"]),
            is_credit=random.choice([True, False]),
        )


def sample_customers() -> List[Customer]:
    return [
        Customer(
            id="cust-1",
            customer_id="C1001",
            name="Acme Corp",
            country="DE",
            is_pep=False,
            annual_declared_income=1_500_000,
        ),
        Customer(
            id="cust-2",
            customer_id="C1002",
            name="Jane Doe",
            country="US",
            is_pep=True,
            annual_declared_income=320_000,
        ),
    ]


def sample_accounts(customers: Iterable[Customer]) -> List[Account]:
    customers_list = list(customers)
    return [
        Account(id="acc-1", account_number="DE0012345678", customer_id=customers_list[0].id),
        Account(id="acc-2", account_number="DE0099999999", customer_id=customers_list[1].id),
    ]
