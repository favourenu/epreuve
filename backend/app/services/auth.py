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
from app.models import Attempt, PasswordResetToken, Role, User, UserSession, utcnow

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


class AccountSuspended(AuthError):
    status_code = 403

    def __init__(self):
        super().__init__("This account has been suspended. Contact support if you think this is a mistake.")


def sync_admin_role(db: Session, user: User) -> None:
    """Promote accounts listed in ADMIN_EMAILS once they have confirmed the address
    (so nobody can claim admin by signing up with it first). Never demotes: admins
    can also be promoted from the dashboard."""
    admins = {normalize_email(e) for e in get_settings().admin_emails}
    if user.email in admins and user.role != Role.ADMIN and user.email_verified:
        user.role = Role.ADMIN
        db.commit()


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

    def __init__(self, max_failures: int, window_seconds: int, message: str = "Too many failed login attempts."):
        self.max_failures, self.window, self.message = max_failures, window_seconds, message
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
                    raise TooManyAttempts(f"{self.message} Try again in {max(1, retry // 60)} minute(s).")

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


@lru_cache
def get_reset_throttle() -> LoginThrottle:
    s = get_settings()
    return LoginThrottle(
        s.password_reset_max_requests, s.password_reset_window_seconds, "Too many password reset requests."
    )


def signup(db: Session, email: str, password: str, name: str) -> User:
    email = normalize_email(email)
    validate_password(password)
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.email_verified:
            raise EmailTaken("An account with this email already exists. Log in instead.")
        # Never confirmed, so it can't have been used: let whoever owns the inbox start
        # again (otherwise anyone could block an address by signing up with it).
        db.delete(existing)
        db.flush()
    is_first_user = db.scalar(select(User.id).limit(1)) is None
    user = User(email=email, name=name.strip(), password_hash=_hasher.hash(password))
    db.add(user)
    db.flush()
    if is_first_user:
        # Attempts made before accounts existed belong to whoever set the app up.
        db.execute(update(Attempt).where(Attempt.user_id.is_(None)).values(user_id=user.id))
    db.commit()
    sync_admin_role(db, user)
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
    if user.disabled_at is not None:
        raise AccountSuspended()
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
        db.commit()
    sync_admin_role(db, user)
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
    if session.user.disabled_at is not None:
        return None
    return session.user


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    db.commit()


class InvalidResetToken(AuthError):
    status_code = 400

    def __init__(self):
        super().__init__("This reset link is invalid or has expired. Request a new one.")


def request_password_reset(db: Session, email: str, client_ip: str, settings: Settings) -> tuple[User, str] | None:
    """Create a single-use reset token for the account with this email, if there is one.

    Returns (user, token) so the caller can email the link, or None when no account
    matches. Callers must respond identically in both cases.
    """
    email = normalize_email(email)
    throttle = get_reset_throttle()
    keys = (f"email:{email}", f"ip:{client_ip}")
    throttle.check(*keys)
    throttle.fail(*keys)  # every request counts toward the limit, not just failures

    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.disabled_at is not None:
        return None
    # Only the newest link works: older unused links are invalidated.
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)))
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=utcnow() + timedelta(minutes=settings.password_reset_minutes),
        )
    )
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < utcnow()))
    db.commit()
    return user, token


def _valid_reset(db: Session, token: str) -> PasswordResetToken:
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _token_hash(token)))
    if reset is None or reset.used_at is not None or reset.expires_at < utcnow():
        raise InvalidResetToken()
    return reset


def check_reset_token(db: Session, token: str) -> User:
    """The account a still-valid reset token belongs to (raises if it isn't valid)."""
    return _valid_reset(db, token).user


def reset_password(db: Session, token: str, new_password: str) -> User:
    """Set a new password with a reset token. Signs the account out everywhere."""
    reset = _valid_reset(db, token)
    validate_password(new_password)
    user = reset.user
    user.password_hash = _hasher.hash(new_password)
    # The link arrived in their inbox, which also confirms the address.
    user.email_verified_at = user.email_verified_at or utcnow()
    reset.used_at = utcnow()
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.id != reset.id))
    db.commit()
    get_throttle().reset(f"email:{user.email}")
    return user
