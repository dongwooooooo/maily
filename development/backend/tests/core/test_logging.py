from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import RequestContextMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_generates_request_id_when_client_sends_none() -> None:
    client = TestClient(_make_app())

    response = client.get("/ping")

    assert response.headers["X-Request-Id"]


def test_echoes_back_client_supplied_request_id() -> None:
    client = TestClient(_make_app())

    response = client.get("/ping", headers={"X-Request-Id": "client-supplied-id-123"})

    assert response.headers["X-Request-Id"] == "client-supplied-id-123"


def test_different_requests_get_different_generated_ids() -> None:
    client = TestClient(_make_app())

    first = client.get("/ping")
    second = client.get("/ping")

    assert first.headers["X-Request-Id"] != second.headers["X-Request-Id"]
