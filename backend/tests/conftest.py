import os
import tempfile
from pathlib import Path

# Configure before the app (and its engine) is imported.
_tmp = Path(tempfile.mkdtemp(prefix="epreuve-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["CODE_RUN_TIMEOUT_SECONDS"] = "2"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OLLAMA_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_ai_service  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai.service import AIService  # noqa: E402
from app.services.auth import get_throttle  # noqa: E402

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
    yield
    get_throttle.cache_clear()


@pytest.fixture
def anon(ai):
    """A client with no session."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_client(ai):
    """Factory: a new client signed in as a brand-new user."""
    clients = []

    def make(email: str | None = None) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        email = email or f"user{next(_ids)}@example.com"
        r = c.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "name": "Test User"})
        assert r.status_code == 201, r.text
        c.email = email
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    """A client signed in as a fresh user."""
    return make_client()
