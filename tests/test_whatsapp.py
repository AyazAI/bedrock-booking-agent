from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from booking_agent.channels.whatsapp import signature_ok
from booking_agent.clock import FrozenClock
from booking_agent.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import make_settings

SECRET = "test-secret"
TOKEN = "verify-token"


def _signed(body: bytes) -> dict[str, str]:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}"}


@pytest.fixture
def wa_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = make_settings(
        tmp_path,
        whatsapp_enabled=True,
        whatsapp_app_secret=SECRET,
        whatsapp_verify_token=TOKEN,
    )
    app = create_app(
        settings,
        FrozenClock(datetime(2026, 11, 18, 12, 0, tzinfo=UTC)),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_signature_fails_closed() -> None:
    body = b"{}"
    assert signature_ok("", body, "sha256=abc") is False
    assert signature_ok(SECRET, body, None) is False
    assert signature_ok(SECRET, body, "sha256=deadbeef") is False
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert signature_ok(SECRET, body, f"sha256={digest}") is True


def test_adapter_is_hidden_until_enabled(client) -> None:
    assert client.post("/api/whatsapp/webhook", content=b"{}").status_code == 404


def test_verify_and_signed_dry_run(wa_client: TestClient) -> None:
    bad = wa_client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"},
    )
    assert bad.status_code == 403
    ok = wa_client.get(
        "/api/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "12345"},
    )
    assert ok.status_code == 200
    assert ok.text == "12345"

    booking = "Book an intro consultation tomorrow at 10:00 for Sam"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15555550100",
                                    "id": "wamid.TEST1",
                                    "type": "text",
                                    "text": {"body": booking},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    unsigned = wa_client.post("/api/whatsapp/webhook", content=raw)
    assert unsigned.status_code == 403
    first = wa_client.post("/api/whatsapp/webhook", content=raw, headers=_signed(raw))
    assert first.status_code == 200
    reply = first.json()["replies"][0]
    assert reply["status"] == "dry_run"
    assert "NL-" in reply["reply"]
    assert "15555550100" not in first.text
    second = wa_client.post("/api/whatsapp/webhook", content=raw, headers=_signed(raw))
    assert second.json()["replies"] == []
    listed = wa_client.get("/api/bookings", headers={"X-Demo-Key": "demo"}).json()["bookings"]
    sam = [row for row in listed if row["customer_name"] == "Sam" and row["status"] == "confirmed"]
    assert len(sam) == 1
