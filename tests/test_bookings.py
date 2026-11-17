from __future__ import annotations

from datetime import UTC, datetime

from booking_agent.bookings.catalog import load_business
from booking_agent.bookings.service import BookingService
from booking_agent.clock import FrozenClock
from booking_agent.config import project_root
from booking_agent.db import init_db, make_engine, make_session_factory


def _service(tmp_path, seed: bool = True) -> BookingService:
    engine = make_engine(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    business = load_business(project_root() / "knowledge")
    service = BookingService(
        make_session_factory(engine),
        business,
        FrozenClock(datetime(2026, 11, 18, 12, 0, tzinfo=UTC)),
        seed_demo=seed,
    )
    service.seed()
    return service


def test_sample_booking_blocks_that_slot(tmp_path) -> None:
    service = _service(tmp_path)
    result = service.check_availability("intro", "2026-11-19")
    assert result["ok"] is True
    assert "15:00" not in result["slots"]
    assert "10:00" in result["slots"]


def test_create_then_overlap(tmp_path) -> None:
    service = _service(tmp_path, seed=False)
    created = service.create_booking("Working session", "2026-11-19", "10:00", "Sam")
    assert created["ok"] is True
    assert created["ends"] == "11:00"
    clash = service.create_booking("intro", "2026-11-19", "10:30", "Ada")
    assert clash["ok"] is False
    assert clash["error"] == "overlap"
    adjacent = service.create_booking("intro", "2026-11-19", "11:00", "Ada")
    assert adjacent["ok"] is True


def test_cancel_is_idempotent_and_frees_the_slot(tmp_path) -> None:
    service = _service(tmp_path)
    blocked = service.check_availability("Intro consultation", "2026-11-19")
    assert "15:00" not in blocked["slots"]
    first = service.cancel_booking("nl-1001")
    assert first == {"ok": True, "code": "NL-1001", "status": "cancelled", "already": False}
    second = service.cancel_booking("NL-1001")
    assert second["already"] is True
    missing = service.cancel_booking("NL-9999")
    assert missing["error"] == "unknown_code"
    free = service.check_availability("intro", "2026-11-19")
    assert "15:00" in free["slots"]


def test_sunday_is_closed(tmp_path) -> None:
    service = _service(tmp_path, seed=False)
    result = service.check_availability("intro", "2026-11-22")
    assert result["closed"] is True
    assert result["slots"] == []
    assert result["next_open_date"] == "2026-11-23"


def test_rejects_a_nameless_booking(tmp_path) -> None:
    service = _service(tmp_path, seed=False)
    result = service.create_booking("intro", "2026-11-19", "10:00", "  ")
    assert result["error"] == "missing_name"
