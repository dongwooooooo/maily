# labels 세부 플랜 (Labels & Classification)

기준: `module-boundaries.md`(컨텍스트·Command/Event Catalog·흐름 4·불변식), `db-schema.md`(labels 섹션), `_integration-contract.md`(충돌 규약 §1·§3·§4·§5). 대응 Task: 8(라벨 카탈로그·이동 신호).

## 도메인 책임 요약

사용자 라벨(생성/이름변경/숨김/순서), Gmail `Maily/` 라벨 매핑 의도, message move target 검증, 사용자 correction signal 기록. **소유 안 함**: Gmail label 실제 apply(gmail_actions command로 실행), rule suggestion 생성(assistant_decisions), cleanup 승인 큐.

강제 invariant(이 도메인이 지키는 것):
- 사용자가 직접 이동시키는 목적지는 라벨이지 기본 브리핑 섹션이 아니다 — 파생 섹션은 move target으로 허용 안 함.
- 라벨 이름 변경(rename)·숨김·순서 변경이 Gmail 매핑 연결을 끊거나 중복 매핑을 만들지 않는다 — `service_labels` ↔ `gmail_label_mappings` 1:1 안정.
- 실제 Gmail label apply는 이 도메인이 실행하지 않는다 — `gmail_actions` command를 요청한다(labels는 `GmailMutationPort`를 import하지 않는다).
- 계정당 `Maily` 부모 라벨은 정확히 하나 — 자식 `Maily/{name}` 매핑 의도는 부모 존재를 전제로 만든다.

소유 테이블: `service_labels`, `gmail_label_mappings`, `label_correction_signals`.
소유 event(producer): `label_correction_recorded`.
소유 job: 없음(assistant_decisions가 `create_rule_suggestions`를 소비, gmail_actions가 apply command를 실행).

## 매핑 분리 근거 (`service_labels` ↔ `gmail_label_mappings`)

두 테이블을 나눈 이유는 rename 안정성이다. 사용자가 라벨 이름을 바꿔도 Gmail 쪽 라벨과의 연결(`gmail_label_id`)이 끊기면 안 된다.

- `service_labels`: 사용자에게 보이는 이름/순서/숨김. rename은 이 테이블 `name`만 바꾼다.
- `gmail_label_mappings`: Gmail 라벨과의 물리적 연결. `service_label_id` UNIQUE 1:1. `gmail_label_id`는 Gmail에 실제 생성된 뒤 채워진다 — 생성 전엔 null인 채 "생성 의도"만 존재한다(`create_or_update_label` 결과가 "intent"인 이유).
- rename은 새 매핑 row를 만들지 않는다 — 기존 `gmail_label_id`를 그대로 두고 `gmail_label_name`(`Maily/{name}`)만 새 이름을 반영한다. 실제 Gmail rename은 gmail_actions command.

`gmail_message_labels`(mail_intake 소유)는 대조 대상이지 이 도메인의 소유가 아니다 — Gmail이 실제로 갖고 있는 라벨 snapshot이고, gmail_actions apply + intake resync 후 `gmail_label_mappings`와 대조해야 사용자 라벨이 Gmail에 실제 반영됐는지 확인된다. labels는 이 테이블에 쓰지 않는다.

---

## Command: `create_or_update_label`

- 소유 테이블: `service_labels`(insert/update), `gmail_label_mappings`(insert, `gmail_label_id` null)
- 발행 event: 없음(로컬 카탈로그 상태 — 크로스도메인 consumer 없음). 실제 Gmail 생성/rename은 gmail_actions command가 별도로 처리하며 apply 후 `gmail_label_id`를 reconcile.
- 입력 → 결과: `{workspace_id, name, order_index?, hidden?, connected_account_id}` → service label + Gmail mapping intent
- API: `POST /labels`(생성), `PATCH /labels/{id}`(rename/hide/reorder)

체크리스트:
- **[정상]** 신규 라벨 생성 → `service_labels` insert(`workspace_id`, `name`, `order_index`, `hidden=false`, `updated_at`) → `gmail_label_mappings` insert(`service_label_id`, `connected_account_id`, `gmail_label_id=null`, `gmail_label_name='Maily/{name}'`). update는 `service_labels` rename/hidden/order_index만 바꾸고 `updated_at` 갱신 — 매핑 row는 그대로, rename 시 `gmail_label_name`만 새 이름 반영.
- **[멱등]** 같은 값으로 재요청(no-op update) → 변화 없으면 `updated_at`·매핑 변경 없음. 같은 이름 재생성 시도는 UNIQUE로 막고 기존 라벨 반환(신규 매핑 미생성). 계정별 `Maily` 부모 라벨 존재 보장은 idempotent get-or-create라 반복 호출 무해(별도 추적 컬럼 없음).
- **[동시]** 같은 workspace+이름으로 두 생성 요청 동시 → UNIQUE `(workspace_id, name)`가 두 번째 insert를 DB 레벨에서 거부(IntegrityError) → 두 번째는 기존 라벨 조회로 폴백. `gmail_label_mappings.service_label_id` UNIQUE가 한 service_label에 매핑 두 개가 붙는 것을 막는다 → 중복 Gmail 매핑 불가.
- **[선행조건]** `workspace_id` 부재/세션 불일치 → 401/403(§권한). `name` 빈 문자열/공백만 → 422(라벨은 fallback 이름이 없다 — mail_sources와 다름). `connected_account_id`가 활성 계정이 아님(`disconnected`/`disconnecting`) → 422, 매핑 생성 거부.
- **[부분실패]** `service_labels` insert 성공·`gmail_label_mappings` insert 실패 → 전체 트랜잭션 롤백(라벨+매핑은 한 트랜잭션) → 라벨만 있고 매핑 없는 상태 불가. Gmail 실제 생성은 gmail_actions apply의 별도 트랜잭션 → 매핑 커밋 후 프로세스가 죽어도 매핑 intent는 남아 재기동 후 apply가 `gmail_label_id`를 채운다.
- **[권한]** 세션 workspace ≠ 라벨 workspace → 403. 타 workspace 라벨 조회·수정 불가(`workspace_id` 직접 컬럼으로 스코프).
- **[데이터경계]** `hidden=true` 처리해도 `gmail_label_mappings` row·`gmail_label_id`는 유지(삭제 아님 — 목록에서만 숨김). `gmail_label_id`가 아직 null인(생성 전) 라벨도 조회·rename 허용, 응답에 "intent" 상태로 노출. rename을 반복해도 새 매핑 row 미생성.
- 검증: `tests/domains/labels/test_label_catalog.py::{test_create_label_creates_mapping_intent, test_rename_keeps_gmail_mapping, test_reorder_hide_no_duplicate_mapping, test_duplicate_name_rejected, test_mapping_id_null_before_apply}`.

## Command: `move_message_to_label`

- 소유 테이블: `label_correction_signals`(insert)
- 발행 event: `label_correction_recorded` (idempotency `message:{message_id}:label:{label_id}:correction:{version}`) — version은 같은 `(message_id, service_label_id)` 조합의 correction 발생 순번. `label_correction_signals`는 move마다 새 row(append-only)이며, 그 순번이 disambiguator다(임의 UUID 미사용).
- 후속: `gmail_actions` label apply command 요청(`request_gmail_action`, add_label_ids=`Maily/{name}`) + assistant_decisions `create_rule_suggestions` 큐잉(§integration §3)
- 입력 → 결과: `{message_id, label_id, actor_id, Idempotency-Key}` → correction signal + label_correction_recorded event + Gmail label apply command 요청
- API: `POST /messages/{id}/move`

체크리스트:
- **[정상]** 유효한 사용자 라벨로 이동 → `label_correction_signals` insert(`message_id`, `service_label_id`, `actor_id`) → outbox `label_correction_recorded` 1건 → gmail_actions에 label apply command 요청(gmail_actions가 command ledger·`GmailMutationPort` 담당). labels는 Gmail을 직접 호출하지 않는다.
- **[멱등]** 같은 move 재요청(네트워크 재시도) → 클라이언트 `Idempotency-Key`(사용자 트리거 액션이라 클라이언트 결정 키)로 dedupe → 새 signal·event·command 미생성, 이전 결과 반환. 실제로 다른 시점의 재분류(같은 라벨로 다시 이동)는 새 version → 새 event(정상적으로 별개 correction).
- **[동시]** 같은 message에 서로 다른 라벨로 두 move 동시 → 각각 append-only signal 기록, 각자 version으로 event dedupe 유지. gmail_actions 쪽 apply는 command idempotency로 마지막 상태가 Gmail에 반영(순서는 command ledger가 관리). 동일 move 동시 중복은 `Idempotency-Key`가 두 번째를 흡수.
- **[선행조건 / negative]** `label_id`가 사용자 `service_labels`가 아니라 기본 브리핑 파생 섹션을 가리키면 → **422 거부**(사용자 이동 목적지는 라벨뿐, 파생 섹션 직접 이동 금지 invariant). `message_id` 부재/타 workspace → 404. 라벨이 `disconnected` 계정에 속함 → 422.
- **[부분실패]** signal insert·outbox `label_correction_recorded` append는 한 트랜잭션 → signal만 있고 event 없음/event만 있고 signal 없음 불가. gmail_actions command 요청은 별도 command(자체 idempotency_key) → signal 커밋 후 프로세스 사망해도 재기동 시 재요청(at-least-once), Gmail에 중복 apply 안 남(command idempotency).
- **[권한]** 타 workspace message move → 403. `actor_id`는 correction signal 신뢰도 판단·audit용으로 기록(자동 규칙 vs 실제 사용자 행동 구분).
- **[데이터경계]** `hidden=true` 라벨도 move target으로 허용(숨김은 사이드바 표시만 제어). `gmail_message_labels`(intake 소유)는 labels가 절대 쓰지 않는다 — Gmail 반영 여부는 gmail_actions apply + intake resync 후 대조로만 확인. correction signal은 purge 전까지 보존(assistant rule 근거 추적).
- 검증: `tests/domains/labels/test_label_move_signal.py::{test_move_records_signal_and_emits, test_move_requests_gmail_apply_command, test_move_to_default_section_rejected, test_move_idempotent_by_key, test_move_cross_workspace_forbidden}`.

## Event: `label_correction_recorded`

- producer: labels
- payload owner: labels
- idempotency: `message:{message_id}:label:{label_id}:correction:{version}`
- consumer: assistant_decisions(`create_rule_suggestions`, payload `{correction_signal_id}`)
- 발행 조건: `move_message_to_label` 성공 시 1건.
- 경계: labels는 신호만 기록·발행한다. rule suggestion 생성·승인 큐·자동 규칙 판단은 assistant_decisions 소유다. gmail_actions 쪽 apply command 요청은 이 event가 아니라 `request_gmail_action` command로 직접 이뤄진다(§integration §3 표에 label_correction_recorded → gmail_actions wiring 없음 — 의도된 분리).

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /labels` (라벨 목록)
- **[정상]** workspace의 라벨 목록 + `order_index` 정렬 + `hidden` 플래그 + 매핑 상태(`gmail_label_id` null이면 intent, 값 있으면 Gmail 반영됨).
- **[필터]** `hidden=true` 라벨은 기본 제외(사이드바 계약), 명시 조회 시 포함. 정렬은 `order_index` 오름차순.
- **[빈상태]** 라벨 0개 → 빈 배열(에러 아님).
- **[권한]** 세션 workspace 스코프만. 타 workspace 라벨 미노출.
- 검증: `test_label_catalog.py::test_list_labels_scoped_and_ordered`.

`POST /labels`·`PATCH /labels/{id}`는 `create_or_update_label` command 엔드포인트(위 command 참조).

---

## 워크트리 격리 노트

- 마이그레이션: `0006_labels`(down `0005_mail_intake_sync`). mail_intake 두 마이그레이션(`0004`·`0005`) 머지 후 머지. `service_labels`·`gmail_label_mappings`·`label_correction_signals` 3개 테이블 생성. `alembic revision --autogenerate` 금지, 슬러그 수동 작성(§integration §1).
- FK 의존: `label_correction_signals.message_id` → `gmail_messages`(mail_intake `0004`), `.actor_id` → `users`(identity `0002`). `gmail_label_mappings.connected_account_id` → `connected_gmail_accounts`(mail_sources `0003`). 로컬 테스트는 필요한 상위 테이블만 있으면 진행 가능.
- 도메인 노출 인터페이스(§integration §4): `app/domains/labels/__init__.py`에 `router`, `JOB_HANDLERS={}`(job 없음), `EVENT_CONSUMERS={}`(소비 없음), `PURGE_HANDLER=purge(source_id)`(Task 13 — 해당 source content에 묶인 correction signal·매핑 정리).
- gmail_actions command 요청 경로는 `request_gmail_action`(§integration §2 `execute_action` 트리거). labels 워크트리는 gmail_actions 미머지 상태에서 fake command port로 계약 테스트 진행, 실 wiring은 gmail_actions(`0007`) 머지 후 교체.
- 라이브 POC 확인(db-schema, 2026-07-09): 계정당 `Maily` 부모 라벨 get-or-create는 `labels.list` 후 없으면 생성하는 idempotent 호출로 충분 — 추적 컬럼 없음. 부모 생성 전 자식은 flat 표시, 부모 생성 후 소급 중첩.
