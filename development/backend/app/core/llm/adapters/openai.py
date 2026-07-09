import time
from typing import cast

import openai
from openai.types.chat import ChatCompletionMessageParam

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

_FINISH: dict[str, FinishReason] = {
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

    def _messages(self, request: LLMRequest) -> list[ChatCompletionMessageParam]:
        msgs: list[ChatCompletionMessageParam] = []
        if request.system is not None:
            system_msg = {"role": "system", "content": request.system}
            msgs.append(cast(ChatCompletionMessageParam, system_msg))
        msgs.extend(
            cast(ChatCompletionMessageParam, {"role": m.role, "content": m.content})
            for m in request.messages
        )
        return msgs

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        model = request.model
        messages = self._messages(request)
        max_tokens = request.max_output_tokens
        temperature = request.temperature
        try:
            if request.output_schema is not None:
                parsed_resp = await self._client.chat.completions.parse(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format=request.output_schema,
                )
                choice = parsed_resp.choices[0]
                usage_data = parsed_resp.usage
                usage = TokenUsage(
                    input_tokens=usage_data.prompt_tokens if usage_data else 0,
                    output_tokens=usage_data.completion_tokens if usage_data else 0,
                )
                if getattr(choice.message, "refusal", None):
                    raise LLMRefusalError(choice.message.refusal)
                result = LLMResult(
                    parsed=choice.message.parsed,
                    model_name=parsed_resp.model,
                    usage=usage,
                    finish_reason="stop",
                )
            else:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                text_choice = resp.choices[0]
                usage_data = resp.usage
                usage = TokenUsage(
                    input_tokens=usage_data.prompt_tokens if usage_data else 0,
                    output_tokens=usage_data.completion_tokens if usage_data else 0,
                )
                result = LLMResult(
                    text=text_choice.message.content or "",
                    model_name=resp.model,
                    usage=usage,
                    finish_reason=_FINISH.get(text_choice.finish_reason, "stop"),
                )
        except openai.APIError as exc:
            raise _map_error(exc) from exc

        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result
