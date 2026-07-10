"""`reactivate_reminders` job — docs/goals/backend-plans/briefing.md "Job:
reactivate_reminders". scheduled(due-scan) trigger이며 payload는 `{}`,
lock_key는 null이다(_integration-contract.md §2).
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event
from app.domains.briefing import events, repository

logger = structlog.get_logger()


async def run_reactivate_reminders(connection: AsyncConnection) -> list[uuid.UUID]:
    """`remind_at`이 지난 모든 `pending` reminder를 집어 `reactivated`로 transition하고
    `reminder_reactivated`를 emit한다.

    repository.reactivate_reminder_if_pending의 conditional `WHERE status='pending'`
    update가 concurrent scan에서도 안전하게 만들고(briefing.md §동시), 재실행도 안전하게
    만든다(§멱등 — 이미 reactivated된 reminder의 remind_at은 여전히 과거일 수 있지만 status가
    더 이상 'pending'이 아니므로 conditional update가 실행되기 전에 다음 scan의 candidate
    list에서 제외된다).
    """
    now = datetime.now(timezone.utc)
    due = await repository.list_due_pending_reminders(connection, now=now)

    reactivated_ids: list[uuid.UUID] = []
    for reminder in due:
        result = await repository.reactivate_reminder_if_pending(
            connection, reminder_id=reminder["id"], reactivated_at=now
        )
        if result is None:
            # 다른 scan과의 race에서 졌거나 이미 reactivated된 경우다.
            # [동시]/[멱등] guard이며 error가 아니다.
            continue

        state = await repository.get_item_state(
            connection, item_state_id=result["briefing_item_state_id"]
        )
        if state is None:
            # briefing_item_state_id는 현재 delete path가 없는 non-nullable FK라서 발생하면
            # 안 된다. 그래도 발생하면(gmail_actions execute_action._finalize_undo_if_reverse의
            # 동일 guard와 같은 패턴), 나중에 worker가 결과 job을 집은 뒤에야 실패할
            # workspace_id/message_id: null event를 emit하지 말고 publish를 건너뛴다.
            logger.warning(
                "reminder의 item_state row가 사라져 reminder_reactivated 발행 생략",
                reminder_id=str(result["id"]),
            )
            reactivated_ids.append(result["id"])
            continue
        await append_event(
            connection,
            event_type=events.REMINDER_REACTIVATED,
            producer_domain="briefing",
            payload={
                "reminder_id": str(result["id"]),
                "briefing_item_state_id": str(result["briefing_item_state_id"]),
                "message_id": str(state["message_id"]),
                "workspace_id": str(state["workspace_id"]),
            },
            idempotency_key=events.reminder_reactivated_key(result["id"]),
        )
        reactivated_ids.append(result["id"])

    logger.info("리마인더 재활성화 스캔 완료", reactivated_count=len(reactivated_ids))
    return reactivated_ids


async def reactivate_reminders_job(payload: dict) -> None:
    """JOB_HANDLERS["reactivate_reminders"] entry point — __init__.py 참고."""
    from app.core.database import engine

    async with engine.begin() as connection:
        await run_reactivate_reminders(connection)
