from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from booking_agent.agent.tools import ToolExecutor
from booking_agent.llm.base import ChatMessage, LLMProvider


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class Turn:
    reply: str
    tool_calls: list[ToolTrace] = field(default_factory=list)
    new_messages: list[ChatMessage] = field(default_factory=list)


def run_turn(
    provider: LLMProvider,
    execute: ToolExecutor,
    specs: list[dict[str, Any]],
    history: list[ChatMessage],
    user_text: str,
    system: str,
    max_steps: int,
) -> Turn:
    messages = [*history, ChatMessage(role="user", content=user_text)]
    visible = [ChatMessage(role="system", content=system), *messages]
    trace: list[ToolTrace] = []
    for _ in range(max_steps):
        completion = provider.complete(visible, specs)
        if completion.tool_calls:
            assistant = ChatMessage(
                role="assistant",
                content=completion.text,
                tool_calls=list(completion.tool_calls),
            )
            messages.append(assistant)
            visible.append(assistant)
            for call in completion.tool_calls:
                result = execute(call.name, call.arguments)
                trace.append(ToolTrace(name=call.name, arguments=call.arguments, result=result))
                tool_message = ChatMessage(
                    role="tool",
                    content=json.dumps(result),
                    name=call.name,
                    tool_call_id=call.id,
                )
                messages.append(tool_message)
                visible.append(tool_message)
            continue
        reply = completion.text.strip() or "I could not complete that."
        messages.append(ChatMessage(role="assistant", content=reply))
        return Turn(reply=reply, tool_calls=trace, new_messages=messages[len(history) :])
    reply = "I need to stop here. Ask me for one thing at a time."
    messages.append(ChatMessage(role="assistant", content=reply))
    return Turn(reply=reply, tool_calls=trace, new_messages=messages[len(history) :])


def history_from_rows(rows: list[tuple[str, str]]) -> list[ChatMessage]:
    return [
        ChatMessage(role=role, content=content)
        for role, content in rows
        if role in {"user", "assistant"}
    ]
