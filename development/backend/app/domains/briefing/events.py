"""briefing event catalog(producer=briefing).

docs/areas/backend/module-boundaries.md Event Catalog와
docs/goals/backend-plans/briefing.md "소유 event(producer)"를 mirror한다.
idempotency-key formatting이 item_state.py / reminders.py에 중복되지 않도록 단일 module로
유지한다.
"""

import uuid

ITEM_STATE_CHANGED = "briefing_item_state_changed"
REMINDER_REACTIVATED = "reminder_reactivated"


def item_state_changed_key(item_state_id: uuid.UUID, version: int) -> str:
    return f"item:{item_state_id}:state:{version}"


def reminder_reactivated_key(reminder_id: uuid.UUID, version: int = 0) -> str:
    """`reminders`(db-schema.md)에는 version column이 없다.

    briefing_item_states와 달리 reminder의 pending->reactivated transition은 terminal이고
    최대 한 번만 발생한다(briefing.md §reminder 상태 전이:
    "reactivated/cancelled는 종료 상태 — 다시 pending으로 돌아가지 않는다"). 따라서
    briefing.md key format의 `{version}` slot은 여기서 항상 0이다.
    """
    return f"reminder:{reminder_id}:reactivated:{version}"
