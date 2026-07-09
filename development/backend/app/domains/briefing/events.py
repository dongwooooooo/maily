"""briefing event catalog (producer=briefing).

Mirrors docs/areas/backend/module-boundaries.md Event Catalog and
docs/goals/backend-plans/briefing.md "소유 event(producer)". Kept as a
single module so idempotency-key formatting isn't duplicated across
item_state.py / reminders.py.
"""

import uuid

ITEM_STATE_CHANGED = "briefing_item_state_changed"
REMINDER_REACTIVATED = "reminder_reactivated"


def item_state_changed_key(item_state_id: uuid.UUID, version: int) -> str:
    return f"item:{item_state_id}:state:{version}"


def reminder_reactivated_key(reminder_id: uuid.UUID, version: int = 0) -> str:
    """`reminders` (db-schema.md) has no version column — unlike
    briefing_item_states, a reminder's pending->reactivated transition is
    terminal and happens at most once (briefing.md §reminder 상태 전이:
    "reactivated/cancelled는 종료 상태 — 다시 pending으로 돌아가지 않는다"),
    so the `{version}` slot in the briefing.md key format is always 0 here.
    """
    return f"reminder:{reminder_id}:reactivated:{version}"
