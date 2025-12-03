from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta
import itertools
from typing import AsyncIterator, Iterable, List

from .domain import Account, Customer, Transaction


class TransactionIngestionService:
    def __init__(self, customers: Iterable[Customer], accounts: Iterable[Account]) -> None:
        self.customers = list(customers)
        self.accounts = list(accounts)
        self._scenario_cycle = itertools.cycle(
            [
                self._scenario_structuring,
                self._scenario_conflict_region,
                self._scenario_high_income_spike,
                self._scenario_conflict_donation,
                self._scenario_luxury_pep_spree,
                self._scenario_generic,
            ]
        )

    async def stream_transactions(self, *, delay_seconds: float = 1.0) -> AsyncIterator[Transaction]:
        while True:
            tx = self._generate_transaction()
            yield tx
            await asyncio.sleep(delay_seconds)

    def _generate_transaction(self) -> Transaction:
        scenario = next(self._scenario_cycle)
        return scenario()

    def _base_transaction(self, account: Account, *, amount: float, counterparty_country: str, channel: str, is_credit: bool, purpose: str | None = None) -> Transaction:
        now = datetime.utcnow()
        return Transaction(
            id=str(uuid.uuid4()),
            account_id=account.id,
            timestamp=now,
            amount=amount,
            currency="EUR",
            counterparty_country=counterparty_country,
            channel=channel,
            is_credit=is_credit,
            merchant_category=random.choice(["travel", "luxury", "crypto", "utilities", "retail"]),
            purpose=purpose,
        )

    def _scenario_structuring(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(5000, 9200), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["DE", "US", "GB"]),
            channel="branch",
            is_credit=True,
            purpose="Structuring pattern",
        )

    def _scenario_conflict_region(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(150, 4000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["SY", "IR", "RU", "UA"]),
            channel=random.choice(["mobile", "web"]),
            is_credit=random.choice([True, False]),
            purpose="Conflict-region transfer",
        )

    def _scenario_high_income_spike(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(15000, 48000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["KY", "VG", "PA", "MT", "DE"]),
            channel=random.choice(["web", "mobile", "unknown_device", "tor"]),
            is_credit=random.choice([True, False]),
            purpose="Income mismatch stress test",
        )

    def _scenario_generic(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(25, 15000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["DE", "US", "FR", "GB", "ES", "IT"]),
            channel=random.choice(["mobile", "web", "branch"]),
            is_credit=random.choice([True, False]),
            purpose="Everyday payment",
        )

    def _scenario_conflict_donation(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(50, 4500), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["SY", "IR", "AF", "UA"]),
            channel=random.choice(["mobile", "web"]),
            is_credit=False,
            purpose="NGO donation in conflict zone",
        )

    def _scenario_luxury_pep_spree(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(7500, 28000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["AE", "US", "FR", "GB"]),
            channel=random.choice(["mobile", "web", "unknown_device"]),
            is_credit=False,
            purpose="Luxury spend spree",
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
        Customer(
            id="cust-3",
            customer_id="C1003",
            name="Helios Offshore Ltd.",
            country="KY",
            is_pep=False,
            annual_declared_income=2_400_000,
        ),
    ]


def sample_accounts(customers: Iterable[Customer]) -> List[Account]:
    customers_list = list(customers)
    return [
        Account(id="acc-1", account_number="DE0012345678", customer_id=customers_list[0].id),
        Account(id="acc-2", account_number="DE0099999999", customer_id=customers_list[1].id),
        Account(id="acc-3", account_number="KY0012345678", customer_id=customers_list[2].id),
    ]
