import time

import openai

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import LLMRequest, LLMResult, TokenUsage

_FINISH = {
    "stop": "stop",
    "length": "length",
    "content_filter": "refusal",
    "tool_calls": "tool",
}


def _map_error(exc: Exception) -> LLMError:
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMAuthError(str(exc))
    if isinstance(exc, openai.RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, openai.BadRequestError):
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return LLMTransientError(str(exc))
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return LLMTransientError(str(exc))
    return LLMTransientError(str(exc))


class OpenAIAdapter:
    def __init__(self, client: openai.AsyncOpenAI) -> None:
        self._client = client

    def _messages(self, request: LLMRequest) -> list[dict]:
        msgs: list[dict] = []
        if request.system is not None:
            msgs.append({"role": "system", "content": request.system})
        msgs.extend({"role": m.role, "content": m.content} for m in request.messages)
        return msgs

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        common = {
            "model": request.model,
            "messages": self._messages(request),
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        try:
            if request.output_schema is not None:
                resp = await self._client.chat.completions.parse(
                    response_format=request.output_schema, **common
                )
            else:
                resp = await self._client.chat.completions.create(**common)
        except openai.APIError as exc:
            raise _map_error(exc) from exc

        choice = resp.choices[0]
        usage = TokenUsage(
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )
        if request.output_schema is not None:
            if getattr(choice.message, "refusal", None):
                raise LLMRefusalError(choice.message.refusal)
            result = LLMResult(
                parsed=choice.message.parsed,
                model_name=resp.model,
                usage=usage,
                finish_reason="stop",
            )
        else:
            result = LLMResult(
                text=choice.message.content or "",
                model_name=resp.model,
                usage=usage,
                finish_reason=_FINISH.get(choice.finish_reason, "stop"),
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result
