# gmail_actions 세부 플랜 (Gmail Actions & Activity)

기준: `module-boundaries.md`(컨텍스트 F06·F11·Command/Event Catalog·흐름 5, `GmailMutationPort` invariant·undo 가능 여부), `db-schema.md`(gmail_actions 섹션: `gmail_action_commands`·`activity_logs`·`undo_actions`), `_integration-contract.md`(§1 `0007_gmail_actions`, §2 `execute_action`, §3 `/actions` + event wiring, §5 status 값). 대응 Task: 9(command ledger·mutation port·activity·undo).

## 도메인 책임 요약

Gmail mutation command ledger, `GmailMutationPort`, changed/not-changed 결과, activity log, undo 가능 여부와 역연산 요청. **소유 안 함**: 연결 계정 설정(mail_sources), 브리핑 섹션 판단(briefing), AI proposal 생성(assistant_decisions), Gmail read/sync(mail_intake).

강제 invariant(이 도메인이 지키는 것):
- Gmail write는 `GmailMutationPort`로만 실행 — 도메인 서비스가 Gmail API를 직접 호출하지 않는다.
- OAuth token 원문을 직접 읽지 않는다 — port 구현체(live_mutator)만 mail_sources credential에 접근하고, 도메인 코드는 `command_id` 기준으로 port를 호출한다.
- `app/domains/mail_intake/gmail_reader`(및 `GmailReaderPort`)를 import하지 않는다 — read/sync 경로와 write 경로는 물리적으로 분리(negative boundary test).
- 모든 Gmail write는 `gmail_action_commands` ledger를 통과한다 — command row 없이 mutation이 나가는 경로가 존재하지 않는다.
- `activity_logs.action_summary`에 message body/summary 텍스트를 담지 않는다(최소 audit).

소유 테이블: `gmail_action_commands`, `activity_logs`, `undo_actions`◆(활동 audit 최소분 보존, content-bearing 아님).
소유 event(producer, payload owner=gmail_actions): `gmail_action_requested`, `gmail_action_applied`, `gmail_action_failed`, `gmail_action_undone`.
소유 job: `execute_action`.

## Command 상태 전이 (`gmail_action_commands.status`)

값 집합은 `_integration-contract.md §5` 고정(`pending`/`applied`/`failed`/`compensating`/`undone`). 전이:

```
(요청)
  → pending              request_gmail_action이 command 생성, execute_action 큐잉 전
pending
  → applied              GmailMutationPort 성공 (changed=true/false 무관)
  → failed               GmailMutationPort 실패 (권한/네트워크/Gmail 오류) — 종료 상태
applied
  → compensating         undo 요청 접수, reverse_command 실행 중
compensating
  → undone               reverse_command applied 확정
```

전이 규칙:
- `failed`는 종료 상태 — undo 대상이 아니다(되돌릴 Gmail 변경이 없음). 재시도는 새 request로 새 command를 만든다.
- `compensating`/`undone`은 **원본** command의 상태다. 역연산 command(reverse)는 별도 row로 자기 `pending→applied` 전이를 독립적으로 밟는다 — undo가 직접 Gmail을 부르지 않고 ledger를 재통과하게 강제하는 구조.
- `changed=false`(이미 목표 상태였음)로 applied된 command는 되돌릴 변화가 없으므로 undo 불가(`undo_available=false`).
- `version`은 매 성공 전이마다 +1 → `applied`/`failed`/`undone` 이벤트 idempotency key disambiguator.

---

## Command: `request_gmail_action`

- 소유 테이블: `gmail_action_commands`(insert, status pending)
- 발행 event: `gmail_action_requested` (idempotency `command:{command_id}:requested`)
- 후속: `execute_action` job 큐잉(§integration §2·§3, lock_key `command:{command_id}`)
- 입력 → 상태전이 → 결과: `{message_id, action_type, idempotency_key}` → status `pending`(version=0) → pending command + mutation job 요청
- API: `POST /actions`

action_type → payload 매핑(배열 하나로 통일, action_type별 shape 분기 없음):
- `mark_read` → `{add_label_ids: [], remove_label_ids: ["UNREAD"]}`
- `archive` → `{add_label_ids: [], remove_label_ids: ["INBOX"]}`
- `read_and_archive` → `{add_label_ids: [], remove_label_ids: ["UNREAD", "INBOX"]}`
- `label_apply` → `{add_label_ids: [gmail_label_id], remove_label_ids: []}` (gmail_label_id는 labels 도메인이 매핑으로 제공)

체크리스트:
- **[정상]** 상세 패널/정리 검토에서 액션 요청 → action_type 검증 → payload를 add/remove 배열로 구성 → 클라이언트 `Idempotency-Key`(UUID v4)를 `gmail_action_commands.idempotency_key`에 그대로 저장 → status `pending`(version=0), `requested_by`·`requested_at` 기록 → outbox `gmail_action_requested` 1건 → `execute_action` 큐잉. 이 시점엔 Gmail 호출을 하지 않는다(응답은 pending까지만).
- **[멱등]** 버튼 두 번/네트워크 재시도로 같은 `idempotency_key` 재수신 → `idempotency_key` unique로 두 번째 insert를 막고 기존 command 반환 → mutation job 재큐잉 안 함, event 재발행 안 함. **버튼 두 번 = mutation 한 번** 불변식이 클라이언트 키로 성립.
- **[동시]** 같은 `idempotency_key` 두 요청 동시 도착 → unique 제약이 두 번째 insert를 DB 레벨에서 거부(IntegrityError) → 두 번째는 기존 row 조회로 폴백. command 한 벌, `execute_action` 한 번만 큐잉.
- **[선행조건]** `message_id` 부재/타 workspace → 404(존재 노출 방지). 미지원 `action_type` → 422. `Idempotency-Key` 헤더 없음 → 422(클라이언트 결정 키 필수). 대상 계정이 `disconnecting`/`disconnected` → 409(해제 중 신규 action 거부, mail_sources disconnect 가드가 이 도메인에도 적용). **command row 없이 mutation 금지** — `GmailMutationPort`는 `command_id` 인자 없이 호출 불가하고, 서비스 레이어가 아닌 워커(`execute_action`)만 호출한다(negative: port 직접 호출 경로가 코드에 없음).
- **[부분실패]** command insert 성공·outbox append 실패 → 롤백(command+outbox 한 트랜잭션). command만 있고 event 없음/event만 있고 command 없음 상태 불가. Gmail 호출은 job이 별도 트랜잭션에서 하므로, request 커밋 후 프로세스가 죽어도 outbox event가 남아 재기동 시 `execute_action`이 큐잉된다(at-least-once).
- **[권한]** 타 workspace message 대상 요청 → 403. `requested_by`는 activity/audit 표시용으로만 기록(자동화 vs 사용자 액션 구분).
- **[데이터경계]** payload는 add/remove label id 배열만 담는다 — raw body/summary/발신자 미포함. `label_apply`의 gmail_label_id는 labels 도메인 매핑에서 온 값이며, 이 도메인은 그 값을 그대로 Gmail에 전달할 뿐 라벨 lifecycle을 소유하지 않는다.
- 검증: `tests/domains/gmail_actions/test_action_commands.py::{test_request_creates_pending_command, test_idempotency_key_dedupes_mutation, test_action_payload_shape, test_mutation_requires_command_row}`.

## Job: `execute_action`

- 트리거: `gmail_action_requested`
- payload: `{command_id}`, lock_key `command:{command_id}`
- 실행: `GmailMutationPort`로 Gmail `messages.modify`(add/remove label ids) → status `pending`→`applied`/`failed` → activity_log 생성 → view 갱신 event 발행
- 발행 event: `gmail_action_applied`(idempotency `command:{command_id}:applied:{version}`) 또는 `gmail_action_failed`(`command:{command_id}:failed:{version}`)

체크리스트:
- **[정상]** pending command 픽업 → `GmailMutationPort.apply(command_id)` → status `applied`, version+1, `applied_at`, `changed` 세팅 → `activity_logs` 1건(`action_summary`, `actor_id`=requested_by, `command_id` 연결) → outbox `gmail_action_applied`. 이 event가 briefing `build_briefing`(해당 message_id 부분 재생성)과 mail_intake snapshot reconcile을 깨운다(§3 wiring).
- **[멱등]** 같은 `command_id`로 job 두 번 실행(at-least-once) → 이미 `applied`면 재실행 skip(no-op), `changed` 재계산·activity 중복 생성 안 함. Gmail `messages.modify`는 그 자체로 idempotent(이미 목표 상태면 재호출 무해)라 재실행이 안전하다.
- **[동시]** lock_key `command:{command_id}`로 두 워커 동시 실행 방지 — 같은 command에 mutation이 두 번 나가지 않는다.
- **[선행조건]** command가 `pending`이 아니면 실행 거부(`applied`/`failed`/`compensating`/`undone` 재실행 방어, 잘못된 트리거 방어). 대상 계정 credential `revoked_at` 세팅(disconnect 진행) → 실행 중단, status 유지(purge가 정리).
- **[부분실패]** status 전이·activity_log·outbox append는 한 트랜잭션, Gmail 호출은 그 밖(외부 시스템이라 롤백 불가). **Gmail 성공·activity_log 생성(로컬 커밋) 실패** → command는 아직 pending으로 남고 job 재실행 → Gmail idempotent 재호출(changed=false 가능) → activity를 ledger 기준으로 재구성. 즉 `command.status`+`applied_at`이 진실의 원천이고 `activity_logs`는 그로부터 재생성 가능. Gmail 실패(권한/네트워크/Gmail 오류) → status `failed`, `failed_at`, `error_reason`, outbox `gmail_action_failed` → notifications `emit_notification`.
- **[changed flag]** 이미 읽음 상태 메일에 `mark_read`, 이미 보관된 메일에 `archive` → Gmail이 상태를 바꾸지 않음 → `changed=false`로 applied. UI가 "이미 처리됨"을 구분하고, 이 command는 이후 undo 불가(`undo_available=false`) 판단의 근거가 된다.
- **[권한]** N/A(내부 job, 사용자 컨텍스트 없음). workspace 스코프는 `command_id`→`connected_account_id`→workspace로 제한. OAuth token은 port 구현체만 접근하고 job 코드는 직접 읽지 않는다.
- **[데이터경계]** `activity_logs.action_summary`에 message body/summary 텍스트 미포함(최소 audit). 다른 command/workspace row 미변경. `GmailMutationPort`는 해당 command의 `connected_account_id` 자격증명만 사용.
- 검증: `tests/domains/gmail_actions/test_execute_action_job.py::{test_execute_applies_and_emits, test_changed_false_on_noop, test_execute_idempotent, test_failure_sets_failed_and_emits}`, `test_activity_log.py::{test_activity_created_on_apply, test_activity_excludes_message_body, test_activity_reconstructable_from_ledger}`.

## Command: `undo_gmail_action`

- 소유 테이블: `undo_actions`(insert), `gmail_action_commands`(reverse command insert; 원본 status `applied`→`compensating`→`undone`)
- 발행 event: `gmail_action_undone` (idempotency `command:{command_id}:undone:{version}`) — `command_id`=원본 command, version=원본 command version 증가분
- 후속: reverse command이 정상 ledger를 재통과(`pending`→`execute_action`→`applied`)
- 입력 → 상태전이 → 결과: `{activity_id}` 또는 `{command_id}` → 원본 `compensating`→`undone` → 역연산 command + undo 기록
- API: `POST /actions/{id}/undo`

action_type별 undo 가능 여부:
- `mark_read` → 역연산 `add UNREAD`(가능), `archive` → 역연산 `add INBOX`(가능), `read_and_archive` → 역연산 `add UNREAD`+`add INBOX`(가능), `label_apply` → 역연산 `remove {gmail_label_id}`(가능).
- 원본이 `changed=false`였으면(되돌릴 변화 없음) `undo_available=false`.

체크리스트:
- **[정상]** activity log 화면에서 undo 요청 → `undo_actions.undo_available` 확인 → 원본 command action_type의 역연산 payload로 **reverse command 새로 생성**(status pending) → 원본 status `compensating` → reverse command이 정상 ledger 통과(`gmail_action_requested`→`execute_action`) → reverse `applied` 시 원본 status `undone`, `undone_at`, version+1 → outbox `gmail_action_undone`(briefing rebuild + notifications). **직접 Gmail 호출 안 함** — undo도 `reverse_command_id`를 통해 command ledger를 다시 거친다.
- **[멱등]** 같은 activity undo 재요청 → `undo_actions.undone_at`이 세팅됐으면 no-op(중복 undo 방지). reverse command은 자체 `idempotency_key`로 한 번만 실행.
- **[동시]** 두 undo 동시 → `undo_actions`가 activity당 하나(원본 command 기준 unique)라 두 번째는 거부/폴백. reverse command도 하나만 생성.
- **[선행조건]** `undo_available=false`(changed=false였거나 action_type이 역연산 불가) → 422. 원본이 `failed` → undo 대상 아님(applied만 undo 가능). 원본이 이미 `undone`/`compensating` → 409 또는 no-op(진행 중 중복 방지).
- **[부분실패]** reverse command insert·원본 `compensating` 전이·outbox append는 한 트랜잭션. reverse command 실행(execute_action) 실패 → 원본은 `compensating`에 머무름, reverse는 `failed`로 재시도 대상. reverse `applied` 후에만 원본 `undone` 확정 → 중간 사망해도 원본이 `applied`로 되돌아가지 않고 재개된다.
- **[권한]** 타 workspace activity/command undo → 403.
- **[데이터경계]** reverse command payload도 add/remove label id 배열만. undo 실행은 새 `activity_logs` 1건을 남긴다(원복도 활동 이력). 원본 command row는 status 외 미변경 — 원본 payload/audit 보존.
- 검증: `tests/domains/gmail_actions/test_undo.py::{test_undo_creates_reverse_command, test_undo_reverses_via_ledger_not_direct_gmail, test_undo_idempotent_via_undone_at, test_undo_unavailable_rejected}`.

## 경계 계약: `GmailMutationPort` (boundary)

- 인터페이스: `apply(command_id) -> MutationResult{changed: bool}`. 입력은 `command_id` 하나 — port는 ledger에서 command를 읽어 `connected_account_id`·payload를 얻는다. command row 없이 호출 불가한 시그니처 자체가 "ledger 통과 강제" 불변식.
- 구현체: `fake_mutator`(계약/테스트용, in-memory 상태로 changed 계산 + noop 판정), `live_mutator`(실 Gmail `messages.modify`, mail_sources credential은 이 구현체 안에서만 복호화). 도메인 서비스/job은 인터페이스에만 의존.
- negative boundary: gmail_actions 패키지는 `app/domains/mail_intake/gmail_reader`·`GmailReaderPort`를 import하지 않는다. OAuth token 원문 컬럼(`*_ciphertext`)을 도메인 코드가 직접 참조하지 않는다.
- 검증: `tests/domains/gmail_actions/test_mutation_port_boundary.py::{test_write_only_through_mutation_port, test_no_oauth_token_direct_read, test_no_mail_intake_reader_import, test_all_writes_pass_command_ledger}`.

## Event(producer) 요약

| event | idempotency key | 큐잉되는 consumer job(§3) |
|---|---|---|
| `gmail_action_requested` | `command:{command_id}:requested` | `execute_action`(gmail_actions) |
| `gmail_action_applied` | `command:{command_id}:applied:{version}` | `build_briefing`(briefing) + mail_intake snapshot reconcile |
| `gmail_action_failed` | `command:{command_id}:failed:{version}` | `emit_notification`(notifications) |
| `gmail_action_undone` | `command:{command_id}:undone:{version}` | `build_briefing`(briefing), `emit_notification`(notifications) |

payload owner는 전부 gmail_actions. producer는 consumer를 직접 호출하지 않고 outbox event만 발행한다(경계 invariant).

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /actions/activity` (활동 로그)
- **[정상]** workspace의 `activity_logs` 타임라인(`occurred_at` 내림차순) + `action_summary` + actor(사용자/자동화) + undo 가능 여부(`undo_actions.undo_available`).
- **[필터]** command 없는 시스템 활동(`command_id` null)도 포함. undo 가능 항목만 보기 등 필터는 UI 계약 따름.
- **[빈상태]** 활동 0건 → 빈 배열(에러 아님).
- **[권한]** 세션 workspace 스코프만. `action_summary`는 최소 문장이라 message body/summary 텍스트를 절대 포함하지 않는다. OAuth token/credential 필드 미포함.
- 검증: `tests/domains/gmail_actions/test_activity_log.py::test_activity_list_scoped_no_body`.

---

## 워크트리 격리 노트

- 마이그레이션: `0007_gmail_actions`(down_revision `0006_labels`). labels 머지 후 머지(§1 배정표). labels↔gmail_actions 간 FK는 없어 상호 순서는 무관하나 표대로 고정한다.
- `GmailMutationPort`는 `fake_mutator` 계약으로 먼저 고정한다 — Gmail write live 검증 지연(모듈별 차단 조건)을 우회해 command ledger·changed flag·activity·undo 계약을 fake로 확정하고, `live_mutator`는 나중에 교체.
- `_integration-contract.md §5` status 값(`pending`/`applied`/`failed`/`compensating`/`undone`)·§2 job 계약(`execute_action`, lock_key `command:{command_id}`)·§3 event wiring(requested→execute_action; applied/failed/undone consumers) 준수.
- `PURGE_HANDLER(source_id)`는 §4 시그니처 고정 — disconnect purge 시 content-bearing 데이터는 지우되 `activity_logs` 최소 audit은 보존(흐름 8, mail_sources 플랜 §purge job).
- 클라이언트 idempotency key는 `Idempotency-Key` 헤더 관례(UUID v4, db-schema 멱등성 키 설계 "클라이언트가 결정하는 키") — 서버가 값을 조합하지 않고 그대로 저장·재사용.
