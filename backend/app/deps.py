from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import User
from app.services.ai.service import AIService, build_providers
from app.services.auth import user_for_token


@lru_cache
def get_ai_service() -> AIService:
    return AIService(build_providers(get_settings()))


def get_session_factory() -> Callable[[], Session]:
    """Used by background tasks, which outlive the request's session."""
    return SessionLocal


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    user = user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Please log in to continue")
    return user
