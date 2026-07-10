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
    """idempotency key를 reserve하고 (scope, key)로 dedupe한다.

    이 (scope, key) pair의 첫 사용이면 True, 이미 reserved라면 False를 반환한다.
    caller는 False를 retry로 보고 재처리 대신 이전에 저장된 response를 반환해야 한다.
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
    """reserve()된 (scope, key) pair의 outcome을 persist한다.

    reserve()가 exclusive access를 부여한 작업을 caller가 끝낸 직후 한 번 호출한다.
    이후 같은 (scope, key)의 retry는 재처리 후 조작되거나 다른 result를 반환하는 대신
    get_response()로 이것을 다시 읽을 수 있다.
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
