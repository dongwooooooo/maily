import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import metadata

outbox_events = Table(
    "outbox_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("event_type", String, nullable=False),
    Column("producer_domain", String, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("status", String, nullable=False, server_default="pending"),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("dispatched_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint(
        "event_type", "idempotency_key", name="uq_outbox_events_event_type_idempotency_key"
    ),
    Index(
        "ix_outbox_events_pending_created_at",
        "created_at",
        postgresql_where=text("status = 'pending'"),
    ),
)


async def append_event(
    connection: AsyncConnection,
    *,
    event_type: str,
    producer_domain: str,
    payload: dict,
    idempotency_key: str,
) -> uuid.UUID | None:
    """Insert an outbox event, deduped on (event_type, idempotency_key).

    Returns the new row's id, or None if a row with the same
    (event_type, idempotency_key) already exists.
    """
    stmt = (
        insert(outbox_events)
        .values(
            id=uuid.uuid4(),
            event_type=event_type,
            producer_domain=producer_domain,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(
            constraint="uq_outbox_events_event_type_idempotency_key"
        )
        .returning(outbox_events.c.id)
    )
    result = await connection.execute(stmt)
    row = result.first()
    return row.id if row is not None else None
