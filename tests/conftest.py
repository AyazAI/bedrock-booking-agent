from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from booking_agent.clock import FrozenClock
from booking_agent.config import Settings
from booking_agent.main import create_app

FROZEN = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "llm_provider": "mock",
        "database_url": f"sqlite:///{tmp_path / 'bookings.db'}",
        "vector_backend": "chroma",
        "chroma_path": str(tmp_path / "chroma"),
        "seed_demo": True,
        "whatsapp_enabled": False,
        "demo_api_key": "demo",
        "openai_api_key": "",
        "whatsapp_app_secret": "",
        "whatsapp_access_token": "",
        "whatsapp_verify_token": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path), FrozenClock(FROZEN))
    with TestClient(app) as test_client:
        yield test_client
