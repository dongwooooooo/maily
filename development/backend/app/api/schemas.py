"""API 공용 응답 스키마 — 에러 봉투.

모든 에러는 `{"error": {code, message, request_id, details?}}` 한 가지 형태다
(docs/goals/backend-plans/_integration-contract.md). MailyError 계열과
RequestValidationError 모두 app/core/error_handlers.py에서 이 봉투로 변환된다.
"""

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    # 검증 에러(RequestValidationError)는 list[dict](Pydantic 위치 정보),
    # 도메인 에러(MailyError.details)는 dict — 두 경로가 같은 필드를 쓴다.
    details: list[dict] | dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
