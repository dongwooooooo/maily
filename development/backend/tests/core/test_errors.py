import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import errors
from app.core.error_handlers import maily_error_handler, unhandled_exception_handler
from app.core.errors import MailyError


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(MailyError, maily_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/boom/{error_type}")
    async def boom(error_type: str):
        exception_classes = {
            "not_found": errors.NotFoundError,
            "conflict": errors.ConflictError,
            "validation": errors.ValidationError,
            "unauthorized": errors.UnauthorizedError,
            "forbidden": errors.ForbiddenError,
            "external": errors.ExternalServiceError,
            "config": errors.ConfigurationError,
        }
        raise exception_classes[error_type]("something went wrong")

    @app.get("/unhandled")
    async def unhandled():
        raise ValueError("a secret internal detail")

    return app


@pytest.mark.parametrize(
    ("error_type", "expected_status", "expected_code"),
    [
        ("not_found", 404, "not_found"),
        ("conflict", 409, "conflict"),
        ("validation", 422, "validation_error"),
        ("unauthorized", 401, "unauthorized"),
        ("forbidden", 403, "forbidden"),
        ("external", 502, "external_service_error"),
        ("config", 500, "internal_error"),
    ],
)
def test_maily_error_maps_to_expected_status_and_body(
    error_type: str, expected_status: int, expected_code: str
) -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get(f"/boom/{error_type}")

    assert response.status_code == expected_status
    body = response.json()
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"] == "something went wrong"
    assert "request_id" in body["error"]


def test_unhandled_exception_returns_generic_500_without_leaking_details() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "Internal server error"
    assert "a secret internal detail" not in response.text
