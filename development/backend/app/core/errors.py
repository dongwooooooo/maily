class MailyError(Exception):
    """모든 domain-thrown exception의 base.

    service/repository layer는 이 class를 직접 raise하지 않고 concrete subclass를 raise한다.
    전체 exception table과 각 exception 사용 시점은
    docs/areas/backend/error-handling-and-logging.md 참고.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(MailyError):
    status_code = 404
    error_code = "not_found"


class ConflictError(MailyError):
    status_code = 409
    error_code = "conflict"


class ValidationError(MailyError):
    status_code = 422
    error_code = "validation_error"


class UnauthorizedError(MailyError):
    status_code = 401
    error_code = "unauthorized"


class ForbiddenError(MailyError):
    status_code = 403
    error_code = "forbidden"


class ExternalServiceError(MailyError):
    status_code = 502
    error_code = "external_service_error"


class ConfigurationError(MailyError):
    status_code = 500
    error_code = "internal_error"
