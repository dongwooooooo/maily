import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import FinishReason, LLMRequest, LLMResult, TokenUsage

_FINISH: dict[str, FinishReason] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "refusal",
    "RECITATION": "refusal",
}
_ROLE = {"user": "user", "assistant": "model"}


def _map_error(exc: Exception) -> LLMError:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return LLMAuthError(str(exc))
    if code == 429:
        return LLMRateLimitError(str(exc))
    if code == 400:
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, errors.ServerError) or (isinstance(code, int) and code >= 500):
        return LLMTransientError(str(exc))
    return LLMTransientError(str(exc))


class GeminiAdapter:
    def __init__(self, client: genai.Client) -> None:
        self._client = client

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        contents = [
            types.Content(role=_ROLE[m.role], parts=[types.Part(text=m.content)])
            for m in request.messages
        ]
        config_kwargs: dict = {
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.system is not None:
            config_kwargs["system_instruction"] = request.system
        if request.output_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = request.output_schema

        try:
            resp = await self._client.aio.models.generate_content(
                model=request.model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except errors.APIError as exc:
            raise _map_error(exc) from exc

        usage_metadata = resp.usage_metadata
        input_tokens = usage_metadata.prompt_token_count if usage_metadata else None
        output_tokens = usage_metadata.candidates_token_count if usage_metadata else None
        usage = TokenUsage(input_tokens=input_tokens or 0, output_tokens=output_tokens or 0)

        candidates = resp.candidates or []
        finish_reason_obj = candidates[0].finish_reason if candidates else None
        finish_name = finish_reason_obj.name if finish_reason_obj else None
        finish_reason: FinishReason = (
            _FINISH.get(finish_name, "stop") if finish_name is not None else "stop"
        )
        model_name = resp.model_version or request.model

        if request.output_schema is not None:
            parsed = resp.parsed
            if parsed is not None and not isinstance(parsed, BaseModel):
                raise LLMError(f"unexpected non-BaseModel parsed result: {type(parsed)!r}")
            result = LLMResult(
                parsed=parsed,
                model_name=model_name,
                usage=usage,
                finish_reason="stop",
            )
        else:
            result = LLMResult(
                text=resp.text or "",
                model_name=model_name,
                usage=usage,
                finish_reason=finish_reason,
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result
