"""activity log 생성 + recovery(docs/goals/backend-plans/gmail_actions.md
"Job: execute_action" §[부분실패] and §activity_log recovery test).

Design note — action_summary copy: CLAUDE.md의 copy rule("카피 즉흥 생성 금지")은
user-facing UI text에 적용된다. `activity_logs.action_summary`는 결국 user-facing이다
(F11 활동 로그). 하지만 `design/copy-principles.md`에는 이 domain에서 직접 재사용할 수
있고 verbatim-confirmed된 phrase가 하나뿐이다("Gmail 읽음 처리" 아래
"Gmail에서도 읽음 처리했습니다."). 아래 mark_read에 이를 사용한다. 다른 세 action type
(archive, read_and_archive, label_apply)과 undo/reverse summary는 해당 문서에 standalone
confirmed phrase가 없다(가장 가까운 예시는 이 domain layer가 갖지 않는 특정 label name과
relative timestamp를 함께 사용). 그래서 "확정 문구가 없으면 placeholder" rule에 따라
`[미확정: ...]` placeholder로 둔다. 실제 UI에 도달하기 전에 product/copy에 보고해야 한다.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.gmail_actions import repository
from app.domains.gmail_actions.schemas import ActivityLogEntry

# reverse mutation이 well-defined된 action type(payload add_label_ids/remove_label_ids를
# 단순 swap하면 됨 — undo.py 참고).
REVERSIBLE_ACTION_TYPES = {"mark_read", "archive", "read_and_archive", "label_apply", "reverse_mutation"}

_ACTION_SUMMARIES = {
    "mark_read": "Gmail에서도 읽음 처리했습니다.",
    "archive": "[미확정: archive activity 요약 카피]",
    "read_and_archive": "[미확정: read_and_archive activity 요약 카피]",
    "label_apply": "[미확정: label_apply activity 요약 카피]",
    "reverse_mutation": "[미확정: undo(reverse) activity 요약 카피]",
}


def build_action_summary(action_type: str) -> str:
    """command가 수행한 일을 설명하는 최소한의 message-body-free 문구.

    여기에는 message subject/body/summary text를 절대 포함하지 않는다.
    "activity log는 감사와 사용자 설명에 필요한 최소 정보만 남긴다" invariant 참고.
    """
    return _ACTION_SUMMARIES.get(action_type, f"[미확정: {action_type} activity 요약 카피]")


def compute_undo_availability(*, action_type: str, changed: bool | None) -> bool:
    """[정상] applied + changed=True + 알려진 reversible action_type이면 undoable이다.

    changed=False(이미 target state)는 undo할 것이 없다
    (docs/goals/backend-plans/gmail_actions.md §Command 상태 전이 "changed=false ...
    되돌릴 변화 없음").
    """
    return bool(changed) and action_type in REVERSIBLE_ACTION_TYPES


async def ensure_activity_and_undo(
    connection: AsyncConnection,
    *,
    command: dict,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> tuple[dict, dict]:
    """command에 대한 activity_log + undo_actions pair를 생성하거나 recover한다.

    설계상 idempotent/recoverable하다. `command.status` + `command.applied_at`이
    "이 mutation이 발생했는가"의 source of truth이며, Gmail call 성공 후 activity_log insert
    commit 전에 crash가 나도 이 function을 다시 호출할 수 있다. command가 applied이면
    activity_log가 항상 존재한다고 가정하지 않고 ledger에서 backfill한다
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
    "Read API ... 활동 로그". [빈상태] row 없음 -> empty list이며 error가 아니다.
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
