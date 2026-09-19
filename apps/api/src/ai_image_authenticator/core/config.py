"""Application settings via pydantic-settings (env / .env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _csv_list(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Runtime configuration. Override with env vars (AIAUTH_* or bare names)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AIAUTH_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    max_upload_bytes: int = 25 * 1024 * 1024
    # Decoded-size cap: a few KB of PNG can decode to hundreds of megapixels
    max_image_pixels: int = 50_000_000
    artifact_ttl_seconds: int = 3600
    artifact_max_entries: int = 256
    log_level: str = "INFO"
    allowed_content_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "image/avif",
        ]
    )
    # prod hides internal exception text from API error responses
    environment: Literal["dev", "prod"] = "dev"
    frontend_dist: str = ""  # optional absolute path; empty = auto-detect

    @field_validator("cors_origins", "allowed_content_types", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        return _csv_list(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def upper_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
