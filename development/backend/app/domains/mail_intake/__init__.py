from app.domains.mail_intake.jobs import (
    poll_history,
    process_notification,
    reconcile_action,
    register_watch,
    renew_watch,
    sync_delta,
    sync_full,
)
from app.domains.mail_intake.purge import purge_source
from app.domains.mail_intake.router import router as router

JOB_HANDLERS: dict = {
    "register_watch": register_watch.handle,
    "renew_watch": renew_watch.handle,
    "process_notification": process_notification.handle,
    "poll_history": poll_history.handle,
    "sync_delta": sync_delta.handle,
    "sync_full": sync_full.handle,
    "reconcile_action": reconcile_action.handle,
}

EVENT_CONSUMERS: dict = {
    # producer: mail_sources — consumer job lives in this domain.
    # _integration-contract.md §3: gmail_source_connected queues both
    # register_watch AND an initial sync_full ("+ 초기 sync_full").
    "gmail_source_connected": ["register_watch", "sync_full"],
    # producer: gmail_actions — IC4 "mail_intake snapshot reconcile".
    "gmail_action_applied": ["reconcile_action"],
    # NOTE: gmail_notification_received is NOT listed here even though
    # §3 names sync_delta as its consumer. service.process_notification
    # already fans this out itself — one Pub/Sub notification can touch
    # several active sources, each needing its own sync_delta job with a
    # real {source_id, start_history_id} payload the generic dispatcher
    # can't derive from the event's {email_address, history_id} shape
    # (1 event -> N jobs, not expressible by the generic pass-through
    # dispatcher — see app/core/jobs/outbox_dispatcher.py's docstring and
    # app/core/jobs/wiring.py). Listing it here would make
    # dispatch_pending_events double-enqueue a second, malformed
    # sync_delta job alongside process_notification's own correct one.
}

PURGE_HANDLER = purge_source
