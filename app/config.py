"""Application configuration loaded from environment variables and .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings.

    Defaults intentionally start in a zero-cost demo mode. Add credentials in
    .env and change AI_MODE / IMAGE_PROVIDER to enable live providers.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ComicCraft"
    app_version: str = "1.0.0"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    storage_dir: Path = BASE_DIR / "storage"
    cors_origins: str = ""

    # Text generation
    ai_mode: Literal["auto", "demo", "gemini"] = "auto"
    gemini_api_key: SecretStr | None = None
    gemini_outline_model: str = "gemini-3.5-flash-lite"
    gemini_story_model: str = "gemini-3.5-flash"
    gemini_outline_fallback_models: str = "gemini-flash-lite-latest,gemini-3.5-flash"
    gemini_story_fallback_models: str = "gemini-flash-latest,gemini-3.6-flash"
    gemini_retry_attempts: int = Field(default=3, ge=1, le=5)
    gemini_retry_base_seconds: float = Field(default=1.5, ge=0.1, le=30.0)
    gemini_retry_max_seconds: float = Field(default=8.0, ge=0.5, le=120.0)
    allow_ai_fallback: bool = True

    # Image generation. placeholder is local, fast, and credential-free.
    image_provider: Literal["placeholder", "huggingface", "diffusers"] = "placeholder"
    allow_image_fallback: bool = True
    image_width: int = Field(default=768, ge=256, le=2048, multiple_of=64)
    image_height: int = Field(default=768, ge=256, le=2048, multiple_of=64)

    # Hugging Face hosted inference
    hf_token: SecretStr | None = None
    hf_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    hf_provider: str = ""
    hf_timeout_seconds: int = Field(default=180, ge=10, le=900)

    # Optional local Diffusers backend
    local_sd_model: str = "stable-diffusion-v1-5/stable-diffusion-v1-5"
    local_sd_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    local_sd_steps: int = Field(default=25, ge=1, le=100)
    local_sd_guidance: float = Field(default=7.0, ge=0, le=30)

    # Application limits
    default_panel_count: int = Field(default=5, ge=3, le=8)
    max_panel_count: int = Field(default=8, ge=3, le=12)
    max_prompt_chars: int = Field(default=1500, ge=100, le=10000)
    enable_test_image_endpoint: bool = True
    keep_failed_workspaces: bool = False

    @field_validator("storage_dir", mode="before")
    @classmethod
    def resolve_storage_dir(cls, value: object) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()

    @computed_field
    @property
    def resolved_ai_mode(self) -> Literal["demo", "gemini"]:
        if self.ai_mode == "auto":
            return "gemini" if self.gemini_api_key else "demo"
        return self.ai_mode

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def gemini_key(self) -> str | None:
        return self.gemini_api_key.get_secret_value() if self.gemini_api_key else None

    @property
    def huggingface_token(self) -> str | None:
        return self.hf_token.get_secret_value() if self.hf_token else None

    def prepare_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "comics").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "test-images").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
