from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.openai import OpenAIAdapter
from app.core.llm.errors import LLMInvalidRequestError, LLMRefusalError


class _Band(BaseModel):
    band: str
    reason: str


def _choice(message, finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        model="gpt-5-2026",
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3),
    )


def _req(**kw):
    return LLMRequest(model="gpt-5", messages=[LLMMessage(role="user", content="hi")], **kw)


@pytest.mark.asyncio
async def test_text_completion():
    msg = SimpleNamespace(content="a summary", refusal=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.model_name == "gpt-5-2026"
    assert result.usage.output_tokens == 3
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion():
    msg = SimpleNamespace(parsed=_Band(band="urgent", reason="boss"), refusal=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    kwargs = client.chat.completions.parse.call_args.kwargs
    assert kwargs["response_format"] is _Band


@pytest.mark.asyncio
async def test_refusal_raises():
    msg = SimpleNamespace(parsed=None, refusal="I can't help with that")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    with pytest.raises(LLMRefusalError):
        await adapter.complete(_req(output_schema=_Band))


@pytest.mark.asyncio
async def test_bad_request_maps():
    import openai

    err = openai.BadRequestError.__new__(openai.BadRequestError)
    Exception.__init__(err, "400")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=err)))
    )
    adapter = OpenAIAdapter(client)
    with pytest.raises(LLMInvalidRequestError):
        await adapter.complete(_req())
