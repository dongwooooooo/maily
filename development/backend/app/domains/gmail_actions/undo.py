"""`undo_gmail_action` — docs/goals/backend-plans/gmail_actions.md
"Command: undo_gmail_action".

Undo never calls GmailMutationPort directly. It creates a brand new
`pending` command (the reverse) and routes it back through the same
`gmail_action_requested` -> `execute_action` ledger path — `reverse_command_id`
is the physical device that forces this (see gmail_mutator.py docstring).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.outbox import append_event
from app.domains.gmail_actions import events, repository
from app.domains.gmail_actions.schemas import UndoResult

# action_type assigned to a reverse command. Not one of the four
# user-requestable SUPPORTED_ACTION_TYPES — a concrete choice made because
# gmail_actions.md pins the reverse *payload* per action_type (swap
# add/remove label id arrays) but does not name a value for the reverse
# command's own action_type column. Kept distinct from the original
# action_type so activity/audit reads can tell "did X" apart from "undid X".
REVERSE_ACTION_TYPE = "reverse_mutation"


def compute_reverse_payload(payload: dict) -> dict:
    """Swap add_label_ids/remove_label_ids — this is exactly the per-type
    reverse mapping in gmail_actions.md §Command: undo_gmail_action for all
    four catalogued action types (mark_read/archive/read_and_archive/
    label_apply), expressed generically instead of by action_type name.
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
    """[정상]/[멱등]/[동시]/[선행조건] — see gmail_actions.md §undo_gmail_action."""
    activity_row = await repository.get_activity_log(connection, activity_id=activity_id)
    if activity_row is None or activity_row["workspace_id"] != workspace_id:
        raise NotFoundError("activity not found")

    undo_row = await repository.get_undo_action_by_activity(connection, activity_id=activity_id)
    if undo_row is None:
        raise ValidationError("activity has no undo record")
    if undo_row["undone_at"] is not None:
        # [멱등] already undone — no-op, return the existing terminal state.
        return _to_result(undo_row)
    if undo_row["reverse_command_id"] is not None:
        # [동시] a reverse command is already in flight for this undo.
        raise ConflictError("undo already in progress for this activity")
    if not undo_row["undo_available"]:
        raise ValidationError("this action is not undoable")

    original_command = await repository.get_command(
        connection, command_id=undo_row["original_command_id"]
    )
    if original_command is None:
        raise NotFoundError("original command not found")
    if original_command["status"] != "applied":
        # [선행조건] failed/compensating/undone are not (re-)undoable here.
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
