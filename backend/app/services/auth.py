"""Accounts and sessions.

Passwords are hashed with Argon2id. A session is a random token in an httpOnly
cookie; the database stores only an HMAC of it keyed with SECRET_KEY, so a leaked
database can't be used to forge cookies and rotating the key logs everyone out.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Attempt, User, UserSession, utcnow

log = logging.getLogger(__name__)

_hasher = PasswordHasher()
# Verified against when the email is unknown, so response time doesn't reveal
# which emails have accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class AuthError(Exception):
    status_code = 400


class InvalidCredentials(AuthError):
    status_code = 401


class EmailTaken(AuthError):
    status_code = 409


class TooManyAttempts(AuthError):
    status_code = 429


@lru_cache
def secret_key() -> bytes:
    key = get_settings().secret_key
    if not key:
        log.warning(
            "SECRET_KEY is not set; using a temporary key, so everyone is logged out when the "
            "server restarts. Set SECRET_KEY in backend/.env."
        )
        key = secrets.token_urlsafe(48)
    elif len(key) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters long")
    return key.encode()


def _token_hash(token: str) -> str:
    return hmac.new(secret_key(), token.encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    if password.strip() == "" or len(set(password)) < 4:
        raise AuthError("Password is too simple; use a mix of characters")


class LoginThrottle:
    """In-memory sliding-window limit on failed logins, per key (email or IP).

    Per-process only: fine for a single-server deployment. Use a shared store
    such as Redis if the API ever runs as multiple processes.
    """

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures, self.window = max_failures, window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def check(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                q = self._recent(key, now)
                if len(q) >= self.max_failures:
                    retry = int(q[0] + self.window - now) + 1
                    raise TooManyAttempts(
                        f"Too many failed login attempts. Try again in {max(1, retry // 60)} minute(s)."
                    )

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._recent(key, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


@lru_cache
def get_throttle() -> LoginThrottle:
    s = get_settings()
    return LoginThrottle(s.login_max_failures, s.login_window_seconds)


def signup(db: Session, email: str, password: str, name: str) -> User:
    email = normalize_email(email)
    validate_password(password)
    if db.scalar(select(User.id).where(User.email == email)):
        raise EmailTaken("An account with this email already exists. Log in instead.")
    is_first_user = db.scalar(select(User.id).limit(1)) is None
    user = User(email=email, name=name.strip(), password_hash=_hasher.hash(password))
    db.add(user)
    db.flush()
    if is_first_user:
        # Attempts made before accounts existed belong to whoever set the app up.
        db.execute(update(Attempt).where(Attempt.user_id.is_(None)).values(user_id=user.id))
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str, client_ip: str) -> User:
    email = normalize_email(email)
    throttle = get_throttle()
    keys = (f"email:{email}", f"ip:{client_ip}")
    throttle.check(*keys)

    user = db.scalar(select(User).where(User.email == email))
    try:
        _hasher.verify(user.password_hash if user else _DUMMY_HASH, password)
        if user is None:
            raise VerifyMismatchError
    except (VerifyMismatchError, InvalidHashError):
        throttle.fail(*keys)
        raise InvalidCredentials("Incorrect email or password") from None

    throttle.reset(f"email:{email}")
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
        db.commit()
    return user


def create_session(db: Session, user: User, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=utcnow() + timedelta(days=settings.session_days),
        )
    )
    # Opportunistic cleanup keeps the table small without a scheduler.
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    db.commit()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if session is None:
        return None
    if session.expires_at < utcnow():
        db.delete(session)
        db.commit()
        return None
    return session.user


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    db.commit()
