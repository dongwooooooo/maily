import pytest
from pydantic import BaseModel

from app.core.llm import (
    LLMMessage,
    LLMPort,
    LLMRequest,
    LLMResult,
    TokenUsage,
)


class _Sample(BaseModel):
    value: str


def test_request_defaults_and_fields():
    req = LLMRequest(model="m", messages=[LLMMessage(role="user", content="hi")])
    assert req.system is None
    assert req.output_schema is None
    assert req.max_output_tokens == 1024
    assert req.temperature == pytest.approx(0.0)
    assert req.metadata == {}


def test_request_accepts_output_schema():
    req = LLMRequest(
        model="m",
        messages=[LLMMessage(role="user", content="hi")],
        output_schema=_Sample,
    )
    assert req.output_schema is _Sample


def test_result_holds_text_or_parsed():
    usage = TokenUsage(input_tokens=1, output_tokens=2)
    text_result = LLMResult(text="ok", model_name="m", usage=usage, finish_reason="stop")
    assert text_result.text == "ok"
    assert text_result.parsed is None

    parsed_result = LLMResult(
        parsed=_Sample(value="v"), model_name="m", usage=usage, finish_reason="stop"
    )
    assert parsed_result.parsed.value == "v"


def test_a_class_can_satisfy_llmport():
    class _Impl:
        async def complete(self, request: LLMRequest) -> LLMResult:
            return LLMResult(
                text="x",
                model_name=request.model,
                usage=TokenUsage(input_tokens=0, output_tokens=0),
                finish_reason="stop",
            )

    impl: LLMPort = _Impl()
    assert isinstance(impl, LLMPort)
