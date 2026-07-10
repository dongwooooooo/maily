# Maily Backend Context-Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Maily backend in the context boundaries defined by
`docs/areas/backend/module-boundaries.md`, proving Gmail sync, briefing read models,
Gmail action trust, labels, assistant decisions, notifications, and purge workflows by TDD.

**Architecture:** FastAPI exposes authenticated APIs. Domain modules own business state and
publish durable events through the core outbox/job dispatch. Gmail read/sync is isolated behind
mail_intake's `GmailReaderPort`, Gmail write/mutation is isolated behind gmail_actions'
`GmailMutationPort`, and all Gmail writes go through the gmail_actions command ledger.

**Tech Stack:** Python 3.14, FastAPI 0.139.0, Pydantic 2.13, SQLAlchemy 2.0, Alembic,
PostgreSQL 18, Redis 8.8, Authlib, google-auth-oauthlib, PyJWT, httpx, pytest.

---

## 구현 상태 (2026-07-10 검증)

원격 main `70869ce` 기준. 전체 테스트 321 passed(`pytest -q`), 통합 테스트 6종 green, 마이그레이션 체인 `0001_core`→`0012_notifications` 선형 완결. **Task 1–13 완료, Task 14·15 미착수.**

| 구분 | 상태 |
|---|---|
| Task 1–13 (G0–G8) | 완료 — Steps 체크박스 반영, 파일·테스트·마이그레이션 검증됨 |
| Task 14 (IG1, Live Gmail Watch) | 미착수 — `live_reader.py`는 `NotImplementedError` 스텁, `test_live_reader_contract.py`·runbook 부재 |
| Task 15 (Operations Handoff) | 미착수 — `development/infra/README.md`만 존재, `test_config`/`test_rate_limit`/`test_retry_idempotency` 및 rate limit 구현 부재 |

### 남은 갭 (Task 1–13 범위, 기능 결손 아님·후속 결정 대상)

1. **core idempotency** — 클라이언트 키 response replay(`store_response`/`get_response`는 구현, 테스트 없음)·`request_hash` 불일치 감지(409) 로직·동시성 테스트 부재. 서버 키 `reserve()` dedupe만 검증됨.
2. **core job 실행기** — lock timeout/죽은 워커 재획득 미구현, retry backoff(`scheduled_at` 미래 스케줄) 미구현(`should_retry` 불린만). outbox 트랜잭션 원자성·재기동 생존 명시 테스트 부재.
3. **런타임 dispatcher 폴러 부재** — `dispatch_pending_events(ACTIVE_EVENT_CONSUMERS)`를 주기 호출하는 워커가 앱 런타임에 없음(테스트에서만 구동). POC 특성이나 live 전 필수.
4. **활성 배선 누락 2건** — `gmail_snapshot_changed→prepare_cleanup_proposals`, `cleanup_proposal_created→build_briefing`이 도메인 `EVENT_CONSUMERS` 선언에만 있고 `ACTIVE_EVENT_CONSUMERS` 미등록 → 실제 큐잉 안 됨.
5. **manual sync 경로 계약 불일치** — `_integration-contract.md §3`은 `POST /sources/{id}/sync`, 실제는 `/intake` prefix로 `POST /intake/sources/{id}/sync` 노출(라우터 주석에 인지됨).
6. **identity 엣지 테스트 2건 부재** — 동시 로그인(google_subject 동시 insert), workspace_id 파라미터 오버라이드 방어.
7. **mail_sources status 부분 검증** — `syncing`/`synced`/`permission_needed`/`error` 전이 직접 테스트 없음(전이 주체가 mail_intake라 Task 3 범위 밖으로 위임된 상태).
8. **Task 13 purge 마커 step 미이행** — 마이그레이션 파일에 content-bearing/purge 마커 없음(db-schema.md ◆ 표기만 존재).
9. **IC6 전용 통합 테스트 없음** — cleanup 승인→command는 직접 동기 호출 설계라 dispatcher 배선 없음, `test_cleanup_review.py` 도메인 테스트로만 커버.
10. **importance_classified outbox 전용 단위 테스트 부재** — 통합 테스트에서 간접 검증만.

## 기준 문서

1. `docs/current/product-wireframe-final.md`  
   제품 범위, 계정 모델, 화면 10종, 카드/상세 역할, Gmail 신뢰 원칙.
2. `docs/current/product-features.md`  
   사용자 기능 설명, MVP 범위, 백엔드 우선 POC 범위.
3. `docs/areas/backend/module-boundaries.md`  
   비즈니스 컨텍스트와 개발 구현 컨텍스트의 source-of-truth.
4. `docs/current/technical-foundation.md`  
   스택, 디렉토리 경계, 인프라 경계, 실행 기준.
5. `development/backend/README.md`  
   로컬 실행과 백엔드 영역 안내.

## 구현 원칙

- 기능 설명은 `docs/current/product-features.md`에서 관리한다.
- 모듈 경계는 `docs/areas/backend/module-boundaries.md`의 컨텍스트와 구현 유닛을 따른다.
- 예외·에러 응답·로깅은 `docs/areas/backend/error-handling-and-logging.md`를 따른다. 서비스/레포지토리 계층에서 `ValueError`/`Exception`/`HTTPException`을 직접 던지지 않는다 — `app/core/errors.py`의 `MailyError` 서브클래스만 쓴다.
- 외부 Gmail API가 막혀도 fake adapter 기반 TDD가 진행되어야 한다.
- Gmail 지속 동기화는 프론트 mock 교체보다 먼저 fake 경로로 증명한다.
- Live Gmail Watch는 integration gate다. 로컬 핵심 구현을 막지 않는다.
- Gmail mutation은 gmail_actions command ledger, activity log, undo 가능 여부 없이 구현하지 않는다.
- 모듈 간 side effect는 직접 도메인 service 호출이 아니라 `outbox_events`, `job_runs`,
  idempotency key, read model로 연결한다.
- core는 도메인 모듈이 아니라 transaction, outbox, idempotency, job dispatch
  같은 공통 실행 메커니즘만 제공한다.
- mail_sources 바깥 모듈은 OAuth token을 직접 읽지 않는다.
- mail_intake의 Gmail read/sync는 `GmailReaderPort`, gmail_actions의 Gmail write/mutation은 `GmailMutationPort`만 사용한다.
- briefing projection은 재생성 가능해야 한다. 사용자 item state는 projection과 분리한다.
- 카드 목록 응답에는 action field, AI reasoning, raw body를 넣지 않는다.
- summary off 계정은 metadata-only fallback을 제공하고 raw prompt/body를 장기 저장하지 않는다.
- `generate_summary`와 `classify_importance`는 별도 job, 별도 테이블(`message_summaries`,
  `message_importance_classifications`)로 분리해 독립적으로 실패·재시도한다.
- briefing projection은 `gmail_snapshot_changed`, `summary_completed`, `importance_classified`
  각각에 반응해 여러 번 재생성될 수 있다. 매번 전체 재생성이 아니라 해당 message_id 단위
  부분 재생성이다. importance 판단 대기중인 아이템은 별도 pending 상태를 만들지 않고
  계정 단위 `syncing` 표시로만 안내한다.

## Gmail API POC 확인 사항

`docs/areas/backend/db-schema.md`의 [미정] 항목 중 Gmail 관련 부분을 Google 공식 문서 대조로 먼저 좁혀둔다. LLM 관련 [미정](importance_band 값, confidence_band 경계, excerpt 길이)은 지금 결정하지 않는다 — provider가 정해지는 시점에 파싱해서 반영하고, 그 전까지는 `fake_llm` 계약만 유지한다.

### 확인된 사실 (출처 포함)

- OAuth scope: `gmail.readonly`(읽기) + `gmail.modify`(읽기/쓰기, 라벨 생성·수정 포함, 영구 삭제는 불허) 두 개로 mail_intake/gmail_actions 요구사항을 전부 커버한다. 별도 `gmail.labels`/`gmail.metadata` scope는 불필요 — [OAuth scopes](https://developers.google.com/identity/protocols/oauth2/scopes#gmail)
- `users.watch`: request `topicName`(필수), `labelIds`, `labelFilterBehavior`. response `historyId`, `expiration`. 최소 7일마다 재호출 필요 — [push guide](https://developers.google.com/gmail/api/guides/push), [watch reference](https://developers.google.com/gmail/api/reference/rest/v1/users/watch)
- `users.history.list`: `startHistoryId`(필수), `historyTypes[]`, `pageToken`, `maxResults`(기본 100/최대 500). response에 `messagesAdded`/`messagesDeleted`/`labelsAdded`/`labelsRemoved`. historyId는 보통 최소 1주일 유효하나 드물게 더 일찍 만료 — 만료 시 404, full resync 필요 — [history.list](https://developers.google.com/gmail/api/reference/rest/v1/users.history/list)
- `users.messages.get` format: FULL/RAW는 최초 조회, MINIMAL은 캐시된 메시지의 labelIds만 갱신할 때 사용 — [sync guide](https://developers.google.com/gmail/api/guides/sync)
- `users.messages.modify`: `addLabelIds[]`/`removeLabelIds[]` 배열 하나로 mark_read(`UNREAD` 제거)/archive(`INBOX` 제거)/label 적용을 전부 처리 — action_type별 별도 API 없음 — [messages.modify](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify)
- `users.labels`: 이름에 `/`로 계층 표기(`Maily/영수증`), `type: user` 생성 시 `labelListVisibility`/`messageListVisibility` 필요 — [labels.create](https://developers.google.com/gmail/api/reference/rest/v1/users.labels/create)
- Cloud Pub/Sub: `gmail-api-push@system.gserviceaccount.com`에 topic Publisher 권한 부여 필수. notification payload는 `{"emailAddress": "...", "historyId": "..."}` — [push guide](https://developers.google.com/gmail/api/guides/push)
- 429/403은 exponential backoff 권장(최소 1초부터) — 정확한 배수·최대 재시도 횟수는 문서에 없음, Task 15에서 실측 — [handle-errors](https://developers.google.com/gmail/api/guides/handle-errors)
- Quota unit(watch=100, history.list=2, messages.get=20, labels.list=1, labels.create=5, messages.modify=5), 유저당 분당 6,000 unit, 프로젝트 일일 80,000,000 unit — [quota](https://developers.google.com/gmail/api/reference/quota). **신뢰도 낮음** — 2차 요약값이라 구현 전 Cloud Console quota 페이지에서 재확인 필요.

### db-schema.md 대조 결과

- `gmail_action_commands.payload`를 `{add_label_ids: [], remove_label_ids: []}` 형태로 수정 완료(반영됨) — 기존 `{label_id}` 단일값 예시는 실제 API(`messages.modify`)와 맞지 않았다.
- `gmail_watch_registrations.topic_name/expiration`, `gmail_sync_cursors.cursor_status`(valid/invalid → full resync), `gmail_notification_events.email_address/history_id` — 전부 실제 API 필드와 그대로 대응, 변경 불필요.

### 라이브 POC 실행 결과 (2026-07-09, `development/backend/scripts/gmail_poc.py`)

- `users.watch` 등록 200 성공(`historyId`, `expiration` 정상 수신) — Pub/Sub topic Publisher 권한 부여, topic/subscription 설정이 실제로 맞다는 것을 확인.
- `messages.get(format=metadata)` 응답에 `snippet` 필드 **포함 확인**. `payload.body`는 응답에 없음 — raw body가 metadata 호출로 새지 않는 것도 같이 확인. `message_excerpts`는 별도 `format=full` 호출 없이 이 `snippet`을 그대로 쓴다(db-schema.md 반영 완료).
- `Maily/{name}` 라벨 계층 **중첩 확인됨** — 단, 부모 `Maily` 라벨이 계정에 먼저 존재해야 한다. 부모 없이 `Maily/POC테스트`를 만들었을 땐 flat하게 표시됐고, 이후 `Maily` 부모를 생성하자 기존 자식까지 소급으로 중첩됐다. `create_or_update_label` 서비스는 계정별로 `Maily` 부모 라벨을 get-or-create로 먼저 보장해야 한다(db-schema.md `gmail_label_mappings` 반영 완료).

### 여전히 라이브 검증 필요 (문서로 안 풀림)

- Quota unit 정확한 수치, 429/403 backoff 배수·최대 재시도 — Task 15 rate limit test에서 실측.

### 라이브 실행 전 준비 체크리스트

- [ ] Google Cloud Project 생성 + Gmail API 활성화
- [ ] OAuth consent screen(테스트 모드) + 테스트 사용자로 실사용 Gmail 계정 등록
- [ ] OAuth client ID/secret 발급, redirect URI 등록(로컬 개발용 포함)
- [ ] Cloud Pub/Sub topic 생성 + `gmail-api-push@system.gserviceaccount.com`에 Publisher 권한 부여
- [ ] Pub/Sub subscription 생성(push 웹훅 vs pull — 백엔드 엔드포인트 준비 상태에 따라 결정)
- [ ] 테스트용 Gmail 계정(실제 송수신 가능한 상태)
- [ ] OAuth scope 확정: `gmail.readonly` + `gmail.modify`

이 체크리스트가 끝나야 Task 14(Live Gmail Watch Integration)를 실제로 돌릴 수 있다. Task 1-13은 fake adapter로 이 체크리스트 없이 진행 가능.

## 도메인 기준 파일 구조

백엔드 코드는 `app/domains/<domain>/`을 기본 단위로 둔다. 개발 모델, repository,
service, router, event schema, job handler, 외부 adapter는 해당 비즈니스 도메인 내부에 둔다.
공통 job 실행 기반만 `app/core/jobs/`에 둔다.

| 도메인 | 주요 위치 | 내부 구성 |
|---|---|---|
| core (Backend Core) | `app/core/`, `app/core/jobs/`, `app/api/`, `app/db/` | config, database, redis, outbox, idempotency, logging, job dispatcher/lock/retry/registry |
| identity (Identity & Workspace) | `app/domains/identity/` | models, schemas, repository, service, router |
| mail_sources (Connected Gmail Sources) | `app/domains/mail_sources/` | models, schemas, repository, service, router, credentials, oauth, events, purge, `jobs/` |
| mail_intake (Gmail Intake & Snapshot) | `app/domains/mail_intake/` | models, schemas, repository, service, router, gmail_reader, fake_reader, live_reader, events, purge, `jobs/` |
| briefing (Briefing & Item State) | `app/domains/briefing/` | models, schemas, repository, service, router, item_state, reminders, events, purge, `jobs/` |
| labels (Labels & Classification) | `app/domains/labels/` | models, schemas, repository, service, router, events |
| gmail_actions (Gmail Actions & Activity) | `app/domains/gmail_actions/` | models, schemas, repository, service, router, gmail_mutator, fake_mutator, live_mutator, activity, undo, events, purge, `jobs/` |
| assistant_decisions (Assistant Decisions) | `app/domains/assistant_decisions/` | models, schemas, repository, service, router, summaries, importance, rules, cleanup, llm, fake_llm, events, purge, `jobs/` |
| notifications (Notifications & Recovery) | `app/domains/notifications/` | models, schemas, repository, service, router, events, `jobs/` |

Job handler는 도메인 내부 `jobs/`에 둔다. `app/core/jobs/`에는 dispatcher, lock,
retry, registry만 둔다.

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
| IG1 | Live Gmail Watch Integration | mail_sources, mail_intake, infra | 테스트 Gmail 계정의 새 메일이 Pub/Sub/history 경로로 반영된다. |

## Task 1: Backend Core Runtime

**Context:** core (Backend Core)  
**Goal:** API 실행 기반, DB session, Redis client, migration runner, outbox envelope,
idempotency, job dispatch, test runner 기준을 고정한다.

**Files:**
- Modify: `development/backend/app/main.py`
- Modify: `development/backend/app/core/config.py`
- Create: `development/backend/app/core/database.py`
- Create: `development/backend/app/core/redis.py`
- Create: `development/backend/app/core/outbox.py`
- Create: `development/backend/app/core/idempotency.py`
- Create: `development/backend/app/core/logging.py`
- Create: `development/backend/app/core/errors.py`
- Create: `development/backend/app/core/error_handlers.py`
- Create: `development/backend/app/api/router.py`
- Create: `development/backend/app/api/deps.py`
- Create: `development/backend/app/core/jobs/dispatcher.py`
- Create: `development/backend/app/core/jobs/lock.py`
- Create: `development/backend/app/core/jobs/retry.py`
- Create: `development/backend/app/core/jobs/registry.py`
- Create: `development/backend/app/db/base.py`
- Create: `development/backend/app/db/migrations/env.py`
- Create: `development/backend/alembic.ini`
- Create: `development/backend/tests/core/test_health.py`
- Create: `development/backend/tests/core/test_ready.py`
- Create: `development/backend/tests/core/test_outbox.py`
- Create: `development/backend/tests/core/test_idempotency.py`
- Create: `development/backend/tests/core/test_errors.py`
- Create: `development/backend/tests/core/test_logging.py`
- Create: `development/backend/tests/core/jobs/test_dispatcher.py`

**Steps:**
- [x] Write tests for `GET /health` returning `{"status": "ok"}`.
- [x] Write readiness tests for DB/Redis success and failure JSON bodies.
- [x] Write outbox dedupe tests keyed by `(event_type, idempotency_key)`.
- [x] Write job lock tests that prevent two workers from running the same job concurrently.
- [x] Write exception hierarchy tests mapping each `MailyError` subclass to its status code/body, and confirming an unhandled exception returns a generic 500 without leaking details (`docs/areas/backend/error-handling-and-logging.md`).
- [x] Write request-id middleware tests (generated when absent, echoed back when client-supplied).
- [x] Add FastAPI app factory, root router, request id logging context, async SQLAlchemy session, Redis dependency.
- [x] Add baseline Alembic migration for `outbox_events`, `job_runs`, `idempotency_keys`.
- [x] Run `cd development/backend && python -m pytest tests/core/test_health.py tests/core/test_ready.py tests/core/test_outbox.py tests/core/test_idempotency.py tests/core/test_errors.py tests/core/test_logging.py tests/core/jobs/test_dispatcher.py -q`.

**Gate:** G0 passes.

## Task 2: Identity & Workspace

**Context:** identity (Identity & Workspace)  
**Goal:** 서비스 로그인 사용자와 workspace context를 만든다.

**Files:**
- Create: `development/backend/app/domains/identity/models.py`
- Create: `development/backend/app/domains/identity/schemas.py`
- Create: `development/backend/app/domains/identity/repository.py`
- Create: `development/backend/app/domains/identity/service.py`
- Create: `development/backend/app/domains/identity/router.py`
- Create: `development/backend/app/core/security.py`
- Create: `development/backend/tests/domains/identity/test_google_login.py`
- Create: `development/backend/tests/domains/identity/test_workspace_resolution.py`
- Create: `development/backend/tests/domains/identity/test_workspace_isolation.py`

**Steps:**
- [x] Write mocked Google profile test that creates one user, one workspace, and one membership.
- [x] Write relogin test where the same Google subject reuses the existing workspace.
- [x] Write JWT/session test for `user_id`, `workspace_id`, issuer `maily`, and expiration.
- [x] Write workspace isolation test where user A cannot resolve user B workspace resources.
- [x] Add migrations for `users`, `workspaces`, `workspace_members`, `sessions`.
- [x] Implement OAuth callback service, session issue/verify, and request context dependency.
- [x] Run `cd development/backend && python -m pytest tests/domains/identity -q`.

**Gate:** identity request context is available to every authenticated API.

## Task 3: Connected Gmail Sources

**Context:** mail_sources (Connected Gmail Sources)  
**Goal:** 연결 Gmail 계정, OAuth credential, 계정 설정, pause/disconnect state를 서비스 로그인과 분리한다.

**Files:**
- Create: `development/backend/app/domains/mail_sources/models.py`
- Create: `development/backend/app/domains/mail_sources/schemas.py`
- Create: `development/backend/app/domains/mail_sources/repository.py`
- Create: `development/backend/app/domains/mail_sources/service.py`
- Create: `development/backend/app/domains/mail_sources/router.py`
- Create: `development/backend/app/domains/mail_sources/credentials.py` (미분리 — service.py에 통합 구현)
- Create: `development/backend/app/core/crypto.py`
- Create: `development/backend/app/domains/mail_sources/oauth.py` (미분리 — service.py에 통합 구현)
- Create: `development/backend/app/domains/mail_sources/events.py` (미분리 — service.py가 `app.core.outbox.append_event` 직접 호출)
- Create: `development/backend/tests/domains/mail_sources/test_connection.py`
- Create: `development/backend/tests/domains/mail_sources/test_credentials.py`
- Create: `development/backend/tests/domains/mail_sources/test_source_settings.py`

**Steps:**
- [x] Write token storage test that fails if access token or refresh token plaintext is persisted.
- [x] Write duplicate constraint test for same Gmail address in one workspace.
- [x] Write status tests for `connected`, `syncing`, `synced`, `permission_needed`, `error`, `paused`, `disconnecting`.
- [x] Write account setting tests for display name fallback, briefing toggle, summary toggle, notification toggle, pause.
- [x] Write outbox test for `gmail_source_connected` and `gmail_source_settings_changed`.
- [x] Add migrations for `connected_gmail_accounts`, `gmail_oauth_credentials`, `gmail_source_settings`.
- [x] Implement account connect/list/update APIs.
- [x] Run `cd development/backend && python -m pytest tests/domains/mail_sources -q`.

**Gate:** G1 account separation and encrypted credential contract pass.

## Task 4: Gmail Reader and Message Snapshot

**Context:** mail_intake (Gmail Intake & Snapshot)  
**Goal:** Gmail read/sync port와 message snapshot 저장 계약을 만든다.

**Files:**
- Create: `development/backend/app/domains/mail_intake/gmail_reader.py`
- Create: `development/backend/app/domains/mail_intake/fake_reader.py`
- Create: `development/backend/app/domains/mail_intake/live_reader.py`
- Create: `development/backend/app/domains/mail_intake/models.py`
- Create: `development/backend/app/domains/mail_intake/repository.py`
- Create: `development/backend/app/domains/mail_intake/schemas.py`
- Create: `development/backend/app/domains/mail_intake/events.py`
- Create: `development/backend/tests/domains/mail_intake/test_fake_reader.py`
- Create: `development/backend/tests/domains/mail_intake/test_message_snapshot.py`

**Steps:**
- [x] Define `GmailReaderPort` methods for watch registration, history delta, message metadata read, and limited excerpt read.
- [x] Write fake reader tests for deterministic history pages and Gmail state snapshots.
- [x] Write snapshot upsert test keyed by `(source_id, gmail_message_id)`.
- [x] Write limited excerpt test that rejects raw body storage.
- [x] Write label/read/archive state update tests for message added, deleted, label added, label removed.
- [x] Write `gmail_snapshot_changed` event test with source id, sync run id, and message ids.
- [x] Add migrations for `gmail_messages`, `message_excerpts`, `gmail_message_labels`.
- [x] Implement fake reader and snapshot repository.
- [x] Run `cd development/backend && python -m pytest tests/domains/mail_intake/test_fake_reader.py tests/domains/mail_intake/test_message_snapshot.py -q`.

**Gate:** Snapshot can be built without live Gmail credentials and without any Gmail write port.

## Task 5: Gmail Continuous Sync

**Context:** mail_intake (Gmail Intake & Snapshot)  
**Goal:** watch/history/polling 기반 동기화 제어 계층을 fake event로 증명한다.

**Files:**
- Modify: `development/backend/app/domains/mail_intake/models.py`
- Modify: `development/backend/app/domains/mail_intake/schemas.py`
- Modify: `development/backend/app/domains/mail_intake/repository.py`
- Create: `development/backend/app/domains/mail_intake/service.py`
- Create: `development/backend/app/domains/mail_intake/router.py`
- Create: `development/backend/app/domains/mail_intake/jobs/register_watch.py`
- Create: `development/backend/app/domains/mail_intake/jobs/renew_watch.py`
- Create: `development/backend/app/domains/mail_intake/jobs/process_notification.py`
- Create: `development/backend/app/domains/mail_intake/jobs/poll_history.py`
- Create: `development/backend/app/domains/mail_intake/jobs/sync_delta.py`
- Create: `development/backend/app/domains/mail_intake/jobs/sync_full.py`
- Create: `development/backend/tests/domains/mail_intake/test_sync_cursor.py`
- Create: `development/backend/tests/domains/mail_intake/test_process_notification_job.py`
- Create: `development/backend/tests/domains/mail_intake/test_poll_history_job.py`
- Create: `development/backend/tests/domains/mail_intake/test_sync_delta_job.py`
- Create: `development/backend/tests/domains/mail_intake/test_sync_full_job.py`

**Steps:**
- [x] Write cursor tests for `last_history_id`, `watch_expiration_at`, `last_successful_sync_at`.
- [x] Write watch renewal target selection test.
- [x] Write Pub/Sub fan-out test from `emailAddress` and `historyId` to every active connected source.
- [x] Write notification dedupe test keyed by email and history id.
- [x] Write fallback polling target selection test.
- [x] Write invalid cursor test that schedules full resync.
- [x] Add migrations for `gmail_sync_cursors`, `gmail_watch_registrations`, `gmail_notification_events`, `sync_runs`.
- [x] Implement notification processing, polling scheduler, delta sync, full sync.
- [x] Run `cd development/backend && python -m pytest tests/domains/mail_intake -q`.

**Gate:** G2 passes without live Gmail.

## Task 6: Briefing Projection and Detail API

**Context:** briefing (Briefing & Item State)  
**Goal:** 프론트 mock을 대체할 오늘 브리핑과 상세 읽기 API를 만든다.

**Files:**
- Create: `development/backend/app/domains/briefing/models.py`
- Create: `development/backend/app/domains/briefing/schemas.py`
- Create: `development/backend/app/domains/briefing/repository.py`
- Create: `development/backend/app/domains/briefing/service.py`
- Create: `development/backend/app/domains/briefing/router.py`
- Create: `development/backend/app/domains/briefing/events.py`
- Create: `development/backend/app/domains/briefing/jobs/build_briefing.py`
- Create: `development/backend/tests/domains/briefing/test_today_briefing.py`
- Create: `development/backend/tests/domains/briefing/test_projection_regenerable.py`
- Create: `development/backend/tests/domains/briefing/test_partial_rebuild.py`
- Create: `development/backend/tests/domains/briefing/test_message_detail.py`

**Steps:**
- [x] Write `GET /briefing/today?scope=all` contract test with account groups and sections.
- [x] Write account scope filter test.
- [x] Write card response negative test for action field, AI reason, raw body.
- [x] Write `GET /messages/{message_id}` readonly detail test with Gmail URL, metadata, excerpt, summary, Gmail handling fact.
- [x] Write projection rebuild idempotency test for repeated `gmail_snapshot_changed`.
- [x] Write partial rebuild test where `summary_completed` and `importance_classified` each rebuild only their own `message_id`, not the full projection.
- [x] Write negative test that a message pending importance classification does not get its own item-level pending state, and that account-level `syncing` status is the only signal used.
- [x] Add migration for `briefing_items`.
- [x] Implement section placement, account grouping, and detail read model.
- [x] Run `cd development/backend && python -m pytest tests/domains/briefing -q`.

**Gate:** G3 briefing/detail read shape is stable.

## Task 7: Item State and Storage

**Context:** briefing (Briefing & Item State)  
**Goal:** seen/remind_later durable state와 보관함 예정 타임라인을 projection에서 분리한다.

**Files:**
- Modify: `development/backend/app/domains/briefing/models.py`
- Modify: `development/backend/app/domains/briefing/schemas.py`
- Modify: `development/backend/app/domains/briefing/repository.py`
- Modify: `development/backend/app/domains/briefing/service.py`
- Modify: `development/backend/app/domains/briefing/router.py`
- Create: `development/backend/app/domains/briefing/item_state.py`
- Create: `development/backend/app/domains/briefing/reminders.py`
- Create: `development/backend/app/domains/briefing/jobs/reactivate_reminders.py`
- Create: `development/backend/tests/domains/briefing/test_seen_state.py`
- Create: `development/backend/tests/domains/briefing/test_reminders.py`
- Create: `development/backend/tests/domains/briefing/test_storage_upcoming.py`
- Create: `development/backend/tests/domains/briefing/test_reactivate_reminders_job.py`

**Steps:**
- [x] Write seen state test that survives briefing projection rebuild.
- [x] Write reminder creation test for a briefing item.
- [x] Write `GET /storage/upcoming` test for today, tomorrow, this week grouping.
- [x] Write negative test that past briefing history is not returned as storage.
- [x] Write reminder reactivation test that emits reminder event and re-enters briefing/notification candidates.
- [x] Add migrations for `briefing_item_states`, `reminders`.
- [x] Implement item state APIs and reactivation worker.
- [x] Run `cd development/backend && python -m pytest tests/domains/briefing -q`.

**Gate:** Durable item state is independent from regenerable briefing view.

## Task 8: Labels and Classification Signals

**Context:** labels (Labels & Classification)  
**Goal:** 사용자 라벨, Gmail `Maily/` mapping, message move target, correction signal을 구현한다.

**Files:**
- Create: `development/backend/app/domains/labels/models.py`
- Create: `development/backend/app/domains/labels/schemas.py`
- Create: `development/backend/app/domains/labels/repository.py`
- Create: `development/backend/app/domains/labels/service.py`
- Create: `development/backend/app/domains/labels/router.py`
- Create: `development/backend/app/domains/labels/events.py`
- Create: `development/backend/tests/domains/labels/test_label_catalog.py`
- Create: `development/backend/tests/domains/labels/test_label_move_signal.py`

**Steps:**
- [x] Write user label creation test that creates stable Gmail `Maily/{label_name}` mapping intent.
- [x] Write rename/hide/reorder tests that do not create duplicate Gmail mappings.
- [x] Write negative test that messages cannot be moved directly to default briefing sections.
- [x] Write message move test that records correction signal and requests gmail_actions label apply command.
- [x] Add migrations for `service_labels`, `gmail_label_mappings`, `label_correction_signals`.
- [x] Implement labels API and move-to-label service.
- [x] Run `cd development/backend && python -m pytest tests/domains/labels -q`.

**Gate:** User classification targets are labels, not default sections.

## Task 9: Gmail Action Ledger, Activity, and Undo

**Context:** gmail_actions (Gmail Actions & Activity)  
**Goal:** Gmail 변경 액션을 command ledger, activity log, undo 가능 여부가 있는 신뢰 계약으로 구현한다.

**Files:**
- Create: `development/backend/app/domains/gmail_actions/models.py`
- Create: `development/backend/app/domains/gmail_actions/schemas.py`
- Create: `development/backend/app/domains/gmail_actions/repository.py`
- Create: `development/backend/app/domains/gmail_actions/service.py`
- Create: `development/backend/app/domains/gmail_actions/router.py`
- Create: `development/backend/app/domains/gmail_actions/gmail_mutator.py`
- Create: `development/backend/app/domains/gmail_actions/fake_mutator.py`
- Create: `development/backend/app/domains/gmail_actions/live_mutator.py`
- Create: `development/backend/app/domains/gmail_actions/activity.py`
- Create: `development/backend/app/domains/gmail_actions/undo.py`
- Create: `development/backend/app/domains/gmail_actions/events.py`
- Create: `development/backend/app/domains/gmail_actions/jobs/execute_action.py`
- Create: `development/backend/tests/domains/gmail_actions/test_action_commands.py`
- Create: `development/backend/tests/domains/gmail_actions/test_mutation_port_boundary.py`
- Create: `development/backend/tests/domains/gmail_actions/test_activity_log.py`
- Create: `development/backend/tests/domains/gmail_actions/test_undo.py`
- Create: `development/backend/tests/domains/gmail_actions/test_execute_action_job.py`

**Steps:**
- [x] Write pending command creation test for mark read, archive, read-and-archive, label apply.
- [x] Write command idempotency test using request idempotency key.
- [x] Write negative test that no Gmail mutation occurs without a command row.
- [x] Define `GmailMutationPort` methods for mark read, archive, apply label, remove label, and reverse mutation when supported. (구현은 `gmail_actions.md` 계약대로 단일 `apply(command_id) -> MutationResult`로 통일 — action_type은 add/remove 배열로 정규화, 역연산은 ledger 계층 `undo.py` 담당)
- [x] Write fake mutator tests for changed/not changed result and reversible mutation state.
- [x] Write boundary test that gmail_actions uses `GmailMutationPort` and never reads OAuth token directly.
- [x] Write negative boundary test that gmail_actions does not import `mail_intake.gmail_reader`.
- [x] Write command transition tests for `pending`, `applied`, `failed`, `compensating`, `undone`.
- [x] Write activity recovery test where Gmail succeeds but activity creation fails and ledger can rebuild activity.
- [x] Write undo availability tests per action type.
- [x] Add migrations for `gmail_action_commands`, `activity_logs`, `undo_actions`.
- [x] Implement action command APIs and worker.
- [x] Run `cd development/backend && python -m pytest tests/domains/gmail_actions -q`.

**Gate:** G4 passes with fake GmailMutationPort.

## Task 10: Message Evaluation — Summary and Importance Classification

**Context:** assistant_decisions (Assistant Decisions)  
**Goal:** 계정별 요약 설정과 최소 payload 요약 계약을 구현하고, `gmail_snapshot_changed`에
반응하는 중요도 판단 job을 요약과 별도 job/테이블로 구현한다.

**Files:**
- Create: `development/backend/app/domains/assistant_decisions/models.py`
- Create: `development/backend/app/domains/assistant_decisions/schemas.py`
- Create: `development/backend/app/domains/assistant_decisions/repository.py`
- Create: `development/backend/app/domains/assistant_decisions/service.py`
- Create: `development/backend/app/domains/assistant_decisions/router.py`
- Create: `development/backend/app/domains/assistant_decisions/summaries.py`
- Create: `development/backend/app/domains/assistant_decisions/importance.py`
- Create: `development/backend/app/domains/assistant_decisions/llm.py`
- Create: `development/backend/app/domains/assistant_decisions/fake_llm.py`
- Create: `development/backend/app/domains/assistant_decisions/events.py`
- Create: `development/backend/app/domains/assistant_decisions/jobs/generate_summary.py`
- Create: `development/backend/app/domains/assistant_decisions/jobs/classify_importance.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_summary_privacy.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_generate_summary_job.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_importance_classification.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_classify_importance_job.py`

**Steps:**
- [x] Write summary toggle off test where no summary job is created.
- [x] Write LLM payload test allowing subject, sender, snippet, labels, limited excerpt only.
- [x] Write negative persistence test for raw body and raw prompt.
- [x] Write metadata-only fallback test for briefing/detail response.
- [x] Write `classify_importance` job test producing an importance band and reason per message.
- [x] Write test that `classify_importance` runs independently of `generate_summary` — one can fail or retry without blocking the other.
- [x] Write `importance_classified` event test carrying band and reason as payload fields, not as separate event types per band.
- [x] Write negative persistence test for raw body/raw prompt in the importance job, matching the summary privacy contract.
- [x] Add migrations for `summary_jobs`, `message_summaries`, `importance_jobs`, `message_importance_classifications`.
- [x] Implement fake LLM client, summary worker, and importance classification worker.
- [x] Run `cd development/backend && python -m pytest tests/domains/assistant_decisions/test_summary_privacy.py tests/domains/assistant_decisions/test_generate_summary_job.py tests/domains/assistant_decisions/test_importance_classification.py tests/domains/assistant_decisions/test_classify_importance_job.py -q`.

**Gate:** G6 privacy contract passes for both summary and importance classification.

## Task 11: Rule Suggestions and Cleanup Review

**Context:** assistant_decisions (Assistant Decisions)  
**Goal:** `다음부터 여기로`, 규칙 후보, 정리 제안, 개별 승인 큐를 Gmail mutation과 분리한다.

**Files:**
- Modify: `development/backend/app/domains/assistant_decisions/models.py`
- Modify: `development/backend/app/domains/assistant_decisions/schemas.py`
- Modify: `development/backend/app/domains/assistant_decisions/repository.py`
- Modify: `development/backend/app/domains/assistant_decisions/service.py`
- Modify: `development/backend/app/domains/assistant_decisions/router.py`
- Create: `development/backend/app/domains/assistant_decisions/rules.py`
- Create: `development/backend/app/domains/assistant_decisions/cleanup.py`
- Create: `development/backend/app/domains/assistant_decisions/jobs/create_rule_suggestions.py`
- Create: `development/backend/app/domains/assistant_decisions/jobs/prepare_cleanup_proposals.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_rule_suggestions.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_cleanup_review.py`
- Create: `development/backend/tests/domains/assistant_decisions/test_prepare_cleanup_proposals_job.py`

**Steps:**
- [x] Write correction signal test that creates a pending rule suggestion.
- [x] Write approval test where only approved rule suggestions become active rules.
- [x] Write confidence band tests for auto-apply, approval-required, silent no-proposal.
- [x] Write review queue test containing approval-required proposals only.
- [x] Write approve/reject tests that process one proposal at a time.
- [x] Write route negative test proving no approve-all endpoint exists.
- [x] Write before/after Gmail state response test.
- [x] Write approval test that requests gmail_actions command and does not call Gmail directly.
- [x] Add migrations for `classification_rules`, `rule_suggestions`, `cleanup_proposals`.
- [x] Implement rules, cleanup APIs, and proposal workers.
- [x] Run `cd development/backend && python -m pytest tests/domains/assistant_decisions/test_rule_suggestions.py tests/domains/assistant_decisions/test_cleanup_review.py tests/domains/assistant_decisions/test_prepare_cleanup_proposals_job.py -q`.

**Gate:** G5 assistant decision contract passes.

## Task 12: Notifications and Recovery Views

**Context:** notifications (Notifications & Recovery)  
**Goal:** 알림 이벤트와 복구 prompt가 기존 화면과 selected item으로 착지하게 한다.

**Files:**
- Create: `development/backend/app/domains/notifications/models.py`
- Create: `development/backend/app/domains/notifications/schemas.py`
- Create: `development/backend/app/domains/notifications/repository.py`
- Create: `development/backend/app/domains/notifications/service.py`
- Create: `development/backend/app/domains/notifications/router.py`
- Create: `development/backend/app/domains/notifications/events.py`
- Create: `development/backend/app/domains/notifications/jobs/emit_notification.py`
- Create: `development/backend/tests/domains/notifications/test_notification_routing.py`
- Create: `development/backend/tests/domains/notifications/test_recovery_views.py`
- Create: `development/backend/tests/domains/notifications/test_emit_notification_job.py`

**Steps:**
- [x] Write route target tests for important mail, reminder, full briefing, cleanup review, permission error.
- [x] Write negative test that no generic notification landing route is produced.
- [x] Write recovery view test where account/sync source state comes from mail_sources/mail_intake and notifications stores view data only.
- [x] Write browser push subscription and permission state tests.
- [x] Add migrations for `notification_subscriptions`, `notification_events`.
- [x] Implement notification event API, read state, route target builder, and emit worker.
- [x] Run `cd development/backend && python -m pytest tests/domains/notifications -q`.

**Gate:** G7 notification and recovery route contract passes.

## Task 13: Disconnect and Purge Workflow

**Context:** mail_sources orchestrated, mail_intake/briefing/gmail_actions/assistant_decisions participants  
**Goal:** 계정 연결 해제 시 token 폐기, sync/action 차단, content-bearing data purge, 최소 audit 보존을 검증한다.

**Files:**
- Create: `development/backend/app/domains/mail_sources/purge.py`
- Create: `development/backend/app/domains/mail_intake/purge.py`
- Create: `development/backend/app/domains/briefing/purge.py`
- Create: `development/backend/app/domains/assistant_decisions/purge.py`
- Create: `development/backend/app/domains/gmail_actions/purge.py`
- Create: `development/backend/app/domains/mail_sources/jobs/purge_disconnected_source.py`
- Create: `development/backend/app/domains/labels/purge.py` (FK-safe 순서상 `label_correction_signals` 삭제에 필요해 추가)
- Create: `development/backend/tests/domains/mail_sources/test_disconnect.py`
- Create: `development/backend/tests/domains/mail_sources/test_purge.py`
- Create: `development/backend/tests/domains/mail_sources/test_purge_disconnected_source_job.py`

**Steps:**
- [x] Write disconnect test that revokes credential, marks source `disconnecting`, and blocks new sync/action.
- [x] Write purge test that removes message/excerpt/summary/cleanup proposal content tied to the source.
- [x] Write audit residue test that keeps minimal activity facts without message body or summary text.
- [x] Write idempotency test where purge job can run twice without deleting unrelated workspace data.
- [x] Add purge markers to affected migrations where needed.
- [x] Implement domain-specific purge handlers and orchestration job.
- [x] Run `cd development/backend && python -m pytest tests/domains/mail_sources/test_disconnect.py tests/domains/mail_sources/test_purge.py tests/domains/mail_sources/test_purge_disconnected_source_job.py -q`.

**Gate:** G8 disconnect/purge contract passes.

## Task 14: Live Gmail Watch Integration

**Context:** mail_sources, mail_intake, infra integration  
**Goal:** fake sync 계약 위에 live Pub/Sub/history watch를 검증한다. 이 task는 G0-G8을 막지 않는다.

**Files:**
- Modify: `development/backend/app/domains/mail_intake/live_reader.py`
- Modify: `development/backend/app/domains/mail_intake/router.py`
- Create: `development/backend/tests/domains/mail_intake/test_live_reader_contract.py`
- Create: `docs/runbooks/gmail-live-watch-poc.md`

**Steps:**
- [ ] Write live reader contract test guarded by `MAILY_RUN_LIVE_GMAIL_TESTS=1`.
- [ ] Implement watch registration and renewal using configured Pub/Sub topic.
- [ ] Implement webhook or pull-subscription handler according to infra setup.
- [ ] Document required Google Cloud project, topic/subscription, OAuth redirect, test Gmail account, and rollback steps.
- [ ] Run default safe command: `cd development/backend && python -m pytest tests/domains/mail_intake -q`.
- [ ] Run live command only with explicit credentials: `cd development/backend && MAILY_RUN_LIVE_GMAIL_TESTS=1 python -m pytest tests/domains/mail_intake/test_live_reader_contract.py -q`.

**Gate:** IG1 passes only in a prepared live environment.

## Task 15: Operations and Developer Handoff

**Context:** core plus all backend modules  
**Goal:** 로컬 실행, 설정 검증, logging, rate limit, retry 기준을 문서화하고 전체 검증 명령을 고정한다.

**Files:**
- Modify: `development/backend/app/core/config.py`
- Modify: `development/backend/README.md`
- Create: `development/infra/README.md`
- Create: `development/backend/tests/core/test_config.py`
- Create: `development/backend/tests/core/test_rate_limit.py`
- Create: `development/backend/tests/core/test_retry_idempotency.py`

**Steps:**
- [ ] Write config validation tests for OAuth secret, JWT secret, token encryption key, DB URL, Redis URL.
- [ ] Write logging context test including request id, workspace id, source id where available.
- [ ] Write OAuth and Gmail action rate limit tests.
- [ ] Write worker retry test proving Gmail mutation is not duplicated.
- [ ] Document local DB/Redis, migration, API server, worker, and test commands in backend/infra README.
- [ ] Run `cd development/backend && python -m ruff check .`.
- [ ] Run `cd development/backend && python -m mypy app`.
- [ ] Run `cd development/backend && python -m pytest`.

**Gate:** A new developer can reproduce API server, worker, migration, and tests from README commands.

## 첫 실행 권장 순서

첫 스프린트는 G0-G3에 집중한다. 목표는 live Gmail write가 아니라 **지속 동기화와 프론트 mock 대체 가능성**을 먼저 증명하는 것이다.

1. Task 1로 로컬 API/DB/Redis 실행 기준을 고정한다.
2. Task 2-3으로 서비스 로그인 계정과 연결 Gmail 계정 분리를 검증한다.
3. Task 4-5로 fake GmailReaderPort, message snapshot, watch/history/fallback sync를 고정한다.
4. Task 6으로 `GET /briefing/today`, `GET /messages/{id}`를 만들어 프론트 mock 교체 기준을 만든다.
5. Task 9의 Gmail write는 command/activity/undo 테스트가 준비된 뒤 fake GmailMutationPort로 먼저 증명한다.
6. Task 14 live Gmail Watch는 Google Cloud 준비 후 별도 branch나 test account로 검증한다.

## 병목 관리

| 병목 | 영향 | 병렬 진행 가능 작업 | 막히면 안 되는 결정 |
|---|---|---|---|
| Google OAuth client/redirect 설정 | live 계정 연결 지연 | mocked Google profile, fake credential repository | 서비스 로그인 계정과 연결 Gmail 계정은 분리. scope는 `gmail.readonly`+`gmail.modify`로 확정(위 Gmail API POC 확인 사항 참고) |
| Pub/Sub topic/webhook 설정 | live watch POC 지연 | fake notification과 fallback polling TDD | 지속 sync는 수동 refresh API만으로 대체하지 않음. topic Publisher 권한은 `gmail-api-push@system.gserviceaccount.com`에 부여 |
| Gmail history cursor 오류 | delta sync 신뢰도 저하 | full resync fallback과 cursor invalid test | 중복 message 저장 금지 |
| API response shape | 프론트 mock 교체 지연 | OpenAPI/schema test, seed API | 카드 목록에 action/reason/raw body 추가 금지 |
| Gmail write/Undo 역연산 | write action 출시 지연 | fake GmailMutationPort, command ledger, activity schema | command/activity/undo 없이 Gmail mutation 금지. payload는 `add_label_ids`/`remove_label_ids` 배열 형태 |
| LLM provider 결정 | 요약 출시 지연 — **의도적으로 지금 결정 안 함** | fake LLM client, privacy test | raw prompt/body 저장 금지. provider 확정 시점에 파싱 로직만 교체, 그 전까지 importance_band/confidence_band 값은 db-schema.md에 [미정]으로 유지 |
| Browser push 설정 | push 전달 지연 | notification event/route target API | generic notification landing 금지 |
| Disconnect/purge 정책 | 개인정보 리스크 | local purge workflow and audit residue tests | token 폐기와 sync/action 차단은 먼저 구현 |

## 테스트 매트릭스

| 계층 | 필요한 테스트 |
|---|---|
| Domain service | source state, section projection, item state, label/rule 동작, undo 가능성 |
| API contract | briefing list shape, detail shape, label shape, cleanup queue shape, activity shape |
| DB migration | 빈 DB에서 head까지 upgrade, unique constraint, cascade/delete, purge 동작 |
| Backend Core async work | outbox event dedupe, job lock, idempotency key, retry |
| Gmail continuous sync | watch renewal, notification dedupe, history cursor, polling fallback, full resync fallback |
| Gmail read integration | fake GmailReaderPort 기반 watch, history, message metadata, limited excerpt, token refresh error |
| Gmail write integration | fake GmailMutationPort 기반 mark read, archive, label mutation, changed/not changed result |
| Action ledger | command status transition, GmailMutationPort-only mutation, activity/undo recoverability |
| Worker | 중복 없는 sync, retry, partial failure, replay |
| Message evaluation | summary/importance job 분리 실행과 독립 실패, briefing partial rebuild(message_id 단위), 판단 대기중 아이템의 계정 syncing-only 표시 |
| Privacy | summary off, 최소 LLM payload, raw prompt/body 미보관, content purge |
| Security | token 암호화, JWT issuer, workspace isolation, source ownership |
| UI boundary | card list에 action field 없음, 기본 응답에 AI reason field 없음 |
| Storage | remind_later 타임라인, 라벨 허브, 지난 브리핑 누적 목록 미생성 |
