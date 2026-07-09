"""`build_briefing` job — docs/goals/backend-plans/briefing.md "Job:
build_briefing".

Official trigger events (_integration-contract.md §3):
`gmail_snapshot_changed`, `summary_completed`, `importance_classified`,
`gmail_action_applied`, `gmail_action_undone`, `reminder_reactivated`.
Wired through the outbox dispatcher to this job at IC2/IC3
(app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS). `handle_build_briefing_trigger`
below is what tests call directly to exercise each trigger's rebuild scope.
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
    """Per-trigger rebuild scope (briefing.md "트리거별 재생성 범위").

    Every trigger type converges on the same rebuild — service.
    rebuild_briefing re-reads current summary_text/importance_band from
    assistant_decisions' tables fresh on every call, so there's no
    per-trigger override to thread through here. `trigger_type` stays an
    explicit, validated parameter: it documents which of the 6
    contract-listed event types is calling this, and rejects anything
    else.
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
    """JOB_HANDLERS["build_briefing"] entry point — see __init__.py.

    payload shape per _integration-contract.md §2:
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
