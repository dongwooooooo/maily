DEFAULT_MAX_ATTEMPTS = 5


def should_retry(attempt_count: int, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> bool:
    return attempt_count < max_attempts
