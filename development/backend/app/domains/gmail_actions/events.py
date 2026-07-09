"""gmail_actions event catalog (producer=gmail_actions).

Mirrors docs/areas/backend/module-boundaries.md Event Catalog and
docs/goals/backend-plans/gmail_actions.md "Event(producer) 요약". Kept as a
single module so idempotency-key formatting isn't duplicated across
service.py / jobs/execute_action.py / undo.py.
"""

import uuid

GMAIL_ACTION_REQUESTED = "gmail_action_requested"
GMAIL_ACTION_APPLIED = "gmail_action_applied"
GMAIL_ACTION_FAILED = "gmail_action_failed"
GMAIL_ACTION_UNDONE = "gmail_action_undone"


def requested_key(command_id: uuid.UUID) -> str:
    return f"command:{command_id}:requested"


def applied_key(command_id: uuid.UUID, version: int) -> str:
    return f"command:{command_id}:applied:{version}"


def failed_key(command_id: uuid.UUID, version: int) -> str:
    return f"command:{command_id}:failed:{version}"


def undone_key(command_id: uuid.UUID, version: int) -> str:
    return f"command:{command_id}:undone:{version}"
