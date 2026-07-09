from fastapi.testclient import TestClient

from app.api.deps import get_database_check, get_redis_check
from app.main import app


def test_ready_returns_ok_when_database_and_redis_healthy() -> None:
    app.dependency_overrides[get_database_check] = lambda: True
    app.dependency_overrides[get_redis_check] = lambda: True
    client = TestClient(app)

    response = client.get("/ready")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_ready_returns_error_body_when_database_unhealthy() -> None:
    app.dependency_overrides[get_database_check] = lambda: False
    app.dependency_overrides[get_redis_check] = lambda: True
    client = TestClient(app)

    response = client.get("/ready")

    app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "error", "redis": "ok"},
    }


def test_ready_returns_error_body_when_redis_unhealthy() -> None:
    app.dependency_overrides[get_database_check] = lambda: True
    app.dependency_overrides[get_redis_check] = lambda: False
    client = TestClient(app)

    response = client.get("/ready")

    app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "ok", "redis": "error"},
    }
