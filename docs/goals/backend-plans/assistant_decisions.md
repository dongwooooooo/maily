# assistant_decisions 세부 플랜 (Assistant Decisions)

기준: `module-boundaries.md`(컨텍스트 F04 중요도·F08·F10·F12, 흐름 2 후반부, 흐름 6, invariant "summary off·최소 LLM payload·approve-one-only"), `db-schema.md`(assistant_decisions 섹션), `_integration-contract.md`(§1 마이그레이션 `0010_assistant_eval`·`0011_assistant_rules`, §2 job 계약, §3 router prefix·event wiring, §5 status). 대응 Task: 10(요약·중요도 평가), 11(규칙·정리 검토).

## 도메인 책임 요약

요약 job/result, importance classification job/result(band·판단 이유), 최소 LLM payload 정책, rule suggestion, active classification rule, cleanup proposal, confidence band, 승인/제외 큐, 자동 적용 기준. **소유 안 함**: OAuth token(mail_sources), Gmail API 직접 호출·command ledger schema(gmail_actions), snapshot 갱신(mail_intake), 브리핑 섹션 배치(briefing).

강제 invariant(이 도메인이 지키는 것):
- summary/importance는 **별도 job·별도 테이블**(`summary_jobs`↔`importance_jobs`, `message_summaries`↔`message_importance_classifications`). job_type이 다르면 독립 row라 한쪽 실패/재시도가 다른 쪽을 막지 못한다.
- LLM payload는 최소만 — subject/sender/snippet/labels/limited excerpt. raw body·raw prompt는 어떤 테이블에도 저장 안 함. 감사는 payload 필드 **목록**만 앱 로그(DB 아님).
- 판단 결과(band·reason)는 event payload 필드로만 구분. band별로 event 종류·테이블을 늘리지 않는다.
- summary_enabled off면 `generate_summary` job 자체를 만들지 않는다(metadata-only fallback). importance는 설정과 무관하게 항상 평가.
- importance 대기중은 `message_importance_classifications`에 row 없음으로 표현. 별도 pending 플래그 없음.
- cleanup 승인은 **한 번에 하나만**(approve-all 엔드포인트 없음). 자동화 판단(assistant)과 Gmail 실행(gmail_actions)은 분리 — 승인은 gmail_actions command를 요청할 뿐 Gmail을 직접 호출하지 않는다.

소유 테이블: `summary_jobs`◆, `message_summaries`◆, `importance_jobs`◆, `message_importance_classifications`◆, `classification_rules`◆, `rule_suggestions`◆, `cleanup_proposals`◆.
소유 event(producer): `summary_completed`, `importance_classified`, `cleanup_proposal_created`, `rule_suggestion_created`.
소유 job: `generate_summary`, `classify_importance`, `create_rule_suggestions`, `prepare_cleanup_proposals`.

## job/status 전이

값 집합은 `_integration-contract.md §5` 고정.

- `summary_jobs.status` / `importance_jobs.status`: `queued`→`running`→`succeeded` 또는 `failed`. 두 job은 서로의 상태를 참조하지 않는다.
- `rule_suggestions.status`: `pending`→`approved` 또는 `rejected`. approved만 `classification_rules`(active=true)로 옮겨진다.
- `cleanup_proposals.status`: `pending`→`approved`→`applied` 또는 `pending`→`rejected`. `applied`은 gmail_actions command 완료 확인 후.
- confidence_band(`auto-apply`/`approval-required`/`silent`) 경계값·importance_band 값 집합은 `db-schema.md [미정]` — LLM POC 실측 전까지 `fake_llm` 계약 상수로만 참조.

---

## Job: `generate_summary`

- 소유 테이블: `summary_jobs`(insert/status), `message_summaries`(upsert)
- 발행 event: `summary_completed` (idempotency `message:{message_id}:summary:{summary_version}`)
- trigger: `gmail_snapshot_changed` (단, `summary_enabled` 시에만 큐잉 — dispatcher가 설정 확인)
- payload: `{message_id}`, lock_key `null`(message 단위, idempotency_key로 충분)
- 입력 → 결과: `{message_id}` → summary result 또는 metadata-only state → `summary_completed`
- consumer: briefing(해당 message_id 부분 재생성)

체크리스트:
- **[정상]** snapshot 존재 + summary_enabled=true → `summary_jobs` `queued`→`running` → LLM 호출(payload=subject/sender/snippet/labels/limited excerpt) → `message_summaries` upsert(`summary_text`, `is_metadata_only=false`, `summary_version+1`, `model_name`) → job `succeeded` → outbox `summary_completed`(disambiguator=summary_version).
- **[멱등]** 같은 `(job_type, idempotency_key)` 재큐잉 → UNIQUE로 중복 job 거부. 같은 snapshot_version에 대한 재실행은 `message_summaries` upsert(1메시지 1요약, `message_id` unique)라 row 하나만 유지, summary_version은 실제 재요약 시에만 증가. event도 같은 summary_version이면 outbox dedupe(`(event_type, idempotency_key)`).
- **[동시]** 같은 message에 두 `generate_summary` 동시 → lock_key null이지만 `message_summaries.message_id` unique + job idempotency_key가 중복 결과를 막는다. summary와 importance 동시 실행은 정상(별도 테이블·별도 job이라 간섭 없음).
- **[선행조건]** summary_enabled=false → **job 자체를 만들지 않는다**(dispatcher가 `gmail_source_settings` 확인 후 큐잉 스킵). 이 경우 `message_summaries`는 `is_metadata_only=true`, `summary_text=null`로만 존재하거나 아예 row 없음 — UI는 이 필드로 fallback 표시 분기(G6). message snapshot 부재 → job 거부(존재 안 하는 메일 요약 금지).
- **[부분실패]** LLM 호출 실패/타임아웃 → job `failed`, `attempt_count+1`, `message_summaries` 미기록. **classify_importance는 영향 없음**(독립 row). 재시도는 이 job만. LLM 응답 수신 후 `message_summaries` write 실패 → job `failed`로 롤백, event 미발행(write와 outbox append는 한 트랜잭션). metadata-only fallback은 실패가 아니라 정상 종료 — LLM 없이 subject 기반 요약 대체.
- **[권한]** N/A(내부 job, 사용자 컨텍스트 없음). workspace 스코프는 `message_id`→snapshot→`connected_account_id`→workspace로 제한.
- **[데이터경계]** raw body·raw prompt 미저장 — `message_summaries`에 body/prompt 컬럼 없음. 감사 필요 시 payload 필드 목록(subject/sender/snippet/labels/excerpt)만 앱 로그로 남기고 값은 남기지 않는다. excerpt 길이 상한은 `message_excerpts`가 이미 제한(mail_intake 소유), 이 도메인은 받은 값만 payload에 싣는다.
- 검증: `tests/domains/assistant_decisions/test_summary_privacy.py::{test_summary_off_makes_no_job, test_metadata_only_fallback, test_raw_body_and_prompt_never_persisted, test_summary_completed_emitted_with_version}`.

## Job: `classify_importance`

- 소유 테이블: `importance_jobs`(insert/status), `message_importance_classifications`(upsert)
- 발행 event: `importance_classified` (idempotency `message:{message_id}:importance:{classification_version}`)
- trigger: `gmail_snapshot_changed` (설정 무관, 항상 큐잉)
- payload: `{message_id}`, lock_key `null`
- 입력 → 결과: `{message_id, snapshot signals}` → importance classification(band, reason) → `importance_classified`
- consumer: briefing(해당 message_id 부분 재생성)

체크리스트:
- **[정상]** snapshot 존재 → `importance_jobs` `queued`→`running` → LLM 호출(최소 payload) → `message_importance_classifications` upsert(`importance_band`, `reason`, `classification_version+1`) → job `succeeded` → outbox `importance_classified`(disambiguator=classification_version). band는 payload 필드로만 구분 — `urgent`/`normal` 결과가 서로 다른 event 종류를 만들지 않는다.
- **[멱등]** 재큐잉 → job UNIQUE `(job_type, idempotency_key)`로 거부. `message_id` unique라 재판단해도 row 하나. 같은 classification_version이면 event outbox dedupe.
- **[동시]** 같은 message에 generate_summary와 classify_importance 동시 → **완전 독립 실행**. 한쪽 running/failed가 다른 쪽 스케줄·상태에 영향 없음(별도 job_type, 별도 테이블). 같은 classify 두 개 동시 → `message_importance_classifications.message_id` unique로 결과 하나만.
- **[선행조건]** message snapshot 부재 → job 거부. summary_enabled와 무관 — 요약을 꺼도 중요도 판단은 돈다(중요도는 브리핑 정렬 근거, 개인정보 노출 아님). 판단 전 상태는 `message_importance_classifications`에 **row 없음**으로 표현, 별도 pending 컬럼 안 만듦(흐름 2 "아이템 단위 대기 상태 금지", 계정 `syncing`으로만 안내).
- **[부분실패]** LLM 실패 → job `failed`, `attempt_count+1`, classification row 미기록. **generate_summary 영향 없음**. 재시도는 이 job만. row 없는 상태가 곧 "판단 전"이라 실패와 미착수가 UI상 같게 보임(의도 — 아이템 단위 대기 표시 안 함).
- **[권한]** N/A(내부 job). workspace 스코프는 message→account→workspace.
- **[데이터경계]** raw body/prompt 미저장(job·result 테이블 모두 LLM payload 컬럼 없음). `reason`은 저장하되 API 응답 기본값에서 제외(최상위 원칙 "AI 판단 이유는 기본으로 노출하지 않는다") — 필요 시에만 노출. importance_band 값 집합 `[미정]`이라 실제 band 문자열은 `fake_llm` 계약 상수로 검증.
- 검증: `tests/domains/assistant_decisions/test_classify_importance_job.py::{test_importance_independent_of_summary, test_pending_is_absent_row_not_flag, test_band_and_reason_persisted, test_reason_hidden_by_default}`.

## Command: `create_rule_suggestion` (job `create_rule_suggestions`)

- 소유 테이블: `rule_suggestions`(insert), `classification_rules`(승인 시 insert)
- 발행 event: `rule_suggestion_created` (idempotency `rule-suggestion:{suggestion_id}:created`)
- trigger: `label_correction_recorded`(labels) → job `create_rule_suggestions` payload `{correction_signal_id}`, lock_key `null`
- 입력 → 결과: `{correction_signal_id}` → pending rule suggestion → `rule_suggestion_created`
- 승인 API: `POST /rules/{id}/approve`
- consumer: briefing(구독)

체크리스트:
- **[정상]** correction signal 도착(사용자가 반복 라벨 이동) → 발신자/제목 패턴 추출 → `rule_suggestions` insert(`suggested_condition` jsonb, `status='pending'`, `correction_signal_id` FK) → outbox `rule_suggestion_created`. 승인(`POST /rules/{id}/approve`) 시에만 `classification_rules` insert(`active=true`) → suggestion `status='approved'`, `decided_at` 세팅. **승인 전까진 active 규칙 아님**(F08 승인/제외 큐).
- **[멱등]** 같은 correction_signal_id로 job 재실행 → 이미 pending suggestion 있으면 중복 insert 안 함(신호당 제안 하나). 같은 suggestion 재승인 → 이미 `approved`면 no-op(추가 `classification_rules` insert 없음). event는 `rule-suggestion:{suggestion_id}:created`로 dedupe.
- **[동시]** 같은 signal로 두 job 동시 → correction_signal_id 기준 조회+insert 경합은 `(correction_signal_id)` 조건 확인으로 하나만 pending 생성. approve와 reject 동시 → 먼저 커밋된 결정이 이김, 두 번째는 `status<>'pending'` 선행조건 위반으로 409.
- **[선행조건]** correction_signal 부재 → job 거부. reject된/이미 approved된 suggestion을 다시 approve → 409(pending만 승인 가능). 매칭 조건이 비었거나 패턴 추출 불가 → suggestion 미생성(빈 규칙 방지).
- **[부분실패]** `rule_suggestions` insert 성공·outbox append 실패 → 롤백(한 트랜잭션). 승인 시 `classification_rules` insert 성공·suggestion status update 실패 → 롤백(승인은 원자적, active 규칙만 있고 승인 흔적 없는 상태 불가).
- **[권한]** `POST /rules/{id}/approve`는 세션 workspace 스코프 — 타 workspace suggestion 승인 → 403. correction signal의 `actor_id`는 신뢰도 계산 참고용으로만.
- **[데이터경계]** suggestion·rule 모두 `workspace_id`로 스코프. 다른 workspace의 label/signal 참조 금지. 원본 메일 body는 참조 안 함 — 패턴은 subject/sender에서만 추출.
- 검증: `tests/domains/assistant_decisions/test_rule_suggestions.py::{test_correction_creates_pending_suggestion, test_only_approved_becomes_active_rule, test_reapprove_is_noop, test_approve_scoped_to_workspace}`.

## Job: `prepare_cleanup_proposals`

- 소유 테이블: `cleanup_proposals`(insert)
- 발행 event: `cleanup_proposal_created` (idempotency `message:{message_id}:cleanup:{proposal_version}`)
- trigger: `gmail_snapshot_changed` → job payload `{workspace_id, message_ids?}`, lock_key `null`
- 입력 → 결과: 낮은 확신 정리 후보 → pending proposal(승인 큐) 또는 auto-apply/ silent 분기
- consumer: notifications(`emit_notification`)

체크리스트:
- **[정상]** snapshot 변경 → 정리 후보 판정 → `confidence_band` 산정 → `cleanup_proposals` insert(`proposed_action`은 `gmail_action_commands.action_type`과 동일 값 집합, `before_state`/`after_state` jsonb, `status='pending'`) → outbox `cleanup_proposal_created`. band별 분기: `auto-apply`는 즉시 gmail_actions command 요청(승인 큐 미노출), `approval-required`는 승인 큐로, `silent`는 제안 자체를 만들지 않는다.
- **[멱등]** 같은 message에 재실행 → `message:{message_id}:cleanup:{proposal_version}`로 outbox dedupe. 같은 후보 중복 proposal 방지(message+action 기준 pending 하나).
- **[동시]** 두 job 동시(같은 workspace) → message 단위로 proposal이 갈려 충돌 없음. auto-apply 분기와 사용자의 수동 action 동시 → gmail_actions command ledger의 idempotency로 이중 실행 방지(assistant는 command 요청만).
- **[선행조건]** snapshot 부재 → 후보 없음. `confidence_band` 경계값 `[미정]`이라 auto-apply/approval-required/silent 분기는 `fake_llm` 계약 상수로만 판정(실측 전 임의 임계값 금지).
- **[부분실패]** proposal insert 성공·outbox append 실패 → 롤백. auto-apply 분기에서 gmail_actions command 요청 실패 → proposal은 `pending` 유지(자동 적용 미완, 재시도 대상), Gmail 직접 호출은 하지 않으므로 부분 mutation 없음.
- **[권한]** N/A(내부 job). workspace 스코프는 payload `workspace_id` + 각 message의 account→workspace 일치 검증.
- **[데이터경계]** `before_state`/`after_state`는 라벨/읽음 상태 같은 메타만 — raw body 미포함. 다른 workspace 메일 대상 proposal 생성 금지.
- 검증: `tests/domains/assistant_decisions/test_cleanup_review.py::{test_confidence_band_routes_proposal, test_silent_makes_no_proposal, test_proposal_before_after_no_raw_body}`.

## Command: `approve_cleanup_proposal`

- 소유 테이블: `cleanup_proposals`(status→approved→applied, `gmail_action_command_id` 세팅)
- 후속: gmail_actions command 요청(승인 시), 실행은 gmail_actions 소유
- 입력 → 결과: `{proposal_id, actor_id}` → proposal approved + Gmail command 요청
- API: `POST /cleanup/{id}/approve`

체크리스트:
- **[정상]** 승인 큐(=`approval-required` band의 `pending` proposal)에서 단건 승인 → `status='approved'`, `decided_at` 세팅 → gmail_actions command 요청(`gmail_action_command_id` FK 연결) → command 적용 확인 후 `status='applied'`. **assistant는 Gmail을 직접 호출하지 않는다** — command ledger를 거친다(경계 설계 원칙).
- **[멱등]** 같은 proposal 재승인 → 이미 `approved`/`applied`면 no-op(추가 command 요청 없음). gmail_actions command는 클라이언트 idempotency_key로 이중 mutation 방지.
- **[동시]** approve와 reject 동시 → 먼저 커밋된 결정이 이김, 두 번째는 `status<>'pending'` 위반으로 409. 두 사용자가 같은 proposal 동시 승인 → status 전이 경합에서 하나만 성공, command도 한 번만 요청.
- **[선행조건]** `pending`이 아닌 proposal 승인 → 409. `silent`/`auto-apply` band proposal은 승인 큐에 없음 — 승인 큐는 `approval-required`만(§도메인 책임). proposal 부재 → 404.
- **[부분실패]** status update 성공·gmail_actions command 요청 실패 → proposal `approved` 유지, command 미연결(`gmail_action_command_id=null`), 재요청 대상. Gmail 직접 실행 안 하므로 부분 mutation 없음. `applied` 확정은 command 성공 event 확인 후에만.
- **[권한]** 타 workspace proposal 승인 → 403. `actor_id`는 activity/audit 표시용.
- **[데이터경계]** **approve-all 엔드포인트 없음**(negative — 한 번에 하나만 승인). 벌크 승인 요청 경로 자체를 제공하지 않는다. proposal은 `workspace_id` 스코프.
- 검증: `tests/domains/assistant_decisions/test_cleanup_review.py::{test_approve_one_requests_command_not_gmail, test_no_approve_all_endpoint, test_approve_only_pending_approval_required, test_approve_scoped_to_workspace}`.

## Event 발행 목록 (producer=assistant_decisions)

| event_type | idempotency key | disambiguator 근거 | consumer |
|---|---|---|---|
| `summary_completed` | `message:{message_id}:summary:{summary_version}` | `message_summaries.summary_version` | briefing(message_id 부분 재생성) |
| `importance_classified` | `message:{message_id}:importance:{classification_version}` | `message_importance_classifications.classification_version` | briefing(message_id 부분 재생성) |
| `cleanup_proposal_created` | `message:{message_id}:cleanup:{proposal_version}` | proposal 버전 | notifications(`emit_notification`), briefing |
| `rule_suggestion_created` | `rule-suggestion:{suggestion_id}:created` | suggestion id(전이 없음) | briefing(구독) |

band·reason은 event payload 필드로만 구분 — 결과별로 event 종류를 늘리지 않는다.

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /rules` (규칙 후보 + active 규칙)
- **[정상]** workspace의 `rule_suggestions`(pending) + `classification_rules`(active) 조회. suggested_condition/match_condition 표시.
- **[필터]** `rejected` suggestion 제외(기본). active=false 규칙은 별도 표기.
- **[빈상태]** 후보·규칙 0개 → 빈 배열(에러 아님).
- **[권한]** 세션 workspace 스코프만.
- 검증: `test_rule_suggestions.py::test_list_rules_scoped`.

### `GET /cleanup` (정리 검토 큐)
- **[정상]** `approval-required` band의 `pending` proposal만(승인 큐). before/after state 미리보기 포함.
- **[필터]** `auto-apply`/`silent`/`approved`/`rejected`는 큐에서 제외. approve-one-only이므로 벌크 액션 필드 미제공.
- **[빈상태]** 대기 proposal 0개 → 빈 배열.
- **[권한]** 세션 workspace 스코프. 응답에 raw body·reason 원문 미포함(reason은 기본 노출 안 함).
- 검증: `test_cleanup_review.py::test_list_cleanup_only_approval_required`.

## fake_llm 계약

LLM provider·임계값 미확정 → `assistant_decisions/fake_llm.py`가 결정론적 계약을 제공한다(모듈 boundaries "fake LLM client, confidence band, privacy test 먼저 고정").

- `generate_summary`: 입력 payload 필드(subject/sender/snippet/labels/excerpt)만 받아 고정 규칙으로 요약 문자열 생성. raw body/prompt 입력 자체를 받지 않는 시그니처 — 저장 금지 불변식을 인터페이스로 강제.
- `classify_importance`: 고정 매핑으로 `importance_band` + `reason` 반환. band 값은 `[미정]`이라 fake 상수(`fake_band_urgent` 등)로만 참조, product 등급 확정 시 교체.
- `prepare_cleanup_proposals`: 고정 confidence_band 산정. 경계값 `[미정]`이라 fake 임계값으로 auto-apply/approval-required/silent 분기 검증. LLM POC 실측 후 db-schema `[미정]` 해소 시 교체.
- 실 LLM은 core/provider 슬라이스가 확정한 뒤 fake와 동일 인터페이스로 교체 — 계약 테스트는 fake·live 공통.

## 워크트리 격리 노트

- 마이그레이션 2개: `0010_assistant_eval`(down `0009_briefing_state`, 생성 `summary_jobs`·`message_summaries`·`importance_jobs`·`message_importance_classifications`), `0011_assistant_rules`(down `0010_assistant_eval`, 생성 `classification_rules`·`rule_suggestions`·`cleanup_proposals`). `_integration-contract.md §1` 슬러그·down_revision 고정, autogenerate 금지. labels(`0006`)·gmail_actions(`0007`) 머지 후 머지 — `rule_suggestions`가 `label_correction_signals`, `cleanup_proposals`가 `gmail_action_commands`를 참조.
- `_integration-contract.md §2` job 계약(job_type 문자열·handler 경로), §3 router prefix(`/rules`, `/cleanup`)·event wiring, §5 status 값 준수. message 평가 job(`generate_summary`, `classify_importance`)은 `lock_key=null`(§2).
- `EVENT_CONSUMERS`: `gmail_snapshot_changed`→`generate_summary`(summary_enabled 시)+`classify_importance`+`prepare_cleanup_proposals`, `label_correction_recorded`→`create_rule_suggestions`(§3).
- `PURGE_HANDLER(source_id)`: 해당 source content 소속 summaries/importance/proposals/suggestions 삭제(◆). mail_sources purge 오케스트레이션(Task 13, 흐름 8)의 assistant 단계.
- 미정 의존: `importance_band`·`confidence_band` 값/경계는 db-schema `[미정]` — `fake_llm` 계약 상수로만 진행, LLM provider 확정 시 반영.
