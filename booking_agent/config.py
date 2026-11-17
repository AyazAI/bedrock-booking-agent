from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment configuration. Defaults run the demo with no API keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    database_url: str = "sqlite:///./data/bookings.db"
    vector_backend: str = "chroma"
    chroma_path: str = "./data/chroma"
    faq_score_threshold: float = 0.28
    embedding_dims: int = 256
    demo_api_key: str = ""
    seed_demo: bool = True
    knowledge_dir: str = "knowledge"
    max_tool_steps: int = 4
    whatsapp_enabled: bool = False
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_graph_version: str = "v21.0"

    @property
    def provider_chain(self) -> list[str]:
        return [part.strip().lower() for part in self.llm_provider.split(",") if part.strip()]

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return project_root() / path


def get_settings() -> Settings:
    return Settings()
