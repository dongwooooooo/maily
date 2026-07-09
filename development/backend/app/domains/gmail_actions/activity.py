"""Activity log construction + recovery (docs/goals/backend-plans/gmail_actions.md
"Job: execute_action" §[부분실패] and §activity_log recovery test).

Design note — action_summary copy: CLAUDE.md's copy rules ("카피 즉흥 생성
금지") apply to user-facing UI text. `activity_logs.action_summary` is
eventually user-facing (F11 활동 로그), but `design/copy-principles.md` only
has one directly reusable, verbatim-confirmed phrase for this domain
("Gmail에서도 읽음 처리했습니다." under "Gmail 읽음 처리") — used below for
mark_read. The other three action types (archive, read_and_archive,
label_apply) and the undo/reverse summary have no standalone confirmed
phrase in that document (the closest examples combine a specific label name
and relative timestamp this domain layer doesn't have), so they are left as
`[미확정: ...]` placeholders per the "확정 문구가 없으면 placeholder" rule.
Report these to product/copy before this reaches a real UI.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.gmail_actions import repository
from app.domains.gmail_actions.schemas import ActivityLogEntry

# Action types where a reverse mutation is well-defined (payload
# add_label_ids/remove_label_ids can simply be swapped — see undo.py).
REVERSIBLE_ACTION_TYPES = {"mark_read", "archive", "read_and_archive", "label_apply", "reverse_mutation"}

_ACTION_SUMMARIES = {
    "mark_read": "Gmail에서도 읽음 처리했습니다.",
    "archive": "[미확정: archive activity 요약 카피]",
    "read_and_archive": "[미확정: read_and_archive activity 요약 카피]",
    "label_apply": "[미확정: label_apply activity 요약 카피]",
    "reverse_mutation": "[미확정: undo(reverse) activity 요약 카피]",
}


def build_action_summary(action_type: str) -> str:
    """Minimal, message-body-free description of what a command did.

    Never include message subject/body/summary text here — see the
    "activity log는 감사와 사용자 설명에 필요한 최소 정보만 남긴다" invariant.
    """
    return _ACTION_SUMMARIES.get(action_type, f"[미확정: {action_type} activity 요약 카피]")


def compute_undo_availability(*, action_type: str, changed: bool | None) -> bool:
    """[정상] applied + changed=True + a known reversible action_type => undoable.

    changed=False (already in target state) has nothing to undo
    (docs/goals/backend-plans/gmail_actions.md §Command 상태 전이 "changed=false
    ... 되돌릴 변화 없음").
    """
    return bool(changed) and action_type in REVERSIBLE_ACTION_TYPES


async def ensure_activity_and_undo(
    connection: AsyncConnection,
    *,
    command: dict,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> tuple[dict, dict]:
    """Create (or recover) the activity_log + undo_actions pair for a command.

    Idempotent/recoverable by design: `command.status` + `command.applied_at`
    is the source of truth for "did this mutation happen", and this function
    can be called again after a crash between the Gmail call succeeding and
    the activity_log insert committing — it backfills from the ledger instead
    of assuming activity_log always exists once a command is applied
    (docs/goals/backend-plans/gmail_actions.md "Job: execute_action" §부분실패,
    test_activity_reconstructable_from_ledger).
    """
    existing_activity = await repository.get_activity_log_by_command(
        connection, command_id=command["id"]
    )
    if existing_activity is not None:
        undo_row = await repository.get_undo_action_by_activity(
            connection, activity_id=existing_activity["id"]
        )
        return existing_activity, undo_row

    activity_id = uuid.uuid4()
    occurred_at = datetime.now(timezone.utc)
    await repository.insert_activity_log(
        connection,
        activity_id=activity_id,
        workspace_id=workspace_id,
        command_id=command["id"],
        action_summary=build_action_summary(command["action_type"]),
        actor_id=actor_id,
        occurred_at=occurred_at,
    )

    undo_id = uuid.uuid4()
    undo_available = compute_undo_availability(
        action_type=command["action_type"], changed=command["changed"]
    )
    await repository.insert_undo_action(
        connection,
        undo_id=undo_id,
        activity_id=activity_id,
        original_command_id=command["id"],
        undo_available=undo_available,
    )

    activity_row = await repository.get_activity_log(connection, activity_id=activity_id)
    undo_row = await repository.get_undo_action_by_activity(connection, activity_id=activity_id)
    return activity_row, undo_row


async def list_activity(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[ActivityLogEntry]:
    """GET /actions/activity — docs/goals/backend-plans/gmail_actions.md
    "Read API ... 활동 로그". [빈상태] no rows -> empty list, not an error.
    """
    rows = await repository.list_activity_logs(connection, workspace_id=workspace_id)
    entries = []
    for row in rows:
        undo_row = await repository.get_undo_action_by_activity(connection, activity_id=row["id"])
        entries.append(
            ActivityLogEntry(
                id=row["id"],
                workspace_id=row["workspace_id"],
                command_id=row["command_id"],
                action_summary=row["action_summary"],
                actor_id=row["actor_id"],
                occurred_at=row["occurred_at"],
                undo_available=bool(undo_row and undo_row["undo_available"] and undo_row["undone_at"] is None),
                undone_at=undo_row["undone_at"] if undo_row else None,
            )
        )
    return entries
