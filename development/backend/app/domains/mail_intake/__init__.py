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
    # producer: mail_sources — consumer job은 이 domain에 있다.
    # _integration-contract.md §3: gmail_source_connected는 register_watch와 initial sync_full
    # 둘 다 queue한다("+ 초기 sync_full").
    "gmail_source_connected": ["register_watch", "sync_full"],
    # producer: gmail_actions — IC4 "mail_intake snapshot reconcile" 기준.
    "gmail_action_applied": ["reconcile_action"],
    # NOTE: §3은 sync_delta를 consumer로 지목하지만 gmail_notification_received는 여기에
    # 나열하지 않는다. service.process_notification이 이미 직접 fan-out한다. 하나의 Pub/Sub
    # notification은 여러 active source를 건드릴 수 있고, 각 source는 generic dispatcher가
    # event의 {email_address, history_id} shape에서 파생할 수 없는 실제
    # {source_id, start_history_id} payload의 sync_delta job이 필요하다(1 event -> N jobs,
    # generic pass-through dispatcher로 표현 불가 — app/core/jobs/outbox_dispatcher.py
    # docstring 및 app/core/jobs/wiring.py 참고). 여기에 나열하면 dispatch_pending_events가
    # process_notification의 올바른 job 옆에 두 번째 malformed sync_delta job을 중복 enqueue하게 된다.
}

PURGE_HANDLER = purge_source
