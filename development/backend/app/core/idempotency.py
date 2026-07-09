import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Table, UniqueConstraint, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import metadata

idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("scope", String, nullable=False),
    Column("key", String, nullable=False),
    Column("request_hash", String, nullable=True),
    Column("response_snapshot", JSONB, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
)


async def reserve(
    connection: AsyncConnection,
    *,
    scope: str,
    key: str,
    expires_at: datetime,
    request_hash: str | None = None,
) -> bool:
    """Reserve an idempotency key, deduped on (scope, key).

    Returns True on first use of this (scope, key) pair, False if it
    was already reserved — callers should treat False as a retry and
    return the previously stored response instead of reprocessing.
    """
    stmt = (
        insert(idempotency_keys)
        .values(
            id=uuid.uuid4(),
            scope=scope,
            key=key,
            request_hash=request_hash,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_keys_scope_key")
        .returning(idempotency_keys.c.id)
    )
    result = await connection.execute(stmt)
    return result.first() is not None


async def store_response(
    connection: AsyncConnection, *, scope: str, key: str, response_snapshot: dict
) -> None:
    """Persist the outcome of a reserve()d (scope, key) pair.

    Called once, right after the caller finishes the work reserve()
    granted exclusive access to — a later retry with the same
    (scope, key) can then read it back via get_response() instead of
    reprocessing and returning a fabricated/different result.
    """
    await connection.execute(
        update(idempotency_keys)
        .where(idempotency_keys.c.scope == scope, idempotency_keys.c.key == key)
        .values(response_snapshot=response_snapshot)
    )


async def get_response(connection: AsyncConnection, *, scope: str, key: str) -> dict | None:
    row = (
        await connection.execute(
            select(idempotency_keys.c.response_snapshot).where(
                idempotency_keys.c.scope == scope, idempotency_keys.c.key == key
            )
        )
    ).first()
    return row[0] if row is not None and row[0] is not None else None
