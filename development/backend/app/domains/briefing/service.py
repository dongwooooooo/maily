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

    항상 briefing_items에 per-message_id upsert를 수행하며, full delete+reinsert는 하지 않는다.
    "언제든 drop-and-rebuild 가능해야 한다" invariant는 이 function의 mechanics가 아니라
    *table*을 설명한다. 실제 drop-and-rebuild 증명은 test_projection_regenerable.py 참고.

    summary_text/importance_band는 호출마다 assistant_decisions의
    message_summaries/message_importance_classifications에서 새로 읽는다
    (repository.get_message_summary/get_message_importance). 해당 domain이 아직 결과를
    만들지 않았으면 null이다. 그래서 문서화된 6개 trigger type 중 어느 것이 rebuild를
    trigger하더라도(gmail_snapshot_changed, summary_completed, importance_classified,
    gmail_action_applied/undone, reminder_reactivated) 어떤 event가 쏘았는지와 무관하게 같은
    real state로 수렴한다(briefing.md Job §동시 — "rebuild가 원본 전체를 재조회").
    IC2/IC3 coordinator note: 이 function의 이전 version은 이 lookup을 simulate하려고
    summary_overrides/importance_overrides param을 받았다. briefing의 isolated worktree에
    message_summaries/message_importance_classifications(migration 0010)가 아직 없던 때의
    코드였고, 실제 table이 merge된 지금 제거했다.
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
            # [선행조건] message가 아직 snapshot에 없으면 project할 것이 없다.
            continue

        account = await repository.get_connected_account(
            connection, connected_account_id=message["connected_account_id"]
        )
        if account is None or account["workspace_id"] != workspace_id:
            # [데이터경계] caller가 message_id를 명시적으로 넘겼더라도 다른 workspace의
            # message는 절대 project하지 않는다.
            continue
        if source_id is not None and account["id"] != source_id:
            continue
        if account["status"] in _INACTIVE_ACCOUNT_STATUSES:
            # disconnecting/disconnected source의 cleanup은 purge가 소유한다. rebuild는
            # purge와 race하지 않는다(briefing.md §데이터경계).
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
