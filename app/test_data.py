from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List

from .domain import Account, Customer, Transaction


def make_customers() -> List[Customer]:
    return [
        Customer(
            id="c-normal",
            customer_id="C2001",
            name="Everyday GmbH",
            country="DE",
            is_pep=False,
            annual_declared_income=120_000,
        ),
        Customer(
            id="c-pep",
            customer_id="C2002",
            name="Minister X",
            country="DE",
            is_pep=True,
            annual_declared_income=450_000,
        ),
    ]


def make_accounts(customers: Iterable[Customer]) -> List[Account]:
    cust_list = list(customers)
    return [
        Account(id="a-normal", account_number="DE02002", customer_id=cust_list[0].id, device_fingerprint="dev-web-test"),
        Account(id="a-pep", account_number="DE02003", customer_id=cust_list[1].id, device_fingerprint="dev-pep"),
    ]


def pep_offshore_transactions(account: Account) -> List[Transaction]:
    now = datetime.utcnow()
    txs = []
    for i, country in enumerate(["PA", "KY", "VG"]):
        txs.append(
            Transaction(
                id=f"tx-pep-{i}",
                account_id=account.id,
                timestamp=now - timedelta(hours=1 - i * 0.2),
                amount=6500 + i * 300,
                currency="EUR",
                counterparty_country=country,
                channel="web",
                is_credit=False,
                merchant_category="luxury",
                purpose="Offshore layering",
                device_id="dev-pep",
                card_present=False,
            )
        )
    return txs


def structuring_burst(account: Account) -> List[Transaction]:
    now = datetime.utcnow()
    return [
        Transaction(
            id=f"tx-struct-{i}",
            account_id=account.id,
            timestamp=now - timedelta(minutes=5 * i),
            amount=9200 - i * 100,
            currency="EUR",
            counterparty_country="DE",
            channel="branch",
            is_credit=True,
            merchant_category="retail",
            purpose="Structuring test",
            device_id="dev-web-test",
            card_present=True,
        )
        for i in range(5)
    ]


def cnp_velocity(account: Account) -> List[Transaction]:
    now = datetime.utcnow()
    base_amount = 2500
    return [
        Transaction(
            id=f"tx-cnp-{i}",
            account_id=account.id,
            timestamp=now - timedelta(minutes=3 * i),
            amount=base_amount + 250 * i,
            currency="EUR",
            counterparty_country="US",
            channel="web",
            is_credit=False,
            merchant_category="retail",
            purpose="Card-not-present test",
            device_id=f"dev-proxy-{i}",
            card_present=False,
        )
        for i in range(3)
    ]
