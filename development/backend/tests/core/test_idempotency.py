import uuid
from datetime import datetime, timedelta, timezone

from app.core.database import engine
from app.core.idempotency import reserve


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def test_reserve_returns_true_on_first_use() -> None:
    key = str(uuid.uuid4())

    async with engine.begin() as connection:
        is_new = await reserve(
            connection, scope="gmail_actions.request_action", key=key, expires_at=_future()
        )

    assert is_new is True


async def test_reserve_returns_false_on_retry_with_same_scope_and_key() -> None:
    key = str(uuid.uuid4())

    async with engine.begin() as connection:
        await reserve(
            connection, scope="gmail_actions.request_action", key=key, expires_at=_future()
        )

    async with engine.begin() as connection:
        is_new = await reserve(
            connection, scope="gmail_actions.request_action", key=key, expires_at=_future()
        )

    assert is_new is False


async def test_reserve_allows_same_key_in_a_different_scope() -> None:
    key = str(uuid.uuid4())

    async with engine.begin() as connection:
        await reserve(connection, scope="gmail_actions.request_action", key=key, expires_at=_future())

    async with engine.begin() as connection:
        is_new = await reserve(
            connection, scope="labels.create_or_update_label", key=key, expires_at=_future()
        )

    assert is_new is True
