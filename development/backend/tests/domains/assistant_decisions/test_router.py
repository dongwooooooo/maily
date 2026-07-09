import uuid

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.assistant_decisions.cleanup import prepare_cleanup_proposals
from app.domains.assistant_decisions.rules import create_rule_suggestion_from_signal
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.main import app
from tests.domains.assistant_decisions.conftest import (
    seed_connected_account,
    seed_correction_signal,
    seed_message,
    seed_message_labels,
    seed_service_label,
    seed_source_settings,
)


async def _auth_headers_and_scope() -> tuple[dict, uuid.UUID, uuid.UUID]:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    headers = {"Authorization": f"Bearer {token}"}
    return headers, login.workspace_id, login.user_id


async def test_get_rules_empty_state() -> None:
    headers, _, _ = await _auth_headers_and_scope()
    client = TestClient(app)

    response = client.get("/rules", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"suggestions": [], "rules": []}


async def test_get_rules_lists_pending_suggestion() -> None:
    headers, workspace_id, user_id = await _auth_headers_and_scope()
    account_id = await seed_connected_account(workspace_id)
    message_id = await seed_message(account_id, sender="ops@example.com")
    label_id = await seed_service_label(workspace_id)
    signal_id = await seed_correction_signal(
        message_id=message_id, service_label_id=label_id, actor_id=user_id
    )
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(connection, correction_signal_id=signal_id)
    client = TestClient(app)

    response = client.get("/rules", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["status"] == "pending"


async def test_approve_rule_route_activates_rule() -> None:
    headers, workspace_id, user_id = await _auth_headers_and_scope()
    account_id = await seed_connected_account(workspace_id)
    message_id = await seed_message(account_id, sender="ops@example.com")
    label_id = await seed_service_label(workspace_id)
    signal_id = await seed_correction_signal(
        message_id=message_id, service_label_id=label_id, actor_id=user_id
    )
    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )
    client = TestClient(app)

    response = client.post(f"/rules/{suggestion['id']}/approve", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    rules_response = client.get("/rules", headers=headers)
    assert len(rules_response.json()["rules"]) == 1


async def test_get_cleanup_queue_only_approval_required() -> None:
    headers, workspace_id, user_id = await _auth_headers_and_scope()
    account_id = await seed_connected_account(workspace_id)
    await seed_source_settings(account_id)
    review_message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(review_message_id, ["INBOX"])
    silent_message_id = await seed_message(account_id, is_read=False, is_archived=False)
    await seed_message_labels(silent_message_id, ["INBOX", "UNREAD"])

    async with engine.begin() as connection:
        await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=[review_message_id, silent_message_id],
            requested_by=user_id,
        )
    client = TestClient(app)

    response = client.get("/cleanup", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["message_id"] == str(review_message_id)


async def test_approve_cleanup_route_requests_command() -> None:
    headers, workspace_id, user_id = await _auth_headers_and_scope()
    account_id = await seed_connected_account(workspace_id)
    await seed_source_settings(account_id)
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])
    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )
    proposal_id = proposals[0]["id"]
    client = TestClient(app)

    response = client.post(f"/cleanup/{proposal_id}/approve", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["gmail_action_command_id"] is not None


async def test_rules_and_cleanup_require_auth() -> None:
    client = TestClient(app)

    assert client.get("/rules").status_code == 401
    assert client.get("/cleanup").status_code == 401
