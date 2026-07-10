from app.domains.notifications.jobs.emit_notification import emit_notification_job
from app.domains.notifications.router import router as router
from app.domains.notifications.service import (
    TRIGGER_CLEANUP_PROPOSAL_CREATED,
    TRIGGER_GMAIL_ACTION_FAILED,
    TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
    TRIGGER_REMINDER_REACTIVATED,
)

JOB_HANDLERS: dict = {"emit_notification": emit_notification_job}

# 이 task scope에 명시된 event type 4개만 여기서 wired한다. gmail_action_undone과
# gmail_snapshot_changed-derived trigger는 service.resolve_route_target이 지원하지만 아직
# 의도적으로 auto-consume하지 않는다. 이유는 service.py module docstring "Trigger scope note" 참고.
EVENT_CONSUMERS: dict = {
    TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED: ["emit_notification"],
    TRIGGER_GMAIL_ACTION_FAILED: ["emit_notification"],
    TRIGGER_CLEANUP_PROPOSAL_CREATED: ["emit_notification"],
    TRIGGER_REMINDER_REACTIVATED: ["emit_notification"],
}

# notifications는 Gmail source에 묶인 content-bearing data를 소유하지 않는다(route_target
# id/screen key만 저장 — notifications.md "[데이터경계]" 및 "워크트리 격리 노트" §2:
# "PURGE_HANDLER는 None(notifications는 content-bearing purge 대상 아님 — source state view-only)").
PURGE_HANDLER = None
