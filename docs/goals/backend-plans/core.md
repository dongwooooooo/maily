# core 세부 플랜 (Backend Core / 백엔드 실행 기반)

기준: `module-boundaries.md`(경계 설계 원칙·강제 invariant·"공통 실행 기반" 표·Job 배치 원칙·흐름 1~8의 `core outbox` 스텝·POC Gate G0), `db-schema.md`(core 섹션 `outbox_events`/`job_runs`/`idempotency_keys`·멱등성 키 설계), `_integration-contract.md`(충돌 규약 §1~§5). 대응 Task: 1(Backend Core Runtime).

core는 도메인이 아니라 **공통 실행 기반**이다. 소유한 업무 데이터·command·event가 없다. 그래서 "동작 단위"를 도메인처럼 Command/Event로 잡지 않고 core가 제공하는 **메커니즘**으로 잡는다. 각 메커니즘에 exemplar와 동일한 6축을 적용하되, 사용자 컨텍스트가 없는 내부 기반이라 `[권한]`·`[데이터경계]`가 자주 N/A다 — N/A인 축은 이유를 명시한다.

## 도메인 책임 요약

FastAPI app composition, config, DB session/transaction, Redis client, migration runner, outbox envelope append/dispatch, idempotency(서버/클라이언트 두 부류), job dispatch/lock/retry/registry, logging, rate limit, health/ready. **소유 안 함**: 도메인 테이블 schema·lifecycle, event payload schema, 도메인 상태 의미(`module-boundaries.md` 강제 invariant "core는 도메인 데이터 의미와 event payload schema를 소유하지 않는다").

강제 invariant(이 기반이 물리적으로 강제하는 것):
- 모듈 간 side effect는 직접 도메인 service 호출이 아니라 `outbox_events`·`job_runs`·idempotency key를 거친다 — producer는 consumer를 직접 호출하지 않는다.
- 비동기 작업은 반드시 outbox event 또는 job_run row를 가진다(재기동 후 재개 가능).
- outbox dedupe는 `(event_type, idempotency_key)` UNIQUE로 강제. 같은 원인이 두 번 이벤트를 만들어도 row는 하나.
- job 중복 큐잉은 `(job_type, idempotency_key)` UNIQUE, 중복 실행은 `lock_key`+`locked_at` timeout으로 방지.
- core는 도메인 패키지 심볼(`router`/`JOB_HANDLERS`/`EVENT_CONSUMERS`/`PURGE_HANDLER`)을 자동 발견으로만 수집한다 — 도메인 코드를 이름으로 직접 import하지 않는다.

소유 테이블: `outbox_events`, `job_runs`, `idempotency_keys`.
소유 event(producer): 없음 — envelope append/dispatch 메커니즘만 제공, event_type 값은 각 발행 도메인이 소유.
소유 job: 없음 — dispatcher/lock/retry/registry 실행 기반만 제공, job_type 값은 각 handler 도메인이 소유(§2).

## 상태 전이 (`outbox_events.status`, `job_runs.status`)

값 집합은 `_integration-contract.md §5` 고정. core는 이 두 status의 전이 규칙 자체를 소유한다(도메인 status와 달리 실행 기반 소유).

`outbox_events.status`:

```
(append 시)
  → pending              트랜잭션 커밋과 함께 생성, dispatcher 미처리
pending
  → dispatched           consumer job 큐잉 성공, dispatched_at 세팅
  → failed               재시도 소진 후 포기(attempt_count 근거)
failed
  → pending              (재큐잉 정책 있을 시) 재시도 대상 복귀
```

`job_runs.status`:

```
(큐잉 시)
  → queued               (job_type, idempotency_key) UNIQUE 통과 후 생성
queued
  → running              워커가 lock 획득, locked_by/locked_at/started_at 세팅
running
  → succeeded            handler 정상 종료, finished_at 세팅
  → retrying             실패, retry 정책이 재시도 허용(attempt_count < 한도)
retrying
  → running              backoff 후 재픽업(scheduled_at 도래)
running/retrying
  → failed               재시도 한도 초과, 최종 실패
```

전이 규칙:
- `outbox_events`/`job_runs` 모두 pending/queued/retrying 부분집합만 partial index로 조회한다(`db-schema` core §). dispatched/succeeded/failed로 끝난 row는 인덱싱하지 않는다 — 인덱스 크기가 "지금 처리 대기 중인 양"에 비례하게 유지.
- status 값은 §5 집합만 사용. 도메인 워크트리가 새 값을 추가하지 않는다.
- retention/archival은 **[미정 — POC 이후 결정]**(`db-schema` core §).

---

## 메커니즘: Health / Readiness (`GET /health`, `GET /ready`)

- 위치: `app/main.py`(app factory) + `app/api/router.py`
- 책임: 프로세스 생존(`/health`)과 의존성(DB/Redis) 준비 상태(`/ready`)를 JSON body로 분리 응답. POC Gate G0의 첫 통과 기준.
- 입력 → 결과: 요청 없음 → `/health` `{"status": "ok"}`(200), `/ready` DB/Redis probe 결과 JSON.

체크리스트:
- **[정상]** `GET /health` → 200 `{"status": "ok"}`(의존성 확인 없이 프로세스 생존만). `GET /ready` → DB `SELECT 1` + Redis `PING` 성공 시 200, body에 각 의존성 상태 키 포함.
- **[멱등]** 두 엔드포인트 모두 read-only, 상태 변경 없음 — 몇 번 호출해도 동일 응답. N/A(부작용 없음).
- **[동시]** 다수 probe 동시 호출 → 공유 session pool/Redis client에서 처리, 상태 변경 없어 경합 없음. pool 고갈 시 `/ready`는 DB 실패로 응답(아래).
- **[선행조건]** `/ready`는 DB session·Redis client 의존성 주입(`app/api/deps.py`)이 성공해야 probe 가능. config 미로딩 시 app factory 자체가 부팅 실패(§config).
- **[부분실패]** DB down·Redis up(또는 반대) → `/ready`는 503, body에 실패한 의존성만 명시(부분 상태 노출). `/health`는 의존성과 무관하게 200 유지 — liveness와 readiness를 섞지 않는다.
- **[권한]** N/A — health/ready는 인증 없이 인프라(로드밸런서·k8s probe)가 호출. workspace 스코프 없음.
- **[데이터경계]** N/A — 도메인 데이터 미조회. probe는 연결 가능성만 확인하고 실제 row를 읽지 않는다.
- 검증: `tests/core/test_health.py::{test_health_returns_ok}`, `tests/core/test_ready.py::{test_ready_db_redis_ok, test_ready_db_down_returns_503, test_ready_redis_down_reports_failed_dependency}`.

## 메커니즘: Outbox append + dispatch

- 위치: `app/core/outbox.py`(append) + `app/core/jobs/dispatcher.py`(dispatch)
- 책임: 도메인이 다른 도메인 service를 직접 호출하지 않고 이벤트만 커밋하게 하는 물리적 강제 장치. 흐름 1~8의 모든 `core outbox: X` 스텝이 이 메커니즘을 쓴다.
- append 입력 → 결과: `{event_type, producer_domain, payload, idempotency_key}` → `outbox_events` row(status `pending`), 도메인 상태 변경과 **같은 트랜잭션**.
- dispatch 입력 → 결과: `pending` row 스캔 → §3 Event→Consumer 매핑대로 `job_runs` 큐잉 → row `dispatched`.

체크리스트:
- **[정상]** 도메인이 상태 변경 트랜잭션 안에서 `append(event_type, payload, idempotency_key)` 호출 → `pending` row 1건. dispatcher가 `status='pending' ORDER BY created_at` 조회 → §3 매핑의 consumer job을 `job_runs`에 큐잉 → row `dispatched`, `dispatched_at` 세팅.
- **[멱등]** 같은 원인이 append를 두 번 호출(예: 재시도) → `(event_type, idempotency_key)` UNIQUE가 두 번째 insert를 거부 → row 하나 유지. dispatcher 재실행 시 이미 `dispatched`면 재큐잉 안 함. disambiguator는 원인에 이미 존재하는 값(`sync_run_id`, `version` 등, `db-schema` 멱등성 키 설계) — 임의 UUID를 새로 붙이지 않는다.
- **[동시]** 두 워커가 같은 pending row를 동시에 dispatch 시도 → `SELECT ... FOR UPDATE SKIP LOCKED`(또는 status CAS)로 한 워커만 큐잉, 나머지는 skip. consumer job 큐잉은 `(job_type, idempotency_key)` UNIQUE라 중복 큐잉돼도 job row는 하나.
- **[선행조건]** append는 호출 트랜잭션이 열려 있어야 함 — 트랜잭션 밖 append는 도메인 상태와 event 원자성이 깨지므로 금지(session 의존성 필수). event_type은 발행 도메인 소유 값이어야 하며 core는 값 유효성을 판단하지 않는다(`producer_domain`으로 감사만).
- **[부분실패]** 도메인 상태 변경 성공·append 실패 → 전체 트랜잭션 롤백(같은 트랜잭션이므로 event만 남거나 상태만 남는 일 없음). append 커밋 후 dispatcher 실행 전 프로세스 사망 → `pending` row가 남아 재기동 시 dispatch 재개(at-least-once). dispatch 중 consumer 큐잉 실패 → row `pending` 유지·`attempt_count`+1, 재시도 대상.
- **[권한]** N/A — 내부 메커니즘, 사용자 컨텍스트 없음. `producer_domain`은 감사용 기록일 뿐 권한 판단에 안 씀.
- **[데이터경계]** core는 `payload` jsonb를 불투명하게 다룬다 — 내용을 파싱·검증하지 않는다(payload schema는 발행 도메인 소유, 강제 invariant). dispatcher는 §3 매핑 외 임의 consumer를 호출하지 않는다.
- 검증: `tests/core/test_outbox.py::{test_append_dedupes_by_event_type_and_key, test_append_and_domain_change_share_transaction, test_pending_survives_restart_and_dispatches}`, `tests/core/jobs/test_dispatcher.py::{test_dispatch_queues_consumer_jobs, test_dispatch_skips_already_dispatched}`.

## 메커니즘: Idempotency (서버 결정 키 vs 클라이언트 결정 키)

- 위치: `app/core/idempotency.py`(범용 `idempotency_keys` 테이블) + outbox/job 내장 키(`outbox_events.idempotency_key`, `job_runs.idempotency_key`)
- 책임: 두 부류를 섞지 않고 각각 강제(`db-schema` 멱등성 키 설계). 서버 결정 키는 도메인 상태 재생 방지, 클라이언트 결정 키는 사용자 중복 요청 방지.
- 입력 → 결과: 서버 결정 = `{entity_type}:{entity_id}:{semantic_action}:{disambiguator}` → dedupe. 클라이언트 결정 = `Idempotency-Key` 헤더 UUID → `(scope, key)` 저장 + `response_snapshot` 재사용.

체크리스트:
- **[정상]** 서버 결정: outbox/job append 시 도메인이 조합한 키를 그대로 저장, UNIQUE로 재생 방지. 클라이언트 결정: 사용자 요청의 `Idempotency-Key`를 `scope`(도메인/API 네임스페이스)와 함께 `idempotency_keys`에 insert, 최초 처리 후 `response_snapshot` 저장.
- **[멱등]** 클라이언트 결정: 같은 `(scope, key)` 재요청 → 도메인 로직 재실행 없이 저장된 `response_snapshot`을 그대로 반환. 서버 결정: 같은 키 재append → UNIQUE 거부로 no-op. disambiguator는 timestamp 금지(clock skew·동시 쓰기 위험) — int counter(`version` 등) 또는 기존 원인 컬럼(`sync_run_id`, `history_id`).
- **[동시]** 같은 `(scope, key)`로 두 요청 동시 도착 → `(scope, key)` UNIQUE가 두 번째 insert를 DB 레벨에서 거부(IntegrityError) → 두 번째는 기존 row 조회로 폴백해 동일 응답 반환(요청 하나만 실제 처리).
- **[선행조건]** 클라이언트 결정 키는 요청에 `Idempotency-Key` 헤더가 있어야 적용(예: `request_gmail_action`, `db-schema` 흐름 5). 헤더 없는 요청은 이 메커니즘 대상 아님. 서버 결정 키는 disambiguator가 될 컬럼(counter/원인 id)이 엔티티에 존재해야 함.
- **[부분실패]** 최초 요청 처리 중 도메인 로직 성공·`response_snapshot` 저장 실패 → 트랜잭션 롤백(키 저장과 처리 원자적). 같은 key 다른 body 재요청(버그·오남용) → `request_hash` 불일치 감지, 409 또는 충돌 리포트(`db-schema` `idempotency_keys.request_hash`).
- **[권한]** `scope`가 도메인/API 네임스페이스를 분리해 다른 도메인이 같은 key 값을 써도 충돌하지 않는다. core는 scope 값을 신뢰하고 저장할 뿐 호출자 권한을 판단하지 않는다(호출 도메인이 workspace 스코프를 이미 검증).
- **[데이터경계]** `key`는 클라이언트가 보낸 값을 그대로 저장(변조 금지). `expires_at`으로 무기한 저장 방지 — 만료된 키는 재사용 가능. core는 도메인 payload 의미를 해석하지 않는다.
- 검증: `tests/core/test_idempotency.py::{test_client_key_replays_response_snapshot, test_duplicate_scope_key_rejected_concurrent, test_same_key_different_body_detected, test_server_key_dedupe_via_unique}`.

## 메커니즘: Job dispatch / lock / retry / registry

- 위치: `app/core/jobs/dispatcher.py`, `lock.py`, `retry.py`, `registry.py`
- 책임: 비동기 작업을 `job_runs` row 하나로 큐잉하고 워커가 집어가는 실행 기반. summary/importance가 "별도 job, 별도 실패·재시도"여야 한다는 요구(흐름 2)를 job_type 단위 독립 row로 강제.
- 입력 → 결과: dispatcher가 §3 event→consumer 매핑으로 `job_runs` 큐잉 → 워커가 `queued`/`retrying` 픽업 → `lock_key` 획득 → registry가 job_type→handler 라우팅 → 실행 → succeeded/retrying/failed.

체크리스트:
- **[정상]** 큐잉된 job을 워커가 `status IN ('queued','retrying') AND scheduled_at <= now()`로 픽업 → `lock_key` 있으면 lock 획득 후 `running`(`locked_by`/`locked_at`/`started_at` 세팅) → registry의 handler 호출 → 정상 종료 시 `succeeded`, `finished_at` 세팅.
- **[멱등]** 같은 작업 중복 큐잉 → `(job_type, idempotency_key)` UNIQUE가 두 번째를 거부(예: 같은 Pub/Sub notification 두 번 와도 `sync_delta` 한 번만 큐잉, `db-schema` `job_runs`). handler 자체 멱등성은 각 도메인 책임 — core는 큐잉 레벨 dedupe만 보장.
- **[동시]** 같은 `lock_key`(예: `source:{source_id}`) job을 두 워커가 동시 픽업 → `lock.py`가 한 워커만 lock 획득, 나머지는 skip(같은 계정 동시 sync 방지, §2 lock_key 규칙). `lock_key = null`인 job(`generate_summary`/`classify_importance`)은 lock 없이 병렬 실행 허용 — idempotency_key로 충분.
- **[선행조건]** registry가 job_type→handler를 매핑하고 있어야 실행 가능 — 미등록 job_type 픽업 시 실행 거부·에러 로그. `lock_key` 있는 job은 lock 획득이 실행 선행조건.
- **[부분실패]** handler 실행 실패 → retry 정책(`retry.py`)이 `attempt_count < 한도`면 `retrying`+backoff(`scheduled_at` 미래로), 초과면 `failed`. lock 보유 중 워커 사망 → `locked_at` timeout(POC 기본 60s, **[미정: 운영 튜닝]**, `db-schema` `job_runs`) 경과 후 죽은 워커로 간주하고 lock 해제 → 다른 워커 재픽업(at-least-once).
- **[권한]** N/A — 내부 job 실행, 사용자 컨텍스트 없음. workspace 스코프는 각 도메인 handler가 payload의 source_id/workspace_id로 자체 제한.
- **[데이터경계]** core는 `payload` jsonb를 handler에 그대로 전달만 하고 내용을 해석하지 않는다. registry는 §2 표의 job_type만 등록 — 임의 job_type을 실행하지 않는다.
- 검증: `tests/core/jobs/test_dispatcher.py::{test_lock_prevents_concurrent_same_job, test_retry_backoff_and_max_attempts, test_lock_timeout_releases_dead_worker, test_unlocked_jobs_run_in_parallel}`.

## 메커니즘: 도메인 자동 발견 (registry / router / consumer / purge wiring)

- 위치: `app/core/jobs/registry.py`(job) + `app/api/router.py`(HTTP) + dispatcher(event consumer) + purge wiring
- 책임: `_integration-contract.md §4` 노출 인터페이스로 각 도메인의 `router`/`JOB_HANDLERS`/`EVENT_CONSUMERS`/`PURGE_HANDLER`를 core가 자동 수집. 도메인 추가 시 core 코드 수정 없이 등록.
- 입력 → 결과: app factory가 `app/domains/` 순회 → 네 심볼 수집 → registry 병합·router include·consumer 매핑·purge handler 등록.

체크리스트:
- **[정상]** app factory 부팅 시 `app/domains/*` 순회 → `router`(§3 prefix)를 include, `JOB_HANDLERS`(§2)를 registry에 병합, `EVENT_CONSUMERS`(§3)를 dispatcher 매핑에 등록, `PURGE_HANDLER`(Task 13)를 purge 오케스트레이션에 수집. 도메인은 registry.py를 직접 수정하지 않는다.
- **[멱등]** 재부팅마다 같은 도메인 집합에서 같은 wiring 생성 — 순서 무관하게 동일 맵. 발견은 상태 변경이 아니라 부팅 시 조립.
- **[동시]** N/A — 부팅 시 단일 프로세스 조립 단계, 동시성 없음.
- **[선행조건]** 각 도메인 `__init__.py`가 네 심볼을 노출해야 함(없으면 `router=None`/`PURGE_HANDLER=None`/빈 dict). 심볼 누락은 부팅 시 감지.
- **[부분실패]** **중복 job_type이 두 도메인에서 등록되면 부팅 시 에러**(§4, registry가 job_type→handler 유일성 강제) — 애매하게 덮어쓰지 않고 부팅을 막아 충돌을 조기 노출. router prefix 충돌·미노출 심볼도 부팅 시 실패로 드러난다.
- **[권한]** N/A — 부팅 조립, 사용자 컨텍스트 없음.
- **[데이터경계]** core는 도메인 이름을 하드코딩 import하지 않고 순회로만 수집 — core→도메인 역방향 의존을 만들지 않는다(경계 설계 원칙). 수집한 handler 내부 로직은 해석하지 않는다.
- 검증: `tests/core/jobs/test_dispatcher.py::{test_registry_collects_domain_handlers, test_duplicate_job_type_fails_boot}`(자동 발견·중복 job_type 부팅 에러). router/consumer/purge 수집의 통합 검증은 각 도메인 머지 후 통합 테스트에서 확인.

---

## 워크트리 격리 노트

- 마이그레이션: `0001_core`(base revision, `down_revision = None`). 체인의 최상단 — 다른 모든 도메인 마이그레이션이 이 위에 쌓인다(§1 배정표). autogenerate 금지, 수동 슬러그 revision.
- 생성 테이블: `outbox_events`, `job_runs`, `idempotency_keys`(§1, `db-schema` core §). status 값은 §5(`outbox_events.status`: pending/dispatched/failed, `job_runs.status`: queued/running/retrying/succeeded/failed) 고정.
- core 슬라이스가 먼저 제공해야 하는 공용물: `app/core/crypto.py`(mail_sources Task 3이 credential 암호화에 의존, mail_sources 플랜 §워크트리 격리 노트). core 머지 전까지 다른 도메인은 fake로 계약 테스트 진행.
- §4 노출 인터페이스 계약(`router`/`JOB_HANDLERS`/`EVENT_CONSUMERS`/`PURGE_HANDLER`)·§2 job registry·§3 event wiring을 core가 소유·강제. 도메인 워크트리는 이 심볼을 노출만 하고 core wiring 코드는 건드리지 않는다.
- job lock timeout POC 기본 60s(`db-schema` 열린 결정), outbox/job retention **[미정 — POC 이후]**.
