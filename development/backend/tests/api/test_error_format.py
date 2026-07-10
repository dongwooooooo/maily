"""PR B2 — 에러 응답 형식 단일화.

프론트 에러 파서가 `{"error": {code, message, request_id, details?}}` 한 가지
형태만 처리하도록, FastAPI 기본 RequestValidationError(`{"detail": [...]}`)도
같은 봉투로 변환한다. OpenAPI에는 ErrorResponse 컴포넌트로 문서화한다.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.error_handlers import (
    maily_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from app.core.errors import ConflictError, MailyError
from app.core.logging import RequestContextMiddleware
from app.main import app

client = TestClient(app)


def _mini_app_client() -> TestClient:
    """운영 app과 같은 미들웨어·핸들러 배선의 격리 앱.

    강제 예외 라우트를 운영 app에 등록하면 OpenAPI 메타데이터 테스트
    (2xx 스키마 가드)를 오염시키므로 별도 앱에서 배선만 재현한다.
    """
    mini = FastAPI()
    mini.add_middleware(RequestContextMiddleware)
    mini.add_exception_handler(MailyError, maily_error_handler)
    mini.add_exception_handler(RequestValidationError, request_validation_error_handler)
    mini.add_exception_handler(Exception, unhandled_exception_handler)

    @mini.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("unexpected")

    @mini.get("/conflict")
    async def conflict() -> dict:
        raise ConflictError("이미 처리된 요청", details={"command_id": "abc"})

    return TestClient(mini, raise_server_exceptions=False)


def test_request_validation_error_uses_error_envelope() -> None:
    # /auth/google/callback은 인증 의존성이 없어 body 검증 실패를 그대로 노출한다.
    response = client.post("/auth/google/callback", json={})

    assert response.status_code == 422
    body = response.json()
    assert "detail" not in body
    error = body["error"]
    assert error["code"] == "validation_error"
    assert error["message"]
    assert "request_id" in error
    assert isinstance(error["details"], list)
    assert any("id_token" in str(item.get("loc", [])) for item in error["details"])


def test_validation_details_never_echo_user_input() -> None:
    # id_token은 크리덴셜 — 타입 검증 실패 시 Pydantic error dict의 input/ctx에
    # 원문이 담기므로, 응답 어디에도 그 값이 나가면 안 된다.
    secret_like = 1234567890
    response = client.post("/auth/google/callback", json={"id_token": secret_like})

    assert response.status_code == 422
    assert str(secret_like) not in response.text
    for item in response.json()["error"]["details"]:
        assert "input" not in item
        assert "ctx" not in item


def test_openapi_documents_error_response_on_every_api_route() -> None:
    schema = app.openapi()
    api_paths = [path for path in schema["paths"] if path not in ("/health", "/ready")]
    assert api_paths
    methods = {"get", "post", "put", "patch", "delete"}
    for path in api_paths:
        for method, operation in schema["paths"][path].items():
            if method not in methods:
                continue
            for status in ("422", "default"):
                ref = operation["responses"][status]["content"]["application/json"]["schema"][
                    "$ref"
                ]
                assert ref.endswith("/ErrorResponse"), (path, method, status, ref)
    component = schema["components"]["schemas"]["ErrorResponse"]
    assert "error" in component["properties"]


def test_maily_error_body_matches_error_response_schema() -> None:
    # Authorization 헤더 없는 보호 엔드포인트 → UnauthorizedError(MailyError 계열).
    # 검증 에러와 도메인 에러가 같은 봉투를 쓰는지 회귀 확인.
    response = client.get("/auth/session")

    assert response.status_code == 401
    error = response.json()["error"]
    assert set(error) <= {"code", "message", "request_id", "details"}
    assert error["code"] == "unauthorized"


def test_maily_error_details_pass_through_to_body() -> None:
    response = _mini_app_client().get("/conflict")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"] == {"command_id": "abc"}


def test_unhandled_exception_keeps_request_id_header() -> None:
    # Exception(500) 핸들러는 ServerErrorMiddleware(사용자 미들웨어 바깥)에서
    # 돌아 RequestContextMiddleware의 헤더 부착이 생략된다 — 핸들러가 직접
    # 붙이는지 확인.
    response = _mini_app_client().get("/boom", headers={"X-Request-Id": "rid-123"})

    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "rid-123"
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["request_id"] == "rid-123"
    assert error["message"] == "Internal server error"
