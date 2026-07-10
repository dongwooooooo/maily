import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ForbiddenError, NotFoundError
from app.core.outbox import append_event
from app.domains.briefing import events, repository
from app.domains.briefing.schemas import ItemStateResult

logger = structlog.get_logger()


def _to_schema(state: dict) -> ItemStateResult:
    return ItemStateResult(
        id=state["id"],
        workspace_id=state["workspace_id"],
        message_id=state["message_id"],
        seen=state["seen"],
        seen_at=state["seen_at"],
        remind_later_at=state["remind_later_at"],
        version=state["version"],
        updated_at=state["updated_at"],
    )


async def resolve_owned_briefing_item(
    connection: AsyncConnection, *, briefing_item_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    """briefing_item_id(client가 GET /briefing/today에서 본 card id)가 현재 가리키는
    message를 resolve하고 workspace ownership을 확인한다.

    durable state(briefing_item_states)는 이 projection id가 아니라 message_id로 key된다.
    repository.upsert_item_state 참고. *현재* projection row를 통해 resolve하는 것은 API가
    client-facing card id를 받는 방법일 뿐이다. resolve된 뒤 아래 write는 항상 message_id-keyed
    durable row에 기록된다. 그래서 이후 drop-and-rebuild가 같은 message에 새
    briefing_items.id를 부여해도 test_seen_survives_rebuild가 통과한다.
    """
    item = await repository.get_briefing_item(connection, item_id=briefing_item_id)
    if item is None:
        raise NotFoundError("briefing item not found")
    if item["workspace_id"] != workspace_id:
        raise ForbiddenError("briefing item belongs to another workspace")
    return item


async def set_item_seen(
    connection: AsyncConnection,
    *,
    briefing_item_id: uuid.UUID,
    actor_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> tuple[ItemStateResult, bool]:
    """Command `set_item_seen` — docs/goals/backend-plans/briefing.md.

    (state, is_new)를 반환한다. 이미 seen인 item의 no-op repeat이면 is_new는 False다
    (§멱등 — no version bump, no event).
    """
    item = await resolve_owned_briefing_item(
        connection, briefing_item_id=briefing_item_id, workspace_id=workspace_id
    )
    message_id = item["message_id"]

    existing = await repository.get_item_state_by_message(connection, message_id=message_id)
    if existing is not None and existing["seen"]:
        return _to_schema(existing), False

    now = datetime.now(timezone.utc)
    state_id = existing["id"] if existing is not None else uuid.uuid4()
    version = (existing["version"] + 1) if existing is not None else 1
    remind_later_at = existing["remind_later_at"] if existing is not None else None

    await repository.upsert_item_state(
        connection,
        state_id=state_id,
        workspace_id=workspace_id,
        message_id=message_id,
        seen=True,
        seen_at=now,
        remind_later_at=remind_later_at,
        version=version,
        updated_at=now,
    )
    await append_event(
        connection,
        event_type=events.ITEM_STATE_CHANGED,
        producer_domain="briefing",
        payload={
            "briefing_item_state_id": str(state_id),
            "message_id": str(message_id),
            "seen": True,
        },
        idempotency_key=events.item_state_changed_key(state_id, version),
    )
    updated = await repository.get_item_state(connection, item_state_id=state_id)
    logger.info("브리핑 아이템 확인 처리", message_id=str(message_id), actor_id=str(actor_id))
    return _to_schema(updated), True
