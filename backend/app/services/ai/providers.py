"""LLM providers behind one small interface.

OpenRouter and Gemini both expose OpenAI-compatible chat endpoints, so one class
covers them. Ollama uses its native API, which lets us turn off "thinking" output
for reasoning models such as qwen3 and request strict JSON.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class ProviderError(Exception):
    """A provider failed in a way that should trigger fallback to the next one."""


class LLMProvider(Protocol):
    name: str

    async def complete(self, system: str, user: str) -> str: ...


@dataclass
class OpenAICompatibleProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    json_mode: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    # OpenRouter only: models to try, in order, if the main one is unavailable.
    fallback_models: list[str] = field(default_factory=list)

    async def complete(self, system: str, user: str) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.fallback_models:
            payload["models"] = [self.model, *self.fallback_models]
        headers = {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name}: timed out after {self.timeout:g}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: request failed ({type(exc).__name__}: {exc})") from exc
        if resp.status_code != 200:
            raise ProviderError(f"{self.name}: HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: unexpected response shape: {resp.text[:300]}") from exc
        if not content:
            raise ProviderError(f"{self.name}: empty response")
        return content


@dataclass
class OllamaProvider:
    base_url: str  # e.g. http://localhost:11434 (no /v1)
    model: str
    timeout: float
    num_ctx: int = 8192
    name: str = "ollama"
    # A local model handles one request at a time; queue ours instead of letting
    # concurrent reports slow each other down until they all time out.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            # Ollama's default context (often 4096) can silently truncate long prompts.
            "options": {"temperature": 0.2, "num_ctx": self.num_ctx},
        }
        try:
            async with self._lock, httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"ollama: no reply within {self.timeout:g}s; the local model is too slow on this machine"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama: not reachable at {self.base_url} ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise ProviderError(f"ollama: HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            content = resp.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"ollama: unexpected response shape: {resp.text[:300]}") from exc
        if not content:
            raise ProviderError("ollama: empty response")
        return content
