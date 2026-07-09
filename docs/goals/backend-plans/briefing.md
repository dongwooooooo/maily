# briefing 세부 플랜 (Briefing & Item State)

기준: `module-boundaries.md`(컨텍스트 F04·F05·F09·Command/Event Catalog·흐름 2·3, 카드 문법 invariant), `db-schema.md`(briefing 섹션), `_integration-contract.md`(§1 마이그레이션 `0008_briefing_items`·`0009_briefing_state`, §2 job `build_briefing`/`reactivate_reminders`, §3 router prefix·event wiring, §5 `reminders.status`). 대응 Task: 6(브리핑 projection·조회), 7(item state·reminder).

## 도메인 책임 요약

오늘 브리핑 read model, 상세 read model, account grouping + section placement, `seen`/`remind_later` durable state, 보관함 예정 타임라인. **소유 안 함**: Gmail write 실행(gmail_actions), 사용자 라벨 lifecycle(labels), AI 판단 생성(assistant_decisions). 진짜 상태는 `gmail_messages`(snapshot) + `message_summaries` + `message_importance_classifications`이고, 이 도메인은 그것을 조회용으로 합쳐 두는 projection과, projection과 분리된 durable state만 소유한다.

강제 invariant(이 도메인이 지키는 것):
- 브리핑 read model(`briefing_items`)은 언제든 drop-and-rebuild 가능해야 한다. 진짜 상태는 snapshot·summary·importance 원본 테이블에 있다.
- `seen`/`remind_later` durable state는 projection과 분리된다 — `briefing_item_states`는 `briefing_items`가 아니라 `gmail_messages`를 직접 참조한다. projection을 통째로 재생성해도 사용자 상태는 보존된다.
- 카드 응답에는 Gmail mutation action, AI 판단 이유, raw body를 넣지 않는다(흐름 3 카드 문법 보호).
- importance 판단이 안 끝난 메일에 아이템 단위 대기 상태를 만들지 않는다 — 계정 단위 `syncing`으로만 안내한다.
- 재생성은 매번 전체가 아니라 message_id 단위 부분 upsert다(`(connected_account_id, message_id)`).

소유 테이블: `briefing_items`◆, `briefing_item_states`◆, `reminders`.
소유 event(producer): `briefing_item_state_changed`, `reminder_reactivated`.
소유 job: `build_briefing`, `reactivate_reminders`.

## reminder 상태 전이 (`reminders.status`)

값 집합은 `_integration-contract.md §5` 고정(`pending`, `reactivated`, `cancelled`). 전이:

```
(신규 schedule_reminder)
  → pending              remind_at 미도래, job 폴링 대상
pending
  → reactivated          reactivate_reminders가 due 픽업 → reminder_reactivated 발행
  → cancelled            사용자가 remind_later 해제(set_item_seen 등으로 대체)
```

전이 규칙:
- `reactivated`/`cancelled`는 종료 상태 — 다시 `pending`으로 돌아가지 않는다. 같은 메일을 다시 나중에 처리하려면 새 `reminders` row.
- `reminders.status`는 job 폴링 필터일 뿐 사용자 노출 상태가 아니다. 사용자 관점의 durable state는 `briefing_item_states.remind_later_at`이 근거다.

## projection vs durable state 경계

| 구분 | 테이블 | 재생성 | 참조 대상 | 근거 |
|---|---|---|---|---|
| projection | `briefing_items` | drop-and-rebuild 가능 | `gmail_messages`(message_id) | 진짜 상태는 snapshot·summary·importance |
| durable state | `briefing_item_states` | 보존(재생성 대상 아님) | `gmail_messages`(message_id) 직접 | projection을 통째로 지워도 seen/remind_later 유지 |
| reminder queue | `reminders` | 보존 | `briefing_item_states`(briefing_item_state_id) | 재활성화 job 전용 폴링 대상 |

`briefing_items.section` 값 집합은 **[미정]**(db-schema 열린 결정 — `product-wireframe-final.md` 카드 섹션 표 확인 필요). 확정 전까지 이 도메인은 `fake_section` 계약 상수로만 참조한다. `importance_band`도 동일하게 assistant_decisions의 [미정] 값을 그대로 denormalize할 뿐, 값 집합을 이 도메인이 정하지 않는다.

---

## Command: `rebuild_briefing`

- 소유 테이블: `briefing_items`(upsert `(connected_account_id, message_id)`)
- 발행 event: 없음(projection 재생성은 read model 갱신일 뿐 — 상태 변화 event는 durable state 쪽에서만 발행). `rebuilt_at` 갱신.
- 입력 → 결과: `{workspace_id, source_id?, message_ids?}` → 재생성된 briefing projection
- 트리거: `build_briefing` job(§job) — API 직접 호출 아님. command는 job 내부 실행 단위.
- 재생성 범위 구분: `message_ids` 지정 시 **부분 rebuild**(해당 message만 upsert), `source_id`만 지정 시 그 계정 전체, 둘 다 없으면 workspace 전체 rebuild.

체크리스트:
- **[정상]** `message_ids=[m1]` 부분 rebuild → `gmail_messages`(snapshot) + `message_summaries` + `message_importance_classifications`를 조회해 m1 한 건만 `briefing_items` upsert(`(connected_account_id, message_id)` 충돌 시 update). `section`(fake 상수)·`importance_band`·`summary_text` denormalize, `rebuilt_at=now()`. 다른 message의 row는 건드리지 않는다.
- **[멱등]** 같은 message_ids로 두 번 rebuild → upsert라 row 수 불변, 값 동일이면 실질 no-op(값이 바뀌었으면 최신 원본 반영). projection 재생성 자체가 멱등 연산 — 몇 번 돌려도 원본에서 같은 결과가 나와야 한다. event 미발행이라 중복 event 걱정 없음.
- **[동시]** 같은 message에 대해 `summary_completed`발 rebuild와 `importance_classified`발 rebuild가 동시 → 둘 다 `(connected_account_id, message_id)` upsert. 마지막 쓰기가 최신 원본을 반영(둘 다 원본 테이블에서 읽으므로 순서 무관하게 수렴). row는 한 벌만 유지.
- **[선행조건]** message가 아직 snapshot에 없음(sync 전) → 그 message_id는 skip(projection에 넣을 원본 없음). importance 결과 없음 → `importance_band=null`로 넣되 아이템 단위 pending row는 만들지 않는다(계정 `syncing`으로만 대기 안내). summary off 계정 → `summary_text=null`(metadata-only).
- **[부분실패]** 여러 message_ids 중 일부 upsert 실패 → 실패 건만 job 재시도 대상, 성공분은 커밋(부분 rebuild는 message 단위 독립). projection이라 일부 누락돼도 다음 rebuild가 복구 — durable state는 별도 테이블이라 영향 없음.
- **[권한]** N/A(내부 job 실행 단위, 사용자 컨텍스트 없음). workspace 스코프는 job payload의 `workspace_id`/`source_id`로 제한 — 다른 workspace의 message는 조회·upsert 대상에서 제외.
- **[데이터경계]** 전체 rebuild(`message_ids` 없음)여도 다른 workspace projection 미삭제 — `WHERE workspace_id=?`로 제한. drop-and-rebuild 시에도 `briefing_item_states`/`reminders`는 대상 아님(생명주기 분리). disconnect purge와 겹칠 때는 purge가 우선(disconnecting source의 message는 rebuild 대상 제외).
- 검증: `tests/domains/briefing/test_partial_rebuild.py::{test_partial_rebuild_single_message, test_rebuild_idempotent, test_rebuild_preserves_item_state, test_full_rebuild_workspace_scoped}`, `test_projection_regenerable.py::{test_drop_and_rebuild_matches_source}`.

## Command: `set_item_seen`

- 소유 테이블: `briefing_item_states`(upsert `message_id`)
- 발행 event: `briefing_item_state_changed` (idempotency `item:{briefing_item_id}:state:{version}`)
- 입력 → 결과: `{briefing_item_id, actor_id}` → durable seen state + state_changed event
- API: (상세/카드에서의 seen 처리 — prefix `/briefing` 하위, 구체 엔드포인트는 카드 UX 계약 따름)

체크리스트:
- **[정상]** 카드/상세를 확인 → `briefing_item_states` upsert(`message_id` unique), `seen=true`·`seen_at=now()`·`updated_at` 갱신 → version+1 → outbox `briefing_item_state_changed`. state row는 `gmail_messages`를 직접 참조하므로 projection과 독립.
- **[멱등]** 이미 `seen=true`인 아이템 재요청 → 값 변화 없으면 version 증가·event 발행 안 함(불필요한 assistant 재평가 방지). state row는 한 벌만 유지(message_id unique).
- **[동시]** 같은 message에 두 seen 요청 동시 → `message_id` unique로 두 번째 insert는 update로 폴백. version optimistic 증가로 event idempotency key가 갈려 dedupe 유지.
- **[선행조건]** `briefing_item_id`가 가리키는 message가 이미 projection에서 사라짐(rebuild 사이) → state는 message_id 기준이라 여전히 기록 가능(projection 부재와 무관). 이것이 durable state를 `gmail_messages` 참조로 둔 이유 — projection 재생성이 seen 기록을 막지 못한다.
- **[부분실패]** state upsert 성공·outbox append 실패 → 한 트랜잭션 롤백. seen 기록과 event는 원자적.
- **[권한]** 타 workspace 아이템 seen 시도 → 403. state row의 `workspace_id`로 스코프.
- **[데이터경계]** projection을 rebuild(drop-and-rebuild)한 직후 seen 상태 조회 → 보존됨(`test_seen_state.py` 핵심). 카드가 새 `briefing_items` row를 얻어도 seen은 message_id로 다시 붙는다.
- 검증: `tests/domains/briefing/test_seen_state.py::{test_seen_upserts_and_emits, test_seen_survives_rebuild, test_noop_seen_no_event, test_seen_scoped_to_workspace}`.

## Command: `schedule_reminder`

- 소유 테이블: `briefing_item_states`(remind_later_at 세팅), `reminders`(insert, status=pending)
- 발행 event: `briefing_item_state_changed` (remind_later 변경도 state 변화) — idempotency `item:{briefing_item_id}:state:{version}`
- 후속: `reactivate_reminders` job이 스케줄로 due를 픽업(별도 스케줄 job, schedule_reminder가 직접 큐잉하지 않음)
- 입력 → 결과: `{briefing_item_id, remind_at}` → reminder row + remind_later durable state
- API: (상세/카드의 "나중에" — prefix `/briefing` 하위)

체크리스트:
- **[정상]** "나중에" + 시각 지정 → `briefing_item_states.remind_later_at=remind_at`·`updated_at` 갱신 → `reminders` insert(`briefing_item_state_id`, `remind_at`, status `pending`) → version+1 → outbox `briefing_item_state_changed`. 이 시점부터 `reactivate_reminders`가 remind_at 도래 시 픽업 대상으로 삼는다.
- **[멱등]** 같은 아이템에 같은 remind_at 재요청 → state 값 변화 없으면 version·event no-op. 단 새 `reminders` row 중복 생성은 막아야 함 — 기존 `pending` reminder가 있으면 remind_at만 갱신(중복 pending row 금지).
- **[동시]** 두 schedule 요청 동시(다른 remind_at) → `briefing_item_states.remind_later_at`은 마지막 쓰기가 이김, `reminders`는 pending 하나로 수렴(기존 pending update). version 증가로 event dedupe.
- **[선행조건]** `remind_at`이 과거 시각 → 거부(422) 또는 즉시 재활성화 대상(정책은 카드 UX 계약 — POC는 거부). 이미 `seen` 처리된 아이템에 remind_later → 허용(seen과 remind_later는 독립 필드).
- **[부분실패]** state update 성공·`reminders` insert 실패 → 한 트랜잭션 롤백. remind_later_at과 reminder row는 원자적으로 같이 생기거나 같이 안 생긴다(state만 세팅되고 job이 픽업할 row 없는 상태 방지).
- **[권한]** 타 workspace 아이템에 reminder → 403. state row `workspace_id` 스코프.
- **[데이터경계]** projection rebuild 후에도 reminder 유지(`reminders`는 재생성 대상 아님). remind_at 도래 후 `reactivated` 상태가 된 reminder에 다시 schedule → 새 pending row(종료 상태는 재사용 안 함, §상태 전이).
- 검증: `tests/domains/briefing/test_reminders.py::{test_schedule_creates_reminder_and_state, test_reschedule_updates_pending, test_past_remind_at_rejected, test_reminder_survives_rebuild}`.

---

## Job: `build_briefing`

- 트리거(§integration §3): `gmail_snapshot_changed`, `summary_completed`, `importance_classified`, `gmail_action_applied`, `gmail_action_undone`, `reminder_reactivated`
- payload: `{workspace_id, source_id?, message_ids?}`, `lock_key = null`(message 단위 upsert는 idempotency로 충분, §integration §2)
- 내부: 트리거 event별로 재생성할 message_id를 결정해 `rebuild_briefing` command 실행. **매번 전체가 아니라 해당 message_id만** 부분 rebuild.

트리거별 재생성 범위:
- `gmail_snapshot_changed` → payload의 변경된 message_ids만 rebuild. snapshot만 반영된 상태(importance 결과 아직 없음)라도 넣되, 아이템 단위 pending 표시 없이 계정 `syncing`으로만 대기 안내.
- `summary_completed` → 해당 message_id 한 건만 부분 rebuild(요약 denormalize 갱신).
- `importance_classified` → 해당 message_id 한 건만 부분 rebuild(importance_band 갱신).
- `gmail_action_applied`/`gmail_action_undone` → 해당 message의 snapshot(is_read/is_archived 등)이 바뀌었으므로 그 message_id rebuild(done 파생 상태 반영).
- `reminder_reactivated` → 재활성화된 message를 브리핑에 다시 올리기 위해 그 message_id rebuild.

체크리스트:
- **[정상]** `summary_completed{message_id=m1}` 수신 → m1 한 건만 `briefing_items` upsert, `summary_text` 갱신, `rebuilt_at` 갱신. 다른 아이템 무변경. 한 메일에 대해 projection은 최소 3번(snapshot 저장·요약 완료·중요도 완료) 재생성될 수 있고 매번 그 message_id만 부분 재생성(흐름 2).
- **[멱등]** 같은 event 재전달(at-least-once) → 같은 message_id upsert라 결과 동일. `job_runs.idempotency_key`로 중복 큐잉 방지, upsert로 중복 실행도 무해.
- **[동시]** 같은 message에 `summary_completed`와 `importance_classified`가 거의 동시 도착 → 두 job 각각 그 message_id upsert. `lock_key=null`이라 동시 실행되지만 둘 다 원본에서 읽어 같은 row에 수렴(summary_text와 importance_band는 서로 다른 컬럼, 최종적으로 둘 다 반영). 마지막 upsert가 두 원본을 다 반영하도록 rebuild가 원본 전체를 재조회.
- **[선행조건]** importance 결과가 아직 없는 상태에서 `gmail_snapshot_changed` → importance_band=null로 rebuild(대기 아이템에 개별 pending row를 만들지 않음, 계정 syncing만). summary_enabled=false 계정 → summary_text=null로 유지(build는 계속 진행).
- **[부분실패]** message_ids 여러 건 중 일부 rebuild 실패 → job `retrying`, 성공분 커밋. 재실행 시 멱등이라 완료분 skip, 미완분만 재시도. projection이라 일부 누락돼도 다음 트리거가 복구.
- **[권한]** N/A(내부 job). workspace 스코프는 payload `workspace_id`/`source_id`로 제한.
- **[데이터경계]** payload에 없는 message는 절대 rebuild 안 함(부분 재생성 보장 — 전체 재생성으로 번지지 않게). disconnecting source의 message_id가 트리거로 와도 rebuild 거부(purge 우선).
- 검증: `tests/domains/briefing/test_build_briefing_job.py::{test_summary_completed_rebuilds_single_message, test_snapshot_changed_no_importance_no_pending_item, test_action_applied_reflects_done_state, test_partial_scope_only, test_job_idempotent}`.

## Job: `reactivate_reminders`

- 트리거: 스케줄(due 스캔) — `_integration-contract.md §2`
- payload: `{}`(due 스캔), `lock_key = null`
- 내부: `reminders WHERE status='pending' AND remind_at <= now()`를 픽업 → 각 reminder를 `reactivated` 전이 + `reactivated_at` 세팅 → `reminder_reactivated` 발행.
- 발행 event: `reminder_reactivated` (idempotency `reminder:{reminder_id}:reactivated:{version}`) → consumer: `build_briefing`(briefing 재생성) + `emit_notification`(notifications).

체크리스트:
- **[정상]** remind_at 도래한 pending reminder 스캔 → status `reactivated`·`reactivated_at=now()` → outbox `reminder_reactivated`(reminder당 1건). build_briefing이 그 message를 브리핑에 다시 올리고, notifications가 알림을 만든다.
- **[멱등]** 같은 스캔이 두 번 돌거나 이미 `reactivated`된 reminder 재조회 → `status='pending'` 필터로 이미 처리된 건 제외. `reactivated_at`이 있으면 재발행 안 함. event idempotency key(`:reactivated:{version}`)로 중복 event dedupe.
- **[동시]** 두 워커가 동시에 due 스캔 → 각 reminder row 업데이트 시 `WHERE status='pending'` 조건부 update로 한쪽만 성공(중복 재활성화 방지). `lock_key=null`이지만 조건부 update가 경쟁을 흡수.
- **[선행조건]** remind_at 미도래 reminder → 픽업 안 함(스캔 필터가 `remind_at <= now()`). `cancelled` reminder → 대상 아님(pending만).
- **[부분실패]** 여러 reminder 중 일부 event append 실패 → 실패분은 다음 스캔에서 재픽업(status가 아직 pending). 성공분은 커밋. reminder별 독립.
- **[권한]** N/A(내부 스케줄 job). 각 reminder는 자기 `briefing_item_state_id`→`workspace_id`로 스코프, cross-workspace 재활성화 없음.
- **[데이터경계]** 다른 workspace reminder를 같이 처리하지 않는다 — 스캔은 전역이되 각 event payload는 해당 reminder의 workspace로 한정. purge된 message의 reminder는 이미 삭제되어 스캔 대상에 없음.
- 검증: `tests/domains/briefing/test_reactivate_reminders_job.py::{test_due_reminder_reactivates_and_emits, test_reactivate_idempotent, test_pending_only_picked, test_concurrent_no_double_reactivate}`.

---

## Read API (briefing 핵심 — command 수준 상세)

브리핑 조회는 이 도메인의 존재 이유이자 프론트 카드 문법을 보호하는 지점이라, 경량이 아니라 command 수준으로 검증한다.

### `GET /briefing/today?scope=all` (오늘 브리핑)

account 그룹 + section 배치. 흐름 3 "returns account-grouped card list".

- **[정상]** workspace의 briefing_enabled 계정별로 그룹핑 → 각 그룹 안에서 section(fake 상수) 배치 → 카드 목록. 카드는 subject/sender/snippet/received_at/importance_band/summary_text/seen 같은 스캔용 최소 필드만. mail_sources source settings·status를 읽어 `syncing` 계정 안내 반영.
- **[필터]** `scope=all`은 전체 계정, `scope={source_id}`는 단일 계정. briefing_enabled=false 계정은 목록에서 제외. seen 아이템 표시 방식은 카드 UX 계약 따름(제외가 아니라 seen 플래그로 전달).
- **[빈상태]** 연결 계정은 있으나 브리핑 대상 message 0개 → 빈 그룹/빈 목록(에러 아님). syncing 중이라 아직 결과 없음도 빈 상태 + 계정 syncing 안내로 구분.
- **[negative — 카드 문법]** 카드 응답에 Gmail mutation action, AI 판단 이유(`reason`), raw body가 **없어야** 함 — 응답 스키마에 해당 필드가 존재하지 않음을 명시적으로 검증(단순 값 null이 아니라 필드 부재). importance는 band만, 이유는 미포함.
- **[권한]** 세션 workspace 스코프만. 타 workspace 카드 미포함. importance 판단 안 끝난 아이템은 계정 syncing으로만 표시, 아이템 단위 pending 필드 없음.
- **[데이터경계]** projection이 오래됐어도(rebuilt_at 과거) 조회는 현재 projection 반환 — 최신성은 build_briefing이 보장. metadata-only(summary off) 계정은 summary_text=null로 전달, 카드가 fallback 렌더.
- 검증: `tests/domains/briefing/test_today_briefing.py::{test_account_grouped_sections, test_card_omits_action_reason_rawbody, test_briefing_disabled_excluded, test_empty_state, test_scoped_to_workspace}`.

### `GET /messages/{id}` (메일 상세 — readonly)

흐름 3 상세 read model. 흐름 5의 Gmail 변경 요청은 gmail_actions로 넘어가고, 상세 자체는 조회 전용.

- **[정상]** Gmail 원문 링크(URL) + 메타(subject/sender/received_at/thread) + excerpt(`message_excerpts`) + summary(있으면) + Gmail 처리 사실(is_read/is_archived에서 파생된 done 표시) 반환. 원문 읽기·답장은 Gmail에서 하도록 URL 제공.
- **[negative — mutation 없음]** 상세 응답에 mark_read/archive/label 같은 mutation action이 **없어야** 함. Gmail 변경은 gmail_actions command로만 — 상세는 read model. raw body도 미포함(excerpt만).
- **[빈상태]** summary 아직 없음 → summary 필드 null(상세는 렌더됨). importance 없음 → band null, 이유는 기본 미노출(최상위 원칙 "AI 판단 이유는 기본으로 노출하지 않는다").
- **[권한]** 타 workspace message → 404(존재 노출 방지). 세션 workspace 스코프.
- **[데이터경계]** disconnecting/purge 중 message → 404 또는 조회 거부(content-bearing purge 대상). excerpt는 raw body가 아닌 제한 발췌만.
- 검증: `tests/domains/briefing/test_message_detail.py::{test_detail_returns_readonly_view, test_detail_has_no_mutation_action, test_detail_omits_reason_by_default, test_detail_cross_workspace_404}`.

### `GET /storage/upcoming` (보관함 예정 타임라인)

F09 보관함 — remind_later 예정 타임라인.

- **[정상]** `reminders`(pending) + `briefing_item_states.remind_later_at`을 오늘/내일/이번주 그룹으로 묶어 반환. 각 그룹 안에서 remind_at 오름차순.
- **[필터]** pending reminder만(reactivated/cancelled 제외). 그룹 경계(오늘/내일/이번주)는 사용자 타임존 기준.
- **[빈상태]** 예정된 remind_later 0개 → 빈 그룹(에러 아님).
- **[negative — 지난 브리핑]** 지난 브리핑(remind_at이 이미 지나 재활성화된 것)은 storage로 반환하지 **않음** — 재활성화되면 오늘 브리핑으로 돌아가지 storage에 남지 않는다. storage는 "앞으로 다시 볼 예정"만.
- **[권한]** 세션 workspace 스코프. 타 workspace reminder 미포함.
- 검증: `tests/domains/briefing/test_storage_upcoming.py::{test_grouped_today_tomorrow_week, test_pending_only, test_past_reactivated_not_in_storage, test_empty_state, test_scoped_to_workspace}`.

---

## 워크트리 격리 노트

- 마이그레이션 2개: `0008_briefing_items`(down `0007_gmail_actions`, Task 6 — `briefing_items`), `0009_briefing_state`(down `0008_briefing_items`, Task 7 — `briefing_item_states`, `reminders`). 자기 down_revision은 `0007`이지만, briefing 로직·테스트는 `gmail_messages`(0004)만 있으면 로컬 개발·테스트 가능하다(요약/중요도는 fake 결과로 대체). 머지 순서는 `_integration-contract.md §1` 표를 따른다 — 로컬에서 상위 테이블만 만들어 개발하되 머지는 표 순서.
- `section`·`importance_band` 값 집합은 db-schema **[미정]** — `fake_section`/`fake_importance_band` 계약 상수로만 참조하고, 확정 시 db-schema [미정] 해소를 반영. 이 도메인 워크트리가 값을 임의로 정하지 않는다.
- summary/importance 원본(`message_summaries`·`message_importance_classifications`, 0010)은 briefing보다 뒤 머지 — briefing 로컬 테스트는 fake 결과 또는 nullable denormalize로 진행. build_briefing은 원본 부재 시 band/summary null로 rebuild.
- `_integration-contract.md §2` job 계약(`build_briefing`/`reactivate_reminders` payload·lock_key)·§3 event wiring(트리거 6종, 발행 event 2종)·§5 `reminders.status` 값 준수. purge handler는 §4 `PURGE_HANDLER(source_id)` 고정 — content-bearing(◆) `briefing_items`·`briefing_item_states` purge, `reminders`는 state 삭제 시 연쇄 정리.
