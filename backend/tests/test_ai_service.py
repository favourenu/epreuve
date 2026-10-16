import asyncio

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.services.ai.providers import ProviderError
from app.services.ai.service import AIService, AIUnavailableError, build_providers, extract_json
from tests.conftest import FakeProvider


class Out(BaseModel):
    value: int


@pytest.mark.parametrize(
    "raw",
    [
        '{"value": 1}',
        '```json\n{"value": 1}\n```',
        '<think>let me reason {"value": 99}</think>{"value": 1}',
        'Sure! Here is the JSON:\n{"value": 1}\nHope that helps.',
    ],
)
def test_extract_json_handles_common_model_output(raw):
    assert extract_json(raw) == {"value": 1}


def test_extract_json_rejects_non_json():
    with pytest.raises(ValueError):
        extract_json("I cannot help with that.")


def test_falls_back_to_next_provider_on_error():
    first = FakeProvider("first", error=ProviderError("first: HTTP 429"))
    second = FakeProvider("second", reply='{"value": 7}')
    result, name = asyncio.run(AIService([first, second]).generate("s", "u", Out))
    assert (result.value, name) == (7, "second")


def test_falls_back_on_invalid_output_and_failed_check():
    bad_json = FakeProvider("a", reply="not json")
    wrong_shape = FakeProvider("b", reply='{"other": 1}')
    fails_check = FakeProvider("c", reply='{"value": -1}')
    good = FakeProvider("d", reply='{"value": 3}')

    def check(out: Out):
        if out.value < 0:
            raise ValueError("negative")

    result, name = asyncio.run(
        AIService([bad_json, wrong_shape, fails_check, good]).generate("s", "u", Out, check=check)
    )
    assert (result.value, name) == (3, "d")


def test_raises_with_all_errors_when_every_provider_fails():
    providers = [FakeProvider("a", error=ProviderError("a: down")), FakeProvider("b", reply="nope")]
    with pytest.raises(AIUnavailableError) as exc:
        asyncio.run(AIService(providers).generate("s", "u", Out))
    assert len(exc.value.errors) == 2


def test_build_providers_respects_order_and_skips_unconfigured():
    settings = Settings(
        openrouter_api_key="", gemini_api_key="g", ollama_enabled=True,
        ai_provider_order=["ollama", "openrouter", "gemini"],
    )
    assert [p.name for p in build_providers(settings)] == ["ollama", "gemini"]
