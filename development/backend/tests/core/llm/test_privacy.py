import structlog

from app.core.llm import LLMMessage, LLMRequest, LLMResult, TokenUsage
from app.core.llm.observability import log_completion


def test_log_completion_excludes_content(capsys):
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    sensitive_body = "SENSITIVE-BODY-TEXT"
    req = LLMRequest(
        model="m",
        system="SECRET-SYSTEM",
        messages=[LLMMessage(role="user", content=sensitive_body)],
    )
    result = LLMResult(
        text="SECRET-OUTPUT",
        model_name="m-2026",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        finish_reason="stop",
    )

    log_completion(req, result, latency_ms=12.3)

    out = capsys.readouterr().out
    assert "llm.complete" in out
    assert "m-2026" in out
    assert "SENSITIVE-BODY-TEXT" not in out
    assert "SECRET-SYSTEM" not in out
    assert "SECRET-OUTPUT" not in out
    assert '"input_tokens": 10' in out or '"input_tokens":10' in out
