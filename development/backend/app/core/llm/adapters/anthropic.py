import time

import anthropic

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import FinishReason, LLMRequest, LLMResult, TokenUsage

_TOOL_NAME = "emit"


def _map_error(exc: Exception) -> LLMError:
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LLMAuthError(str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return LLMTransientError(str(exc))
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return LLMTransientError(str(exc))
    if isinstance(exc, anthropic.APIStatusError) and 400 <= exc.status_code < 500:
        return LLMInvalidRequestError(str(exc))
    return LLMTransientError(str(exc))


class AnthropicAdapter:
    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        kwargs: dict = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system is not None:
            kwargs["system"] = request.system
        if request.output_schema is not None:
            kwargs["tools"] = [
                {
                    "name": _TOOL_NAME,
                    "description": "Return the structured result.",
                    "input_schema": request.output_schema.model_json_schema(),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": _TOOL_NAME}

        try:
            resp = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise _map_error(exc) from exc

        usage = TokenUsage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
        if request.output_schema is not None:
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if block is None:
                if resp.stop_reason == "refusal":
                    raise LLMRefusalError("structured output request was refused")
                raise LLMInvalidRequestError(
                    "structured output returned no tool_use block "
                    f"(stop_reason={resp.stop_reason})"
                )
            result = LLMResult(
                parsed=request.output_schema.model_validate(block.input),
                model_name=resp.model,
                usage=usage,
                finish_reason=_STOP_REASON.get(resp.stop_reason, "stop"),
            )
        else:
            text = next((b.text for b in resp.content if b.type == "text"), "")
            result = LLMResult(
                text=text,
                model_name=resp.model,
                usage=usage,
                finish_reason=_STOP_REASON.get(resp.stop_reason, "stop"),
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result


_STOP_REASON: dict[str, FinishReason] = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool",
    "refusal": "refusal",
    "stop_sequence": "stop",
}
