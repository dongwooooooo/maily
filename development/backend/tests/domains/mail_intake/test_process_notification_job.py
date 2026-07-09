import base64
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import engine
from app.core.jobs.models import job_runs
from app.core.outbox import outbox_events
from app.domains.mail_intake import service
from app.domains.mail_intake.models import gmail_notification_events
from app.main import app
from tests.domains.mail_intake.conftest import seed_connected_account


async def test_fanout_to_active_sources_by_email() -> None:
    email = f"fanout-{uuid.uuid4()}@gmail.com"
    source_a = await seed_connected_account(gmail_address=email)
    source_b = await seed_connected_account(gmail_address=email)
    # A paused source with the same address must not receive a queued sync_delta.
    paused_source = await seed_connected_account(gmail_address=email, paused=True)

    async with engine.begin() as connection:
        result = await service.process_notification(
            connection, email_address=email, history_id=500
        )

    assert result["deduped"] is False
    queued_ids = set(result["queued_source_ids"])
    assert {source_a, source_b} <= queued_ids
    assert paused_source not in queued_ids

    async with engine.connect() as connection:
        jobs = (
            await connection.execute(select(job_runs).where(job_runs.c.job_type == "sync_delta"))
        ).mappings().all()
    job_source_ids = {uuid.UUID(job["payload"]["source_id"]) for job in jobs}
    assert {source_a, source_b} <= job_source_ids


async def test_notification_dedupe_by_email_and_history() -> None:
    email = f"dedupe-{uuid.uuid4()}@gmail.com"
    await seed_connected_account(gmail_address=email)

    async with engine.begin() as connection:
        first = await service.process_notification(connection, email_address=email, history_id=42)
    async with engine.begin() as connection:
        second = await service.process_notification(connection, email_address=email, history_id=42)

    assert first["deduped"] is False
    assert second["deduped"] is True
    assert second["queued_source_ids"] == []

    dedupe_key = f"gmail-notification:{email}:42"
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_notification_events).where(
                    gmail_notification_events.c.dedupe_key == dedupe_key
                )
            )
        ).mappings().all()
    assert len(rows) == 1

    async with engine.connect() as connection:
        event_rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == dedupe_key)
            )
        ).all()
    assert len(event_rows) == 1


async def test_no_active_source_is_noop() -> None:
    email = f"orphan-{uuid.uuid4()}@gmail.com"

    async with engine.begin() as connection:
        result = await service.process_notification(connection, email_address=email, history_id=7)

    assert result["deduped"] is False
    assert result["queued_source_ids"] == []

    dedupe_key = f"gmail-notification:{email}:7"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(gmail_notification_events).where(
                    gmail_notification_events.c.dedupe_key == dedupe_key
                )
            )
        ).mappings().first()
    assert row is not None
    assert row["processed_at"] is not None


async def test_pubsub_endpoint_acks_and_queues() -> None:
    client = TestClient(app)
    email = f"pubsub-{uuid.uuid4()}@gmail.com"
    await seed_connected_account(gmail_address=email)

    payload = {"emailAddress": email, "historyId": 999}
    data_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    body = {
        "message": {"data": data_b64, "messageId": str(uuid.uuid4())},
        "subscription": "projects/x/subscriptions/y",
    }

    response = client.post("/intake/pubsub", json=body)

    assert response.status_code == 200
    assert response.json()["deduped"] is False

    # Redelivery of the exact same Pub/Sub message must still ack 200, not
    # error, or Pub/Sub will retry-storm us (mail_intake.md "[멱등]").
    response_again = client.post("/intake/pubsub", json=body)
    assert response_again.status_code == 200
    assert response_again.json()["deduped"] is True
