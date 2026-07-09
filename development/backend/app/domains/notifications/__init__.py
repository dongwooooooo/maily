from app.domains.notifications.jobs.emit_notification import emit_notification_job
from app.domains.notifications.router import router as router
from app.domains.notifications.service import (
    TRIGGER_CLEANUP_PROPOSAL_CREATED,
    TRIGGER_GMAIL_ACTION_FAILED,
    TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
    TRIGGER_REMINDER_REACTIVATED,
)

JOB_HANDLERS: dict = {"emit_notification": emit_notification_job}

# Only the 4 event types named in this task's scope are wired here —
# gmail_action_undone and the gmail_snapshot_changed-derived triggers
# are supported by service.resolve_route_target but intentionally not
# auto-consumed yet. See service.py module docstring "Trigger scope
# note" for why.
EVENT_CONSUMERS: dict = {
    TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED: ["emit_notification"],
    TRIGGER_GMAIL_ACTION_FAILED: ["emit_notification"],
    TRIGGER_CLEANUP_PROPOSAL_CREATED: ["emit_notification"],
    TRIGGER_REMINDER_REACTIVATED: ["emit_notification"],
}

# notifications owns no content-bearing data tied to a Gmail source (it
# only stores route_target ids/screen keys — notifications.md "[데이터
# 경계]" and "워크트리 격리 노트" §2: "PURGE_HANDLER는 None(notifications는
# content-bearing purge 대상 아님 — source state view-only)").
PURGE_HANDLER = None
