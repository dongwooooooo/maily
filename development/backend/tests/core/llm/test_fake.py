import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMPort, LLMRequest
from app.core.llm.fake import FakeLLM


class _Band(BaseModel):
    band: str
    reason: str


def _req(**kw):
    return LLMRequest(
        model="fake-model", messages=[LLMMessage(role="user", content="x")], **kw
    )


def test_fake_satisfies_port():
    assert isinstance(FakeLLM(), LLMPort)


@pytest.mark.asyncio
async def test_fake_returns_text_when_no_schema():
    fake = FakeLLM(text="hello")
    result = await fake.complete(_req())
    assert result.text == "hello"
    assert result.parsed is None
    assert result.model_name == "fake-model"
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_returns_parsed_schema_instance():
    fake = FakeLLM(structured={"band": "urgent", "reason": "boss"})
    result = await fake.complete(_req(output_schema=_Band))
    assert isinstance(result.parsed, _Band)
    assert result.parsed.band == "urgent"
    assert result.text is None


@pytest.mark.asyncio
async def test_fake_is_deterministic_and_records_request():
    fake = FakeLLM(text="same")
    r1 = await fake.complete(_req())
    r2 = await fake.complete(_req())
    assert r1.text == r2.text == "same"
    assert fake.last_request is not None
    assert fake.last_request.model == "fake-model"
