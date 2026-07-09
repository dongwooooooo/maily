import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.main import app


async def _auth_headers() -> dict:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    return {"Authorization": f"Bearer {token}"}


def _connect_body(**overrides) -> dict:
    body = {
        "gmail_address": f"router-{uuid.uuid4()}@gmail.com",
        "access_token": "ya29.a0-example-access-token",
        "refresh_token": "1//0g-example-refresh-token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    body.update(overrides)
    return body


async def test_connect_list_and_get_source() -> None:
    headers = await _auth_headers()
    client = TestClient(app)

    connect_response = client.post("/sources", headers=headers, json=_connect_body())
    assert connect_response.status_code == 200
    source = connect_response.json()

    list_response = client.get("/sources", headers=headers)
    assert list_response.status_code == 200
    assert any(s["id"] == source["id"] for s in list_response.json())

    get_response = client.get(f"/sources/{source['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == source["id"]


async def test_get_source_from_other_workspace_returns_404() -> None:
    headers_a = await _auth_headers()
    headers_b = await _auth_headers()
    client = TestClient(app)

    connect_response = client.post("/sources", headers=headers_a, json=_connect_body())
    source_id = connect_response.json()["id"]

    response = client.get(f"/sources/{source_id}", headers=headers_b)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_patch_source_settings_toggle() -> None:
    headers = await _auth_headers()
    client = TestClient(app)

    connect_response = client.post("/sources", headers=headers, json=_connect_body())
    source_id = connect_response.json()["id"]

    patch_response = client.patch(
        f"/sources/{source_id}", headers=headers, json={"summary_enabled": False}
    )

    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["summary_enabled"] is False
    assert body["briefing_enabled"] is True


async def test_patch_source_from_other_workspace_returns_404() -> None:
    headers_a = await _auth_headers()
    headers_b = await _auth_headers()
    client = TestClient(app)

    connect_response = client.post("/sources", headers=headers_a, json=_connect_body())
    source_id = connect_response.json()["id"]

    response = client.patch(f"/sources/{source_id}", headers=headers_b, json={"paused": True})

    assert response.status_code == 404


async def test_connect_source_without_auth_returns_401() -> None:
    client = TestClient(app)

    response = client.post("/sources", json=_connect_body())

    assert response.status_code == 401


async def test_list_sources_scoped_to_workspace() -> None:
    headers_a = await _auth_headers()
    headers_b = await _auth_headers()
    client = TestClient(app)

    connect_a = client.post("/sources", headers=headers_a, json=_connect_body())
    source_a_id = connect_a.json()["id"]

    list_b = client.get("/sources", headers=headers_b)

    assert list_b.status_code == 200
    assert all(s["id"] != source_a_id for s in list_b.json())
