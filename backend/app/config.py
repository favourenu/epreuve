from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, read from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'assessment.db').as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Seconds of leeway after a test's deadline before answers are rejected,
    # to absorb network latency on the final submission.
    deadline_grace_seconds: int = 5

    # Code execution
    code_run_timeout_seconds: float = 5.0
    code_max_output_chars: int = 10_000

    # AI providers, tried in this order. Unconfigured providers are skipped.
    ai_provider_order: list[str] = Field(default=["openrouter", "gemini", "ollama"])
    ai_request_timeout_seconds: float = 120.0

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    ollama_enabled: bool = True
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://localhost:11434"
    # Local models on a CPU-only machine can take several minutes for a full report.
    ollama_timeout_seconds: float = 900.0
    ollama_num_ctx: int = 8192


@lru_cache
def get_settings() -> Settings:
    return Settings()
