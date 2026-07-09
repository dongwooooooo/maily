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


async def _resolve_owned_item(
    connection: AsyncConnection, *, briefing_item_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    """briefing_item_id (a card id the client saw in GET /briefing/today) ->
    the message it currently identifies, plus a workspace ownership check.

    Durable state (briefing_item_states) is keyed by message_id, not by
    this projection id — see repository.upsert_item_state. Resolving
    through the *current* projection row is only how the API accepts a
    client-facing card id; once resolved, the write below always lands on
    the message_id-keyed durable row, which is what makes
    test_seen_survives_rebuild pass even when a later drop-and-rebuild
    assigns the same message a brand-new briefing_items.id.
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

    Returns (state, is_new) where is_new is False for the no-op repeat of
    an already-seen item (§멱등 — no version bump, no event).
    """
    item = await _resolve_owned_item(
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
