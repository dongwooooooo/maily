import pytest

from app.core.llm import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)


def test_base_defaults_not_retryable():
    assert LLMError().retryable is False


@pytest.mark.parametrize(
    "exc_cls, retryable",
    [
        (LLMAuthError, False),
        (LLMRateLimitError, True),
        (LLMTransientError, True),
        (LLMInvalidRequestError, False),
        (LLMRefusalError, False),
    ],
)
def test_retryable_flags(exc_cls, retryable):
    assert exc_cls().retryable is retryable
    assert isinstance(exc_cls(), LLMError)


def test_rate_limit_carries_retry_after():
    err = LLMRateLimitError("slow down", retry_after=1.5)
    assert err.retry_after == 1.5
    assert err.retryable is True
