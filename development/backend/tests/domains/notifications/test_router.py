import uuid

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.domains.notifications import service
from app.domains.notifications.jobs.emit_notification import run_emit_notification
from app.main import app
from tests.domains.notifications.conftest import seed_connected_account


async def _auth_headers() -> tuple[dict, uuid.UUID, uuid.UUID]:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    return {"Authorization": f"Bearer {token}"}, login.user_id, login.workspace_id


async def test_get_notifications_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/notifications")
    assert response.status_code == 401


async def test_get_notifications_scoped_to_session_workspace() -> None:
    headers, _user_id, workspace_id = await _auth_headers()
    account_id = await seed_connected_account(workspace_id)

    async with engine.begin() as connection:
        await run_emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(account_id),
                "reason": "auth_error",
                "version": 0,
            },
        )

    client = TestClient(app)
    response = client.get("/notifications", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["notification_type"] == "recovery_needed"
    assert body[0]["route_target"]["screen"] == "account_settings"
    assert body[0]["route_target"]["item_id"] == str(account_id)


async def test_subscribe_via_router_excludes_keys_from_response() -> None:
    headers, _user_id, _workspace_id = await _auth_headers()
    client = TestClient(app)

    response = client.post(
        "/notifications/subscribe",
        headers=headers,
        json={"endpoint": f"https://push.example.com/{uuid.uuid4()}", "keys": {"p256dh": "k", "auth": "a"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "keys" not in body
    assert body["revoked_at"] is None


async def test_subscribe_without_auth_returns_401() -> None:
    client = TestClient(app)
    response = client.post(
        "/notifications/subscribe",
        json={"endpoint": f"https://push.example.com/{uuid.uuid4()}", "keys": {"p256dh": "k"}},
    )
    assert response.status_code == 401
