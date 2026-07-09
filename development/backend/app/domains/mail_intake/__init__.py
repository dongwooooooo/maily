from app.domains.mail_intake.jobs import (
    poll_history,
    process_notification,
    register_watch,
    renew_watch,
    sync_delta,
    sync_full,
)
from app.domains.mail_intake.router import router as router

JOB_HANDLERS: dict = {
    "register_watch": register_watch.handle,
    "renew_watch": renew_watch.handle,
    "process_notification": process_notification.handle,
    "poll_history": poll_history.handle,
    "sync_delta": sync_delta.handle,
    "sync_full": sync_full.handle,
}

EVENT_CONSUMERS: dict = {
    # producer: mail_sources — consumer job lives in this domain
    "gmail_source_connected": ["register_watch"],
    "gmail_notification_received": ["sync_delta"],
}

PURGE_HANDLER = None
