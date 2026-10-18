import os
import re
import tempfile
from pathlib import Path

# Configure before the app (and its engine) is imported.
_tmp = Path(tempfile.mkdtemp(prefix="epreuve-test-"))
# These must be set before anything imports app.config (settings are cached).
os.environ["CODE_RUN_TIMEOUT_SECONDS"] = "2"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OLLAMA_ENABLED"] = "false"
os.environ["PAYSTACK_SECRET_KEY"] = ""  # tests never use real payment keys; see test_payments.py
os.environ["ADMIN_EMAILS"] = "[]"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
# Set TEST_DATABASE_URL to run the whole suite against Postgres instead (its schema is wiped).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(_tmp / 'test.db').as_posix()}"
if os.environ.get("TEST_DATABASE_URL"):
    from sqlalchemy import create_engine, text

    from app.db import normalize_url

    with create_engine(normalize_url(os.environ["TEST_DATABASE_URL"])).begin() as _conn:
        _conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_ai_service  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai.service import AIService  # noqa: E402
from app.services.auth import get_reset_throttle, get_throttle  # noqa: E402
from app.services.email import get_email_sender  # noqa: E402

PASSWORD = "correct-horse-battery"
_ids = itertools.count()


class FakeProvider:
    """Returns a scripted reply, or raises, and records the prompts it received."""

    def __init__(self, name="fake", reply=None, error: Exception | None = None):
        self.name, self.reply, self.error = name, reply, error
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.reply(user) if callable(self.reply) else self.reply


@pytest.fixture
def ai():
    service = AIService([])
    app.dependency_overrides[get_ai_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_ai_service, None)


@pytest.fixture(autouse=True)
def fresh_login_throttle():
    get_throttle.cache_clear()
    get_reset_throttle.cache_clear()
    yield
    get_throttle.cache_clear()
    get_reset_throttle.cache_clear()


class OutboxSender:
    """Captures emails instead of sending them."""

    def __init__(self):
        self.sent = []

    def send(self, email):
        self.sent.append(email)


@pytest.fixture(autouse=True)
def outbox():
    box = OutboxSender()
    app.dependency_overrides[get_email_sender] = lambda: box
    yield box
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture
def anon(ai):
    """A client with no session."""
    with TestClient(app) as c:
        yield c


def latest_code(outbox, email: str) -> str:
    """The confirmation code in the newest email sent to this address."""
    mail = next(m for m in reversed(outbox.sent) if m.to == email and "confirmation code" in m.subject)
    return re.match(r"(\d{6}) ", mail.subject).group(1)


@pytest.fixture
def make_client(ai, outbox):
    """Factory: a new client signed in as a brand-new user with a confirmed email."""
    clients = []

    def make(email: str | None = None, confirm: bool = True) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        email = email or f"user{next(_ids)}@example.com"
        r = c.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "name": "Test User"})
        assert r.status_code == 201, r.text
        if confirm:
            r = c.post("/api/auth/email/verify", json={"code": latest_code(outbox, email)})
            assert r.status_code == 200 and r.json()["email_verified"], r.text
            outbox.sent.clear()  # tests start with an empty outbox
        c.email = email
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    """A client signed in as a fresh user."""
    return make_client()
