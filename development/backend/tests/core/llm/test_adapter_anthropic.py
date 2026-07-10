from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.anthropic import AnthropicAdapter
from app.core.llm.errors import (
    LLMAuthError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
)


class _Band(BaseModel):
    band: str
    reason: str


def _text_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="a summary")],
        stop_reason="end_turn",
        model="claude-sonnet-5-2026",
        usage=SimpleNamespace(input_tokens=11, output_tokens=4),
    )


def _tool_response():
    tool_input = {"band": "urgent", "reason": "boss"}
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="emit", input=tool_input)],
        stop_reason="tool_use",
        model="claude-sonnet-5-2026",
        usage=SimpleNamespace(input_tokens=11, output_tokens=4),
    )


def _no_tool_response(stop_reason: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="")],
        stop_reason=stop_reason,
        model="claude-sonnet-5-2026",
        usage=SimpleNamespace(input_tokens=11, output_tokens=4),
    )


def _req(**kw):
    messages = [LLMMessage(role="user", content="hi")]
    return LLMRequest(model="claude-sonnet-5", messages=messages, **kw)


@pytest.mark.asyncio
async def test_text_completion_maps_result():
    create = AsyncMock(return_value=_text_response())
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    adapter = AnthropicAdapter(client)
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.parsed is None
    assert result.model_name == "claude-sonnet-5-2026"
    assert result.usage.input_tokens == 11
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion_returns_parsed():
    create = AsyncMock(return_value=_tool_response())
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    adapter = AnthropicAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    assert result.finish_reason == "tool"
    # forced tool_choice was sent
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"]["name"] == "emit"
    assert kwargs["tools"][0]["input_schema"]["properties"]["band"]


@pytest.mark.asyncio
async def test_structured_refusal_with_no_tool_use_raises_refusal():
    create = AsyncMock(return_value=_no_tool_response("refusal"))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMRefusalError):
        await adapter.complete(_req(output_schema=_Band))


@pytest.mark.asyncio
async def test_structured_truncated_with_no_tool_use_raises_invalid_request():
    create = AsyncMock(return_value=_no_tool_response("max_tokens"))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMInvalidRequestError):
        await adapter.complete(_req(output_schema=_Band))


@pytest.mark.asyncio
async def test_not_found_maps_to_invalid_request_not_transient():
    import anthropic

    err = anthropic.NotFoundError.__new__(anthropic.NotFoundError)
    Exception.__init__(err, "404")
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=err)))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMInvalidRequestError):
        await adapter.complete(_req())


@pytest.mark.asyncio
async def test_rate_limit_maps_to_typed_error():
    import anthropic

    err = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    Exception.__init__(err, "429")
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=err)))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMRateLimitError):
        await adapter.complete(_req())


@pytest.mark.asyncio
async def test_auth_error_maps_to_typed_error():
    import anthropic

    err = anthropic.AuthenticationError.__new__(anthropic.AuthenticationError)
    Exception.__init__(err, "401")
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=err)))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMAuthError):
        await adapter.complete(_req())
