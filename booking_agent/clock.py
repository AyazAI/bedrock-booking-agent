from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("clock moment must be timezone-aware")
        self.moment = moment

    def now(self) -> datetime:
        return self.moment
