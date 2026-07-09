import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.jobs.execute_action import run_execute_action
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.main import app
from tests.domains.gmail_actions.conftest import seed_message


async def _auth_headers() -> dict:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    return {"Authorization": f"Bearer {token}"}


def _connect_source_body(**overrides) -> dict:
    body = {
        "gmail_address": f"router-{uuid.uuid4()}@gmail.com",
        "access_token": "ya29.a0-example-access-token",
        "refresh_token": "1//0g-example-refresh-token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    body.update(overrides)
    return body


async def test_create_action_requires_idempotency_key_header() -> None:
    headers = await _auth_headers()
    client = TestClient(app)
    connect_response = client.post("/sources", headers=headers, json=_connect_source_body())
    account_id = connect_response.json()["id"]

    response = client.post(
        "/actions",
        headers=headers,
        json={"connected_account_id": account_id, "action_type": "mark_read"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_create_action_returns_pending_command() -> None:
    headers = await _auth_headers()
    client = TestClient(app)
    connect_response = client.post("/sources", headers=headers, json=_connect_source_body())
    account_id = connect_response.json()["id"]

    response = client.post(
        "/actions",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"connected_account_id": account_id, "action_type": "mark_read"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["action_type"] == "mark_read"
    assert body["payload"] == {"add_label_ids": [], "remove_label_ids": ["UNREAD"]}


async def test_create_action_without_auth_returns_401() -> None:
    client = TestClient(app)

    response = client.post(
        "/actions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"connected_account_id": str(uuid.uuid4()), "action_type": "mark_read"},
    )

    assert response.status_code == 401


async def test_activity_and_undo_round_trip_through_router() -> None:
    mutator = execute_action.get_mutator()
    headers = await _auth_headers()
    client = TestClient(app)
    connect_response = client.post("/sources", headers=headers, json=_connect_source_body())
    account_id = connect_response.json()["id"]
    message_id = str(await seed_message(uuid.UUID(account_id)))
    mutator.seed_labels(uuid.UUID(message_id), {"UNREAD", "INBOX"})

    create_response = client.post(
        "/actions",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "connected_account_id": account_id,
            "message_id": message_id,
            "action_type": "mark_read",
        },
    )
    command_id = create_response.json()["id"]

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=uuid.UUID(command_id))

    activity_response = client.get("/actions/activity", headers=headers)
    assert activity_response.status_code == 200
    activities = activity_response.json()
    assert any(a["command_id"] == command_id for a in activities)
    entry = next(a for a in activities if a["command_id"] == command_id)
    assert entry["undo_available"] is True

    undo_response = client.post(f"/actions/{entry['id']}/undo", headers=headers)
    assert undo_response.status_code == 200
    assert undo_response.json()["reverse_command_id"] is not None


async def test_activity_scoped_to_workspace() -> None:
    headers_a = await _auth_headers()
    headers_b = await _auth_headers()
    client = TestClient(app)
    connect_a = client.post("/sources", headers=headers_a, json=_connect_source_body())
    account_a = connect_a.json()["id"]
    client.post(
        "/actions",
        headers={**headers_a, "Idempotency-Key": str(uuid.uuid4())},
        json={"connected_account_id": account_a, "action_type": "archive"},
    )

    response_b = client.get("/actions/activity", headers=headers_b)

    assert response_b.status_code == 200
    assert response_b.json() == []
