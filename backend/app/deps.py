from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import User
from app.services.ai.service import AIService, build_providers
from app.services.auth import sync_admin_role, user_for_token


@lru_cache
def get_ai_service() -> AIService:
    return AIService(build_providers(get_settings()))


def get_session_factory() -> Callable[[], Session]:
    """Used by background tasks, which outlive the request's session."""
    return SessionLocal


def get_signed_in_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Any signed-in user, including one who hasn't confirmed their email yet.
    Only for the account endpoints that confirming needs."""
    token = request.cookies.get(get_settings().session_cookie_name)
    user = user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Please log in to continue")
    sync_admin_role(db, user)  # ADMIN_EMAILS takes effect without logging out
    return user


def get_current_user(user: User = Depends(get_signed_in_user)) -> User:
    """A signed-in user with a confirmed email: required by everything else."""
    if not user.email_verified:
        raise HTTPException(403, "Please confirm your email address to continue.")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user
