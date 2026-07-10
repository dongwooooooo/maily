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
) -> list[uuid.UUID]:
    """Command `rebuild_briefing` — docs/goals/backend-plans/briefing.md.

    Always a per-message_id upsert into briefing_items, never a full
    delete+reinsert (the "언제든 drop-and-rebuild 가능해야 한다" invariant
    describes the *table*, not this function's mechanics — see
    test_projection_regenerable.py for a literal drop-and-rebuild proof).

    summary_text/importance_band are re-read fresh from
    assistant_decisions' message_summaries/message_importance_classifications
    on every call (repository.get_message_summary/get_message_importance) —
    null if that domain hasn't produced a result yet. This is what makes
    a rebuild triggered by ANY of the 6 documented trigger types
    (gmail_snapshot_changed, summary_completed, importance_classified,
    gmail_action_applied/undone, reminder_reactivated) converge on the
    same real state regardless of which event fired it (briefing.md Job
    §동시 — "rebuild가 원본 전체를 재조회"). IC2/IC3 coordinator note: an
    earlier version of this function took summary_overrides/
    importance_overrides params to simulate this lookup, from when
    message_summaries/message_importance_classifications (migration 0010)
    didn't exist yet in briefing's isolated worktree — removed now that
    the real tables are merged.
    """
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
        summary_row = await repository.get_message_summary(connection, message_id=message_id)
        importance_row = await repository.get_message_importance(connection, message_id=message_id)
        summary_text = summary_row["summary_text"] if summary_row is not None else None
        importance_band = importance_row["importance_band"] if importance_row is not None else None
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
