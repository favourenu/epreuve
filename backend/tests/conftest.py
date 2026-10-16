import os
import tempfile
from pathlib import Path

# Configure before the app (and its engine) is imported.
_tmp = Path(tempfile.mkdtemp(prefix="assess-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["CODE_RUN_TIMEOUT_SECONDS"] = "2"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OLLAMA_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_ai_service  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai.service import AIService  # noqa: E402


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


@pytest.fixture
def client(ai):
    with TestClient(app) as c:
        yield c
