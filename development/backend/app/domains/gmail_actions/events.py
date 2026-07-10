"""gmail_actions event catalog(producer=gmail_actions).

docs/areas/backend/module-boundaries.md Event Catalog와
docs/goals/backend-plans/gmail_actions.md "Event(producer) 요약"을 mirror한다.
idempotency-key formatting이 service.py / jobs/execute_action.py / undo.py에 중복되지 않도록
단일 module로 유지한다.
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
