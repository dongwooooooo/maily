from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.gemini import GeminiAdapter
from app.core.llm.errors import LLMAuthError, LLMTransientError


class _Band(BaseModel):
    band: str
    reason: str


def _response(text=None, parsed=None, finish="STOP"):
    return SimpleNamespace(
        text=text,
        parsed=parsed,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        usage_metadata=SimpleNamespace(prompt_token_count=8, candidates_token_count=2),
        model_version="gemini-2.5-pro-2026",
    )


def _client(response=None, side_effect=None):
    if side_effect is None:
        gen = AsyncMock(return_value=response)
    else:
        gen = AsyncMock(side_effect=side_effect)
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))


def _req(**kw):
    messages = [LLMMessage(role="user", content="hi")]
    return LLMRequest(model="gemini-2.5-pro", messages=messages, **kw)


@pytest.mark.asyncio
async def test_text_completion():
    adapter = GeminiAdapter(_client(_response(text="a summary")))
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.model_name == "gemini-2.5-pro-2026"
    assert result.usage.output_tokens == 2
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion():
    client = _client(_response(parsed=_Band(band="urgent", reason="boss")))
    adapter = GeminiAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    kwargs = client.aio.models.generate_content.call_args.kwargs
    assert kwargs["config"].response_schema is _Band
    assert kwargs["config"].response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_max_tokens_maps_to_length():
    adapter = GeminiAdapter(_client(_response(text="partial", finish="MAX_TOKENS")))
    result = await adapter.complete(_req())
    assert result.finish_reason == "length"


@pytest.mark.asyncio
async def test_client_error_maps():
    from google.genai import errors

    err = errors.ClientError.__new__(errors.ClientError)
    Exception.__init__(err, "403 forbidden")
    err.code = 403
    adapter = GeminiAdapter(_client(side_effect=err))
    with pytest.raises(LLMAuthError):
        await adapter.complete(_req())


@pytest.mark.asyncio
async def test_server_error_maps_transient():
    from google.genai import errors

    err = errors.ServerError.__new__(errors.ServerError)
    Exception.__init__(err, "503")
    err.code = 503
    adapter = GeminiAdapter(_client(side_effect=err))
    with pytest.raises(LLMTransientError):
        await adapter.complete(_req())
