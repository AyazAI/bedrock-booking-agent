from __future__ import annotations

import json
from typing import Any

from booking_agent.llm.base import ChatMessage, Completion, ProviderError, ToolCall


def to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "assistant" and message.tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
            continue
        if message.role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        converted.append({"role": message.role, "content": message.content})
    return converted


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for spec in tools
    ]


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> Completion:
        if not self._api_key:
            raise ProviderError("OPENAI_API_KEY is empty")
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        response = client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=to_openai_messages(messages),  # type: ignore[arg-type]
            tools=to_openai_tools(tools),  # type: ignore[arg-type]
        )
        choice = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in choice.tool_calls or []:
            function = getattr(call, "function", None)
            if function is None:
                continue
            raw = function.arguments or "{}"
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=function.name,
                    arguments=json.loads(raw) if isinstance(raw, str) else raw,
                )
            )
        return Completion(text=choice.content or "", tool_calls=tool_calls, provider=self.name)
