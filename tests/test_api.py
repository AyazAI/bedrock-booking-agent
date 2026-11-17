from __future__ import annotations


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


def test_booking_list_requires_the_demo_key(client) -> None:
    hidden = client.get("/api/bookings")
    assert hidden.status_code == 401
    shown = client.get("/api/bookings", headers={"X-Demo-Key": "demo"})
    assert shown.status_code == 200
    codes = [row["code"] for row in shown.json()["bookings"]]
    assert "NL-1001" in codes
