"""Live event -> job wiring — _integration-contract.md §3 / _build-schedule.md.

`app.core.discovery.collect_event_consumers` merges every domain's
EVENT_CONSUMERS as *declared intent* — several domains explicitly flag
entries there as "documented for the contract, not really wired yet"
(e.g. briefing/assistant_decisions' module docstrings say wiring happens
at IC2/IC3/IC5/IC6). Calling `dispatch_pending_events` with that raw
merged map turns every domain's declared intent live at once, including
event_type/job_type pairs whose payload shape was never actually proven
to line up end to end (see IC1 code review: gmail_snapshot_changed's
`message_ids` list can't generically fan out into N `{message_id}` jobs
through the pass-through dispatcher, and gmail_notification_received's
sync_delta fan-out is already handled by
mail_intake.service.process_notification directly).

This module is the dispatcher's actual activation switch. An
(event_type -> job_type list) entry is added here only when that
specific integration checkpoint has a passing cross-domain test proving
the payload shape works (tests/integration/test_ic*.py), one IC at a
time, per _build-schedule.md's sequential IC ordering.
"""

ACTIVE_EVENT_CONSUMERS: dict[str, list[str]] = {
    # IC1 (연결→sync) — tests/integration/test_ic1_connect_to_sync.py
    "gmail_source_connected": ["register_watch", "sync_full"],
}
