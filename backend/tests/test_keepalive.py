import asyncio

import httpx

from app import keepalive
from app.config import get_settings


def test_off_unless_enabled_on_a_public_https_url(monkeypatch):
    s = get_settings()
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://epreuve.onrender.com")
    monkeypatch.setattr(s, "keep_awake", False)
    assert keepalive.ping_url() is None

    monkeypatch.setattr(s, "keep_awake", True)
    assert keepalive.ping_url() == "https://epreuve.onrender.com/api/health"

    monkeypatch.delenv("RENDER_EXTERNAL_URL")
    monkeypatch.setattr(s, "app_base_url", "https://epreuve.site/")
    assert keepalive.ping_url() == "https://epreuve.site/api/health"

    monkeypatch.setattr(s, "app_base_url", "http://localhost:5173")
    assert keepalive.ping_url() is None


def test_pings_repeatedly_and_survives_failures(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"status": "ok"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        keepalive.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )

    async def run():
        task = asyncio.create_task(keepalive._loop("https://x.test/api/health", 0.01))
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 3 and set(calls) == {"https://x.test/api/health"}
