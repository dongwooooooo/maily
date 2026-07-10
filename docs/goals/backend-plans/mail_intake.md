# mail_intake 세부 플랜 (Gmail Intake & Snapshot)

기준: `module-boundaries.md`(컨텍스트·Command/Event Catalog·흐름 2 "새 메일 지속 동기화"·`GmailReaderPort` invariant·notification dedupe/fan-out), `db-schema.md`(mail_intake 섹션), `_integration-contract.md`(§1 Alembic, §2 job·lock_key, §3 event wiring, §5 status). 대응 Task: 4(reader·snapshot), 5(지속 동기화).

## 도메인 책임 요약

Gmail watch 등록/갱신, Pub/Sub notification dedupe·fan-out, history cursor, delta/full sync, message snapshot·limited excerpt 저장, `GmailReaderPort`. **소유 안 함**: OAuth credential lifecycle·계정 status source of truth(mail_sources), 브리핑 섹션 배치·item state(briefing), 요약·중요도 판단(assistant_decisions), Gmail write/mutation(gmail_actions).

강제 invariant(이 도메인이 지키는 것):
- Gmail read/sync 호출은 `GmailReaderPort`로만 한다 — repository·service·job은 Gmail API SDK를 직접 import 금지.
- OAuth token 원문을 직접 안 읽는다. `gmail_oauth_credentials`는 mail_sources 밖에서 import 금지 → reader 구현체는 mail_sources가 주입한 자격증명 핸들만 받는다.
- raw body 미보관 — snapshot(`gmail_messages`)에는 body 컬럼이 없고, 발췌는 `message_excerpts.excerpt_text`(metadata 응답의 `snippet`)만 저장한다.
- snapshot(`gmail_messages`+`message_excerpts`+`gmail_message_labels`)은 언제든 재생성 가능하다 — 진짜 상태는 Gmail이고 이 테이블은 재동기화로 복원된다.
- importance 판단 대기 아이템에 개별 pending 상태를 안 만든다. 계정 `syncing`(mail_sources 소유 status)으로만 대기를 안내한다.

소유 테이블: `gmail_messages`◆, `message_excerpts`◆, `gmail_message_labels`, `gmail_sync_cursors`, `gmail_watch_registrations`, `gmail_notification_events`, `sync_runs`.
소유 event(producer): `gmail_notification_received`, `gmail_snapshot_changed`, `gmail_source_recovery_needed`(mail_sources와 공동).
소유 job: `register_watch`, `renew_watch`, `process_notification`, `poll_history`, `sync_delta`, `sync_full`.

## sync 경로와 cursor 상태

값 집합은 `_integration-contract.md §5` 고정. `gmail_sync_cursors.cursor_status`는 `valid`/`invalid`, `gmail_watch_registrations.status`는 `active`/`expired`/`failed`, `sync_runs.status`는 `running`/`succeeded`/`failed`.

```
연결(gmail_source_connected)
  → register_watch          watch 등록 + 초기 sync_full 큐잉(§integration §3)
  → sync_full               전체 스냅샷 + cursor last_history_id 확정 → cursor_status=valid
실시간(watch 살아있음)
  Pub/Sub notification → process_notification → (dedupe) → 활성 source fan-out → sync_delta
  → sync_delta              history 증분 반영 → cursor last_history_id 전진
cursor 만료(history 너무 오래됨, Gmail 404)
  → cursor_status=invalid → sync_full(reason=cursor_invalid) 트리거 → 복원 후 valid
watch 만료 임박(7일 이내)
  → renew_watch             expiration 연장
watch 끊김/notification 미도착
  → poll_history(fallback)  스케줄 폴링으로 history 확인 → 필요 시 sync_delta 경로
권한 오류(401/403·scope 축소)
  → gmail_source_recovery_needed 발행 + 계정 status permission_needed(mail_sources가 확정)
```

전이 규칙:
- delta는 cursor가 `valid`일 때만 유효하다. Gmail이 `start_history_id`를 더 못 알아보면(`invalid`) delta를 포기하고 full로 승격한다 — delta를 억지로 재시도하지 않는다.
- `permission_needed`/`error` status 자체는 mail_sources 소유다. mail_intake는 sync 실패를 감지해 `gmail_source_recovery_needed`를 발행할 뿐 status 컬럼을 직접 쓰지 않는다(`reason`으로 원인 구분, 흐름 7).

---

## Port 계약: `GmailReaderPort` (+ `fake_reader`)

- 위치: `mail_intake/gmail_reader.py`(추상), `fake_reader.py`(결정적 테스트 더블), `live_reader.py`(Gmail API). service·job은 추상 타입에만 의존한다.
- 메서드(4개): `register_watch(source) -> {topic_name, expiration, history_id}`, `history(source, start_history_id) -> {records[], new_history_id, valid}`, `get_message_metadata(source, gmail_message_id) -> {subject, sender, snippet, thread_id, label_ids[], is_read, is_archived, received_at}`(`messages.get(format=metadata)` — `snippet` 포함), `list_message_ids(source) -> {gmail_message_id[], history_id}`(full sync 대상 열거).
- 자격증명 경계: reader는 `connected_account_id`만 받고, 실제 token은 mail_sources가 제공하는 주입 핸들에서 꺼낸다. `access_token_ciphertext`·복호화 로직은 reader 안에 두지 않는다.
- **raw body 금지**: port에 `get_full_body` 류 메서드를 두지 않는다. excerpt는 metadata 응답의 `snippet`이 유일한 출처다(db-schema `message_excerpts` 라이브 POC 확인). live_reader가 `format=full`을 호출하면 계약 위반.

체크리스트:
- **[정상]** fake_reader는 결정적 history page·message metadata·Gmail state snapshot을 시드값대로 돌려준다. 같은 시드 → 같은 응답(테스트 재현성).
- **[멱등]** 같은 `start_history_id`로 `history()` 재호출 → 같은 record 집합. delta 재실행이 snapshot을 중복 생성하지 않는 근거.
- **[동시]** N/A(port는 상태 없는 read 계약. 동시성은 호출자 job의 lock_key로 처리).
- **[선행조건]** `history(start_history_id)`가 Gmail에 없으면 `valid=false` 반환 → 호출자가 full로 승격. metadata에 필수 필드 부재 → 해당 필드 null 저장(subject/sender/snippet nullable).
- **[부분실패]** `history()` 중간 페이지 fetch 실패 → 부분 반영 금지, 해당 sync_run `failed` 처리 후 재시도(cursor 미전진 → 다음 실행이 같은 지점부터).
- **[권한]** 401/403·scope 축소 감지 → reader가 auth 오류 타입을 올려보내고 호출자가 `gmail_source_recovery_needed` 발행. reader는 status 컬럼을 안 만진다.
- **[데이터경계]** live_reader가 `format=full`/body fetch를 호출하지 않음을 계약 테스트로 고정. fake_reader에도 body 필드 자체가 없다.
- 검증: `tests/domains/mail_intake/test_fake_reader.py::{test_deterministic_history_pages, test_gmail_state_snapshot, test_reader_never_returns_raw_body}`.

## Command: `sync_gmail_full`

- 소유 테이블: `gmail_messages`(upsert), `message_excerpts`(upsert), `gmail_message_labels`(replace), `gmail_sync_cursors`(last_history_id 재설정, cursor_status=valid), `sync_runs`(insert)
- 발행 event: `gmail_snapshot_changed` (idempotency `source:{source_id}:snapshot:{sync_run_id}`, payload `{source_id, sync_run_id, message_ids}`)
- job: `sync_full` (`{source_id, reason}`, lock_key `source:{source_id}`)
- 트리거: 초기 연결(register_watch 뒤), cursor invalid 승격, 수동 재동기화
- 입력 → 결과: `{source_id, reason}` → 전체 스냅샷 재구성 + 새 cursor + snapshot_changed
- API: `POST /sources/{id}/sync`(manual, run_type=full 요청)

체크리스트:
- **[정상]** `list_message_ids` 열거 → 각 메시지 `get_message_metadata` → `(connected_account_id, gmail_message_id)` upsert(snapshot_version+1), snippet을 `message_excerpts`에 upsert, label snapshot replace, is_read/is_archived 반영 → `sync_runs`(run_type=full, status succeeded, messages_changed_count) → cursor last_history_id=응답 history_id, cursor_status=valid → outbox `gmail_snapshot_changed`(message_ids = 이번에 바뀐 것).
- **[멱등]** full sync 재실행 → 같은 upsert key로 덮어써 row 수 불변. 이미 최신인 메시지는 snapshot_version 증가 없이 no-op(불필요한 summary/importance 재큐잉 방지 — `gmail_snapshot_changed` message_ids에서 제외). 재실행이 새 sync_run은 만들지만 event idempotency는 sync_run_id로 갈려 dedupe 유지.
- **[동시]** lock_key `source:{source_id}`로 같은 계정 full/delta 동시 실행 차단 → snapshot 꼬임 방지. 두 번째 워커는 lock 실패로 대기/스킵.
- **[선행조건]** source가 `disconnecting`/`disconnected`/`paused` → 실행 거부(가드). credential `revoked_at` 세팅됨 → reader 호출 전 중단. `reason` 미지정 → `initial`/`cursor_invalid`/`manual` 중 트리거가 채운다.
- **[부분실패]** 열거 성공·일부 메시지 metadata fetch 실패 → sync_run `failed`, cursor 미전진(부분 스냅샷을 valid로 확정하지 않음). 재실행 시 upsert 멱등이라 완료분 재적용 무해. snapshot upsert 성공·outbox append 실패 → 한 트랜잭션 롤백(snapshot과 event 원자적).
- **[권한]** N/A(내부 job, 사용자 컨텍스트 없음). manual `POST /sources/{id}/sync`는 세션 workspace 스코프로 source 소유 확인 후 큐잉(타 workspace 403).
- **[데이터경계]** upsert·label replace는 `WHERE connected_account_id = ?` 범위로만 — 다른 계정 스냅샷 미변경. body 컬럼 없음(raw body 미보관 재확인).
- 검증: `tests/domains/mail_intake/test_message_snapshot.py::{test_snapshot_upsert_keyed_by_account_and_message, test_excerpt_rejects_raw_body, test_snapshot_changed_event_payload}`, `test_sync_full_job.py::{test_full_resync_is_idempotent, test_invalid_cursor_triggers_full}`.

## Command: `sync_gmail_delta`

- 소유 테이블: `gmail_messages`(upsert), `message_excerpts`(upsert), `gmail_message_labels`(diff 반영), `gmail_sync_cursors`(last_history_id 전진 / invalid 표시), `sync_runs`(insert)
- 발행 event: `gmail_snapshot_changed` (idempotency `source:{source_id}:snapshot:{sync_run_id}`, payload `{source_id, sync_run_id, message_ids}`)
- job: `sync_delta` (`{source_id, start_history_id}`, lock_key `source:{source_id}`, idempotency `sync-delta:{source_id}:{start_history_id}`)
- 트리거: `gmail_notification_received`(dedupe 후), `poll_history` fallback
- 입력 → 결과: `{source_id, start_history_id}` → 증분 반영 + cursor 전진 + snapshot_changed
- API: `POST /sources/{id}/sync`(manual, run_type=delta)

체크리스트:
- **[정상]** cursor `last_history_id`부터 `history(start_history_id)` 호출 → record별 반영: messagesAdded → snapshot upsert + excerpt, messagesDeleted → snapshot 제거/마킹, labelsAdded/Removed → `gmail_message_labels` diff + is_read/is_archived 갱신(snapshot_version+1) → `sync_runs`(run_type=delta, succeeded) → cursor last_history_id 전진, last_successful_sync_at=now → outbox `gmail_snapshot_changed`(바뀐 message_ids만).
- **[멱등]** 같은 `start_history_id`로 재큐잉(같은 notification 두 번 처리·재시도). job UNIQUE `(job_type, idempotency_key=sync-delta:{source_id}:{start_history_id})`로 중복 큐잉 차단. 이미 반영된 record는 upsert로 no-op → snapshot_version 불변, event message_ids 비면 소비자 재기동 안 함.
- **[동시]** lock_key `source:{source_id}`로 같은 계정 delta/full 동시 실행 차단. notification과 poll이 겹쳐 두 delta가 큐잉돼도 lock으로 직렬화, cursor는 한 번에 하나만 전진.
- **[선행조건]** cursor `cursor_status=invalid` → delta 실행 거부하고 `sync_full{reason=cursor_invalid}` 큐잉. `start_history_id`가 현재 cursor보다 과거 → 이미 반영된 구간, no-op 종료. source `paused`/`disconnecting` → 스킵.
- **[부분실패]** `history()`가 `valid=false`(Gmail이 start_history_id 인식 못 함) → cursor `cursor_status=invalid` 마킹, sync_run `failed`, full resync 승격(delta 무한 재시도 안 함). 중간 record 반영 후 실패 → sync_run `failed`, cursor 미전진 → 재실행이 같은 지점부터(멱등 upsert로 안전). snapshot upsert·outbox append는 한 트랜잭션.
- **[권한]** N/A(내부 job). reader가 401/403 반환 → sync_run `failed`(error_reason=auth), `gmail_source_recovery_needed` 발행(계정 status는 mail_sources 확정). manual delta는 workspace 스코프 검증.
- **[데이터경계]** history record는 그 source 소속 메시지에만 반영(`connected_account_id` 스코프). 같은 email 주소의 다른 활성 source에는 각자 자기 delta가 따로 돈다(fan-out은 process_notification이 이미 분리). raw body 미저장.
- 검증: `tests/domains/mail_intake/test_sync_delta_job.py::{test_delta_applies_history_records, test_delta_idempotent_on_replay, test_invalid_cursor_schedules_full}`, `test_sync_cursor.py::{test_cursor_advances_on_success, test_last_successful_sync_at_updates}`.

## Command: `process_gmail_notification`

- 소유 테이블: `gmail_notification_events`(insert, dedupe)
- 발행 event: `gmail_notification_received` (idempotency `gmail-notification:{email}:{history_id}`) — consumer는 `sync_delta`(§integration §3)
- job: `process_notification` (`{email_address, history_id, notification_id}`, lock_key `null` — dedupe가 중복을 막아 lock 불필요)
- 트리거: Pub/Sub 수신(`POST /intake/pubsub`)
- 입력 → 결과: `{emailAddress, historyId}` → dedupe 후 active source fan-out → 각 source에 `sync_delta` 큐잉
- API: `POST /intake/pubsub`(webhook)

체크리스트:
- **[정상]** Pub/Sub payload `{emailAddress, historyId}` decode → `gmail_notification_events` insert(dedupe_key=`gmail-notification:{email}:{history_id}`) → `email_address`로 활성 연결(`status <> 'disconnected'/'disconnecting'`, `paused=false`) 조회 → 매칭 source마다 `sync_delta{source_id, start_history_id=history_id}` 큐잉(각 lock_key `source:{source_id}`) → outbox `gmail_notification_received`.
- **[멱등]** Pub/Sub at-least-once로 같은 notification 재전달 → `gmail_notification_events.dedupe_key` UNIQUE가 두 번째 insert 거부(IntegrityError) → 조기 종료(재 fan-out 없음). `gmail_notification_received` event도 재발행 안 함.
- **[동시]** 같은 email+history 두 전달 동시 도착 → dedupe UNIQUE가 DB 레벨에서 한 건만 통과, 두 번째는 no-op. sync_delta 자체 idempotency(`sync-delta:{source_id}:{history_id}`)가 fan-out 중복까지 이중 방어.
- **[선행조건]** `emailAddress`에 매칭되는 활성 source 0개(연결 해제됨·전부 paused) → notification은 기록하되 sync_delta 큐잉 없음(orphan notification, 에러 아님). payload에 `emailAddress`/`historyId` 부재 → 400, insert 없음.
- **[부분실패]** notification insert 성공·일부 source의 sync_delta 큐잉 실패 → 큐잉은 outbox event 기반이라 재기동 시 미큐잉분 재처리(at-least-once). notification 기록과 event append는 한 트랜잭션.
- **[권한]** Pub/Sub webhook은 사용자 세션이 아니라 topic 인증(OIDC/토큰)으로 검증 → 검증 실패 시 401, payload 미처리. workspace 스코프는 email_address→active source 조회가 자연히 제한.
- **[데이터경계]** 같은 Gmail 주소가 여러 workspace의 active connection에 존재 → 전부로 fan-out(module-boundaries 불변식 "active connection 전체로 fan-out"). 각 source는 자기 credential로 자기 delta만 실행 → 계정 간 데이터 섞임 없음.
- 검증: `tests/domains/mail_intake/test_process_notification_job.py::{test_fanout_to_active_sources_by_email, test_notification_dedupe_by_email_and_history, test_no_active_source_is_noop}`.

## Job: `register_watch`

- 소유 테이블: `gmail_watch_registrations`(insert), `gmail_sync_cursors`(insert/watch_expiration_at 세팅)
- payload: `{source_id}`, lock_key `source:{source_id}`
- 트리거: `gmail_source_connected`(§integration §3) — 초기 `sync_full`과 함께 큐잉
- 결과: watch 등록 + 초기 cursor 준비

체크리스트:
- **[정상]** `GmailReaderPort.register_watch(source)` → `gmail_watch_registrations`(topic_name, expiration, status=active) insert → `gmail_sync_cursors` 없으면 생성하고 watch_expiration_at·초기 last_history_id 세팅 → 이후 sync_full이 스냅샷을 채운다.
- **[멱등]** `gmail_source_connected` 재수신·재큐잉 → 이미 active watch 있으면 갱신만(중복 registration row 생성 안 함). cursor는 upsert.
- **[동시]** lock_key `source:{source_id}`로 register/renew 동시 실행 차단.
- **[선행조건]** source `disconnecting`/credential revoked → 실행 거부. Pub/Sub topic 미설정(live) → registration `failed` 마킹, fallback으로 `poll_history` 경로 유지.
- **[부분실패]** watch 등록 성공·cursor 세팅 실패 → 롤백(한 트랜잭션). 원격 watch만 걸리고 로컬 기록 없음 상태 방지 → 재실행 시 reader가 기존 watch 반환(멱등).
- **[권한]** N/A(내부 job). 401/403 → registration `failed`, `gmail_source_recovery_needed` 발행.
- **[데이터경계]** N/A(단일 source 대상, 다른 계정 무관).
- 검증: `tests/domains/mail_intake/test_sync_cursor.py::test_register_watch_sets_expiration`.

## Job: `renew_watch`

- 소유 테이블: `gmail_watch_registrations`(expiration 갱신), `gmail_sync_cursors`(watch_expiration_at 갱신)
- payload: `{source_id}`, lock_key `source:{source_id}`
- 트리거: 스케줄(만료 전) — Gmail watch는 최대 7일 유효, 만료 전 갱신
- 결과: watch expiration 연장

체크리스트:
- **[정상]** `expiration` 7일 임박(만료 전) 대상 선정 → `register_watch`(재호출) → registration expiration·cursor watch_expiration_at 갱신, status=active 유지.
- **[멱등]** 스케줄 중복 실행 → 같은 registration 갱신, row 수 불변. 이미 충분히 미래면 no-op.
- **[동시]** lock_key `source:{source_id}`로 register_watch와 상호 배제.
- **[선행조건]** source `disconnecting`/`paused`/credential revoked → 갱신 스킵(watch 자연 만료 허용). registration `failed`/`expired` → renew 대신 register 경로.
- **[부분실패]** 원격 갱신 성공·로컬 기록 실패 → 재실행 시 reader가 현재 watch 반환해 정합 복원. 갱신 실패 → registration `expired` 마킹 → poll_history fallback이 공백을 메움.
- **[권한]** N/A(내부 job). auth 오류 → `gmail_source_recovery_needed`.
- **[데이터경계]** N/A(단일 source).
- 검증: `tests/domains/mail_intake/test_sync_cursor.py::test_renew_selects_expiring_watches`.

## Job: `poll_history`

- 소유 테이블: 읽기(`gmail_sync_cursors`) → 필요 시 `sync_delta` 큐잉
- payload: `{source_id}`, lock_key `source:{source_id}`
- 트리거: 스케줄(fallback) — watch 끊김·notification 미도착 시 실시간 경로 공백 보완
- 결과: cursor 기준 history 확인 → 변경 있으면 delta 경로

체크리스트:
- **[정상]** cursor `last_history_id`로 `history()` 확인 → 새 record 있으면 `sync_delta{source_id, start_history_id=last_history_id}` 큐잉, 없으면 last_successful_sync_at만 갱신(살아있음 표시).
- **[멱등]** 폴링 반복 실행 → sync_delta 자체 idempotency(`sync-delta:{source_id}:{history_id}`)로 중복 큐잉 차단. 변경 없으면 반복해도 no-op.
- **[동시]** lock_key `source:{source_id}`로 sync_delta/full과 직렬화. notification 경로와 poll이 같은 history를 동시 감지해도 delta idempotency가 이중 실행 방지.
- **[선행조건]** cursor `invalid` → delta 대신 `sync_full{reason=cursor_invalid}` 큐잉. source `paused`/`disconnecting` → 폴링 스킵. watch가 아직 `active`면 폴링은 저빈도 안전망으로만.
- **[부분실패]** 폴링 중 reader 오류 → 이번 폴링만 실패, cursor 미변경(다음 스케줄이 재시도). last_successful_sync_at이 오래 정체 → 흐름 7 recovery 판단 근거.
- **[권한]** N/A(내부 job). 401/403 → `gmail_source_recovery_needed`.
- **[데이터경계]** 대상 선정은 활성·미paused source로 한정(`WHERE status`/`paused` 스코프). 계정별 독립 폴링.
- 검증: `tests/domains/mail_intake/test_poll_history_job.py::{test_poll_selects_stale_sources, test_poll_queues_delta_on_change, test_poll_noop_when_no_change}`.

## Event(producer): `gmail_snapshot_changed`

- producer: mail_intake
- payload: `{source_id, sync_run_id, message_ids}` — briefing이 어느 message_id를 부분 재생성할지 아는 근거
- idempotency: `source:{source_id}:snapshot:{sync_run_id}`
- consumer(§integration §3): `build_briefing`(briefing), `generate_summary`+`classify_importance`(assistant, summary는 `summary_enabled` 시만), `prepare_cleanup_proposals`(assistant), route(notifications)
- 경계: mail_intake는 event만 발행하고 briefing/assistant/notifications를 직접 호출하지 않는다(흐름 2 불변식). `message_ids`가 빈 sync_run은 event를 발행하지 않는다 — 소비자 무의미 재기동 방지.

## Event(producer): `gmail_notification_received`

- producer: mail_intake
- payload: `{email_address, history_id}` + fan-out 대상
- idempotency: `gmail-notification:{email}:{history_id}` — `gmail_notification_events.dedupe_key`와 동일 값
- consumer(§integration §3): `sync_delta`(intake)
- 경계: raw Pub/Sub 수신을 durable event로 고정하는 자리. dedupe는 이 event 발행 전 `gmail_notification_events` UNIQUE로 이미 강제.

## Event(공동 producer): `gmail_source_recovery_needed`

- producer: mail_intake 또는 mail_sources(실패 감지한 쪽이 payload owner) — sync/watch 실패를 mail_intake가 감지하면 이쪽이 발행
- idempotency: `source:{source_id}:recovery:{reason}:{version}`
- consumer: notifications(`emit_notification`, route_target=계정 설정 화면)
- 발행 조건: reader 401/403, scope 축소, watch 등록 실패, cursor 장기 정체 → `reason`(`auth_error`/`scope_reduced`/`watch_failed`) 구분.
- 경계: 계정 status(`permission_needed`) source of truth는 mail_sources(`connected_gmail_accounts.status`)다. mail_intake는 실패 사실만 event로 알리고 status 컬럼을 직접 쓰지 않는다. 결과별 event 종류를 늘리지 않고 `reason`으로만 구분.

## Read/webhook API (경량 — 6축 대신 정상/멱등/권한/빈상태)

### `POST /intake/pubsub` (Pub/Sub webhook)
- **[정상]** Pub/Sub push payload decode → `process_notification` 큐잉 → 200(빠른 ack). 응답은 `PubSubAckResponse{deduped: bool}` — OpenAPI codegen 대상이라 dict 반환 금지.
- **[멱등]** 같은 message 재전달 → dedupe로 no-op, 여전히 200(Pub/Sub 재전송 폭주 방지 위해 실패로 안 돌림).
- **[권한]** topic 인증(OIDC 토큰) 검증 실패 → 401. 사용자 세션 아님.
- **[빈상태]** 매칭 active source 0개 → notification 기록만, 200.
- 검증: `test_process_notification_job.py::test_pubsub_endpoint_acks_and_queues`.

### `POST /sources/{id}/sync` (수동 재동기화)
- **[정상]** run_type(delta/full) 요청 → 해당 job 큐잉 → 202. **[멱등]** 진행 중 같은 source sync 있으면 lock으로 직렬화, 중복 job은 idempotency로 차단. **[권한]** 세션 workspace ≠ source workspace → 403(또는 존재 노출 방지 404). **[선행조건]** `disconnecting`/`disconnected`/`paused` → 409.

---

## 워크트리 격리 노트

- 마이그레이션: `0004_mail_intake_snapshot`(down `0003_mail_sources`, 테이블 `gmail_messages`/`message_excerpts`/`gmail_message_labels`)와 `0005_mail_intake_sync`(down `0004_mail_intake_snapshot`, 테이블 `gmail_sync_cursors`/`gmail_watch_registrations`/`gmail_notification_events`/`sync_runs`) 두 개로 분리(§integration §1). Task 4가 `0004`, Task 5가 `0005`. mail_sources(`0003`) 머지 후 순서대로 머지.
- snapshot upsert key는 db-schema를 따라 `(connected_account_id, gmail_message_id)`. Task 4가 `(source_id, gmail_message_id)`로 표기한 `source_id`는 `connected_account_id`의 다른 이름 — 컬럼명은 `connected_account_id` 고정.
- reader 자격증명 주입: mail_sources가 credential 핸들 제공 인터페이스를 먼저 노출해야 한다. 미제공 시 `fake_reader`로 계약 테스트 진행(Task 4는 live 없이 통과가 Gate), live_reader는 mail_sources 머지 후 배선.
- job 계약은 §2 표 고정(`job_type` 문자열·handler 경로·lock_key `source:{source_id}`). event wiring은 §3, status 값은 §5 준수. `EVENT_CONSUMERS`/`JOB_HANDLERS` 노출은 §4 규칙(`__init__.py`).
- 미정 의존: excerpt 길이 상한(LLM 프롬프트 예산, db-schema 열린 결정) → 그 전까지 Gmail `snippet`을 자르지 않고 그대로 저장. Pub/Sub topic·live credential 미준비 → fake notification·fake reader·fallback polling TDD로 G2 통과(module-boundaries 차단 조건 우회).
