# notifications 세부 플랜 (Notifications & Recovery)

기준: `module-boundaries.md`(컨텍스트·Command/Event Catalog·흐름 7·F13·F14), `db-schema.md`(notifications 섹션), `_integration-contract.md`(충돌 규약 §1·§2·§3·§5). 대응 Task: 12(알림 라우팅·구독·복구 view).

## 도메인 책임 요약

browser push 구독, notification event 발행, route target 결정, 권한/sync 복구 안내 view. **소유 안 함**: account/sync source state(mail_sources·mail_intake), Gmail mutation(gmail_actions), message snapshot(mail_intake). 다른 도메인 event를 소비해 알림으로 변환할 뿐, 상태의 source of truth는 발행 도메인에 있다.

강제 invariant(이 도메인이 지키는 것):
- 모든 notification event는 `route_target`을 가진다 — generic landing route를 만들지 않는다. route target 없이는 알림이 "일반 landing page"가 되어 최상위 원칙("기존 화면과 selected item으로 착지")을 깬다.
- 복구 안내는 source state의 view만 만든다 — `connected_gmail_accounts.status`·`gmail_sync_cursors`를 직접 쓰지 않는다(view-only).
- browser push는 구독(`notification_subscriptions`)이 있고 해지(`revoked_at`)되지 않은 대상에만 발송한다.
- 소비 event 종류가 늘어도 알림 처리 분기는 `notification_type` + `route_target` 두 필드로만 구분한다 — event별로 route 로직을 복제하지 않는다.

소유 테이블: `notification_subscriptions`, `notification_events`.
소유 event(producer): `notification_event_created`(→ browser push worker).
소유 job: `emit_notification`.

## Route target 매핑 (`notification_events.route_target`)

`route_target`은 "어느 화면 + 어느 selected item"을 담는 jsonb다. 소비 event별 착지점을 아래로 고정한다 — 이 표에 없는 조합은 새로 만들지 않는다(generic landing 금지 invariant).

| 소비 event | notification_type | 착지 화면 | selected item |
|---|---|---|---|
| `gmail_snapshot_changed`(중요 메일) | `important_mail` | 오늘 브리핑 | 해당 message |
| `reminder_reactivated` | `reminder_due` | 오늘 브리핑(보관함 예정) | 해당 briefing item |
| `gmail_snapshot_changed`(전체 브리핑) | `daily_briefing` | 오늘 브리핑 | 없음(화면만) |
| `cleanup_proposal_created` | `cleanup_review` | 정리 검토 큐 | 해당 proposal |
| `gmail_source_recovery_needed` | `recovery_needed` | 계정 설정 | 해당 source |
| `gmail_action_failed` | `action_failed` | 활동 로그 | 해당 command/activity |
| `gmail_action_undone` | `action_undone` | 활동 로그 | 해당 command/activity |

매핑 규칙:
- `route_target`이 비면(selected item 부재는 허용, 화면 부재는 불가) 발행을 거부한다 — "화면 없음"은 곧 generic landing이라 invariant 위반이다. `daily_briefing`처럼 selected item이 없는 알림도 화면 키는 반드시 채운다.
- 착지 화면·item id는 소비한 event payload에서 도출한다. notifications가 message/proposal/source의 상태를 다시 조회해 판단하지 않는다(view-only 경계).
- `notification_enabled=false`(mail_sources 설정) 계정 관련 알림은 event를 받아도 event row를 만들지 않는다 — 설정은 read 시점에 반영(§integration §3 `gmail_source_settings_changed`는 job 없이 조회 반영).

---

## Command/Job: `emit_notification`

- 소유 테이블: `notification_events`(insert)
- 발행 event: `notification_event_created` (idempotency `notification:{notification_id}:created`)
- 후속: browser push worker가 `notification_event_created`를 소비해 구독 대상에 push(§integration §3)
- 트리거 event: `gmail_source_recovery_needed`, `gmail_action_failed`, `gmail_action_undone`, `cleanup_proposal_created`, `reminder_reactivated`, `gmail_snapshot_changed`(route) — §integration §3
- 입력 → 결과: `{notification_type, route_target, workspace_id}` → notification_event + optional browser push
- API: 사용자 직접 호출 없음(내부 job). 결과는 `GET /notifications`로 조회.

체크리스트:
- **[정상]** 소비 event 도착 → `notification_type` 결정 → payload에서 `route_target`(화면+selected item) 도출 → `notification_events` insert(workspace 스코프) → outbox `notification_event_created` 1건 → push worker가 활성 구독에 발송. route target 매핑표대로 착지점 확정.
- **[멱등]** 같은 원인 event가 두 번 dispatch(at-least-once). idempotency key로 event row 중복 insert 차단 → notification_event 1건, push 1회. dedupe key는 소비 event의 기존 값에서 도출(예: `source_id`+`reason`+`version`, `command_id`+`version`, `reminder_id`)해 재시도마다 갈리지 않게 한다.
- **[동시]** 같은 workspace로 여러 소비 event 동시 도착 → 각기 다른 `notification_type`/원인이면 별개 row(독립 알림). 같은 원인 두 워커 동시 처리 → UNIQUE(idempotency)로 두 번째 insert 거부, push도 1회.
- **[선행조건]** `route_target`에 착지 화면 키 없음 → 발행 거부(generic landing 방지, negative — route target 없는 알림은 만들지 않는다). 대상 계정 `notification_enabled=false` → event 무시(row 없음). workspace_id 부재 → 내부 오류로 처리 중단(사용자 컨텍스트 없는 job).
- **[부분실패]** event insert 성공·outbox append 실패 → 트랜잭션 롤백(한 트랜잭션) → event만 남고 push 안 됨/push 됐는데 event 없음 상태 불가. event 커밋 후 push worker 실행 전 프로세스 사망 → `notification_event_created` outbox가 남아 재기동 시 push 재시도(at-least-once). push 자체 실패(브라우저 endpoint 만료)는 구독 `revoked_at` 세팅으로 처리, notification_event는 유지.
- **[권한]** N/A — 내부 job, 사용자 컨텍스트 없음. workspace 스코프는 소비 event payload의 workspace_id로 제한, 타 workspace로 알림 누출 없음.
- **[데이터경계]** route_target에 message body/summary 텍스트를 넣지 않는다 — 착지에 필요한 id·화면 키만(카드 문법·최소 payload 원칙). notification_type이 늘어도 event 종류를 늘리지 않고 payload 필드로만 구분.
- 검증: `tests/domains/notifications/test_notification_routing.py::{test_route_target_required_no_generic_landing, test_type_maps_to_screen_and_item, test_notification_disabled_account_skipped}`, `test_emit_notification_job.py::{test_emit_creates_event_and_outbox, test_emit_idempotent_single_push}`.

## 동작: browser push 구독 (`subscribe`/`unsubscribe`)

- 소유 테이블: `notification_subscriptions`(insert/update `revoked_at`)
- 발행 event: 없음(구독 등록은 알림 발행이 아님)
- 입력 → 결과: `{endpoint, keys}` → 구독 등록(재구독 시 갱신) / `revoked_at` 세팅
- API: `POST /notifications/subscribe`

체크리스트:
- **[정상]** 브라우저 Push API 구독 정보(`endpoint`+`keys`) 수신 → 세션 user로 `notification_subscriptions` insert → 이후 `notification_event_created` push 대상에 포함.
- **[멱등]** 같은 `endpoint` 재구독(재방문·permission 재승인). endpoint 기준으로 기존 row 갱신(`keys` 갱신, `revoked_at` 초기화) → 중복 row 안 생김.
- **[동시]** 같은 endpoint 두 요청 동시 → endpoint UNIQUE 제약으로 한 벌만 유지, 두 번째는 갱신으로 폴백.
- **[선행조건]** `endpoint`/`keys` 누락·형식 불량(Web Push 스펙 위반) → 422, 구독 거부(insert 없음). 브라우저 permission `denied` 상태에서 온 stale 구독 → 저장하되 push 실패 시 `revoked_at`으로 정리.
- **[부분실패]** N/A — 단일 테이블 insert/update, 별도 event·job 없음. outbox 참여 없음.
- **[권한]** 세션 user 스코프만 — 구독은 user 소유(`notification_subscriptions.user_id`). 타 user 구독 조회·해지 불가. push 발송 시 workspace 알림을 그 workspace 소속 user 구독으로만 fan-out.
- **[데이터경계]** `keys`(push 암호화 키)는 응답에 절대 미포함. 해지(`revoked_at`)된 구독은 push 대상에서 즉시 제외, row는 감사용으로 보존.
- 검증: `tests/domains/notifications/test_notification_routing.py::{test_subscribe_registers_endpoint, test_resubscribe_updates_not_duplicates, test_subscription_scoped_to_user}`.

## 동작: 복구 안내 view (recovery view)

- 소유 테이블: 없음(read-only view — source state를 저장·변경하지 않음)
- 발행 event: 없음(복구 알림 자체는 `emit_notification`이 `recovery_needed` type으로 발행)
- 입력 → 결과: `gmail_source_recovery_needed` 소비 시 route_target=계정 설정 화면 + 해당 source → 사용자에게 복구 안내
- API: 복구 상태는 `GET /notifications`(알림 목록)과 mail_sources `GET /sources`(실제 status)로 조회

체크리스트:
- **[정상]** `gmail_source_recovery_needed`(reason=token_refresh_failed/scope_reduced/auth_error) 수신 → `recovery_needed` 알림 발행 → route_target=계정 설정 + 해당 source_id. 사용자가 알림을 눌러 계정 설정 화면으로 착지, 재인증을 유도.
- **[멱등]** 같은 source에 대한 recovery event 반복 도착(refresh 재실패). idempotency key(`source_id`+`reason`+`version`)로 알림 중복 발행 차단 → 같은 원인은 알림 1건. 원인(`reason`)이 바뀌면 별개 알림.
- **[동시]** mail_sources·mail_intake가 같은 source 실패를 각각 감지해 event 두 개 발행 → payload owner는 감지한 쪽이지만 notifications는 idempotency로 중복 알림을 막는다(둘의 `reason`이 같으면 dedupe, 다르면 각각).
- **[선행조건]** source state는 이미 발행 도메인이 `permission_needed`로 전이한 뒤 event가 온다 — notifications는 state 전이 여부를 재확인하지 않고 event 도착만으로 view를 만든다(view-only). source가 이후 복구되면 mail_sources가 status를 되돌리고, notifications는 별도 "복구됨" 알림을 만들지 않는다(과잉 알림 방지, negative).
- **[부분실패]** 알림 발행은 `emit_notification`의 부분실패 규약과 동일(event+outbox 한 트랜잭션). recovery view가 source state를 직접 안 바꾸므로 notifications 실패가 source 복구 흐름을 막지 않는다.
- **[권한]** 타 workspace source 복구 알림 누출 없음 — event payload의 workspace_id 스코프. N/A: 사용자 직접 명령 없음(event 기반).
- **[데이터경계]** notifications는 `connected_gmail_accounts.status`·credential·cursor를 읽거나 쓰지 않는다 — route_target에 source_id만 담고, 실제 상태 표시는 프론트가 mail_sources `GET /sources`로 조회. source of truth 이중화 없음.
- 검증: `tests/domains/notifications/test_recovery_views.py::{test_recovery_event_routes_to_account_settings, test_recovery_idempotent_per_reason, test_recovery_does_not_mutate_source_state}`.

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /notifications` (알림 목록)
- **[정상]** workspace의 notification event 목록 + `notification_type` + `route_target` + `read_at`.
- **[필터]** 미확인(`read_at` null) 우선/최신순. 화면 착지에 필요한 route_target 그대로 포함.
- **[빈상태]** 알림 0건 → 빈 배열(에러 아님).
- **[권한]** 세션 workspace 스코프만. route_target에 message body/summary 텍스트 미포함(id·화면 키만).
- 검증: `test_notification_routing.py::test_list_notifications_scoped`.

### `POST /notifications/subscribe`
- **[정상]** browser push 구독 등록/갱신(위 subscribe 동작 참조). **[권한]** 세션 user 스코프, `keys` 응답 미포함. **[데이터경계]** 해지된 구독 재등록 시 `revoked_at` 초기화.

---

## 워크트리 격리 노트

- 마이그레이션: `0012_notifications`(down `0011_assistant_rules`). assistant_decisions rules 머지 후 머지 — 체인 마지막(§integration §1 표 12행). 새 FK 대상은 `workspaces`(0002)·`users`(0002)뿐이라 앞 도메인 중 identity만 있으면 로컬 개발·테스트 가능.
- `_integration-contract.md §5`에는 notifications 테이블 status enum이 없다 — `notification_events`/`notification_subscriptions`는 상태 enum 컬럼을 두지 않는다(read_at·revoked_at nullable timestamp로 상태 표현). 새 status 컬럼이 필요하면 §5 표를 먼저 갱신.
- §2 job 계약(`emit_notification`, payload `{notification_type, route_target, workspace_id}`, lock_key null — message 단위 아님, idempotency로 충분), §3 event wiring(소비 6종 + producer `notification_event_created`) 준수. §4 `EVENT_CONSUMERS`에 소비 event→`emit_notification` 매핑, `PURGE_HANDLER`는 None(notifications는 content-bearing purge 대상 아님 — source state view-only).
- browser push worker(실 Web Push 발송)는 infra/live 의존 → POC는 fake push sink로 `notification_event_created` 소비 계약만 검증, 실 발송은 IG(live) 단계에서 교체(module-boundaries 차단 조건 "browser push 미준비 → notification event와 route target API 먼저 고정").
