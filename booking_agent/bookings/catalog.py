from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path

import yaml

_DAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class ServiceDef:
    id: str
    name: str
    duration_min: int
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Business:
    name: str
    timezone: str
    slot_minutes: int
    disclaimer: str
    suggestions: tuple[str, ...]
    hours: dict[int, tuple[time, time]]
    services: tuple[ServiceDef, ...]
    sample_code: str
    sample_service_id: str
    sample_customer: str
    sample_time: time

    def resolve_service(self, text: str) -> ServiceDef | None:
        raw = " ".join(text.lower().replace("-", " ").split())
        if not raw:
            return None
        by_id = {service.id: service for service in self.services}
        if raw in by_id:
            return by_id[raw]
        candidates: list[tuple[int, ServiceDef]] = []
        for service in self.services:
            names = (service.name, *service.aliases)
            for name in names:
                needle = " ".join(name.lower().replace("-", " ").split())
                if raw == needle:
                    return service
                if needle and needle in raw:
                    candidates.append((len(needle), service))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]


def describe_hours(business: Business) -> str:
    if not business.hours:
        return f"{business.name} has no published hours in this demo."
    weekday_span = tuple(business.hours.get(day) for day in range(5))
    weekend_closed = 5 not in business.hours and 6 not in business.hours
    if weekend_closed and len(set(weekday_span)) == 1 and weekday_span[0] is not None:
        start, end = weekday_span[0]
        return (
            f"{business.name} is open Monday to Friday, "
            f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')} {business.timezone}. "
            "Saturday and Sunday are closed. This is sample data."
        )
    parts = [
        f"{_DAY_NAME[day]} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        for day, (start, end) in sorted(business.hours.items())
    ]
    return f"{business.name} is open {'; '.join(parts)} ({business.timezone}). This is sample data."


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def load_business(knowledge_dir: Path) -> Business:
    raw = yaml.safe_load((knowledge_dir / "business.yaml").read_text(encoding="utf-8"))
    services = tuple(
        ServiceDef(
            id=item["id"],
            name=item["name"],
            duration_min=int(item["duration_min"]),
            aliases=tuple(item.get("aliases") or ()),
        )
        for item in raw["services"]
    )
    hours: dict[int, tuple[time, time]] = {}
    for key, span in raw["hours"].items():
        hours[_DAY[key]] = (_parse_time(span[0]), _parse_time(span[1]))
    sample = raw["sample_booking"]
    return Business(
        name=raw["name"],
        timezone=raw["timezone"],
        slot_minutes=int(raw["slot_minutes"]),
        disclaimer=raw["disclaimer"],
        suggestions=tuple(raw["suggestions"]),
        hours=hours,
        services=services,
        sample_code=sample["code"],
        sample_service_id=sample["service_id"],
        sample_customer=sample["customer_name"],
        sample_time=_parse_time(sample["time"]),
    )
