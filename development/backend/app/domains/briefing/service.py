import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.briefing import repository
from app.domains.briefing.schemas import FAKE_SECTION

logger = structlog.get_logger()

_INACTIVE_ACCOUNT_STATUSES = ("disconnecting", "disconnected")


async def rebuild_briefing(
    connection: AsyncConnection,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    message_ids: list[uuid.UUID] | None = None,
    summary_overrides: dict[uuid.UUID, str | None] | None = None,
    importance_overrides: dict[uuid.UUID, str | None] | None = None,
) -> list[uuid.UUID]:
    """Command `rebuild_briefing` — docs/goals/backend-plans/briefing.md.

    Always a per-message_id upsert into briefing_items, never a full
    delete+reinsert (the "언제든 drop-and-rebuild 가능해야 한다" invariant
    describes the *table*, not this function's mechanics — see
    test_projection_regenerable.py for a literal drop-and-rebuild proof).

    `summary_overrides` / `importance_overrides` let build_briefing's
    per-trigger wrapper (jobs/build_briefing.py) simulate what a real
    `summary_completed`/`importance_classified` event payload would carry.
    These two maps are NOT part of the official `build_briefing` job
    payload contract (_integration-contract.md §2 lists only
    `{workspace_id, source_id?, message_ids?}`) — message_summaries /
    message_importance_classifications (migration 0010) don't exist in
    this worktree yet, so there is no source table to join for real. A
    message_id absent from the relevant override map keeps whatever
    value the existing projection row already has (or null for a
    brand-new row) instead of being reset — this is what makes
    `summary_completed` and `importance_classified` each touch only
    their own column (briefing.md Job §동시).
    """
    summary_overrides = summary_overrides or {}
    importance_overrides = importance_overrides or {}

    if message_ids is not None:
        candidate_message_ids = list(message_ids)
    else:
        accounts = await repository.list_connected_accounts_for_workspace(
            connection, workspace_id=workspace_id, source_id=source_id
        )
        candidate_message_ids = []
        for account in accounts:
            messages = await repository.list_messages_for_account(
                connection, connected_account_id=account["id"]
            )
            candidate_message_ids.extend(message["id"] for message in messages)

    now = datetime.now(timezone.utc)
    rebuilt_message_ids: list[uuid.UUID] = []

    for message_id in candidate_message_ids:
        message = await repository.get_message(connection, message_id=message_id)
        if message is None:
            # [선행조건] message not in snapshot yet — nothing to project.
            continue

        account = await repository.get_connected_account(
            connection, connected_account_id=message["connected_account_id"]
        )
        if account is None or account["workspace_id"] != workspace_id:
            # [데이터경계] never project another workspace's message, even
            # if the caller passed its message_id explicitly.
            continue
        if source_id is not None and account["id"] != source_id:
            continue
        if account["status"] in _INACTIVE_ACCOUNT_STATUSES:
            # purge owns cleanup for a disconnecting/disconnected source —
            # rebuild does not race it (briefing.md §데이터경계).
            continue

        existing = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account["id"], message_id=message_id
        )
        importance_band = (
            importance_overrides[message_id]
            if message_id in importance_overrides
            else (existing["importance_band"] if existing is not None else None)
        )
        summary_text = (
            summary_overrides[message_id]
            if message_id in summary_overrides
            else (existing["summary_text"] if existing is not None else None)
        )
        item_id = existing["id"] if existing is not None else uuid.uuid4()

        await repository.upsert_briefing_item(
            connection,
            item_id=item_id,
            workspace_id=workspace_id,
            connected_account_id=account["id"],
            message_id=message_id,
            section=FAKE_SECTION,
            importance_band=importance_band,
            summary_text=summary_text,
            rebuilt_at=now,
        )
        rebuilt_message_ids.append(message_id)

    logger.info(
        "브리핑 프로젝션 재생성 완료",
        workspace_id=str(workspace_id),
        source_id=str(source_id) if source_id else None,
        message_count=len(rebuilt_message_ids),
    )
    return rebuilt_message_ids
