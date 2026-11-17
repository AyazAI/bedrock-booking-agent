from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from booking_agent.bookings.catalog import Business, ServiceDef
from booking_agent.clock import Clock
from booking_agent.db import BookingRow, ServiceRow, session_scope

_CODE = re.compile(r"^NL-(\d+)$")


class BookingService:
    """One calendar. Overlaps are rejected in this process, not by the model."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        business: Business,
        clock: Clock,
        seed_demo: bool = True,
    ) -> None:
        self._factory = factory
        self.business = business
        self._clock = clock
        self._seed_demo = seed_demo
        self._zone = ZoneInfo(business.timezone)

    def now(self) -> datetime:
        return self._clock.now().astimezone(self._zone)

    def today(self) -> date:
        return self.now().date()

    def seed(self) -> None:
        with session_scope(self._factory) as session:
            for service in self.business.services:
                if session.get(ServiceRow, service.id) is None:
                    session.add(
                        ServiceRow(
                            id=service.id,
                            name=service.name,
                            duration_min=service.duration_min,
                        )
                    )
            if not self._seed_demo:
                return
            existing = session.scalar(
                select(BookingRow).where(BookingRow.code == self.business.sample_code)
            )
            if existing is not None:
                return
            day = self._next_open_date(self.today())
            start = datetime.combine(day, self.business.sample_time, self._zone)
            service = self._service_by_id(self.business.sample_service_id)
            end = start + timedelta(minutes=service.duration_min)
            session.add(
                BookingRow(
                    code=self.business.sample_code,
                    service_id=service.id,
                    customer_name=self.business.sample_customer,
                    starts_at=start.isoformat(),
                    ends_at=end.isoformat(),
                    status="confirmed",
                )
            )

    def check_availability(self, service_text: str, day_text: str) -> dict[str, object]:
        service = self.business.resolve_service(service_text)
        if service is None:
            return {"ok": False, "error": "unknown_service"}
        day = _parse_day(day_text)
        if day is None:
            return {"ok": False, "error": "bad_date"}
        if day < self.today():
            return {"ok": False, "error": "past", "date": day.isoformat()}
        if day > self.today() + timedelta(days=60):
            return {"ok": False, "error": "too_far", "date": day.isoformat()}
        if day.weekday() not in self.business.hours:
            return {
                "ok": True,
                "service": service.name,
                "date": day.isoformat(),
                "closed": True,
                "slots": [],
                "next_open_date": self._next_open_date(day).isoformat(),
            }
        slots = self._open_slots(service, day)
        return {
            "ok": True,
            "service": service.name,
            "date": day.isoformat(),
            "closed": False,
            "slots": slots,
            "next_open_date": None,
        }

    def create_booking(
        self,
        service_text: str,
        day_text: str,
        time_text: str,
        customer_name: str,
    ) -> dict[str, object]:
        service = self.business.resolve_service(service_text)
        if service is None:
            return {"ok": False, "error": "unknown_service"}
        name = " ".join(customer_name.split())
        if not name or not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,79}", name):
            return {"ok": False, "error": "missing_name"}
        day = _parse_day(day_text)
        start_time = _parse_clock(time_text)
        if day is None or start_time is None:
            return {"ok": False, "error": "bad_datetime"}
        if day.weekday() not in self.business.hours:
            return {"ok": False, "error": "closed", "date": day.isoformat()}
        start = datetime.combine(day, start_time, self._zone)
        end = start + timedelta(minutes=service.duration_min)
        if end <= self.now():
            return {"ok": False, "error": "past"}
        if not self._inside_hours(start, end):
            return {"ok": False, "error": "outside_hours"}
        with session_scope(self._factory) as session:
            if self._overlaps(session, start, end):
                return {
                    "ok": False,
                    "error": "overlap",
                    "date": day.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                }
            code = self._next_code(session)
            session.add(
                BookingRow(
                    code=code,
                    service_id=service.id,
                    customer_name=name,
                    starts_at=start.isoformat(),
                    ends_at=end.isoformat(),
                    status="confirmed",
                )
            )
        return {
            "ok": True,
            "code": code,
            "service": service.name,
            "customer_name": name,
            "date": day.isoformat(),
            "time": start_time.strftime("%H:%M"),
            "ends": end.strftime("%H:%M"),
        }

    def cancel_booking(self, code: str) -> dict[str, object]:
        normalized = code.strip().upper()
        with session_scope(self._factory) as session:
            row = session.scalar(select(BookingRow).where(BookingRow.code == normalized))
            if row is None:
                return {"ok": False, "error": "unknown_code", "code": normalized}
            if row.status == "cancelled":
                return {"ok": True, "code": row.code, "status": "cancelled", "already": True}
            row.status = "cancelled"
            return {"ok": True, "code": row.code, "status": "cancelled", "already": False}

    def list_bookings(self) -> list[dict[str, object]]:
        with session_scope(self._factory) as session:
            rows = session.scalars(select(BookingRow).order_by(BookingRow.starts_at)).all()
            return [
                {
                    "code": row.code,
                    "service_id": row.service_id,
                    "customer_name": row.customer_name,
                    "starts_at": row.starts_at,
                    "ends_at": row.ends_at,
                    "status": row.status,
                }
                for row in rows
            ]

    def _open_slots(self, service: ServiceDef, day: date) -> list[str]:
        open_at, close_at = self.business.hours[day.weekday()]
        cursor = datetime.combine(day, open_at, self._zone)
        close = datetime.combine(day, close_at, self._zone)
        step = timedelta(minutes=self.business.slot_minutes)
        now = self.now()
        slots: list[str] = []
        with session_scope(self._factory) as session:
            while cursor + timedelta(minutes=service.duration_min) <= close:
                end = cursor + timedelta(minutes=service.duration_min)
                if end > now and not self._overlaps(session, cursor, end):
                    slots.append(cursor.strftime("%H:%M"))
                cursor += step
        return slots

    def _overlaps(self, session: Session, start: datetime, end: datetime) -> bool:
        rows = session.scalars(select(BookingRow).where(BookingRow.status == "confirmed")).all()
        for row in rows:
            other_start = datetime.fromisoformat(row.starts_at)
            other_end = datetime.fromisoformat(row.ends_at)
            if start < other_end and other_start < end:
                return True
        return False

    def _inside_hours(self, start: datetime, end: datetime) -> bool:
        if start.date() != end.date():
            return False
        span = self.business.hours.get(start.weekday())
        if span is None:
            return False
        open_at, close_at = span
        return open_at <= start.time() and end.time() <= close_at

    def _next_open_date(self, after: date) -> date:
        for offset in range(1, 8):
            candidate = after + timedelta(days=offset)
            if candidate.weekday() in self.business.hours:
                return candidate
        return after + timedelta(days=1)

    def _next_code(self, session: Session) -> str:
        codes = session.scalars(select(BookingRow.code)).all()
        numbers = [int(match.group(1)) for code in codes if (match := _CODE.match(code))]
        return f"NL-{max(numbers, default=1000) + 1:04d}"

    def _service_by_id(self, service_id: str) -> ServiceDef:
        for service in self.business.services:
            if service.id == service_id:
                return service
        raise KeyError(service_id)


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_clock(value: str) -> time | None:
    try:
        hour, minute = value.strip().split(":")
        parsed = time(int(hour), int(minute))
    except ValueError:
        return None
    if parsed.strftime("%H:%M") != f"{int(hour):02d}:{int(minute):02d}":
        return None
    return parsed
