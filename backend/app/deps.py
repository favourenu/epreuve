from collections.abc import Callable
from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.services.ai.service import AIService, build_providers


@lru_cache
def get_ai_service() -> AIService:
    return AIService(build_providers(get_settings()))


def get_session_factory() -> Callable[[], Session]:
    """Used by background tasks, which outlive the request's session."""
    return SessionLocal
