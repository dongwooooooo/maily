# Maily Backend Module Boundaries

기준 문서: `docs/current/product-wireframe-final.md`, `docs/current/product-features.md`  
정리일: 2026-07-08

## 문서 역할

이 문서는 Maily 백엔드를 두 층으로 나눈다.

1. **비즈니스 컨텍스트**: 사용자가 인식하는 업무 흐름, 상태, 정책, 데이터 소유권.
2. **개발 구현 컨텍스트**: 코드 패키지, worker, table, event, command, adapter 경계.

기능 설명은 `docs/current/product-features.md`에 둔다. POC, TDD, 파일 단위 작업은
`docs/goals/backend-implementation-plan.md`에서 관리한다.

## 최상위 제품 원칙

- Gmail은 원본 시스템이다. Maily DB는 브리핑, 판단, 처리 이력을 위한 snapshot이다.
- Maily는 Gmail을 대체하지 않는다. 원문 읽기, 답장, 작성, 발송은 Gmail에서 한다.
- 서비스 로그인 계정과 연결 Gmail 계정은 다른 모델이다.
- 연결 Gmail 계정은 브리핑, 요약, 알림, 정리 대상인 mail source다.
- 첫 화면은 전체 inbox가 아니라 오늘 브리핑이다.
- 메일 카드는 스캔과 선택만 담당한다. 카드 응답에는 Gmail 변경 action, AI 판단 이유, raw body를 넣지 않는다.
- 기본 브리핑 섹션은 파생 목록이다. 사용자가 직접 이동시키는 목적지는 Gmail `Maily/` 라벨과 동기화되는 사용자 라벨이다.
- Gmail 변경은 반드시 command ledger, activity log, Undo 가능 여부를 거친다.
- AI 판단 이유는 기본으로 노출하지 않는다. 사용자는 이동, 라벨, `다음부터 여기로`로 분류를 고친다.
- 알림은 일반 landing page가 아니라 기존 화면과 selected item으로 착지한다.

## 경계 설계 원칙

- `core`는 도메인이 아니다. request context, transaction, outbox envelope,
  idempotency, job dispatch, logging, health 같은 공통 실행 기반만 제공한다.
- 도메인 컨텍스트는 같이 변경되어야 하는 업무 데이터, 정책, 상태 전이, 실패 복구 단위로 나눈다.
- 구현 유닛은 도메인 컨텍스트보다 작을 수 있다. OAuth credential, Gmail adapter, sync worker,
  projection, command ledger처럼 개발자가 독립적으로 테스트할 수 있는 단위로 자른다.
- 모듈 간 side effect는 직접 도메인 service 호출이 아니라 command, durable event, read model로 연결한다.
- Gmail API 접근 port는 도메인별로 나눈다. `mail_intake`는 read/sync용
  `GmailReaderPort`를 소유하고, `gmail_actions`는 write/mutation용
  `GmailMutationPort`를 소유한다.
- 각 event type과 payload schema는 발행 도메인 컨텍스트가 소유한다.
- 실제 배포 인프라, Docker, cloud scheduler, Pub/Sub topic, secret provisioning은 `development/infra`가 소유한다.

## 강제 Invariant

- `core`는 도메인 데이터 의미와 event payload schema를 소유하지 않는다.
- OAuth token 원문은 연결 Gmail 소스 컨텍스트 밖에서 직접 읽을 수 없다.
- Gmail read/sync 호출은 `mail_intake`의 `GmailReaderPort`, Gmail write 호출은
  `gmail_actions`의 `GmailMutationPort`를 통해서만 한다.
- Gmail write는 `gmail_actions`(Gmail Actions & Activity) command ledger를 반드시 통과한다.
- 비동기 작업은 `outbox_events`, `job_runs`, idempotency key를 가진다.
- 브리핑 read model은 재생성 가능해야 한다.
- `seen`, `remind_later` 같은 사용자 item state는 재생성 가능한 projection과 분리된 durable state다.
- importance classification이 아직 끝나지 않은 메일은 아이템 단위 대기 상태를 따로 만들지 않는다. 계정 단위 `syncing` 표시로 대기 사실을 알린다.
- `done`은 독립 버튼 상태가 아니라 Gmail read/archive state와 사용자 action 결과에서 파생한다.
- 동일 Gmail 계정은 한 workspace 안에서 중복 연결할 수 없다.
- 동일 Gmail 주소가 여러 active connection에 존재하면 Pub/Sub notification은 해당 active connection 전체로 fan-out한다.
- 계정 연결 해제 시 token은 즉시 폐기하고 sync/action을 막는다.
- 계정 연결 해제 후 message, excerpt, summary, cleanup proposal 같은 content-bearing 데이터는 purge 대상이다.
- activity log는 감사와 사용자 설명에 필요한 최소 정보만 남긴다.

## 공통 실행 기반

| 이름 | 분류 | 소유 책임 | 외부 계약 |
|---|---|---|---|
| core (Backend Core / 백엔드 실행 기반) | Technical Core | FastAPI app composition, config, DB session/transaction, Redis client, migration runner, outbox envelope, job lock, idempotency, logging, rate limit, health/ready | request context helper, transaction boundary, outbox append/dispatch, job dispatch, config/logging/health |

`core`는 `users`, `connected_gmail_accounts`, `gmail_messages`, `briefing_items`,
`service_labels`, `gmail_action_commands`, `cleanup_proposals`, `activity_logs` 같은
도메인 테이블의 schema와 lifecycle을 소유하지 않는다.

## 비즈니스 컨텍스트

| 이름 | 비즈니스 소유권 | 포함 기능 | 절대 소유하지 않는 것 |
|---|---|---|---|
| identity (Identity & Workspace / 사용자·워크스페이스) | 서비스 로그인 사용자, workspace, session, membership, request user/workspace context | F01 | 연결 Gmail 계정 OAuth token, Gmail message snapshot |
| mail_sources (Connected Gmail Sources / 연결 Gmail 소스) | 연결 Gmail 계정, 계정 표시 이름, summary/briefing/notification toggle, pause/disconnect, OAuth credential lifecycle, account status source state | F02, F12 설정 일부, F14 계정 상태 | Gmail history sync, message snapshot projection, Gmail mutation command |
| mail_intake (Gmail Intake & Snapshot / Gmail 수집·스냅샷) | Gmail watch/history/polling, sync run, history cursor, Gmail message snapshot, limited excerpt, Gmail state snapshot, `GmailReaderPort` | F03, F05 source state | 오늘 브리핑 섹션 배치, 사용자 라벨 정책, AI rule/proposal, Gmail write |
| briefing (Briefing & Item State / 브리핑·항목 상태) | 오늘 브리핑 read model, 상세 read model, account grouping, section placement, seen/remind_later durable state, 보관함 예정 타임라인, 라벨 허브 조회 | F04, F05, F09 | Gmail write 실행, 사용자 라벨 lifecycle, AI 판단 생성 |
| labels (Labels & Classification / 라벨·분류) | 사용자 라벨, Gmail `Maily/` 라벨 매핑, 라벨 이름/숨김/순서, message move target, 사용자 correction signal | F07, F08 입력 신호 | Gmail write command 실행, cleanup proposal 승인 큐 |
| gmail_actions (Gmail Actions & Activity / Gmail 변경·활동 이력) | Gmail mutation command ledger, `GmailMutationPort`, changed/not changed result, activity log, undo 가능 여부와 역연산 요청 | F06, F11 | 연결 계정 설정, 브리핑 섹션 판단, AI proposal 생성, Gmail read/sync |
| assistant_decisions (Assistant Decisions / 요약·규칙·정리 제안) | 요약 job/result, importance classification job/result(중요도 band, 판단 이유), 최소 payload 정책, rule suggestion, active classification rule, cleanup proposal, confidence band, 승인/제외 큐, 자동 적용 기준 | F04 중요도 판단, F08, F10, F12 | OAuth token, Gmail API 직접 호출, command ledger schema |
| notifications (Notifications & Recovery / 알림·복구 안내) | browser subscription, notification event, route target, permission/sync recovery prompt view | F13, F14 user-facing view | account/sync source state, Gmail mutation, message snapshot |

## 도메인 내부 구현 구조

백엔드 코드는 `app/domains/<domain>/`을 기본 단위로 둔다. 모델, schema, repository,
service, router, event, job handler, 외부 adapter는 해당 비즈니스 도메인 안에 배치한다.
공통 실행 기반만 `app/core/`와 `app/core/jobs/`에 둔다.

| 도메인 | 권장 코드 위치 | 내부 구성 | 소유 데이터/계약 | 주 검증 |
|---|---|---|---|---|
| core (Backend Core) | `app/core/`, `app/core/jobs/`, `app/api/`, `app/db/` | config, database, redis, outbox, idempotency, logging, job dispatcher/lock/retry/registry | 실행 기반, outbox envelope, idempotency key, job lock, health/ready | health/ready, transaction, outbox dedupe, job lock |
| identity (Identity & Workspace) | `app/domains/identity/` | models, schemas, repository, service, router | users, workspaces, workspace_members, sessions/JWT | 재로그인 workspace 재사용, workspace isolation |
| mail_sources (Connected Gmail Sources) | `app/domains/mail_sources/` | models, schemas, repository, service, router, credentials, oauth, events, purge | connected_gmail_accounts, encrypted oauth credentials, per-account settings, disconnect state | token plaintext 미저장, 중복 연결 금지, pause/disconnect |
| mail_intake (Gmail Intake & Snapshot) | `app/domains/mail_intake/` | models, schemas, repository, service, router, gmail_reader, fake_reader, live_reader, events, purge, `jobs/` | GmailReaderPort, watch registrations, notification events, sync cursors, sync runs, gmail_messages, excerpts | snapshot upsert, watch renewal, notification dedupe, raw body 미보관 |
| briefing (Briefing & Item State) | `app/domains/briefing/` | models, schemas, repository, service, router, item_state, reminders, events, purge, `jobs/` | briefing_items, detail read model, seen state, reminders, account-grouped card response | card action/reason/raw body 금지, projection rebuild, durable state 보존 |
| labels (Labels & Classification) | `app/domains/labels/` | models, schemas, repository, service, router, events | service_labels, gmail_label_mappings, label order/visibility, correction signals | `Maily/` mapping 안정성, 기본 섹션 이동 금지 |
| gmail_actions (Gmail Actions & Activity) | `app/domains/gmail_actions/` | models, schemas, repository, service, router, gmail_mutator, fake_mutator, live_mutator, activity, undo, events, purge, `jobs/` | GmailMutationPort, gmail_action_commands, activity_logs, undo_actions | command status 전이, changed flag, activity_id, undo 가능성 |
| assistant_decisions (Assistant Decisions) | `app/domains/assistant_decisions/` | models, schemas, repository, service, router, summaries, importance, rules, cleanup, llm, fake_llm, events, purge, `jobs/` | summary jobs/results, message_importance_classifications, classification rules, cleanup proposals, confidence band | summary off, 최소 LLM payload, approve-one-only |
| notifications (Notifications & Recovery) | `app/domains/notifications/` | models, schemas, repository, service, router, events, `jobs/` | notification_subscriptions, notification_events, route targets | generic landing 금지, source state view-only recovery |

### Job 배치 원칙

- Job handler는 해당 비즈니스 도메인 내부 `jobs/`에 둔다.
- `sync_delta`는 `mail_intake/jobs/`, `execute_action`은 `gmail_actions/jobs/`,
  `generate_summary`는 `assistant_decisions/jobs/`에 둔다.
- 전역 `app/jobs/`는 만들지 않는다.
- 공통 job 실행 기반만 `app/core/jobs/`에 둔다.
  - `dispatcher.py`: outbox/job_runs를 읽고 등록된 handler를 호출한다.
  - `lock.py`: 중복 실행을 막는다.
  - `retry.py`: 재시도 정책을 제공한다.
  - `registry.py`: job type을 domain handler에 매핑한다.

## 기능과 비즈니스 컨텍스트 연결

| 기능 | 주 컨텍스트 | 보조 컨텍스트 | 연결 설명 |
|---|---|---|---|
| F01 서비스 로그인/워크스페이스 | identity | core | API 요청은 항상 user/workspace context를 가진다. |
| F02 Gmail 계정 연결 | mail_sources | identity, mail_intake, notifications | 연결 Gmail 계정은 workspace 아래 mail source로 저장되고 초기 sync를 예약한다. |
| F03 지속 Gmail 동기화 | mail_intake | core, mail_sources, briefing, assistant_decisions, notifications | mail_intake가 snapshot을 갱신하고 durable event로 briefing, assistant, notification 작업을 깨운다. |
| F04 오늘 브리핑 | briefing | mail_sources, mail_intake, assistant_decisions | briefing이 snapshot, summary, 사용자 item state를 조합해 카드 목록을 만든다. |
| F05 메일 상세 | briefing | mail_intake, gmail_actions, assistant_decisions | 상세는 읽기 모델을 제공하고 Gmail 변경 요청은 gmail_actions command로 넘긴다. |
| F06 Gmail 변경 액션 | gmail_actions | core, mail_intake, briefing, notifications | gmail_actions가 command를 기록하고 `GmailMutationPort`로 실행한 뒤 view 갱신 event를 발행한다. |
| F07 라벨/분류 | labels | mail_intake, gmail_actions, assistant_decisions | 사용자 이동 목적지는 label이며, 실제 Gmail label apply는 gmail_actions command로 실행한다. |
| F08 다음부터 여기로 | assistant_decisions | labels, gmail_actions | labels의 사용자 correction signal을 바탕으로 assistant_decisions가 rule suggestion을 만들고 승인 후 gmail_actions command를 요청할 수 있다. |
| F09 보관함 | briefing | labels, notifications | remind_later 예정 타임라인과 라벨 허브를 조회면으로 제공한다. |
| F10 정리 검토 | assistant_decisions | gmail_actions | 낮은 확신 제안은 개별 승인 큐로 가고 승인 시 gmail_actions command를 요청한다. |
| F11 활동 로그/Undo | gmail_actions | notifications | Gmail 변경과 자동 처리 이력을 사용자에게 설명 가능한 사실로 남긴다. |
| F12 요약/개인정보 | assistant_decisions | mail_sources, mail_intake, briefing | 계정 설정과 message snapshot 범위 안에서만 요약을 만든다. |
| F13 알림/라우팅 | notifications | mail_sources, briefing, assistant_decisions | 알림은 기존 화면과 selected item으로 착지한다. |
| F14 동기화/오류 복구 | notifications | mail_sources, mail_intake, core | source state는 mail_sources/mail_intake가 소유하고 notifications은 사용자 복구 view만 만든다. |

## Command Catalog

| Command | 소유 컨텍스트 | 입력 | 결과 |
|---|---|---|---|
| `connect_gmail_source` | mail_sources | workspace_id, oauth callback profile, encrypted credential | connected source, initial sync job |
| `update_gmail_source_settings` | mail_sources | source_id, display_name, toggles, paused flag | source settings changed event |
| `disconnect_gmail_source` | mail_sources | source_id, actor_id | token revoked, sync/action blocked, purge job requested |
| `process_gmail_notification` | mail_intake | emailAddress, historyId, notification id | sync job deduped or queued |
| `sync_gmail_delta` | mail_intake | source_id, history cursor | snapshot changes, sync run result |
| `sync_gmail_full` | mail_intake | source_id, resync reason | refreshed snapshot and cursor |
| `rebuild_briefing` | briefing | workspace_id, source/message scope | regenerated briefing read model |
| `set_item_seen` | briefing | briefing_item_id, actor_id | durable seen state |
| `schedule_reminder` | briefing | briefing_item_id, remind_at | reminder row and reactivation job |
| `create_or_update_label` | labels | workspace_id, label name/order/visibility | service label and Gmail mapping intent |
| `move_message_to_label` | labels then gmail_actions | message_id, label_id, actor_id | correction signal and Gmail label command |
| `request_gmail_action` | gmail_actions | message_id, action type, idempotency key | pending command |
| `execute_gmail_action` | gmail_actions | command_id | applied/failed command and activity event |
| `undo_gmail_action` | gmail_actions | activity_id or command_id | undo command when supported |
| `generate_summary` | assistant_decisions | message_id, summary settings | summary result or metadata-only state |
| `classify_importance` | assistant_decisions | message_id, snapshot signals | importance classification result (band, reason) |
| `create_rule_suggestion` | assistant_decisions | correction signal | pending rule suggestion |
| `approve_cleanup_proposal` | assistant_decisions then gmail_actions | proposal_id, actor_id | proposal approved and Gmail command requested |
| `emit_notification` | notifications | notification type, route target | notification event and optional browser push |

## Event Catalog

| Event | Producer | Payload owner | Idempotency key | Primary consumers |
|---|---|---|---|---|
| `gmail_source_connected` | mail_sources | mail_sources | `source:{source_id}:connected:{version}` | mail_intake, notifications |
| `gmail_source_settings_changed` | mail_sources | mail_sources | `source:{source_id}:settings:{version}` | briefing, assistant_decisions, notifications |
| `gmail_source_disconnected` | mail_sources | mail_sources | `source:{source_id}:disconnected:{version}` | mail_intake, briefing, gmail_actions, assistant_decisions, notifications |
| `gmail_source_recovery_needed` | mail_sources or mail_intake | 실패를 감지한 쪽이 소유 | `source:{source_id}:recovery:{reason}:{version}` | notifications |
| `gmail_notification_received` | mail_intake | mail_intake | `gmail-notification:{email}:{history_id}` | mail_intake sync worker |
| `gmail_snapshot_changed` | mail_intake | mail_intake | `source:{source_id}:snapshot:{sync_run_id}` | briefing, assistant_decisions, notifications |
| `briefing_item_state_changed` | briefing | briefing | `item:{briefing_item_id}:state:{version}` | assistant_decisions |
| `reminder_reactivated` | briefing | briefing | `reminder:{reminder_id}:reactivated:{version}` | briefing, notifications |
| `label_correction_recorded` | labels | labels | `message:{message_id}:label:{label_id}:correction:{version}` | assistant_decisions |
| `gmail_action_requested` | gmail_actions | gmail_actions | `command:{command_id}:requested` | gmail_actions worker |
| `gmail_action_applied` | gmail_actions | gmail_actions | `command:{command_id}:applied:{version}` | mail_intake, briefing |
| `gmail_action_failed` | gmail_actions | gmail_actions | `command:{command_id}:failed:{version}` | notifications |
| `gmail_action_undone` | gmail_actions | gmail_actions | `command:{command_id}:undone:{version}` | mail_intake, briefing, notifications |
| `summary_completed` | assistant_decisions | assistant_decisions | `message:{message_id}:summary:{summary_version}` | briefing |
| `importance_classified` | assistant_decisions | assistant_decisions | `message:{message_id}:importance:{classification_version}` | briefing |
| `cleanup_proposal_created` | assistant_decisions | assistant_decisions | `message:{message_id}:cleanup:{proposal_version}` | briefing, notifications |
| `rule_suggestion_created` | assistant_decisions | assistant_decisions | `rule-suggestion:{suggestion_id}:created` | briefing |
| `notification_event_created` | notifications | notifications | `notification:{notification_id}:created` | browser push worker |

## 주요 흐름

### 1. 계정 연결

```text
Frontend OAuth callback
-> identity context
-> mail_sources creates connected source and encrypted credential
-> core outbox: gmail_source_connected
-> mail_intake schedules initial sync
-> mail_intake snapshot update
-> core outbox: gmail_snapshot_changed
-> briefing projection rebuild
-> assistant_decisions summary/proposal jobs when account settings allow
-> notifications notification/recovery view if needed
```

초기 sync가 끝나기 전에도 계정은 `syncing` 상태로 목록에 보여야 한다.

### 2. 새 메일 지속 동기화

```text
Gmail mailbox change
-> Google Cloud Pub/Sub
-> mail_intake process_gmail_notification
-> fan-out to active connected sources by emailAddress
-> mail_intake sync_gmail_delta or sync_gmail_full
-> mail_intake message snapshot update
-> core outbox: gmail_snapshot_changed
-> briefing rebuild (스냅샷만 반영, importance 결과 없는 상태 — 아이템 단위 대기 표시 없이 계정 syncing으로만 안내)
-> assistant_decisions generate_summary, classify_importance job 큐잉 (별도 job, 별도 실패/재시도)
-> assistant_decisions summary job 완료 -> core outbox: summary_completed -> briefing 해당 message_id만 부분 재생성
-> assistant_decisions importance job 완료 -> core outbox: importance_classified -> briefing 해당 message_id만 부분 재생성
-> notifications route event
```

mail_intake는 watch 등록/갱신, notification dedupe, history cursor, fallback polling,
snapshot 갱신까지만 담당한다. 브리핑 생성, 요약, 알림은 직접 호출하지 않는다.

한 메일에 대해 briefing projection은 최소 3번(스냅샷 저장 시, 요약 완료 시, 중요도
판단 완료 시) 재생성될 수 있다 — 매번 전체 재생성이 아니라 해당 message_id 단위
부분 재생성이다. summary와 importance는 별도 job, 별도 테이블(`message_summaries`,
`message_importance_classifications`)로 각자 실패/재시도한다. 판단 결과(band, reason)는
이벤트 payload 필드로만 구분하고, 결과별로 이벤트 종류를 늘리지 않는다.

### 3. 브리핑과 상세 조회

```text
Frontend today briefing
-> briefing
-> reads mail_sources source settings and status
-> reads mail_intake message snapshot
-> reads assistant_decisions summary result when available
-> returns account-grouped card list
```

briefing은 프론트 카드 문법을 보호한다. 목록 응답에는 Gmail mutation action, AI reasoning,
raw body를 넣지 않는다.

### 4. 사용자 라벨 이동과 다음부터 여기로

```text
Detail panel move action
-> labels validates label target
-> labels records label correction signal
-> gmail_actions creates label apply command
-> core outbox: gmail_action_requested
-> assistant_decisions may create rule_suggestion from correction signal
```

기본 브리핑 섹션은 직접 이동 대상이 아니다. 사용자가 고치는 목적지는 사용자 라벨이다.

### 5. Gmail 변경 액션

```text
Detail or Cleanup Review
-> gmail_actions creates command: pending
-> core outbox: gmail_action_requested
-> gmail_actions worker executes command through GmailMutationPort
-> gmail_actions command status: applied / failed / compensating / undone
-> core outbox: gmail_action_applied or gmail_action_failed
-> mail_intake snapshot reconcile
-> briefing view rebuild
```

gmail_actions는 mutation 실행 전후 상태, activity log, undo 가능 여부를 같이 만든다.

### 6. 자동화와 정리 검토

```text
core outbox: gmail_snapshot_changed or label_correction_recorded
-> assistant_decisions
-> summary result / rule suggestion / cleanup proposal
-> user approves one proposal
-> gmail_actions command
```

규칙 후보와 정리 제안은 assistant_decisions가 만들고 실제 Gmail 변경은 gmail_actions가 실행한다.
자동화 판단과 Gmail mutation 실행을 같은 구현 유닛에 섞지 않는다.

### 7. 권한 오류와 복구

```text
Token refresh failure or Gmail API auth error
-> mail_sources or mail_intake source state: permission_needed
-> core outbox: gmail_source_recovery_needed
-> notifications recovery route view
-> Frontend connected account settings route
```

권한 오류 source of truth는 mail_sources/mail_intake source state다. notifications은 복구 안내와 route target만 만든다.

### 8. 계정 연결 해제와 purge

```text
Disconnect request
-> mail_sources marks source disconnecting and revokes token
-> mail_sources blocks new sync/action for source
-> core outbox: gmail_source_disconnected
-> mail_intake purges message snapshot/excerpts
-> briefing purges briefing projections/item states for content-bearing rows
-> assistant_decisions purges summaries/proposals/rules tied to source content
-> gmail_actions keeps minimal activity audit
-> notifications emits recovery/settings route update if needed
```

해제는 단순 delete가 아니다. token 폐기, 신규 작업 차단, content-bearing data purge,
최소 audit 보존을 하나의 workflow로 검증한다.

## POC Gate

| Gate | 목표 | 포함 컨텍스트 | 통과 기준 |
|---:|---|---|---|
| G0 | Runtime & Core | core | `/health`, `/ready`, migration baseline, outbox/idempotency/job lock이 재현된다. |
| G1 | Identity & Connected Source | identity, mail_sources | 서비스 로그인 계정과 연결 Gmail 계정이 분리되고 token plaintext가 남지 않는다. |
| G2 | Fake Continuous Sync | mail_sources, mail_intake, core | fake notification/history cursor로 snapshot과 outbox event가 중복 없이 생성된다. |
| G3 | Briefing API | mail_intake, briefing, assistant_decisions 일부 | 프론트 mock 없이 오늘 브리핑과 상세를 렌더할 수 있고 projection rebuild가 가능하다. |
| G4 | Gmail Action Ledger | gmail_actions, mail_intake | fake GmailMutationPort로 command status, changed flag, activity_id, undo 가능 여부가 나온다. |
| G5 | Labels, Rules, Cleanup Review | labels, assistant_decisions, gmail_actions | 라벨 목적지, 규칙 후보, 개별 승인 큐가 Gmail mutation과 분리된다. |
| G6 | Summary Privacy | assistant_decisions, mail_sources, mail_intake | summary off, metadata-only fallback, raw body/prompt 미저장이 검증된다. |
| G7 | Notification & Recovery | notifications, mail_sources, mail_intake, briefing | route target과 recovery prompt가 source state의 view로 재현된다. |
| G8 | Disconnect & Purge | mail_sources, mail_intake, briefing, gmail_actions, assistant_decisions | token 폐기, sync/action 차단, content-bearing data purge, 최소 audit 보존이 검증된다. |
| IG1 | Live Gmail Watch Integration | mail_sources, mail_intake, infra | 테스트 Gmail 계정의 새 메일이 Pub/Sub/history 경로로 반영된다. G0-G8 구현을 막지 않는다. |

## 모듈별 차단 조건

| 컨텍스트 | 차단 조건 | 우회 방법 |
|---|---|---|
| core | 로컬 DB/Redis 또는 secret 미준비 | health, config, outbox/idempotency service test부터 구현 |
| identity | Google 로그인 client 미준비 | mocked Google profile과 JWT/session test로 구현 |
| mail_sources | OAuth client 미준비 | fake credential과 encrypted token repository test로 구현 |
| mail_intake | Pub/Sub topic, Gmail live credential 미준비 | fake notification, fake GmailReaderPort, fallback polling TDD로 구현 |
| briefing | 프론트 API shape 변경 가능성 | source-of-truth 카드 문법과 seed DB contract test로 shape 고정 |
| labels | Gmail label live 검증 지연 | service label과 Gmail mapping intent를 fake command로 검증 |
| gmail_actions | Gmail write live 검증 지연 | fake GmailMutationPort로 command ledger와 activity/undo 계약 먼저 고정 |
| assistant_decisions | LLM provider 또는 자동화 임계값 미확정 | fake LLM client, confidence band, privacy test 먼저 고정 |
| notifications | browser push 미준비 | notification event와 route target API 먼저 고정 |
| purge | 실제 Google revoke 검증 지연 | local token revoke marker와 content table purge test 먼저 고정 |
