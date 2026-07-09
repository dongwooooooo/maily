import uuid

from app.core.database import engine
from app.core.outbox import append_event


async def test_append_event_creates_row_and_returns_id() -> None:
    idempotency_key = f"source:{uuid.uuid4()}:connected:1"

    async with engine.begin() as connection:
        event_id = await append_event(
            connection,
            event_type="gmail_source_connected",
            producer_domain="mail_sources",
            payload={"source_id": "abc"},
            idempotency_key=idempotency_key,
        )

    assert event_id is not None


async def test_append_event_dedupes_on_event_type_and_idempotency_key() -> None:
    idempotency_key = f"source:{uuid.uuid4()}:connected:1"

    async with engine.begin() as connection:
        first_id = await append_event(
            connection,
            event_type="gmail_source_connected",
            producer_domain="mail_sources",
            payload={"source_id": "abc"},
            idempotency_key=idempotency_key,
        )

    async with engine.begin() as connection:
        second_id = await append_event(
            connection,
            event_type="gmail_source_connected",
            producer_domain="mail_sources",
            payload={"source_id": "abc"},
            idempotency_key=idempotency_key,
        )

    assert first_id is not None
    assert second_id is None


async def test_append_event_allows_same_idempotency_key_for_different_event_type() -> None:
    idempotency_key = f"source:{uuid.uuid4()}:connected:1"

    async with engine.begin() as connection:
        first_id = await append_event(
            connection,
            event_type="gmail_source_connected",
            producer_domain="mail_sources",
            payload={},
            idempotency_key=idempotency_key,
        )

    async with engine.begin() as connection:
        second_id = await append_event(
            connection,
            event_type="gmail_source_settings_changed",
            producer_domain="mail_sources",
            payload={},
            idempotency_key=idempotency_key,
        )

    assert first_id is not None
    assert second_id is not None
