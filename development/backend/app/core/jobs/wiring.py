"""Live event -> job wiring — _integration-contract.md §3 / _build-schedule.md.

`app.core.discovery.collect_event_consumers`는 모든 domain의 EVENT_CONSUMERS를
*선언된 의도*로 merge한다. 여러 domain은 거기 있는 entry가 "contract 문서용이며
아직 실제로 wired된 것은 아님"이라고 명시한다(예: briefing/assistant_decisions의
module docstring은 wiring이 IC2/IC3/IC5/IC6에서 일어난다고 적는다). 그 raw merged map으로
`dispatch_pending_events`를 호출하면 모든 domain의 선언된 의도가 한 번에 live가 되며,
payload shape가 end to end로 맞는지 실제 입증되지 않은 event_type/job_type pair까지
포함된다(IC1 code review 참고: gmail_snapshot_changed의 `message_ids` list는
pass-through dispatcher를 통해 N개의 `{message_id}` job으로 generic fan-out할 수 없고,
gmail_notification_received의 sync_delta fan-out은 이미
mail_intake.service.process_notification이 직접 처리한다).

이 module은 dispatcher의 실제 activation switch다. (event_type -> job_type list)
entry는 해당 integration checkpoint에서 payload shape가 동작함을 입증하는 cross-domain
test(tests/integration/test_ic*.py)가 통과할 때만, _build-schedule.md의 순차 IC 순서에
따라 IC별로 하나씩 여기에 추가한다.
"""

ACTIVE_EVENT_CONSUMERS: dict[str, list[str]] = {
    # IC1 (연결→sync) — tests/integration/test_ic1_connect_to_sync.py
    "gmail_source_connected": ["register_watch", "sync_full"],
    # IC2+IC3 (sync→briefing, sync→assistant→briefing 부분재생성) —
    # 관련 test: tests/integration/test_ic2_ic3_sync_to_briefing_and_assistant.py.
    # gmail_snapshot_changed는 message별 generate_summary/classify_importance job으로
    # fan-out되고(outbox_dispatcher._fan_out_per_message_id), 전체 message_ids list를 담은
    # build_briefing job 하나도 만든다.
    "gmail_snapshot_changed": ["build_briefing", "generate_summary", "classify_importance"],
    "summary_completed": ["build_briefing"],
    "importance_classified": ["build_briefing"],
    # IC4 (action ledger) 관련 test — tests/integration/test_ic4_action_ledger.py.
    # gmail_action_applied는 briefing뿐 아니라 mail_intake의 own-action snapshot
    # reconcile도 구동한다(message-less command에는 outbox_dispatcher.py의
    # _skip_if_no_message_id guard 적용).
    "gmail_action_requested": ["execute_action"],
    "gmail_action_applied": ["build_briefing", "reconcile_action"],
    "gmail_action_undone": ["build_briefing"],
    # IC5 (labels 이동→action·rule) — tests/integration/test_ic5_labels_move.py.
    # "move → label apply command"는 dispatcher-wired가 아니다. labels.md §73은 이것이
    # event/job pair가 아니라 labels.service.move_message_to_label에서 직접 수행하는
    # synchronous request_gmail_action call이라고 명시한다. rule-suggestion 절반만
    # dispatcher를 거친다.
    "label_correction_recorded": ["create_rule_suggestions"],
    # IC6 (cleanup 승인→action)도 마찬가지로 dispatcher-wired가 아니다.
    # assistant_decisions.cleanup.approve_cleanup_proposal이 이미
    # gmail_actions.request_gmail_action을 직접 호출한다(module-boundaries.md F10).
    # W3에서 실제 gmail_actions module을 대상으로 build/test됐고(assistant_decisions
    # worktree가 들어올 때 Task 9는 이미 merge됨), IC6용 새 wiring entry는 여기 필요 없다.
    # IC7 (알림 라우팅) — tests/integration/test_ic7_notifications.py.
    # notifications.md의 route_target table이 이미 깔끔하게 resolve하는 trigger 4개만
    # wired한다(notifications/service.py "Trigger scope note"). gmail_action_undone->
    # emit_notification과 gmail_snapshot_changed split 2개는 unwired로 둔다. 이유는 같은
    # docstring과 outbox_dispatcher.py의 IC7 comment 참고.
    "gmail_source_recovery_needed": ["emit_notification"],
    "gmail_action_failed": ["emit_notification"],
    "cleanup_proposal_created": ["emit_notification"],
    # reminder_reactivated -> build_briefing은 IC2/IC3부터 contract 문서에 있었지만
    # (_integration-contract.md §3) 실제로 wired되지는 않았다(그 wave의 scope column은
    # summary_completed/importance_classified만 언급). 둘 다 같은 event를 consume하므로
    # notification 절반과 함께 여기서 완성한다.
    "reminder_reactivated": ["build_briefing", "emit_notification"],
    # W4/IC8 (disconnect→purge) 관련 test — tests/integration/test_ic8_disconnect_purge.py.
    # source-locked(outbox_dispatcher._SOURCE_LOCKED_JOB_TYPES)이므로 purge가 같은
    # account의 동시 sync/watch job과 race하지 않는다.
    "gmail_source_disconnected": ["purge_disconnected_source"],
}
