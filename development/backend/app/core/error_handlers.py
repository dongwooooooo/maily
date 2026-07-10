import structlog
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import MailyError
from app.core.logging import REQUEST_ID_HEADER

logger = structlog.get_logger()

# Pydantic 검증 에러 항목의 input/ctx에는 사용자가 보낸 원문 값이 그대로 담긴다
# — id_token 같은 크리덴셜 필드가 검증에 실패하면 그 원문이 응답과 로그로
# 유출되므로, 두 키는 응답·로그 어디에도 내보내지 않는다.
_SENSITIVE_VALIDATION_KEYS = frozenset({"input", "ctx"})


def _sanitized_validation_details(exc: RequestValidationError) -> list[dict]:
    return [
        {key: value for key, value in item.items() if key not in _SENSITIVE_VALIDATION_KEYS}
        for item in jsonable_encoder(exc.errors())
    ]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def maily_error_handler(request: Request, exc: MailyError) -> JSONResponse:
    request_id = _request_id(request)
    log = logger.bind(request_id=request_id, error_code=exc.error_code)
    if exc.status_code >= 500:
        log.error("도메인 예외 발생", message=str(exc), details=exc.details)
    else:
        log.warning("도메인 예외 발생", message=str(exc), details=exc.details)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "request_id": request_id,
                "details": jsonable_encoder(exc.details) or None,
            }
        },
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI 기본 응답은 {"detail": [...]} — 프론트 에러 파서가 단일 봉투만
    # 처리하도록 MailyError와 같은 {"error": {...}} 형태로 변환한다.
    # Pydantic 위치 정보는 error.details로 보존한다.
    request_id = _request_id(request)
    details = _sanitized_validation_details(exc)
    logger.warning("요청 검증 실패", request_id=request_id, details=details)

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": request_id,
                "details": details,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error("처리되지 않은 예외 발생", request_id=request_id, exc_info=exc)

    # Exception(500) 핸들러는 Starlette ServerErrorMiddleware(사용자 미들웨어
    # 스택 바깥)에서 실행되므로 RequestContextMiddleware의 헤더 부착 라인이
    # 돌지 않는다 — 유일하게 여기서만 X-Request-Id를 직접 붙여야 한다.
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=500,
        headers=headers,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": request_id,
            }
        },
    )
