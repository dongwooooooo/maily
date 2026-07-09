class MailyError(Exception):
    """Base for every domain-thrown exception.

    Service/repository layers raise a concrete subclass, never this
    class directly — see docs/areas/backend/error-handling-and-logging.md
    for the full exception table and when to use each one.
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
