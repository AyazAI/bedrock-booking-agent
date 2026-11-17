from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from booking_agent.clock import FrozenClock
from booking_agent.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import make_settings


def test_health_hides_secrets(client) -> None:
    client.app.state.settings.whatsapp_app_secret = "not-a-real-secret"
    client.app.state.settings.openai_api_key = "sk-test-placeholder"
    body = client.get("/health").json()
    encoded = str(body)
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"
    assert body["vector_backend"] == "chroma"
    assert "not-a-real-secret" not in encoded
    assert "sk-test-placeholder" not in encoded
    assert body["faq_chunks"] >= 4


def test_chat_and_services_page(client) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "appointment desk" in page.text
    meta = client.get("/api/meta").json()
    assert meta["business_name"] == "Northline Studio"
    assert meta["llm_provider"] == "mock"
    empty = client.post("/api/chat", json={"message": "   "})
    assert empty.status_code == 400


def test_empty_demo_key_rejects_the_example_header(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path, demo_api_key=""),
        FrozenClock(datetime(2026, 11, 18, 12, 0, tzinfo=UTC)),
    )
    with TestClient(app) as test_client:
        assert test_client.get("/api/bookings").status_code == 401
        assert test_client.get("/api/bookings", headers={"X-Demo-Key": "demo"}).status_code == 401


def test_booking_list_requires_the_demo_key(client) -> None:
    hidden = client.get("/api/bookings")
    assert hidden.status_code == 401
    shown = client.get("/api/bookings", headers={"X-Demo-Key": "demo"})
    assert shown.status_code == 200
    codes = [row["code"] for row in shown.json()["bookings"]]
    assert "NL-1001" in codes
