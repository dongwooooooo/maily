# Maily Backend DB Schema

기준 문서: `docs/areas/backend/module-boundaries.md`, `docs/goals/backend-implementation-plan.md`
정리일: 2026-07-09

## 문서 역할

`module-boundaries.md`의 Command/Event Catalog와 각 Task의 migration 목록을 필드 단위 스키마로 구체화한다. 이 문서가 DB 모델링의 source-of-truth다. Alembic migration은 여기 정의를 그대로 옮긴다.

값이 확정되지 않은 항목은 표 안에 **[미정: 이유]**로 남긴다 — 임의로 값을 만들어 채우지 않는다.

각 테이블 제목 아래에는 `module-boundaries.md`의 어느 흐름(1~8)·불변식·Command/Event Catalog 항목 때문에 이 테이블이 필요한지 적는다. 표의 **목적** 열은 그 컬럼이 없으면 어떤 상황에서 무엇이 깨지는지를 적는다.

## 공통 규칙

- PK는 전부 `UUID` (`gen_random_uuid()`). Gmail 쪽 원본 ID(`gmail_message_id`, `history_id` 등)는 별도 컬럼으로 보관하고 PK로 쓰지 않는다.
- 모든 테이블에 `created_at timestamptz not null default now()`. 갱신 있는 테이블은 `updated_at`도 추가.
- workspace 소유 데이터는 `workspace_id`를 직접 컬럼으로 둔다 (조인 없이 isolation 검증/인덱싱하기 위해 — `identity`의 workspace isolation test 요구사항과 연결).
- 이벤트/커맨드 idempotency key는 `module-boundaries.md`의 Event/Command Catalog 패턴을 그대로 UNIQUE 제약으로 강제한다.
- content-bearing 테이블(◆ 표시)은 `mail_sources.disconnect_gmail_source` 이후 purge 대상이다 (Task 13, 흐름 8).

## 멱등성 키 설계

두 부류로 나뉜다 — 섞지 않는다.

**서버가 결정하는 키** (`outbox_events.idempotency_key`, `job_runs.idempotency_key`): 도메인 상태 변화 재생 방지가 목적이라 클라이언트 값을 쓰지 않는다. 포맷은 `{entity_type}:{entity_id}:{semantic_action}:{disambiguator}`. disambiguator는 그 원인 자체에 이미 존재하는 값이어야 한다 — 임의 UUID를 새로 붙이면 재시도마다 키가 달라져 dedupe가 무의미해진다. `sync_run_id`, `history_id`처럼 기존 컬럼으로 되는 경우도 있지만, 상태 전이 자체를 구분해야 하는 이벤트(`connected`, `applied`, `summary_completed`, `importance_classified` 등)는 해당 엔티티에 int counter 컬럼이 필요하다 — 컬럼명은 테이블마다 의미에 맞게 짓는다(`version`, `snapshot_version`, `summary_version`, `classification_version` 등). timestamp는 clock skew·동시 쓰기 위험 때문에 대체재로 쓰지 않는다.

**클라이언트가 결정하는 키** (`gmail_action_commands.idempotency_key`, 범용 `idempotency_keys.key`): 사용자가 액션을 트리거하는 시점엔 서버가 조합할 상태가 아직 없다. 클라이언트가 UUID v4를 생성해 요청에 실어 보낸다(`Idempotency-Key` 헤더 관례). 서버는 값을 그대로 저장하고, 재시도는 같은 값을 재사용한다 — 새로 만들면 안 된다.

## core

경계 설계 원칙 "모듈 간 side effect는 command, durable event, read model로 연결한다"와 강제 invariant "비동기 작업은 outbox_events, job_runs, idempotency key를 가진다"를 구현하는 세 테이블이다. 흐름 1~8 전부가 도메인 서비스를 직접 호출하지 않고 이 세 테이블을 거쳐 연결된다 — 예를 들어 흐름 2(새 메일 지속 동기화)에서 mail_intake가 briefing/assistant_decisions/notifications를 직접 호출했다면 mail_intake가 세 도메인의 실패까지 책임져야 하고 트랜잭션이 얽힌다. outbox_events가 있으면 mail_intake는 이벤트 하나만 커밋하고 끝나고, 각 소비자는 자기 실패를 자기가 책임진다.

### `outbox_events`

흐름 1~8의 모든 `core outbox: X` 스텝이 쓰는 테이블. 도메인이 다른 도메인 서비스를 직접 호출하지 않고 이벤트만 발행하게 만드는 물리적 강제 장치다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| event_type | text | not null | 어떤 이벤트인지(예: `gmail_source_connected`) — 컨슈머가 이 값으로 처리 분기. |
| producer_domain | text | not null | 어느 도메인이 발행했는지. 잘못된 도메인이 남의 이벤트를 발행하는 경계 위반을 감사로 잡아낸다. |
| payload | jsonb | not null | 컨슈머가 실제로 처리할 데이터. 예: `gmail_snapshot_changed`는 source_id/sync_run_id/message_ids를 담아야 briefing이 무엇을 재생성할지 안다. |
| idempotency_key | text | not null | 같은 원인(예: 같은 sync_run)이 두 번 이벤트를 만들어도 중복 row가 안 생기게 막는다. |
| status | text | not null default 'pending' | dispatcher가 아직 처리 안 한 이벤트만 골라내는 기준. |
| attempt_count | int | not null default 0 | dispatch 실패 시 재시도 횟수 — retry 정책(포기/backoff)의 판단 근거. |
| created_at | timestamptz | not null | 같은 소스에서 발행된 이벤트를 순서대로 처리해야 할 때 정렬 기준. |
| dispatched_at | timestamptz | nullable | 언제 컨슈머에 전달됐는지 — 지연/장애 감지. |

- UNIQUE `(event_type, idempotency_key)` — dedupe 불변식.
- PARTIAL INDEX `(created_at) WHERE status = 'pending'` — dispatcher는 `status='pending' ORDER BY created_at`만 조회. `(status, created_at)` 일반 composite는 dispatched/failed로 넘어간 과거 row까지 계속 인덱싱해 시간이 지날수록 인덱스만 커짐. pending 부분집합만 인덱싱하면 크기가 "지금 처리 대기중인 양"에 비례.
- `dispatched`/`failed`로 전이된 row는 무기한 보관하지 않는다. retention/archival 전략 **[미정 — POC 이후 결정, 후보: N일 지난 dispatched row를 별도 archive 테이블로 이동하는 cron]**.

### `job_runs`

비동기 작업(예: `sync_delta`, `generate_summary`, `classify_importance`, `execute_action`)을 커맨드 하나로 큐잉하고 워커가 집어가는 테이블. 흐름 2에서 summary/importance가 "별도 job, 별도 실패/재시도"여야 한다는 요구사항이 이 테이블 구조 자체로 강제된다 — job_type이 다르면 완전히 독립된 row라 한쪽 실패가 다른 쪽에 영향을 못 준다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| job_type | text | not null | registry.py가 어느 도메인 handler로 라우팅할지 결정. |
| payload | jsonb | not null | job 실행에 필요한 입력. 예: `sync_delta`면 source_id + history cursor. |
| idempotency_key | text | not null | 같은 작업이 중복 큐잉되는 것 방지 — 예: 같은 Pub/Sub notification이 두 번 와도 `sync_delta`는 한 번만 큐잉. |
| lock_key | text | nullable | 같은 리소스(예: 같은 source_id) 대상 job이 동시에 두 워커에서 도는 것 방지. 동시 sync 두 개가 돌면 snapshot이 꼬인다. |
| status | text | not null default 'queued' | 워커가 어떤 job을 집어갈지 판단하는 기준. |
| attempt_count | int | not null default 0 | retry.py가 재시도 횟수 제한을 판단하는 근거. |
| locked_by | text | nullable | 어떤 워커가 잡고 있는지 — 장애 시 어떤 워커가 죽었는지 추적. |
| locked_at | timestamptz | nullable | lock timeout 계산 기준. 오래된 lock은 죽은 워커로 간주하고 풀어준다. |
| scheduled_at | timestamptz | not null | 예약 실행 시점 — 예: watch 갱신은 만료 전에 미리 스케줄된다. |
| started_at | timestamptz | nullable | 실행 시작 시각 — 소요 시간 계산. |
| finished_at | timestamptz | nullable | 실행 종료 시각 — 느린 job 파악. |

- UNIQUE `(job_type, idempotency_key)`.
- PARTIAL INDEX `(scheduled_at) WHERE status IN ('queued', 'retrying')` — outbox_events와 동일 이유. `succeeded`/`failed`로 끝난 job까지 인덱싱할 필요 없음.
- 중복 실행 방지는 `lock_key` + `locked_at` timeout 조합 — 락 timeout 값 **[미정: 운영 중 튜닝 필요, POC 기본값 60s 제안]**.

### `idempotency_keys`

사용자가 버튼을 두 번 누르거나 네트워크 재시도로 같은 요청이 두 번 서버에 도착하는 경우(예: 흐름 5 `request_gmail_action`) 중복 커맨드가 생성되는 것을 막는 API 레벨 범용 테이블.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| scope | text | not null | 어떤 API/도메인 요청인지 — 다른 도메인이 같은 키 값을 써도 충돌하지 않게 네임스페이스 분리. |
| key | text | not null | 클라이언트가 보낸 값 그대로. |
| request_hash | text | nullable | 같은 key로 다른 body가 오면(버그 또는 재사용 오남용) 감지. |
| response_snapshot | jsonb | nullable | 재시도 요청에 서버가 다시 처리하지 않고 동일 응답을 그대로 돌려준다. |
| expires_at | timestamptz | not null | 무기한 저장 방지 — 오래된 키는 만료시켜 재사용 가능하게 한다. |

- UNIQUE `(scope, key)`.

## identity

최상위 제품 원칙 "서비스 로그인 계정과 연결 Gmail 계정은 다른 모델이다"를 구현하는 도메인. 흐름 1의 첫 스텝 "Frontend OAuth callback → identity context"가 이 도메인에서 시작한다. 여기서 만드는 것은 Maily 서비스 자체에 로그인한 사람이지, 나중에 연결하는 Gmail 계정이 아니다.

### `users`

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| google_subject | text | unique, not null | 재로그인 시 같은 사람인지 식별 — Task 2 test "같은 Google subject가 기존 workspace 재사용"의 판단 키. |
| email | text | not null | 화면 표시, 알림 발송 시 참고 주소. |
| display_name | text | nullable | 화면 표시용. |
| last_login_at | timestamptz | nullable | 세션/보안 감사. |

### `workspaces`

흐름 1 "mail_sources creates connected source" 이전에, mail source가 어느 workspace 아래 속할지가 먼저 정해져야 한다. 지금은 1 user = 1 workspace지만, briefing_items를 포함한 모든 도메인 데이터가 workspace_id로 스코프되는 isolation 경계 자체가 이 테이블이다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. 다른 모든 도메인 테이블의 `workspace_id` FK 대상. |
| name | text | nullable | 화면 표시용. 멀티 멤버 워크스페이스가 생기면 구분자로 쓰인다. |

### `workspace_members`

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK → workspaces | 어느 workspace 소속인지. |
| user_id | uuid | FK → users | 어느 사용자인지. |
| role | text | not null default 'owner' | 향후 권한 분기 대비 — 현재 POC는 owner 고정이라 로직에서는 안 쓰지만 컬럼은 지금부터 열어둔다. |

- UNIQUE `(workspace_id, user_id)`.
- POC 범위는 1 user = 1 workspace(재로그인 시 기존 workspace 재사용, Task 2 test). 멤버 여러 명 붙는 시나리오는 스키마만 열어두고 로직은 만들지 않는다.

### `sessions`

식별된 사용자가 이후 모든 API 요청에서 "이 요청은 어느 user, 어느 workspace의 요청인가"를 판단하는 근거. identity 도메인의 책임 "request user/workspace context"가 이 테이블에서 나온다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| user_id | uuid | FK → users | 이 세션이 누구 것인지 — workspace isolation 검증(유저 A가 유저 B의 workspace 리소스를 못 보는 것)의 출발점. |
| workspace_id | uuid | FK → workspaces | 이 세션이 어느 workspace 컨텍스트로 요청하는지. |
| issuer | text | not null default 'maily' | JWT issuer claim과 대조 — 다른 시스템이 발급한 토큰을 거부하는 근거. |
| issued_at | timestamptz | not null | 세션 시작 시각. |
| expires_at | timestamptz | not null | 세션 만료 판단. |
| revoked_at | timestamptz | nullable | 로그아웃/강제 만료 시 즉시 무효화하는 값 — expires_at이 안 지났어도 이 값이 있으면 거부. |

## mail_sources

흐름 1 "계정 연결"의 핵심 산출물. 최상위 원칙 "연결 Gmail 계정은 브리핑, 요약, 알림, 정리 대상인 mail source다"가 이 도메인 전체의 존재 이유다. identity의 `users`와 분리한 이유는, 한 서비스 로그인 계정이 여러 Gmail 계정을 연결할 수 있고, Gmail 연결이 끊겨도 서비스 로그인 자체는 유지돼야 하기 때문이다.

### `connected_gmail_accounts`

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. mail_intake/briefing/gmail_actions 등 거의 모든 도메인이 이 id를 참조한다. |
| workspace_id | uuid | FK → workspaces | 어느 workspace의 소스인지 — 동일 계정 중복 연결 금지 불변식이 workspace 스코프로 적용된다. |
| gmail_address | text | not null | 어떤 Gmail 계정인지. Pub/Sub notification이 emailAddress로 오므로, 흐름 2 "fan-out to active connected sources by emailAddress"의 매칭 키가 된다. |
| display_name | text | nullable | 계정 구분 표시용. 값이 없으면 응답 시 `gmail_address`로 fallback(Task 3 test). |
| status | text | not null | 흐름 1 "초기 sync가 끝나기 전에도 계정은 syncing 상태로 목록에 보여야 한다", 흐름 7의 `permission_needed`, 흐름 8의 `disconnecting` — UI가 계정 상태를 안내하는 유일한 근거. |
| version | int | not null default 0 | 상태 전이마다 증가 — `gmail_source_connected`/`gmail_source_settings_changed` 이벤트 idempotency key disambiguator. |
| connected_at | timestamptz | not null | 연결 시각 — 재연결 시 이전 연결 이력과 구분. |
| disconnected_at | timestamptz | nullable | 흐름 8 disconnect 완료 시각. |

- UNIQUE 부분 인덱스 `(workspace_id, gmail_address) WHERE status <> 'disconnected'` — 동일 계정 중복 연결 금지 불변식은 활성 연결에만 적용, 재연결은 허용.

### `gmail_oauth_credentials` ◆

강제 invariant "OAuth token 원문은 연결 Gmail 소스 컨텍스트 밖에서 직접 읽을 수 없다"를 구현하는 테이블 그 자체. mail_intake와 gmail_actions는 이 테이블을 직접 읽지 않고 `GmailReaderPort`/`GmailMutationPort`를 통해서만 접근한다 — 그래서 이 테이블은 mail_sources 도메인 코드 밖에서는 아예 import되지 않아야 한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| connected_account_id | uuid | FK → connected_gmail_accounts, unique | 1:1 — 계정이 삭제/purge되면 자격증명도 같이 정리된다. |
| access_token_ciphertext | bytea | not null | Gmail API 호출에 실제로 쓰이는 자격증명(암호화). 평문 저장 금지 invariant. |
| refresh_token_ciphertext | bytea | not null | access token 만료 시 재발급에 쓰는 자격증명(암호화). |
| encryption_key_version | int | not null | 키 로테이션 시 어떤 키로 복호화해야 하는지 판단. |
| scope | text | not null | Gmail API가 실제로 허용한 권한 범위 — 사용자가 Google 쪽에서 권한을 축소했는지 판단 근거. |
| expires_at | timestamptz | not null | access token 만료 시점 — 만료 전에 refresh를 트리거. |
| revoked_at | timestamptz | nullable | 흐름 8 "token은 즉시 폐기" — 값이 세팅되면 이후 어떤 sync/action도 이 자격증명을 쓸 수 없다. |

- 암호화 알고리즘/키 관리 **[미정 — POC 필수 결정 사항, `app/core/crypto.py` 설계 전에 확정 필요]**. 후보: 로컬은 Fernet + `.env` 키, 운영은 KMS 연동. POC 단계는 Fernet 제안하되 키 로테이션 컬럼(`encryption_key_version`)은 지금부터 넣는다.

### `gmail_source_settings`

기능 표의 F02/F12에서 언급된 summary/briefing/notification toggle과 pause. 흐름 1 "assistant_decisions summary/proposal jobs when account settings allow"가 바로 이 값을 읽고 job을 만들지 말지 결정한다는 뜻이다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| connected_account_id | uuid | FK → connected_gmail_accounts, unique | 어느 계정의 설정인지. |
| briefing_enabled | bool | not null default true | 이 계정 메일을 오늘 브리핑에 포함할지. |
| summary_enabled | bool | not null default true | assistant_decisions가 `generate_summary` job을 큐잉할지 판단 — 꺼져 있으면 job 자체를 만들지 않는다(G6 summary off 불변식). |
| notification_enabled | bool | not null default true | notifications가 이 계정 관련 알림을 보낼지. |
| paused | bool | not null default false | 흐름 2 sync 자체를 건너뛸지 — 계정 연결은 유지한 채 일시정지. |
| updated_at | timestamptz | not null | 설정이 마지막으로 언제 바뀌었는지. |

## mail_intake

흐름 2 "새 메일 지속 동기화" 전체를 담당하는 도메인. 최상위 원칙 "Gmail은 원본 시스템이다. Maily DB는 브리핑, 판단, 처리 이력을 위한 snapshot이다"의 그 snapshot을 실제로 저장하는 자리다.

### `gmail_messages` ◆

흐름 2 "mail_intake message snapshot update" 스텝의 산출물. 최상위 원칙 "done은 독립 버튼 상태가 아니라 Gmail read/archive state와 사용자 action 결과에서 파생한다"의 근거 데이터가 이 테이블의 `is_read`/`is_archived`다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. briefing_items, gmail_action_commands 등이 이 id로 참조한다. |
| connected_account_id | uuid | FK → connected_gmail_accounts | 어느 계정의 메일인지 — 계정별 스코프 조인의 기준. |
| gmail_message_id | text | not null | Gmail 원본과 매핑하는 키. gmail_actions가 mutation을 실행할 때 이 ID로 Gmail API를 호출한다. |
| gmail_thread_id | text | not null | 스레드 단위 그룹핑 — 상세 패널에서 스레드 맥락을 보여줄 때 쓴다. |
| subject | text | nullable | 브리핑 카드/상세에 표시할 최소 메타데이터. |
| sender | text | nullable | 카드 표시, classification_rules 매칭 조건의 원재료. |
| snippet | text | nullable | Gmail이 주는 짧은 미리보기(raw body 아님) — 카드 문법 원칙("카드 응답에는 raw body를 넣지 않는다")을 지키면서도 스캔 가능하게 하는 최소 정보. |
| received_at | timestamptz | nullable | 브리핑 정렬(최신순) 기준. |
| is_read | bool | not null default false | "done"이 파생되는 원천 데이터 중 하나 — Gmail 쪽 읽음 상태. |
| is_archived | bool | not null default false | "done"이 파생되는 원천 데이터 중 하나 — Gmail 쪽 보관 상태. |
| last_history_id | bigint | nullable | 이 메시지가 마지막으로 확인된 history 시점 — 증분 동기화 정합성 확인용. |
| snapshot_version | int | not null default 0 | snapshot upsert마다 증가 — `generate_summary`/`classify_importance` job idempotency key disambiguator. |

- UNIQUE `(connected_account_id, gmail_message_id)` — snapshot upsert key. `backend-implementation-plan.md` Task 4는 이 키를 `(source_id, gmail_message_id)`로 표기하는데, `source_id`는 `connected_account_id`를 가리키는 같은 개념의 다른 이름이다 — 컬럼명은 이 문서(`connected_account_id`)를 따른다.

### `message_excerpts` ◆

강제 invariant "raw body 저장 금지"를 물리적으로 강제하는 테이블. Gmail 원문 대신 제한된 발췌만 `gmail_messages`와 분리된 별도 테이블에 두어, `gmail_messages`를 아무리 조회해도 원문이 나올 수 없게 한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| message_id | uuid | FK → gmail_messages, unique | 1:1 — 어느 메시지의 발췌인지. |
| excerpt_text | text | not null | assistant_decisions가 요약/중요도 판단에 넘길 최소 컨텍스트, 상세 화면 미리보기. |
| updated_at | timestamptz | not null | snapshot 갱신 시 발췌도 같이 최신화됐는지 추적. |

- 소스 확정(라이브 POC 확인, 2026-07-09): `messages.get(format=metadata)` 응답에 `snippet` 필드가 그대로 포함된다. 별도 `format=full` 호출 없이 이 `snippet` 값을 `excerpt_text`로 쓴다 — quota 20 unit(FULL) 대신 metadata 호출 하나로 스냅샷과 발췌를 동시에 얻는다.
- 길이 상한 자체는 여전히 **[미정: LLM 프롬프트 예산에서 결정]** — Gmail이 주는 snippet 길이(관찰상 200자 내외, "..." truncation)가 이미 짧아서 추가 자르기가 필요 없을 수 있다. raw body 저장 금지 불변식은 이 테이블 존재 자체로 강제 — `gmail_messages`에는 body 컬럼을 두지 않는다.

### `gmail_message_labels`

흐름 2에서 Gmail 쪽 라벨 변경(message added, deleted, label added, label removed)도 snapshot에 반영돼야 한다는 요구사항(Task 4 test)을 담당. `labels` 도메인의 `service_labels`와는 다른 테이블이다 — 이건 Gmail이 실제로 갖고 있는 라벨의 원본 snapshot이고, `gmail_label_mappings`와 대조해야 사용자 라벨이 Gmail에 실제로 반영됐는지 확인할 수 있다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| message_id | uuid | FK → gmail_messages | 어느 메시지에 붙은 라벨인지. |
| gmail_label_id | text | not null | Gmail 라벨 원본 ID — `Maily/영수증` 같은 라벨이 실제로 이 메시지에 붙어있는지 확인하는 키. |
| label_name | text | not null | 화면 표시/디버깅용 라벨 이름. |

- UNIQUE `(message_id, gmail_label_id)`.

### `gmail_sync_cursors`

흐름 2 `sync_gmail_delta` 커맨드의 입력값인 history cursor를 보관. 계정마다 마지막으로 어디까지 동기화했는지 저장하지 않으면 매번 full sync를 해야 하고, 이는 Gmail API 쿼터와 성능을 갉아먹는다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| connected_account_id | uuid | FK, unique | 계정당 커서 하나. |
| last_history_id | bigint | nullable | 다음 delta sync가 어디서부터 가져올지 결정하는 기준점. |
| watch_expiration_at | timestamptz | nullable | Pub/Sub watch 갱신 스케줄링 근거 — 만료 전에 renew job이 트리거된다. |
| last_successful_sync_at | timestamptz | nullable | 마지막 성공 시각이 오래됐으면 흐름 7 알림/복구가 필요하다는 판단 근거. |
| cursor_status | text | not null default 'valid' | Gmail이 커서를 더 이상 인식 못 하는 경우(너무 오래된 history) `invalid`로 바뀌고, 이 값이 흐름 2 "invalid cursor → full resync 트리거"의 분기 조건이 된다. |

### `gmail_watch_registrations`

Gmail Pub/Sub watch는 최대 7일만 유효하다 — 갱신하지 않으면 새 메일 알림 자체가 끊긴다. 흐름 2의 진입점("Gmail mailbox change → Google Cloud Pub/Sub")이 살아있으려면 이 등록이 항상 최신이어야 한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| connected_account_id | uuid | FK | 어느 계정의 watch인지. |
| topic_name | text | not null | 어느 Pub/Sub topic을 구독 중인지 — live 환경 설정에 의존하는 값. |
| expiration | timestamptz | not null | `renew_watch` job이 이 값을 기준으로 갱신을 스케줄링한다. |
| status | text | not null default 'active' | 이 계정이 지금 실시간 알림을 받을 수 있는 상태인지 — 흐름 7 recovery 판단과 연결. |

### `gmail_notification_events`

흐름 2 진입 스텝 "Gmail mailbox change → Google Cloud Pub/Sub → mail_intake process_gmail_notification"의 입력을 기록. Pub/Sub는 at-least-once 전달이라 같은 notification이 중복으로 올 수 있어 dedupe가 필요하다(Event Catalog `gmail-notification:{email}:{history_id}`).

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| email_address | text | not null | Pub/Sub payload 원본 — 어느 계정의 변경인지, 흐름 2 fan-out 매칭에 쓰인다. |
| history_id | bigint | not null | Pub/Sub payload 원본 — 어느 시점의 변경인지. |
| dedupe_key | text | not null, unique | 같은 email_address+history_id가 중복 전달돼도 한 번만 처리하게 막는다. |
| processed_at | timestamptz | nullable | 아직 처리 안 된 notification을 재시도 대상으로 골라내는 기준. |

### `sync_runs`

흐름 2에서 delta/full sync가 실행될 때마다 결과를 기록. 실패 원인 추적, 재시도 판단, "몇 개 메시지가 바뀌었는지"는 `gmail_snapshot_changed` 이벤트 payload의 근거 데이터가 된다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. `gmail_snapshot_changed` 이벤트의 idempotency key(`source:{source_id}:snapshot:{sync_run_id}`)가 이 id를 쓴다. |
| connected_account_id | uuid | FK | 어느 계정의 sync인지. |
| run_type | text | not null | delta면 가벼운 쿼리, full이면 전체 재동기화 — 어떤 경로인지 구분해 쿼터/성능을 모니터링. |
| trigger | text | not null | 왜 이 sync가 실행됐는지(notification/poll/manual/initial) — 디버깅 시 "왜 갑자기 폴링이 돌았지"에 답한다. |
| status | text | not null | 진행중/성공/실패. |
| started_at | timestamptz | not null | 시작 시각. |
| finished_at | timestamptz | nullable | 종료 시각 — 소요 시간 계산. |
| messages_changed_count | int | not null default 0 | 이 실행으로 몇 개 메시지가 갱신됐는지 — `gmail_snapshot_changed` 이벤트 payload에 들어갈 근거 데이터. |
| error_reason | text | nullable | 실패 원인(권한 오류인지 네트워크인지) — 흐름 7 recovery 판단에 쓰인다. |

## briefing

강제 invariant "브리핑 read model은 재생성 가능해야 한다"를 구현하는 도메인. 흐름 3 "briefing이 snapshot, summary, 사용자 item state를 조합해 카드 목록을 만든다"의 산출물이자, 흐름 2에서 한 메일에 대해 최소 3번(스냅샷 저장 시, 요약 완료 시, 중요도 판단 완료 시) message_id 단위 부분 재생성이 일어나야 한다는 요구사항을 두 테이블로 나눠 감당한다.

### `briefing_items` (재생성 가능 projection) ◆

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| connected_account_id | uuid | FK | 흐름 3 "returns account-grouped card list" — 계정별로 묶어서 응답하기 위한 그룹핑 키. |
| message_id | uuid | FK → gmail_messages | 원본 메시지와 매핑, 그리고 재생성 시 upsert 키. |
| section | text | not null | 카드가 어느 섹션에 배치되는지. 최상위 원칙 "기본 브리핑 섹션은 파생 목록이다 — 사용자가 직접 이동시키지 않는다"의 값 자체. 섹션 값 **[미정: `product-wireframe-final.md` 카드 섹션 정의 확인 필요]** |
| importance_band | text | nullable | assistant_decisions 결과를 미리 합쳐둔다 — 카드 응답 시점에 다른 테이블을 조인하지 않고 바로 읽기 위한 denormalize. |
| summary_text | text | nullable | 위와 동일한 이유의 denormalize. metadata-only 계정이면 null. |
| rebuilt_at | timestamptz | not null | 이 row가 마지막으로 언제 재생성됐는지 — 오래된 카드(재생성 누락) 감지. |

- UNIQUE `(connected_account_id, message_id)` — message_id 단위 부분 재생성 upsert key.
- 이 테이블은 언제든 drop-and-rebuild 가능해야 한다. 진짜 상태는 `gmail_messages` + `message_summaries` + `message_importance_classifications`.

### `briefing_item_states` (durable) ◆

강제 invariant "`seen`, `remind_later` 같은 사용자 item state는 재생성 가능한 projection과 분리된 durable state다"를 구현하는 테이블 그 자체. `briefing_items`를 통째로 drop-and-rebuild해도 사용자가 "읽음 처리"한 사실은 사라지면 안 된다 — 그래서 `briefing_items`가 아니라 `gmail_messages`를 직접 참조한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| message_id | uuid | FK → gmail_messages, unique | projection(`briefing_items`)이 아니라 원본 메시지를 직접 참조해 생명주기를 분리한다. |
| seen | bool | not null default false | 사용자가 카드를 확인했는지. |
| seen_at | timestamptz | nullable | 언제 확인했는지. |
| remind_later_at | timestamptz | nullable | F09 "나중에" 처리 — 사용자가 다시 보고 싶은 시점. |
| updated_at | timestamptz | not null | 마지막 상태 변경 시각. |

### `reminders`

`remind_later_at` 하나만으로는 "몇 시에 다시 브리핑에 올릴지"를 골라내려면 전체 item_state를 스캔해야 한다. 재활성화 job이 폴링할 전용 대상 목록을 별도로 분리한 것이 이 테이블이다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| briefing_item_state_id | uuid | FK | 어느 아이템의 리마인더인지. |
| remind_at | timestamptz | not null | 이 시각이 지나면 재활성화 대상으로 job이 픽업한다. |
| reactivated_at | timestamptz | nullable | 이미 처리된 리마인더를 중복 처리하지 않게 막는다. |
| status | text | not null default 'pending' | job 폴링 대상 필터(pending만 조회). |

## labels

최상위 원칙 "사용자가 직접 이동시키는 목적지는 Gmail `Maily/` 라벨과 동기화되는 사용자 라벨이다"를 구현하는 도메인. 흐름 4 "사용자 라벨 이동과 다음부터 여기로"의 앞부분(라벨 목적지 검증, correction signal 기록)을 담당한다.

### `service_labels`

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 라벨은 workspace 단위로 존재. |
| name | text | not null | 사용자가 지정한 라벨 이름. |
| order_index | int | not null | 사이드바 표시 순서. |
| hidden | bool | not null default false | 숨김 처리된 라벨(삭제는 아니지만 목록에는 안 보임 — Gmail 매핑은 유지). |
| updated_at | timestamptz | not null | 이름/순서/숨김 변경 시각. |

- UNIQUE `(workspace_id, name)`.

### `gmail_label_mappings`

강제 invariant는 아니지만 module-boundaries.md가 명시한 검증 항목 "`Maily/` mapping 안정성" — 사용자가 라벨 이름을 바꿔도(rename) Gmail 쪽 라벨과의 연결이 끊기면 안 된다는 요구사항을 위해 매핑을 `service_labels`와 별도 테이블로 분리했다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| service_label_id | uuid | FK → service_labels, unique | 1:1 — 어느 사용자 라벨의 매핑인지. |
| connected_account_id | uuid | FK | Gmail 라벨은 계정별로 존재하므로, 어느 계정에 생성된 매핑인지 구분해야 한다. |
| gmail_label_id | text | nullable | Gmail에 실제 생성된 후 채워진다 — 생성 전엔 null인 상태로 "생성 의도"만 존재할 수 있다(Command Catalog `create_or_update_label`의 결과가 "Gmail mapping intent"인 이유). |
| gmail_label_name | text | not null | `Maily/{label_name}` 형태로 Gmail에 실제 보이는 이름. |

- **라이브 POC 확인(2026-07-09)**: 부모 라벨 `Maily`가 계정에 존재하지 않는 상태로 `Maily/{label_name}`을 바로 생성하면 Gmail 사이드바에 flat하게(중첩 안 됨) 표시된다. 부모 `Maily` 라벨을 생성하고 나서야 기존 자식 라벨까지 소급으로 중첩된다. 계정당 `Maily` 부모 라벨이 정확히 하나만 있어야 하므로, `create_or_update_label` 서비스 로직은 계정별로 `Maily` 부모 라벨 존재를 먼저 get-or-create로 보장한 뒤 자식 라벨을 만든다 — 매 계정 최초 연결 시 한 번만 필요한 선행 단계이며, 이 보장 여부를 추적할 별도 컬럼은 두지 않는다(매번 `labels.list`로 존재 확인 후 없으면 생성하는 idempotent 호출로 충분).

### `label_correction_signals`

흐름 4 "labels records label correction signal" 스텝의 산출물. 사용자가 메일을 특정 라벨로 옮기는 행동 자체가 "이런 메일은 이렇게 분류해줘"라는 신호이고, F08 "다음부터 여기로"의 유일한 입력 데이터다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| message_id | uuid | FK | 어떤 메일이 옮겨졌는지 — assistant_decisions가 발신자/제목 패턴을 여기서 추출한다. |
| service_label_id | uuid | FK | 어디로 옮겼는지. |
| actor_id | uuid | FK → users | 누가 옮겼는지 — 자동 규칙 신뢰도 계산 시 실제 사용자 행동인지 구분하는 근거가 될 수 있다. |

## gmail_actions

최상위 원칙 "Gmail 변경은 반드시 command ledger, activity log, Undo 가능 여부를 거친다"를 구현하는 도메인. 흐름 5 "Gmail 변경 액션" 전체가 이 도메인의 세 테이블을 순서대로 지나간다.

### `gmail_action_commands`

command ledger 그 자체. 흐름 5 "gmail_actions creates command: pending → ... → applied/failed/compensating/undone"이 이 테이블의 상태 전이와 정확히 일치한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| connected_account_id | uuid | FK | 어느 계정에 대한 mutation인지 — 워커가 `GmailMutationPort` 호출 시 이 계정 자격증명을 쓴다. |
| message_id | uuid | FK, nullable | 어느 메시지 대상인지(라벨 생성처럼 메시지와 무관한 액션 대비 nullable). |
| action_type | text | not null | 어떤 mutation을 실행할지 — 워커가 `GmailMutationPort`의 어느 메서드를 호출할지 분기하는 키. |
| payload | jsonb | not null | mutation 실행에 필요한 추가 데이터. Gmail `messages.modify`가 `addLabelIds[]`/`removeLabelIds[]` 배열 하나로 mark_read/archive/label 변경을 전부 처리하므로 `{add_label_ids: [], remove_label_ids: []}` 형태로 둔다 — action_type별로 payload shape을 따로 만들지 않는다(`mark_read`는 remove_label_ids에 `UNREAD`, `archive`는 remove_label_ids에 `INBOX`, `read_and_archive`는 둘 다 포함). |
| idempotency_key | text | not null, unique | 사용자가 버튼을 두 번 눌러도 Gmail에 mutation이 두 번 나가지 않게 막는다(클라이언트 결정 키). |
| status | text | not null default 'pending' | 흐름 5의 상태 전이 그 자체 — 워커가 `pending`만 골라 실행한다. |
| version | int | not null default 0 | 상태 전이마다 증가 — `gmail_action_applied`/`gmail_action_failed`/`gmail_action_undone` 이벤트 idempotency key disambiguator. |
| changed | bool | nullable | Gmail 쪽이 실제로 상태를 바꿨는지 — 이미 읽음 처리된 메일에 mark_read를 또 요청하면 `changed=false`로 응답해, UI가 "이미 처리됨"을 구분할 수 있다. |
| requested_by | uuid | FK → users | 누가 요청했는지 — 자동화 실행과 사용자 액션을 구분해 activity log에 표시. |
| requested_at | timestamptz | not null | 요청 시각. |
| applied_at | timestamptz | nullable | 적용 시각 — undo 가능 시간 판단, 지연 감지. |
| failed_at | timestamptz | nullable | 실패 시각. |
| error_reason | text | nullable | 실패 원인 — 재시도 정책 판단 근거. |

### `activity_logs`

강제 invariant "activity log는 감사와 사용자 설명에 필요한 최소 정보만 남긴다"를 구현. F11 활동 로그. `command_id`를 nullable로 둔 이유는 자동화로 발생한 활동(예: 정리 제안 자동 적용)이 사용자 커맨드 없이도 기록될 수 있기 때문이다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| command_id | uuid | FK → gmail_action_commands, nullable | 어느 command 실행 결과인지(nullable — 시스템 이벤트성 활동 대비). |
| action_summary | text | not null | 사용자에게 "무엇을 했는지" 설명할 최소 문장. message body 포함 금지 invariant가 이 컬럼에 적용된다. |
| actor_id | uuid | FK, nullable | null이면 자동화가 한 일 — UI에 "자동으로 처리됨"을 표시하는 근거. |
| occurred_at | timestamptz | not null | 활동 로그 타임라인 정렬 기준. |

### `undo_actions`

최상위 원칙 "Gmail 변경은 반드시 command ledger, activity log, Undo 가능 여부를 거친다"를 구현. undo 실행도 직접 Gmail을 호출하지 않고 새 command를 만들어 command ledger를 다시 거친다 — `reverse_command_id`가 그 경계를 강제한다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| activity_id | uuid | FK → activity_logs | 사용자가 activity log 화면에서 undo를 누르는 대상. |
| original_command_id | uuid | FK → gmail_action_commands | 되돌릴 원래 command. |
| reverse_command_id | uuid | FK → gmail_action_commands, nullable | undo 실행 시 새로 생성되는 역연산 command — command ledger를 다시 거치게 강제하는 장치. |
| undo_available | bool | not null | 액션 타입별로 undo가 불가능한 경우(예: 이미 archive된 걸 다시 archive)가 있어, UI가 undo 버튼 노출 여부를 이 값으로 판단한다. |
| undone_at | timestamptz | nullable | 이미 undo 됐는지 — 중복 undo 방지. |

## assistant_decisions

강제 invariant는 아니지만 구현 원칙에 명시된 "`generate_summary`와 `classify_importance`는 별도 job, 별도 테이블로 분리해 독립적으로 실패·재시도한다"가 이 도메인 테이블 구성의 핵심이다. 흐름 2 후반부(요약/중요도 판단)와 흐름 6 "자동화와 정리 검토"를 담당한다.

### `summary_jobs` / `message_summaries` ◆

요약이 실패해도 중요도 판단은 별개로 진행돼야 한다는 요구사항이, job과 결과 테이블을 importance 쪽과 분리한 이유다.

| 테이블 | 컬럼 | 목적 |
|---|---|---|
| summary_jobs | id | 행 식별자. |
| summary_jobs | message_id (FK) | 어느 메시지의 요약 작업인지. |
| summary_jobs | status | 진행 상태 — 실패 시 이 job만 재시도, importance_jobs와 독립. |
| summary_jobs | attempt_count | 재시도 횟수 제한 판단. |
| summary_jobs | finished_at | 완료 시각 — `summary_completed` 이벤트 발행 시점 판단. |
| message_summaries | id | 행 식별자. |
| message_summaries | message_id (FK, unique) | 1메시지 1요약. |
| message_summaries | summary_text (nullable) | G6 "summary off 계정은 metadata-only fallback" — null이면 이 계정은 요약을 껐다는 뜻, UI는 이 필드로 fallback 표시를 분기. |
| message_summaries | is_metadata_only (bool) | summary_text가 null인 이유를 명시적으로 구분(끔 vs 아직 처리 전 vs 실패). |
| message_summaries | summary_version (int) | 재요약 시 이전 결과와 구분, `summary_completed` 이벤트 idempotency key(`message:{message_id}:summary:{summary_version}`)에 쓰인다. |
| message_summaries | model_name (text) | 나중에 provider/모델이 바뀌었을 때 결과 재현성 추적. |

### `importance_jobs` / `message_importance_classifications` ◆

흐름 2 "importance classification이 아직 끝나지 않은 메일은 아이템 단위 대기 상태를 따로 만들지 않는다"는 요구사항을, 이 테이블에 아직 row가 없는 상태 자체로 "판단 전"을 표현해 구현한다 — 별도 pending 플래그 컬럼을 두지 않는다.

| 테이블 | 컬럼 | 목적 |
|---|---|---|
| importance_jobs | id | 행 식별자. |
| importance_jobs | message_id (FK) | 어느 메시지의 판단 작업인지. |
| importance_jobs | status | summary_jobs와 동일 상태값, 독립 실행. |
| importance_jobs | attempt_count | 재시도 횟수 제한 판단. |
| importance_jobs | finished_at | 완료 시각. |
| message_importance_classifications | id | 행 식별자. |
| message_importance_classifications | message_id (FK, unique) | 1메시지 1판단. |
| message_importance_classifications | importance_band (text) | "판단 결과(band, reason)는 이벤트 payload 필드로만 구분하고, 결과별로 이벤트 종류를 늘리지 않는다"는 원칙이 DB에도 동일하게 적용 — band별로 테이블을 나누지 않는다. 값 **[미정: product 쪽 등급 정의 필요 — 예 urgent/normal/low]** |
| message_importance_classifications | reason (text) | AI 판단 이유. 최상위 원칙 "AI 판단 이유는 기본으로 노출하지 않는다"에 따라 API 응답 기본값에서는 빠지고, 필요 시에만 노출. |
| message_importance_classifications | classification_version (int) | 재판단 시 버전 구분, `importance_classified` 이벤트 idempotency key에 쓰인다. |

- raw prompt/body 미저장 불변식 — 두 job 테이블 모두 LLM 요청 payload를 컬럼으로 두지 않는다. 감사 필요하면 payload 필드 목록만 로그(별도 `assistant_decisions` 애플리케이션 로그, DB 테이블 아님)로 남긴다.

### `classification_rules` ◆

F08에서 승인된 규칙만 여기 들어온다(`rule_suggestions`에서 승인된 결과가 옮겨짐). 새 메일이 들어올 때 이 규칙과 매칭해 자동 라벨링/제안 생성을 판단하는 근거다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| service_label_id | uuid | FK | 매칭되면 어느 라벨로 분류할지. |
| match_condition | jsonb | not null | 발신자/제목 패턴(jsonb로 유연하게 — 패턴 종류가 늘어나도 스키마 변경 없이 대응). |
| active | bool | not null default true | 사용자가 규칙을 껐다 켰다 할 수 있게. |

### `rule_suggestions` ◆

흐름 4 "assistant_decisions may create rule_suggestion from correction signal" 스텝의 산출물. 사용자가 반복해서 같은 패턴으로 라벨 이동을 시키면 자동화 후보를 제안하되, 승인 전까진 활성 규칙이 아니다(F08 "승인/제외 큐").

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| correction_signal_id | uuid | FK → label_correction_signals | 어떤 사용자 행동이 이 제안의 근거인지 추적 가능하게. |
| suggested_condition | jsonb | not null | 제안하는 매칭 조건. |
| status | text | not null default 'pending' | 승인/거절 대기 큐 필터. |
| decided_at | timestamptz | nullable | 언제 결정됐는지. |

### `cleanup_proposals` ◆

F10 정리 검토. 구현 원칙 "낮은 확신 제안은 개별 승인 큐로 가고 승인 시 gmail_actions command를 요청한다"가 `confidence_band`와 `gmail_action_command_id`로 구현된다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| message_id | uuid | FK | 어느 메일에 대한 제안인지. |
| proposed_action | text | not null | 무슨 조치를 제안하는지 — `gmail_action_commands.action_type`과 동일 값 집합. |
| confidence_band | text | not null | 자동 실행할지, 사용자 승인을 받을지, 아예 제안하지 않을지를 가르는 임계값 구분. |
| status | text | not null default 'pending' | F10 승인/제외 큐의 필터. |
| before_state | jsonb | not null | 사용자에게 "이렇게 바뀝니다"를 보여주는 승인 화면 UX용 미리보기. |
| after_state | jsonb | nullable | 위와 동일한 이유. |
| gmail_action_command_id | uuid | FK, nullable | 승인되면 실제 gmail_actions command로 연결된다 — 정리 판단(assistant_decisions)과 실행(gmail_actions)이 다른 도메인이라는 경계 설계 원칙을 이 FK가 물리적으로 구현. |
| decided_at | timestamptz | nullable | 언제 승인/거절됐는지. |

- 임계값(confidence_band 경계) **[미정 — LLM POC에서 실측 후 결정]**.

## notifications

최상위 원칙 "알림은 일반 landing page가 아니라 기존 화면과 selected item으로 착지한다"를 구현하는 도메인. F13/F14와 흐름 7 "권한 오류와 복구"의 사용자 안내 화면을 담당한다.

### `notification_subscriptions`

F13 브라우저 푸시 — 어느 브라우저/기기가 이 사용자의 알림을 받을 자격이 있는지 기록.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| user_id | uuid | FK | 어느 사용자의 구독인지. |
| endpoint | text | not null | 브라우저 Push API 구독 정보(표준 Web Push 스펙) — 실제 push를 보낼 대상. |
| keys | jsonb | not null | Push 암호화에 필요한 키 세트. |
| revoked_at | timestamptz | nullable | 구독 해제/만료 시 더 이상 발송하지 않게 막는 값. |

### `notification_events`

최상위 원칙 "알림은 ... 기존 화면과 selected item으로 착지한다"가 `route_target` 컬럼으로 구현된다. 흐름 7 recovery 안내도 이 테이블을 통해 나간다.

| 컬럼 | 타입 | 제약 | 목적 |
|---|---|---|---|
| id | uuid | PK | 행 식별자. |
| workspace_id | uuid | FK | 조회 스코프. |
| notification_type | text | not null | 어떤 종류의 알림인지 — 화면 분기 기준. |
| route_target | jsonb | not null | 어느 화면 + 어느 아이템으로 이동시킬지. generic landing 금지 invariant를 지키기 위한 필수 데이터 — 이 값 없이는 "일반 landing page"가 될 수밖에 없다. |
| read_at | timestamptz | nullable | 알림 확인 여부. |

## 열린 결정 사항 (스키마 확정 전 필요)

| 항목 | 막는 것 | 제안 |
|---|---|---|
| OAuth token 암호화 방식/키 관리 | `gmail_oauth_credentials`, `app/core/crypto.py` | POC: Fernet + env 키, `encryption_key_version` 컬럼으로 로테이션 대비 |
| excerpt 길이 상한 | `message_excerpts`, LLM 프롬프트 예산 | POC 계약 문서에서 LLM 토큰 예산과 같이 결정 |
| importance_band 값 집합 | `message_importance_classifications`, `briefing_items.importance_band` | product-wireframe 카드 등급 정의 확인 |
| briefing section 값 집합 | `briefing_items.section` | `product-wireframe-final.md` 카드 섹션 표 확인 |
| confidence_band 경계값 | `cleanup_proposals` | LLM POC 실측 후 결정 |
| job lock timeout | `job_runs.locked_at` | POC 기본 60s, 운영 중 튜닝 |

## 다음 단계

별도 POC 계약 문서를 만들지 않고 `docs/goals/backend-implementation-plan.md`의 "Gmail API POC 확인 사항" 섹션에 Gmail 쪽 확인 결과를 반영했다. LLM 관련 [미정](importance_band, confidence_band, excerpt 길이 상한)은 지금 결정하지 않는다 — LLM provider가 정해지는 시점에 파싱해서 반영하고, 그 전까지 `fake_llm` 계약만 유지한다. 확정되면 이 문서의 [미정] 표시를 갱신한다.
