from __future__ import annotations

import json
from typing import Any

from booking_agent.llm.base import ChatMessage, Completion, ProviderError, ToolCall


def to_bedrock_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "toolSpec": {
                "name": spec["name"],
                "description": spec["description"],
                "inputSchema": {"json": spec["parameters"]},
            }
        }
        for spec in tools
    ]


def to_bedrock_messages(
    messages: list[ChatMessage],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    system = [{"text": message.content} for message in messages if message.role == "system"]
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "assistant" and message.tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": call.id,
                                "name": call.name,
                                "input": call.arguments,
                            }
                        }
                        for call in message.tool_calls
                    ],
                }
            )
            continue
        if message.role == "tool":
            payload: Any
            try:
                payload = json.loads(message.content)
            except json.JSONDecodeError:
                payload = {"text": message.content}
            block = {
                "toolResult": {
                    "toolUseId": message.tool_call_id,
                    "content": [{"json": payload}],
                }
            }
            if converted and converted[-1]["role"] == "user" and _is_tool_result(converted[-1]):
                converted[-1]["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
            continue
        role = "assistant" if message.role == "assistant" else "user"
        converted.append({"role": role, "content": [{"text": message.content}]})
    return system, converted


def _is_tool_result(message: dict[str, Any]) -> bool:
    content = message.get("content") or []
    return bool(content) and "toolResult" in content[0]


class BedrockProvider:
    name = "bedrock"

    def __init__(self, region: str, model_id: str) -> None:
        self._region = region
        self._model_id = model_id

    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> Completion:
        if not self._model_id:
            raise ProviderError("BEDROCK_MODEL_ID is empty")
        import boto3

        client = boto3.client("bedrock-runtime", region_name=self._region)
        system, bedrock_messages = to_bedrock_messages(messages)
        response = client.converse(
            modelId=self._model_id,
            system=system,
            messages=bedrock_messages,
            toolConfig={"tools": to_bedrock_tools(tools)},
            inferenceConfig={"maxTokens": 800, "temperature": 0},
        )
        tool_calls: list[ToolCall] = []
        texts: list[str] = []
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                texts.append(block["text"])
            if "toolUse" in block:
                use = block["toolUse"]
                tool_calls.append(
                    ToolCall(
                        id=use["toolUseId"],
                        name=use["name"],
                        arguments=use.get("input") or {},
                    )
                )
        return Completion(text="".join(texts), tool_calls=tool_calls, provider=self.name)
