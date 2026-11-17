from __future__ import annotations

from typing import Any

from booking_agent.bookings.catalog import Business
from booking_agent.clock import Clock
from booking_agent.config import Settings
from booking_agent.llm.base import ChatMessage, Completion, LLMProvider, ProviderError
from booking_agent.llm.bedrock import BedrockProvider
from booking_agent.llm.mock import MockProvider
from booking_agent.llm.openai_provider import OpenAIProvider


class FallbackProvider:
    """Try each provider. An empty key raises before any network call."""

    name = "fallback"

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ProviderError("LLM_PROVIDER is empty")
        self._providers = providers
        self.name = ",".join(provider.name for provider in providers)

    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> Completion:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.complete(messages, tools)
            except ProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
        raise ProviderError("; ".join(errors))


def build_provider(settings: Settings, business: Business, clock: Clock) -> LLMProvider:
    providers: list[LLMProvider] = []
    for name in settings.provider_chain:
        if name == "mock":
            providers.append(MockProvider(business, clock))
        elif name == "openai":
            providers.append(
                OpenAIProvider(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    base_url=settings.openai_base_url,
                )
            )
        elif name == "bedrock":
            providers.append(
                BedrockProvider(region=settings.aws_region, model_id=settings.bedrock_model_id)
            )
        else:
            raise ProviderError(f"unknown LLM provider: {name}")
    if len(providers) == 1:
        return providers[0]
    return FallbackProvider(providers)
