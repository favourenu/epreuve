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

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'epreuve.db').as_posix()}"
    # Browser origins allowed to call the API. Also used as the CSRF allow-list:
    # state-changing requests carrying any other Origin header are rejected.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Authentication. SECRET_KEY signs session tokens; set a long random value in .env
    # (python -c "import secrets; print(secrets.token_urlsafe(48))").
    secret_key: str = ""
    session_cookie_name: str = "epreuve_session"
    session_days: int = 30
    # Set true when serving over HTTPS so the cookie is never sent in plain text.
    session_cookie_secure: bool = False
    # Failed logins allowed per email (and per client IP) within the window before throttling.
    login_max_failures: int = 5
    login_window_seconds: int = 900

    # Built frontend to serve from this server (one service, one domain, so cookies
    # need no cross-site setup). Ignored if the folder has no index.html (e.g. in dev).
    frontend_dist_dir: str = str(BACKEND_DIR.parent / "frontend" / "dist")

    # Accounts with these emails become admins when they sign up or log in.
    admin_emails: list[str] = []

    # Certification: proctored attempts scoring at least the pass mark earn a certificate.
    certification_pass_percent: float = 75.0
    certification_distinction_percent: float = 90.0
    # Wait between certification attempts at the same test, so the question pool can't be farmed.
    certification_cooldown_days: int = 7

    # Company invitations to take an assessment
    invite_valid_days: int = 14

    # Public URL of the web app, used to build links in emails (no trailing slash).
    app_base_url: str = "http://localhost:5173"

    # Email (Resend). Without an API key, emails are logged instead of sent.
    resend_api_key: str = ""
    email_from: str = "Épreuve <noreply@epreuve.site>"

    # Password reset links
    password_reset_minutes: int = 60
    # Reset emails allowed per address (and per client IP) within the window.
    password_reset_max_requests: int = 3
    password_reset_window_seconds: int = 3600

    # Seconds of leeway after a test's deadline before answers are rejected,
    # to absorb network latency on the final submission.
    deadline_grace_seconds: int = 5

    # Code execution
    code_run_timeout_seconds: float = 5.0
    code_max_output_chars: int = 10_000
    # Enforced on Linux/macOS via resource limits (the deployment target). Sized for
    # small hosts: e.g. Render's free tier has 512 MB for the whole server.
    code_memory_limit_mb: int = 256
    code_output_limit_bytes: int = 1_000_000
    # Runs allowed at once; more wait in line (up to code_queue_wait_seconds).
    code_max_concurrent_runs: int = 2
    code_queue_wait_seconds: float = 20.0

    # AI providers, tried in this order. Unconfigured providers are skipped.
    ai_provider_order: list[str] = Field(default=["openrouter", "gemini", "ollama"])
    ai_request_timeout_seconds: float = 120.0

    openrouter_api_key: str = ""
    # Free models come and go and are often rate-limited upstream, so OpenRouter is
    # given backups to try in order. Current list: https://openrouter.ai/models?q=free
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_fallback_models: list[str] = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-lightning:free"]
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    gemini_api_key: str = ""
    # An alias that always points at Google's current Flash model.
    gemini_model: str = "gemini-flash-latest"
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
