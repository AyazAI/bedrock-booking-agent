from __future__ import annotations

from pathlib import Path

import yaml
from booking_agent.agent.prompts import system_prompt
from booking_agent.bookings.catalog import load_business
from booking_agent.config import project_root


def test_eval_cases(client) -> None:
    cases = yaml.safe_load((Path("evals/cases.yaml")).read_text(encoding="utf-8"))["cases"]
    for case in cases:
        response = client.post("/api/chat", json={"message": case["message"]})
        assert response.status_code == 200, case["name"]
        body = response.json()
        names = [call["name"] for call in body["tool_calls"]]
        assert names == case["expect_tools"], case["name"]
        for snippet in case.get("reply_contains", []):
            assert snippet in body["reply"], case["name"]
        lowered = body["reply"].lower()
        for snippet in case.get("reply_not_contains", []):
            assert snippet.lower() not in lowered, case["name"]


def test_system_prompt_forbids_invented_facts() -> None:
    business = load_business(project_root() / "knowledge")
    prompt = system_prompt(business)
    assert "matched false" in prompt
    assert "check_availability" in prompt
    assert "Northline Studio" in prompt


def test_session_keeps_history(client) -> None:
    first = client.post(
        "/api/chat",
        json={"message": "Book an intro consultation tomorrow at 10:00 for Sam"},
    ).json()
    second = client.post(
        "/api/chat",
        json={"session_id": first["session_id"], "message": "Hello"},
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == first["session_id"]
