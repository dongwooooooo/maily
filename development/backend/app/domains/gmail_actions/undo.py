"""`undo_gmail_action` — docs/goals/backend-plans/gmail_actions.md
"Command: undo_gmail_action".

Undo는 GmailMutationPort를 직접 호출하지 않는다. brand-new `pending` command(reverse)를
만들고 같은 `gmail_action_requested` -> `execute_action` ledger path로 다시 보낸다.
`reverse_command_id`가 이를 강제하는 physical device다(gmail_mutator.py docstring 참고).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.outbox import append_event
from app.domains.gmail_actions import events, repository
from app.domains.gmail_actions.schemas import UndoResult

# reverse command에 할당하는 action_type. user가 request할 수 있는 4개 SUPPORTED_ACTION_TYPES
# 중 하나가 아니다. gmail_actions.md는 action_type별 reverse *payload*(add/remove label id
# array swap)는 고정하지만 reverse command 자체의 action_type column 값은 명명하지 않으므로
# 이렇게 concrete choice를 했다. activity/audit read가 "did X"와 "undid X"를 구분할 수
# 있도록 original action_type과 분리해 둔다.
REVERSE_ACTION_TYPE = "reverse_mutation"


def compute_reverse_payload(payload: dict) -> dict:
    """add_label_ids/remove_label_ids를 swap한다.

    이는 catalog에 있는 네 action type(mark_read/archive/read_and_archive/label_apply)에 대해
    gmail_actions.md §Command: undo_gmail_action의 per-type reverse mapping을 action_type
    이름별이 아니라 generic하게 표현한 것이다.
    """
    return {
        "add_label_ids": list(payload.get("remove_label_ids") or []),
        "remove_label_ids": list(payload.get("add_label_ids") or []),
    }


def _to_result(row: dict) -> UndoResult:
    return UndoResult(**row)


async def request_undo(
    connection: AsyncConnection,
    *,
    activity_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> UndoResult:
    """[정상]/[멱등]/[동시]/[선행조건] — gmail_actions.md §undo_gmail_action 참고."""
    activity_row = await repository.get_activity_log(connection, activity_id=activity_id)
    if activity_row is None or activity_row["workspace_id"] != workspace_id:
        raise NotFoundError("activity not found")

    undo_row = await repository.get_undo_action_by_activity(connection, activity_id=activity_id)
    if undo_row is None:
        raise ValidationError("activity has no undo record")
    if undo_row["undone_at"] is not None:
        # [멱등] 이미 undone이면 no-op이며 기존 terminal state를 반환한다.
        return _to_result(undo_row)
    if undo_row["reverse_command_id"] is not None:
        # [동시] 이 undo에 대한 reverse command가 이미 in flight다.
        raise ConflictError("undo already in progress for this activity")
    if not undo_row["undo_available"]:
        raise ValidationError("this action is not undoable")

    original_command = await repository.get_command(
        connection, command_id=undo_row["original_command_id"]
    )
    if original_command is None:
        raise NotFoundError("original command not found")
    if original_command["status"] != "applied":
        # [선행조건] failed/compensating/undone은 여기서 (재)undo할 수 없다.
        raise ConflictError("original command is not in an undoable state")

    reverse_command_id = uuid.uuid4()
    reverse_payload = compute_reverse_payload(original_command["payload"])
    now = datetime.now(timezone.utc)

    await repository.insert_command(
        connection,
        command_id=reverse_command_id,
        connected_account_id=original_command["connected_account_id"],
        message_id=original_command["message_id"],
        action_type=REVERSE_ACTION_TYPE,
        payload=reverse_payload,
        idempotency_key=f"undo:{undo_row['id']}:reverse",
        requested_by=actor_id,
        requested_at=now,
    )
    await append_event(
        connection,
        event_type=events.GMAIL_ACTION_REQUESTED,
        producer_domain="gmail_actions",
        payload={"command_id": str(reverse_command_id)},
        idempotency_key=events.requested_key(reverse_command_id),
    )

    new_version = original_command["version"] + 1
    await repository.mark_command_compensating(
        connection, command_id=original_command["id"], version=new_version
    )
    await repository.set_undo_action_reverse_command(
        connection, undo_id=undo_row["id"], reverse_command_id=reverse_command_id
    )

    updated = await repository.get_undo_action_by_activity(connection, activity_id=activity_id)
    return _to_result(updated)
