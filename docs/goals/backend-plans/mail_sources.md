# mail_sources 세부 플랜 (Connected Gmail Sources)

기준: `module-boundaries.md`(컨텍스트·Command/Event Catalog·흐름 1·7·8), `db-schema.md`(mail_sources 섹션), `_integration-contract.md`(충돌 규약). 대응 Task: 3(연결), 13(purge 오케스트레이션).

## 도메인 책임 요약

연결 Gmail 계정, OAuth credential lifecycle, 계정 설정(toggle/pause), 계정 상태 source state, disconnect/purge 오케스트레이션. **소유 안 함**: Gmail history sync·snapshot(mail_intake), Gmail mutation(gmail_actions).

강제 invariant(이 도메인이 지키는 것):
- OAuth token 원문은 이 도메인 밖에서 직접 못 읽음 → `gmail_oauth_credentials`는 mail_sources 코드 밖에서 import 금지.
- 동일 Gmail 계정은 한 workspace에서 중복 활성 연결 불가.
- 연결 해제 시 token 즉시 폐기 + sync/action 차단.
- token plaintext 미저장.

소유 테이블: `connected_gmail_accounts`, `gmail_oauth_credentials`◆, `gmail_source_settings`.
소유 event(producer): `gmail_source_connected`, `gmail_source_settings_changed`, `gmail_source_disconnected`, `gmail_source_recovery_needed`(mail_intake와 공동).
소유 job: `purge_disconnected_source`.

## 계정 상태 전이 (`connected_gmail_accounts.status`)

값 집합은 `_integration-contract.md §5` 고정. 전이:

```
(신규)
  → connected            연결 직후, 초기 sync 큐잉 전
  → syncing              초기/재 sync 진행 중 (흐름 1 "초기 sync 끝나기 전 syncing 노출")
  → synced               최소 1회 sync 성공
syncing/synced
  → permission_needed    token refresh 실패·Gmail auth 오류 (흐름 7, mail_intake도 세팅 가능)
  → error                복구 불가 sync 오류
synced/permission_needed/error/paused
  → paused               사용자 일시정지 (update settings)
  → disconnecting        해제 요청 접수, purge 진행 중 (흐름 8)
disconnecting
  → disconnected         purge 완료·token 폐기 확정
```

전이 규칙:
- `permission_needed`/`error`는 mail_sources 단독 소유가 아니다 — mail_intake sync 실패도 이 상태로 밀 수 있다. 둘 다 `gmail_source_recovery_needed`를 발행하되 payload `reason`으로 원인 구분(§recovery).
- `disconnected` → 다른 상태로 복귀 없음. 재연결은 새 row(중복 인덱스가 `status <> 'disconnected'`만 적용).

---

## Command: `connect_gmail_source`

- 소유 테이블: `connected_gmail_accounts`(insert), `gmail_oauth_credentials`(insert, 암호화), `gmail_source_settings`(insert, 기본값)
- 발행 event: `gmail_source_connected` (idempotency `source:{source_id}:connected:{version=0}`)
- 후속: `register_watch` + 초기 `sync_full` 큐잉(§integration §3)
- 입력 → 상태전이 → 결과: `{workspace_id, oauth callback profile, encrypted credential}` → status `connected`→(sync job이 `syncing`으로) → connected source + initial sync job
- API: `POST /sources`

체크리스트:
- **[정상]** 신규 Gmail 주소 연결 → credential 3-token(access/refresh/scope) 암호화 저장(`access_token_ciphertext` bytea, `encryption_key_version` 기록) → settings 기본값(모두 true, paused=false) → `connected` insert(version=0) → outbox `gmail_source_connected` 1건 → `register_watch`+`sync_full` 큐잉.
- **[멱등]** OAuth callback 재수신(뒤로가기·재시도). connect는 클라이언트 idempotency-key가 없는 흐름 → 서버는 `(workspace_id, gmail_address) WHERE status<>'disconnected'` 활성 유니크로 중복 insert를 막고, 이미 활성 연결이면 기존 source 반환(신규 sync 재큐잉 금지). event도 재발행 안 함(version 그대로).
- **[동시]** 같은 workspace+주소로 두 요청 동시 도착. 부분 유니크 인덱스가 두 번째 insert를 DB 레벨에서 거부(IntegrityError) → 두 번째 요청은 기존 row 조회로 폴백. token은 한 벌만 저장.
- **[선행조건]** `workspace_id` 부재/세션 workspace와 불일치 → 401/403(§권한). OAuth callback profile에 gmail_address 없음/scope 부족(`gmail.modify` 누락) → 422, 연결 거부(insert 없음). 암호화 키(`MAILY_TOKEN_ENC_KEY`) 미설정 → 500, credential 저장 시도 자체를 막고 계정 insert도 롤백(§부분실패).
- **[부분실패]** 계정 insert 성공·credential 암호화 저장 실패 → 전체 트랜잭션 롤백(계정+credential+settings+outbox는 한 트랜잭션). outbox event append도 같은 트랜잭션 → event만 남고 계정 없음/계정만 있고 event 없음 상태 불가. sync job 큐잉은 dispatcher가 outbox를 읽어 처리(별도 트랜잭션) → 계정 커밋 후 프로세스 죽어도 event는 남아 재기동 시 큐잉됨.
- **[권한]** 세션 workspace ≠ 요청 workspace_id → 403. 타 workspace 계정 목록 조회·조작 불가(workspace_id 직접 컬럼으로 스코프).
- **[데이터경계]** 같은 주소가 과거 `disconnected` row로 존재 → 신규 연결 허용(새 row, 부분 유니크가 disconnected 제외). purge 미완료(`disconnecting`) 상태의 같은 주소 재연결 시도 → 거부(활성 취급), purge 완료까지 대기.
- 검증: `tests/domains/mail_sources/test_connection.py::{test_connect_creates_source_and_credential, test_duplicate_active_address_rejected, test_disconnected_address_reconnectable}`, `test_credentials.py::{test_token_plaintext_never_persisted, test_missing_enc_key_rolls_back}`.

## Command: `update_gmail_source_settings`

- 소유 테이블: `gmail_source_settings`(update), `connected_gmail_accounts`(status: paused 전이 시)
- 발행 event: `gmail_source_settings_changed` (idempotency `source:{source_id}:settings:{version}`) — `connected_gmail_accounts.version` 증가분 사용
- 입력 → 결과: `{source_id, display_name?, briefing?, summary?, notification?, paused?}` → 설정 반영 + settings_changed event
- API: `PATCH /sources/{id}`

체크리스트:
- **[정상]** toggle/display_name/paused 변경 → `gmail_source_settings` update, `updated_at` 갱신 → version+1 → outbox `gmail_source_settings_changed`. paused=true면 계정 status `paused` 전이(sync 스킵 근거).
- **[멱등]** 같은 값으로 재요청(no-op update). 값 변화 없으면 version 증가·event 발행 안 함(불필요한 briefing/assistant 재평가 방지). 변화 있는 필드만 diff해 발행.
- **[동시]** 두 PATCH 동시 → `version` optimistic 증가로 순서 보장. 마지막 쓰기가 이김(POC 범위). version은 매 성공 전이마다 +1이라 event idempotency key가 갈려 dedupe 유지.
- **[선행조건]** source 없음/`disconnected`/`disconnecting` → 404 또는 409(해제 중 설정 변경 거부). summary_enabled를 off로 바꾸면 이후 `generate_summary` job 큐잉 중단(assistant가 read 시점에 반영, 진행 중 job은 완료).
- **[부분실패]** settings update 성공·outbox append 실패 → 트랜잭션 롤백(한 트랜잭션). paused 전이와 settings update는 원자적.
- **[권한]** 타 workspace source PATCH → 403.
- **[데이터경계]** display_name을 빈 문자열/null로 → 저장 허용, 응답 시 `gmail_address`로 fallback(Task 3 test). paused=true 상태에서 다시 briefing_enabled 조작 → 허용(설정은 paused와 독립).
- 검증: `tests/domains/mail_sources/test_source_settings.py::{test_toggle_updates_and_emits, test_noop_update_no_event, test_pause_transitions_status, test_display_name_fallback}`.

## Command: `disconnect_gmail_source`

- 소유 테이블: `connected_gmail_accounts`(status→disconnecting), `gmail_oauth_credentials`(revoked_at 세팅)
- 발행 event: `gmail_source_disconnected` (idempotency `source:{source_id}:disconnected:{version}`)
- 후속: `purge_disconnected_source` 큐잉 + 각 도메인 purge 참여(흐름 8)
- 입력 → 결과: `{source_id, actor_id}` → token revoked, sync/action 차단, purge job 요청
- API: `DELETE /sources/{id}`

체크리스트:
- **[정상]** 해제 요청 → status `disconnecting` → `gmail_oauth_credentials.revoked_at=now()` → version+1 → outbox `gmail_source_disconnected` → `purge_disconnected_source` 큐잉. 이 시점부터 신규 sync/action job은 이 source_id로 큐잉 거부(§선행조건 가드가 다른 도메인에도 적용).
- **[멱등]** 재요청/이미 `disconnecting`. status가 이미 disconnecting/disconnected면 no-op(추가 event·job 없음). purge job은 자체 idempotency(§purge job)로 중복 실행 무해.
- **[동시]** disconnect와 update_settings 동시 → disconnect 우선. update는 `disconnecting` 선행조건 위반으로 409. disconnect와 진행 중 sync job 동시 → sync는 credential `revoked_at` 확인 후 중단(§부분실패), 이미 fetch된 snapshot은 purge가 정리.
- **[부분실패]** status 전이·revoke 성공·outbox append 실패 → 롤백(한 트랜잭션, token은 아직 유효). revoke 후 purge job 실행 전 프로세스 사망 → outbox event 남아 재기동 시 purge 재큐잉(at-least-once). Google 원격 revoke(live) 실패 → 로컬 `revoked_at`은 세팅해 sync/action 차단은 즉시 발효, 원격 revoke는 retry(Task 13 marker).
- **[권한]** 타 workspace source 해제 → 403. `actor_id`는 activity/audit용으로만 기록.
- **[데이터경계]** disconnect 후 content-bearing 데이터(◆) purge 대상: `gmail_oauth_credentials`, `gmail_messages`, `message_excerpts`, `briefing_items`, `briefing_item_states`, summaries, importance, cleanup_proposals, rule_suggestions. 최소 audit(`activity_logs` action_summary)는 보존(body/summary 텍스트 없이). 다른 workspace 데이터는 절대 미삭제(§purge job 멱등).
- 검증: `tests/domains/mail_sources/test_disconnect_purge.py::{test_disconnect_revokes_and_blocks, test_disconnect_idempotent, test_disconnect_emits_and_queues_purge}`.

## Event(공동 producer): `gmail_source_recovery_needed`

- producer: mail_sources 또는 mail_intake(실패 감지한 쪽이 payload owner)
- idempotency: `source:{source_id}:recovery:{reason}:{version}`
- consumer: notifications(`emit_notification`, route_target=계정 설정 화면)
- 발행 조건: token refresh 실패, Gmail auth 오류(403/401), scope 축소 감지 → 계정 status `permission_needed`.
- 경계: notifications는 복구 안내 view만 만든다. 상태 source of truth는 이 도메인(`connected_gmail_accounts.status`). `reason` 값으로 원인 구분(`token_refresh_failed`/`scope_reduced`/`auth_error`), 결과별 event 종류를 늘리지 않는다.

## Job: `purge_disconnected_source`

- 트리거: `gmail_source_disconnected`
- payload: `{source_id}`, lock_key `source:{source_id}`
- 오케스트레이션(Task 13): 각 도메인 `PURGE_HANDLER(source_id)` 순차 호출 → 최종 계정 status `disconnected`.

체크리스트:
- **[정상]** mail_intake→briefing→assistant_decisions→gmail_actions(최소 audit 보존)→mail_sources(credential row 삭제) 순 purge → 계정 status `disconnected`.
- **[멱등]** job 두 번 실행 → 이미 삭제된 row는 no-op, 이미 `disconnected`면 조기 종료. 결과 동일(멱등 필수 — at-least-once 큐잉).
- **[동시]** lock_key `source:{source_id}`로 두 워커 동시 purge 방지.
- **[선행조건]** source가 `disconnecting`이 아니면 실행 거부(잘못된 트리거 방어).
- **[부분실패]** 중간 도메인 purge 실패 → job `retrying`, 나머지 미완. 재실행 시 멱등이라 완료분은 skip, 미완분만 재시도. 모든 도메인 성공 후에만 `disconnected` 확정.
- **[권한]** N/A(내부 job, 사용자 컨텍스트 없음). workspace 스코프는 각 도메인 handler가 source_id→workspace로 제한.
- **[데이터경계]** 절대 다른 source/workspace 데이터 미삭제 — 각 handler는 `WHERE source_id = ?`(또는 message가 그 source 소속인 것만)로 제한. 최소 audit(`activity_logs`)는 삭제 대상 아님.
- 검증: `tests/domains/mail_sources/test_purge_disconnected_source_job.py::{test_purge_removes_content, test_purge_keeps_audit, test_purge_idempotent_no_cross_workspace_delete}`.

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /sources` (계정 목록)
- **[정상]** workspace의 활성 계정 목록 + status + display_name(fallback) + settings.
- **[필터]** `disconnected` 계정 제외(기본). status별 정렬은 UI 계약 따름.
- **[빈상태]** 연결 계정 0개 → 빈 배열(에러 아님).
- **[권한]** 세션 workspace 스코프만. token/credential 필드는 응답에 절대 미포함.
- 검증: `test_connection.py::test_list_sources_scoped`.

### `GET /sources/{id}`
- **[정상]** 단건 상태·설정. **[권한]** 타 workspace 404(존재 노출 방지). **[데이터경계]** `disconnecting`/`disconnected`도 상태 확인용 조회는 허용, credential 필드 미포함.

---

## 워크트리 격리 노트

- 마이그레이션: `0003_mail_sources`(down `0002_identity`). identity 머지 후 머지.
- credential 암호화: `app/core/crypto.py`는 core 슬라이스가 먼저 제공(Task 3 Files에 포함). 미제공 시 fake crypto로 계약 테스트 진행, 실 암호화는 core 머지 후 교체.
- `_integration-contract.md §5` status 값·§2 job 계약·§3 event wiring 준수. purge handler 시그니처는 §4 `PURGE_HANDLER(source_id)` 고정.
- 미정 의존: token 암호화 방식(db-schema 열린 결정) → POC Fernet+env, `encryption_key_version` 컬럼 유지.
