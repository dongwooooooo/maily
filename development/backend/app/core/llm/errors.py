class LLMError(Exception):
    retryable: bool = False


class LLMAuthError(LLMError):
    retryable = False


class LLMRateLimitError(LLMError):
    retryable = True

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMTransientError(LLMError):
    retryable = True


class LLMInvalidRequestError(LLMError):
    retryable = False


class LLMRefusalError(LLMError):
    retryable = False
