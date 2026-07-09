import uuid

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.briefing.service import rebuild_briefing
from app.domains.identity.service import issue_session
from app.main import app
from tests.domains.briefing.conftest import seed_connected_account, seed_message, seed_scope


async def _headers_for(user_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    async with engine.begin() as connection:
        token = await issue_session(connection, user_id=user_id, workspace_id=workspace_id)
    return {"Authorization": f"Bearer {token}"}


async def test_account_grouped_sections() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    account_2 = await seed_connected_account(workspace_id)
    m1 = await seed_message(account_id, subject="첫 메일")
    m2 = await seed_message(account_2, subject="둘째 계정 메일")
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1, m2])
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/briefing/today?scope=all", headers=headers)

    assert response.status_code == 200
    groups = response.json()
    account_ids = {g["connected_account_id"] for g in groups}
    assert account_ids == {str(account_id), str(account_2)}
    group1 = next(g for g in groups if g["connected_account_id"] == str(account_id))
    assert group1["items"][0]["message_id"] == str(m1)
    assert group1["items"][0]["section"] == "fake_section"


async def test_card_omits_action_reason_rawbody() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1])
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/briefing/today?scope=all", headers=headers)
    card = response.json()[0]["items"][0]

    forbidden_fields = {"action", "action_type", "reason", "raw_body", "body", "mutation"}
    assert forbidden_fields.isdisjoint(card.keys())


async def test_briefing_disabled_excluded() -> None:
    workspace_id, user_id, _account_id = await seed_scope(briefing_enabled=False)
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/briefing/today?scope=all", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_invalid_scope_returns_422_not_500() -> None:
    workspace_id, user_id, _account_id = await seed_scope()
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/briefing/today?scope=not-a-uuid", headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_empty_state() -> None:
    workspace_id, user_id, _account_id = await seed_scope()
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/briefing/today?scope=all", headers=headers)

    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["items"] == []


async def test_scoped_to_workspace() -> None:
    workspace_a, user_a, account_a = await seed_scope()
    workspace_b, user_b, account_b = await seed_scope()
    headers_a = await _headers_for(user_a, workspace_a)
    m_a = await seed_message(account_a)
    m_b = await seed_message(account_b)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_a, message_ids=[m_a])
        await rebuild_briefing(connection, workspace_id=workspace_b, message_ids=[m_b])

    client = TestClient(app)
    response = client.get("/briefing/today?scope=all", headers=headers_a)

    groups = response.json()
    assert {g["connected_account_id"] for g in groups} == {str(account_a)}
