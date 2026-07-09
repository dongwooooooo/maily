import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import engine
from app.core.errors import ValidationError
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.domains.labels.models import gmail_label_mappings
from app.domains.labels.schemas import CreateLabelInput, UpdateLabelInput
from app.domains.labels.service import create_or_update_label, list_labels, update_label
from app.main import app
from tests.domains.labels.conftest import seed_connected_account, seed_workspace


async def _create_input(**overrides) -> CreateLabelInput:
    workspace_id = overrides.pop("workspace_id", None) or await seed_workspace()
    connected_account_id = overrides.pop("connected_account_id", None) or (
        await seed_connected_account(workspace_id)
    )
    defaults = {
        "workspace_id": workspace_id,
        "connected_account_id": connected_account_id,
        "name": f"Recruiting-{uuid.uuid4()}",
        "hidden": False,
    }
    defaults.update(overrides)
    return CreateLabelInput(**defaults)


async def _auth_headers() -> tuple[dict, uuid.UUID]:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    return {"Authorization": f"Bearer {token}"}, login.workspace_id


async def test_create_label_creates_mapping_intent() -> None:
    data = await _create_input()

    async with engine.begin() as connection:
        label, is_new = await create_or_update_label(connection, data)

    assert is_new is True
    assert label.name == data.name
    assert label.hidden is False
    assert label.gmail_label_name == f"Maily/{data.name}"
    assert label.gmail_label_id is None
    assert label.connected_account_id == data.connected_account_id


async def test_mapping_id_null_before_apply() -> None:
    data = await _create_input()

    async with engine.begin() as connection:
        label, _ = await create_or_update_label(connection, data)

    # Gmail label creation is gmail_actions' job — labels only records intent.
    assert label.gmail_label_id is None


async def test_rename_keeps_gmail_mapping() -> None:
    data = await _create_input()
    async with engine.begin() as connection:
        label, _ = await create_or_update_label(connection, data)

    new_name = f"renamed-{uuid.uuid4()}"
    async with engine.begin() as connection:
        renamed = await update_label(
            connection, label_id=label.id, changes=UpdateLabelInput(name=new_name)
        )

    assert renamed.id == label.id
    assert renamed.name == new_name
    assert renamed.gmail_label_name == f"Maily/{new_name}"
    # Same mapping row — gmail_label_id (whatever it was) is preserved, not reset.
    assert renamed.gmail_label_id == label.gmail_label_id

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_label_mappings).where(
                    gmail_label_mappings.c.service_label_id == label.id
                )
            )
        ).mappings().all()
    assert len(rows) == 1


async def test_reorder_hide_no_duplicate_mapping() -> None:
    data = await _create_input()
    async with engine.begin() as connection:
        label, _ = await create_or_update_label(connection, data)

    async with engine.begin() as connection:
        updated = await update_label(
            connection,
            label_id=label.id,
            changes=UpdateLabelInput(order_index=5, hidden=True),
        )

    assert updated.order_index == 5
    assert updated.hidden is True
    assert updated.gmail_label_name == label.gmail_label_name
    assert updated.gmail_label_id == label.gmail_label_id

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_label_mappings).where(
                    gmail_label_mappings.c.service_label_id == label.id
                )
            )
        ).mappings().all()
    assert len(rows) == 1


async def test_duplicate_name_rejected() -> None:
    data = await _create_input()
    async with engine.begin() as connection:
        first, first_is_new = await create_or_update_label(connection, data)

    async with engine.begin() as connection:
        second, second_is_new = await create_or_update_label(connection, data)

    assert first_is_new is True
    assert second_is_new is False
    assert second.id == first.id

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_label_mappings).where(
                    gmail_label_mappings.c.service_label_id == first.id
                )
            )
        ).mappings().all()
    assert len(rows) == 1


async def test_concurrent_create_same_name_creates_only_one_mapping() -> None:
    data = await _create_input()

    async def attempt():
        async with engine.begin() as connection:
            return await create_or_update_label(connection, data)

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(is_new for _, is_new in results) == [False, True]
    assert results[0][0].id == results[1][0].id


async def test_create_label_blank_name_rejected() -> None:
    data = await _create_input(name="   ")

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await create_or_update_label(connection, data)


async def test_create_label_on_disconnected_account_rejected() -> None:
    workspace_id = await seed_workspace()
    account_id = await seed_connected_account(workspace_id, status="disconnected")
    data = await _create_input(workspace_id=workspace_id, connected_account_id=account_id)

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await create_or_update_label(connection, data)


async def test_list_labels_scoped_and_ordered() -> None:
    workspace_id = await seed_workspace()
    account_id = await seed_connected_account(workspace_id)
    other_workspace_id = await seed_workspace()
    other_account_id = await seed_connected_account(other_workspace_id)

    async with engine.begin() as connection:
        second, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name="B-label",
                order_index=1,
            ),
        )
        first, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name="A-label",
                order_index=0,
            ),
        )
        hidden, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name="Hidden-label",
                order_index=2,
                hidden=True,
            ),
        )
        await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=other_workspace_id,
                connected_account_id=other_account_id,
                name="Other-workspace-label",
            ),
        )

    async with engine.begin() as connection:
        default_list = await list_labels(
            connection, workspace_id=workspace_id, include_hidden=False
        )
        full_list = await list_labels(connection, workspace_id=workspace_id, include_hidden=True)

    assert [label.id for label in default_list] == [first.id, second.id]
    assert hidden.id not in {label.id for label in default_list}
    assert {label.id for label in full_list} == {first.id, second.id, hidden.id}
    assert all(label.workspace_id == workspace_id for label in full_list)


async def test_list_labels_empty_returns_empty_list() -> None:
    workspace_id = await seed_workspace()

    async with engine.begin() as connection:
        result = await list_labels(connection, workspace_id=workspace_id, include_hidden=False)

    assert result == []


async def test_patch_label_from_other_workspace_returns_403() -> None:
    data = await _create_input()
    async with engine.begin() as connection:
        label, _ = await create_or_update_label(connection, data)

    headers, _ = await _auth_headers()
    client = TestClient(app)

    response = client.patch(f"/labels/{label.id}", headers=headers, json={"hidden": True})

    assert response.status_code == 403


async def test_create_and_patch_label_via_router() -> None:
    headers, workspace_id = await _auth_headers()
    account_id = await seed_connected_account(workspace_id)
    client = TestClient(app)

    create_response = client.post(
        "/labels",
        headers=headers,
        json={"connected_account_id": str(account_id), "name": f"Sales-{uuid.uuid4()}"},
    )
    assert create_response.status_code == 200
    label = create_response.json()
    assert label["gmail_label_id"] is None
    assert label["gmail_label_name"] == f"Maily/{label['name']}"

    list_response = client.get("/labels", headers=headers)
    assert list_response.status_code == 200
    assert any(row["id"] == label["id"] for row in list_response.json())

    patch_response = client.patch(
        f"/labels/{label['id']}", headers=headers, json={"hidden": True}
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["hidden"] is True

    hidden_excluded = client.get("/labels", headers=headers)
    assert all(row["id"] != label["id"] for row in hidden_excluded.json())

    hidden_included = client.get("/labels?include_hidden=true", headers=headers)
    assert any(row["id"] == label["id"] for row in hidden_included.json())


async def test_create_label_without_auth_returns_401() -> None:
    client = TestClient(app)

    response = client.post(
        "/labels",
        json={"connected_account_id": str(uuid.uuid4()), "name": "no-auth"},
    )

    assert response.status_code == 401
