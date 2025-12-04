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
                self._scenario_crypto_mixer_burst,
                self._scenario_refund_carousel,
                self._scenario_conflict_donation,
                self._scenario_aid_corridor_story,
                self._scenario_luxury_pep_spree,
                self._scenario_offshore_hopping,
                self._scenario_everyday_business,
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

    def _scenario_aid_corridor_story(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(250, 5200), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["SY", "IR", "AF", "UA"]),
            channel=random.choice(["mobile", "web", "tor"]),
            is_credit=False,
            purpose="Aid corridor relief transfer",
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

    def _scenario_crypto_mixer_burst(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(300, 4500), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["RU", "UA", "PA", "KY"]),
            channel=random.choice(["tor", "unknown_device", "mobile"]),
            is_credit=True,
            purpose="Crypto mixer payout",
        )

    def _scenario_refund_carousel(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(3000, 9000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["US", "DE", "GB", "FR"]),
            channel=random.choice(["web", "mobile", "branch"]),
            is_credit=False,
            purpose="Refund after large purchase",
        )

    def _scenario_offshore_hopping(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(6500, 18000), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["PA", "KY", "VG", "MT", "IM"]),
            channel=random.choice(["web", "mobile", "unknown_device"]),
            is_credit=False,
            purpose="Offshore routing",
        )

    def _scenario_everyday_business(self) -> Transaction:
        account = random.choice(self.accounts)
        amount = round(random.uniform(1200, 9500), 2)
        return self._base_transaction(
            account,
            amount=amount,
            counterparty_country=random.choice(["DE", "FR", "GB", "NL", "US"]),
            channel=random.choice(["web", "mobile", "branch"]),
            is_credit=random.choice([True, False]),
            purpose="Payroll or invoice settlement",
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
        Customer(
            id="cust-4",
            customer_id="C1004",
            name="Frontier Aid",
            country="DE",
            is_pep=False,
            annual_declared_income=180_000,
        ),
        Customer(
            id="cust-5",
            customer_id="C1005",
            name="Lux Holdings AG",
            country="CH",
            is_pep=True,
            annual_declared_income=1_800_000,
        ),
    ]


def sample_accounts(customers: Iterable[Customer]) -> List[Account]:
    customers_list = list(customers)
    return [
        Account(id="acc-1", account_number="DE0012345678", customer_id=customers_list[0].id),
        Account(id="acc-2", account_number="DE0099999999", customer_id=customers_list[1].id),
        Account(id="acc-3", account_number="KY0012345678", customer_id=customers_list[2].id),
        Account(id="acc-4", account_number="DE0088888888", customer_id=customers_list[3].id),
        Account(id="acc-5", account_number="CH0011111111", customer_id=customers_list[4].id),
    ]
