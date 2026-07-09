import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session
from app.domains.labels.models import label_correction_signals
from app.domains.labels.schemas import CreateLabelInput, MoveMessageInput, MoveMessageResult
from app.domains.labels.service import create_or_update_label, move_message_to_label
from app.domains.mail_sources.models import connected_gmail_accounts
from app.main import app
from tests.domains.labels.conftest import seed_connected_account, seed_message, seed_user


async def _auth_headers() -> tuple[dict, uuid.UUID]:
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com")
    async with engine.begin() as connection:
        login = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=login.user_id, workspace_id=login.workspace_id
        )
    return {"Authorization": f"Bearer {token}"}, login.workspace_id


async def _seed_scenario(*, account_status: str = "connected") -> dict:
    headers, workspace_id = await _auth_headers()
    account_id = await seed_connected_account(workspace_id, status=account_status)
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        label, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name=f"Recruiting-{uuid.uuid4()}",
            ),
        )

    return {
        "headers": headers,
        "workspace_id": workspace_id,
        "account_id": account_id,
        "message_id": message_id,
        "label_id": label.id,
    }


async def test_move_records_signal_and_emits() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)

    response = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message_id"] == str(scenario["message_id"])
    assert body["service_label_id"] == str(scenario["label_id"])
    assert body["version"] == 0

    async with engine.connect() as connection:
        signal_rows = (
            await connection.execute(
                select(label_correction_signals).where(
                    label_correction_signals.c.id == uuid.UUID(body["correction_signal_id"])
                )
            )
        ).mappings().all()
    assert len(signal_rows) == 1
    assert str(signal_rows[0]["message_id"]) == str(scenario["message_id"])
    assert str(signal_rows[0]["service_label_id"]) == str(scenario["label_id"])

    key = f"message:{scenario['message_id']}:label:{scenario['label_id']}:correction:0"
    async with engine.connect() as connection:
        event_rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().all()
    assert len(event_rows) == 1
    assert event_rows[0]["event_type"] == "label_correction_recorded"
    assert event_rows[0]["producer_domain"] == "labels"
    assert event_rows[0]["payload"]["correction_signal_id"] == body["correction_signal_id"]


async def test_move_to_default_section_rejected() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)
    not_a_label_id = uuid.uuid4()

    response = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(not_a_label_id)},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_no_default_section_move_endpoint_exists() -> None:
    # This domain owns no "default briefing section" concept/table at all —
    # prove the API surface has no endpoint that could move a message to one.
    paths = set(app.openapi()["paths"].keys())
    assert not any("section" in path for path in paths)
    assert "/messages/{message_id}/move" in paths


async def test_move_idempotent_by_key() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)
    idempotency_key = str(uuid.uuid4())

    first = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": idempotency_key},
        json={"label_id": str(scenario["label_id"])},
    )
    second = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": idempotency_key},
        json={"label_id": str(scenario["label_id"])},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["correction_signal_id"] == second.json()["correction_signal_id"]

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(label_correction_signals).where(
                    label_correction_signals.c.message_id == scenario["message_id"],
                    label_correction_signals.c.service_label_id == scenario["label_id"],
                )
            )
        ).mappings().all()
    assert len(rows) == 1


async def test_move_same_label_again_with_new_key_creates_new_version() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)

    first = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )
    second = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )

    assert first.json()["version"] == 0
    assert second.json()["version"] == 1
    assert first.json()["correction_signal_id"] != second.json()["correction_signal_id"]


async def test_move_cross_workspace_forbidden() -> None:
    scenario = await _seed_scenario()
    other_headers, _ = await _auth_headers()
    client = TestClient(app)

    response = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**other_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )

    assert response.status_code == 403


async def test_move_message_not_found_returns_404() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)

    response = client.post(
        f"/messages/{uuid.uuid4()}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )

    assert response.status_code == 404


async def test_move_to_label_on_disconnected_account_rejected() -> None:
    # The label must be created while the account is still active — a
    # disconnected account can no longer create new label mapping intents
    # either (create_or_update_label's own precondition). What this test
    # covers is the realistic sequence: account disconnects *after* a
    # label already exists, and a move against that now-stale mapping
    # must still be rejected.
    scenario = await _seed_scenario()
    async with engine.begin() as connection:
        await connection.execute(
            update(connected_gmail_accounts)
            .where(connected_gmail_accounts.c.id == scenario["account_id"])
            .values(status="disconnected")
        )
    client = TestClient(app)

    response = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers={**scenario["headers"], "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(scenario["label_id"])},
    )

    assert response.status_code == 422


async def test_move_without_idempotency_key_header_rejected() -> None:
    scenario = await _seed_scenario()
    client = TestClient(app)

    response = client.post(
        f"/messages/{scenario['message_id']}/move",
        headers=scenario["headers"],
        json={"label_id": str(scenario["label_id"])},
    )

    assert response.status_code == 422


async def test_move_to_hidden_label_allowed() -> None:
    headers, workspace_id = await _auth_headers()
    account_id = await seed_connected_account(workspace_id)
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        label, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name=f"Archive-{uuid.uuid4()}",
                hidden=True,
            ),
        )

    client = TestClient(app)
    response = client.post(
        f"/messages/{message_id}/move",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"label_id": str(label.id)},
    )

    assert response.status_code == 200


async def test_move_different_labels_concurrently_creates_two_signals() -> None:
    _, workspace_id = await _auth_headers()
    account_id = await seed_connected_account(workspace_id)
    message_id = await seed_message(account_id)
    actor_id = await seed_user()

    async with engine.begin() as connection:
        label_a, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name=f"A-{uuid.uuid4()}",
            ),
        )
        label_b, _ = await create_or_update_label(
            connection,
            CreateLabelInput(
                workspace_id=workspace_id,
                connected_account_id=account_id,
                name=f"B-{uuid.uuid4()}",
            ),
        )

    async def move(label_id: uuid.UUID) -> MoveMessageResult:
        async with engine.begin() as connection:
            return await move_message_to_label(
                connection,
                MoveMessageInput(
                    workspace_id=workspace_id,
                    message_id=message_id,
                    label_id=label_id,
                    actor_id=actor_id,
                    idempotency_key=str(uuid.uuid4()),
                ),
            )

    results = await asyncio.gather(move(label_a.id), move(label_b.id))

    assert sorted(result.version for result in results) == [0, 0]
    assert len({result.correction_signal_id for result in results}) == 2
