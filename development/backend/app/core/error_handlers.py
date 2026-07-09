import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import MailyError

logger = structlog.get_logger()


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def maily_error_handler(request: Request, exc: MailyError) -> JSONResponse:
    request_id = _request_id(request)
    log = logger.bind(request_id=request_id, error_code=exc.error_code)
    if exc.status_code >= 500:
        log.error("domain_error", message=str(exc), details=exc.details)
    else:
        log.warning("domain_error", message=str(exc), details=exc.details)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error("unhandled_exception", request_id=request_id, exc_info=exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": request_id,
            }
        },
    )
