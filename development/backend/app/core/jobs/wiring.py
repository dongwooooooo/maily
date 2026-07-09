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
    # IC2+IC3 (sync→briefing, sync→assistant→briefing 부분재생성) —
    # tests/integration/test_ic2_ic3_sync_to_briefing_and_assistant.py.
    # gmail_snapshot_changed fans out to per-message generate_summary/
    # classify_importance jobs (outbox_dispatcher._fan_out_per_message_id)
    # and one build_briefing job carrying the whole message_ids list.
    "gmail_snapshot_changed": ["build_briefing", "generate_summary", "classify_importance"],
    "summary_completed": ["build_briefing"],
    "importance_classified": ["build_briefing"],
    # IC4 (action ledger) — tests/integration/test_ic4_action_ledger.py.
    # gmail_action_applied also drives mail_intake's own-action snapshot
    # reconcile (outbox_dispatcher.py's _skip_if_no_message_id guard for
    # message-less commands), not just briefing.
    "gmail_action_requested": ["execute_action"],
    "gmail_action_applied": ["build_briefing", "reconcile_action"],
    "gmail_action_undone": ["build_briefing"],
    # IC5 (labels 이동→action·rule) — tests/integration/test_ic5_labels_move.py.
    # "move → label apply command" is NOT dispatcher-wired — labels.md §73
    # is explicit that's a direct synchronous request_gmail_action call
    # from labels.service.move_message_to_label, not an event/job pair.
    # Only the rule-suggestion half goes through the dispatcher.
    "label_correction_recorded": ["create_rule_suggestions"],
    # IC6 (cleanup 승인→action) is likewise NOT dispatcher-wired —
    # assistant_decisions.cleanup.approve_cleanup_proposal already calls
    # gmail_actions.request_gmail_action directly (module-boundaries.md
    # F10), built and tested against the real gmail_actions module back
    # in W3 (Task 9 was already merged by the time assistant_decisions'
    # worktree landed) — no new wiring entry needed here for IC6.
}
