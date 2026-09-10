"""Typed, validated app configuration loaded from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "llama3.2"

    semantic_cache_threshold: float = 0.05
    semantic_cache_ttl_seconds: int = 3600
    semantic_cache_candidates: int = 5

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None


settings = Settings()
