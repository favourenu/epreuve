import json
import logging
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.services.ai.providers import LLMProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AIUnavailableError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("No AI provider could complete the request: " + " | ".join(errors) if errors
                         else "No AI provider is configured")


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply that may include fences or reasoning."""
    text = _THINK_RE.sub("", text).strip()
    text = _FENCE_RE.sub("", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in model output") from None
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output is JSON but not an object")
    return value


class AIService:
    """Tries each configured provider in order until one returns valid output."""

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers

    async def generate(
        self,
        system: str,
        user: str,
        schema: type[T],
        check: Callable[[T], None] | None = None,
    ) -> tuple[T, str]:
        """Return validated output and the name of the provider that produced it.

        `check` can raise ValueError to reject output that is well-formed but
        incomplete, which moves on to the next provider.
        """
        errors: list[str] = []
        for provider in self.providers:
            try:
                raw = await provider.complete(system, user)
                result = schema.model_validate(extract_json(raw))
                if check:
                    check(result)
                return result, provider.name
            except ProviderError as exc:
                errors.append(str(exc))
            except (ValueError, ValidationError) as exc:
                errors.append(f"{provider.name}: invalid output ({str(exc)[:200]})")
            log.warning("AI provider failed, trying next: %s", errors[-1])
        raise AIUnavailableError(errors)


def build_providers(settings: Settings) -> list[LLMProvider]:
    available: dict[str, LLMProvider] = {}
    timeout = settings.ai_request_timeout_seconds
    if settings.openrouter_api_key:
        available["openrouter"] = OpenAICompatibleProvider(
            name="openrouter",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            timeout=timeout,
            # Not every free model supports response_format; we parse JSON from text instead.
            json_mode=False,
            extra_headers={"X-Title": "Epreuve"},
        )
    if settings.gemini_api_key:
        available["gemini"] = OpenAICompatibleProvider(
            name="gemini",
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=timeout,
        )
    if settings.ollama_enabled:
        available["ollama"] = OllamaProvider(
            base_url=settings.ollama_base_url.rstrip("/"),
            model=settings.ollama_model,
            timeout=settings.ollama_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
        )
    return [available[name] for name in settings.ai_provider_order if name in available]
