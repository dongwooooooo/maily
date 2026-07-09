import structlog

from app.core.llm.port import LLMRequest, LLMResult

_log = structlog.get_logger("app.core.llm")


def log_completion(request: LLMRequest, result: LLMResult, latency_ms: float) -> None:
    _log.info(
        "llm.complete",
        model=request.model,
        model_name=result.model_name,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        finish_reason=result.finish_reason,
        latency_ms=round(latency_ms, 1),
        message_roles=[m.role for m in request.messages],
        has_output_schema=request.output_schema is not None,
    )
