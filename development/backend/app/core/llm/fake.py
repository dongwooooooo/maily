from app.core.llm.port import LLMRequest, LLMResult, TokenUsage


class FakeLLM:
    def __init__(
        self, text: str = "fake-summary", structured: dict | None = None
    ) -> None:
        self._text = text
        self._structured = structured or {}
        self.last_request: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.last_request = request
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        if request.output_schema is not None:
            return LLMResult(
                parsed=request.output_schema.model_validate(self._structured),
                model_name=request.model,
                usage=usage,
                finish_reason="stop",
            )
        return LLMResult(
            text=self._text,
            model_name=request.model,
            usage=usage,
            finish_reason="stop",
        )
