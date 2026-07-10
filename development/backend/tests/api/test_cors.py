"""PR B4 — CORS.

프론트(Next.js dev, 127.0.0.1:3000)가 브라우저에서 직접 API를 호출한다.
인증이 Authorization 헤더 기반(쿠키 없음)이라 CORS 허용만으로 충분하며
Next rewrites 프록시는 병행하지 않는다 — _integration-contract.md §6.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ORIGIN = "http://127.0.0.1:3000"


def test_preflight_allows_frontend_origin_and_headers() -> None:
    response = client.options(
        "/briefing/today",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type,Idempotency-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    for header in ("authorization", "content-type", "idempotency-key"):
        assert header in allowed_headers


def test_simple_request_gets_cors_header() -> None:
    response = client.get("/health", headers={"Origin": ORIGIN})

    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_unhandled_500_still_carries_cors_headers() -> None:
    """Exception(500) 핸들러는 ServerErrorMiddleware(최외곽, CORSMiddleware
    바깥)에서 실행돼 CORS 헤더가 누락된다 — 핸들러가 직접 붙이는지 확인.
    누락되면 브라우저가 진짜 500을 CORS 에러로 오인한다."""
    from fastapi import FastAPI

    from app.core.error_handlers import unhandled_exception_handler
    from app.core.logging import RequestContextMiddleware

    mini = FastAPI()
    mini.add_middleware(RequestContextMiddleware)
    mini.add_exception_handler(Exception, unhandled_exception_handler)

    @mini.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("unexpected")

    mini_client = TestClient(mini, raise_server_exceptions=False)
    response = mini_client.get("/boom", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-expose-headers"] == "X-Request-Id"


def test_unknown_origin_not_allowed() -> None:
    response = client.options(
        "/briefing/today",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"
