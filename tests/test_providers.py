from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from booking_agent.bookings.catalog import load_business
from booking_agent.clock import FrozenClock
from booking_agent.config import Settings, project_root
from booking_agent.llm.base import ChatMessage, ProviderError, ToolCall
from booking_agent.llm.bedrock import to_bedrock_messages, to_bedrock_tools
from booking_agent.llm.factory import FallbackProvider, build_provider
from booking_agent.llm.mock import MockProvider
from booking_agent.llm.openai_provider import OpenAIProvider, to_openai_messages, to_openai_tools


def test_openai_and_bedrock_payloads_share_one_tool_shape() -> None:
    specs = [
        {
            "name": "search_faq",
            "description": "Find a note",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
    ]
    call = ToolCall(id="call_1", name="search_faq", arguments={"query": "hours"})
    messages = [
        ChatMessage(role="system", content="Be brief."),
        ChatMessage(role="user", content="When are you open?"),
        ChatMessage(role="assistant", tool_calls=[call]),
        ChatMessage(
            role="tool",
            content=json.dumps({"matched": True}),
            tool_call_id="call_1",
            name="search_faq",
        ),
    ]
    openai = to_openai_messages(messages)
    assert openai[0]["role"] == "system"
    assert openai[2]["tool_calls"][0]["function"]["name"] == "search_faq"
    assert openai[3]["tool_call_id"] == "call_1"
    assert to_openai_tools(specs)[0]["type"] == "function"
    system, bedrock = to_bedrock_messages(messages)
    assert system[0]["text"] == "Be brief."
    assert bedrock[1]["content"][0]["toolUse"]["name"] == "search_faq"
    assert bedrock[2]["content"][0]["toolResult"]["toolUseId"] == "call_1"
    assert to_bedrock_tools(specs)[0]["toolSpec"]["name"] == "search_faq"


def test_openai_refuses_without_a_key() -> None:
    provider = OpenAIProvider(api_key="", model="gpt-4o-mini", base_url="https://api.openai.com/v1")
    with pytest.raises(ProviderError):
        provider.complete([ChatMessage(role="user", content="Hi")], [])


def test_fallback_skips_an_unconfigured_provider() -> None:
    business = load_business(project_root() / "knowledge")
    clock = FrozenClock(datetime(2026, 11, 18, 12, 0, tzinfo=UTC))
    provider = FallbackProvider(
        [
            OpenAIProvider(api_key="", model="gpt-4o-mini", base_url="https://example.invalid"),
            MockProvider(business, clock),
        ]
    )
    completion = provider.complete([ChatMessage(role="user", content="Hello")], [])
    assert completion.provider == "mock"
    assert "appointment desk" in completion.text


def test_unknown_provider_name_is_rejected() -> None:
    business = load_business(project_root() / "knowledge")
    clock = FrozenClock(datetime(2026, 11, 18, 12, 0, tzinfo=UTC))
    settings = Settings(_env_file=None, llm_provider="nope")
    with pytest.raises(ProviderError):
        build_provider(settings, business, clock)
