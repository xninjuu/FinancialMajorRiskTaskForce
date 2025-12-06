from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncIterator, Iterable, List


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: datetime
    url: str


class NewsService:
    def __init__(self, headlines: Iterable[NewsItem]) -> None:
        self.headlines = list(headlines)

    async def stream_news(self, *, delay_seconds: float = 5.0) -> AsyncIterator[NewsItem]:
        index = 0
        while True:
            if not self.headlines:
                await asyncio.sleep(delay_seconds)
                continue
            yield self.headlines[index % len(self.headlines)]
            index += 1
            await asyncio.sleep(delay_seconds)


def sample_news() -> List[NewsItem]:
    now = datetime.utcnow()
    return [
        NewsItem(
            title="FATF warnt vor steigenden TF-Risiken in Konfliktregionen",
            source="Global Compliance Wire",
            published_at=now - timedelta(minutes=2),
            url="https://example.com/news/fatf-tf-risk",
        ),
        NewsItem(
            title="Großrazzia wegen Verdacht auf Geldwäsche im Kryptobereich",
            source="Finance Times",
            published_at=now - timedelta(minutes=6),
            url="https://example.com/news/crypto-aml",
        ),
        NewsItem(
            title="Mehrere Banken verschärfen Kontrollen gegen Steuerbetrug",
            source="Tax Alert Daily",
            published_at=now - timedelta(minutes=11),
            url="https://example.com/news/tax-controls",
        ),
    ]
