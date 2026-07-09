import uuid

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.identity.service import issue_session
from app.main import app
from tests.domains.briefing.conftest import seed_message, seed_scope


async def _headers_for(user_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    async with engine.begin() as connection:
        token = await issue_session(connection, user_id=user_id, workspace_id=workspace_id)
    return {"Authorization": f"Bearer {token}"}


async def test_detail_returns_readonly_view() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(
        account_id, subject="분기 정산", sender="billing@example.com", is_read=True
    )
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get(f"/messages/{message_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "분기 정산"
    assert body["sender"] == "billing@example.com"
    assert body["gmail_url"].startswith("https://mail.google.com/")
    assert body["excerpt_text"] is not None
    assert body["done"] is True


async def test_detail_has_no_mutation_action() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get(f"/messages/{message_id}", headers=headers)
    body = response.json()

    forbidden_fields = {"action", "action_type", "mark_read", "archive", "label", "body", "raw_body"}
    assert forbidden_fields.isdisjoint(body.keys())


async def test_detail_omits_reason_by_default() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get(f"/messages/{message_id}", headers=headers)
    body = response.json()

    assert "reason" not in body
    assert body["importance_band"] is None
    assert body["summary_text"] is None


async def test_detail_cross_workspace_404() -> None:
    workspace_a, user_a, account_a = await seed_scope()
    workspace_b, user_b, _account_b = await seed_scope()
    message_id = await seed_message(account_a)
    headers_b = await _headers_for(user_b, workspace_b)

    client = TestClient(app)
    response = client.get(f"/messages/{message_id}", headers=headers_b)

    assert response.status_code == 404
