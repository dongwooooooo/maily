"""`build_briefing` job — docs/goals/backend-plans/briefing.md "Job:
build_briefing".

공식 trigger event(_integration-contract.md §3):
`gmail_snapshot_changed`, `summary_completed`, `importance_classified`,
`gmail_action_applied`, `gmail_action_undone`, `reminder_reactivated`.
IC2/IC3에서 outbox dispatcher를 통해 이 job으로 wired된다
(app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS). 아래 `handle_build_briefing_trigger`는
test가 각 trigger의 rebuild scope를 검증하기 위해 직접 호출하는 함수다.
"""

import uuid

import structlog

from app.core.errors import ValidationError
from app.domains.briefing import service

logger = structlog.get_logger()

TRIGGER_TYPES = frozenset(
    {
        "gmail_snapshot_changed",
        "summary_completed",
        "importance_classified",
        "gmail_action_applied",
        "gmail_action_undone",
        "reminder_reactivated",
    }
)


async def handle_build_briefing_trigger(
    connection,
    *,
    trigger_type: str,
    workspace_id: uuid.UUID,
    message_ids: list[uuid.UUID],
    source_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """trigger별 rebuild scope(briefing.md "트리거별 재생성 범위").

    모든 trigger type은 같은 rebuild로 수렴한다. service.rebuild_briefing은 호출마다
    assistant_decisions table에서 현재 summary_text/importance_band를 새로 읽으므로,
    여기로 전달할 trigger별 override는 없다. `trigger_type`은 explicit하고 validated된
    parameter로 유지한다. contract에 나열된 6개 event type 중 무엇이 호출했는지를 문서화하고
    그 외 값을 거부하기 위해서다.
    """
    if trigger_type not in TRIGGER_TYPES:
        raise ValidationError(f"unknown build_briefing trigger_type: {trigger_type}")

    rebuilt = await service.rebuild_briefing(
        connection,
        workspace_id=workspace_id,
        source_id=source_id,
        message_ids=message_ids,
    )
    logger.info(
        "build_briefing 트리거 처리 완료",
        trigger_type=trigger_type,
        workspace_id=str(workspace_id),
        message_count=len(rebuilt),
    )
    return rebuilt


async def build_briefing_job(payload: dict) -> None:
    """JOB_HANDLERS["build_briefing"] entry point — __init__.py 참고.

    _integration-contract.md §2 기준 payload shape:
    `{workspace_id, source_id?, message_ids?}`.
    """
    from app.core.database import engine

    workspace_id = uuid.UUID(str(payload["workspace_id"]))
    source_id = uuid.UUID(str(payload["source_id"])) if payload.get("source_id") else None
    message_ids = (
        [uuid.UUID(str(m)) for m in payload["message_ids"]]
        if payload.get("message_ids")
        else None
    )
    async with engine.begin() as connection:
        await service.rebuild_briefing(
            connection, workspace_id=workspace_id, source_id=source_id, message_ids=message_ids
        )
