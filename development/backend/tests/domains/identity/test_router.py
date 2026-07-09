from fastapi.testclient import TestClient

from app.domains.identity.router import get_google_profile_verifier
from app.domains.identity.schemas import GoogleProfile
from app.main import app


def _override_verifier(profile: GoogleProfile):
    async def _verify(id_token: str) -> GoogleProfile:
        return profile

    return _verify


def test_google_callback_creates_session_and_get_session_returns_summary() -> None:
    profile = GoogleProfile(
        google_subject="router-test-subject", email="router@example.com", display_name="Router Test"
    )
    app.dependency_overrides[get_google_profile_verifier] = lambda: _override_verifier(profile)
    client = TestClient(app)

    callback_response = client.post("/auth/google/callback", json={"id_token": "fake"})

    assert callback_response.status_code == 200
    body = callback_response.json()
    assert body["is_new_user"] is True
    token = body["token"]

    session_response = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})

    app.dependency_overrides.clear()
    assert session_response.status_code == 200
    session_body = session_response.json()
    assert session_body["email"] == "router@example.com"
    assert session_body["user_id"] == body["user_id"]
    assert session_body["workspace_id"] == body["workspace_id"]


def test_get_session_without_token_returns_401() -> None:
    client = TestClient(app)

    response = client.get("/auth/session")

    assert response.status_code == 401


def test_get_session_with_garbage_token_returns_401() -> None:
    client = TestClient(app)

    response = client.get("/auth/session", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
