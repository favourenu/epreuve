"""Keep a free Render service awake.

Render puts free web services to sleep after 15 minutes without inbound requests,
and the next visitor then waits up to a minute. While the server runs, this task
requests the site's own public URL on a timer. The request goes out through
Render's proxy, so it counts as traffic. A GitHub Actions workflow
(.github/workflows/keep-awake.yml) pings from outside too, as a backup that can
also wake the service if it ever does fall asleep.
"""

import asyncio
import logging
import os

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def ping_url() -> str | None:
    s = get_settings()
    if not s.keep_awake:
        return None
    base = os.environ.get("RENDER_EXTERNAL_URL") or s.app_base_url
    if not base.startswith("https://"):
        return None  # only meaningful for a public deployment
    return f"{base.rstrip('/')}/api/health"


async def _loop(url: str, interval: float) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            await asyncio.sleep(interval)
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    log.warning("Keep-awake ping got HTTP %s", resp.status_code)
            except httpx.HTTPError as exc:
                log.warning("Keep-awake ping failed: %s", exc)


def start() -> asyncio.Task | None:
    url = ping_url()
    if url is None:
        return None
    interval = get_settings().keep_awake_minutes * 60
    log.info("Keep-awake: pinging %s every %.0f minutes", url, interval / 60)
    return asyncio.create_task(_loop(url, interval))
