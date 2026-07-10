# identity 세부 플랜 (Identity & Workspace)

기준: `module-boundaries.md`(컨텍스트 F01·흐름 1 첫 스텝·workspace isolation invariant·Command/Event Catalog), `db-schema.md`(identity 섹션), `_integration-contract.md`(§1 Alembic·§3 router prefix `/auth`·§4 노출 인터페이스·§5 status). 대응 Task: 2(Identity & Workspace).

## 도메인 책임 요약

Maily 서비스에 로그인한 사용자, workspace, session/JWT, membership, 그리고 모든 인증 API가 쓰는 user/workspace request context. **소유 안 함**: 연결 Gmail 계정 OAuth token(mail_sources), Gmail message snapshot(mail_intake).

강제 invariant(이 도메인이 지키는 것):
- 서비스 로그인 계정 ≠ 연결 Gmail 계정. 여기서 만드는 user는 Maily에 로그인한 사람이지, 나중에 연결하는 Gmail 계정이 아니다(그건 mail_sources 소관).
- workspace isolation — 유저 A의 세션으로 유저 B workspace 리소스에 접근 불가. 모든 도메인 쿼리는 request context의 `workspace_id`로만 스코프된다.
- 재로그인 시 같은 `google_subject`는 기존 workspace를 재사용한다(새 workspace/membership 생성 금지).
- JWT는 `issuer=maily`로 발급·대조하고, `sessions.revoked_at`이 세팅되면 `expires_at` 미경과여도 즉시 무효화한다.
- 1 user = 1 workspace(POC). 멤버 다수 시나리오는 `workspace_members` 스키마만 열어두고 로직은 만들지 않는다.

소유 테이블: `users`, `workspaces`, `workspace_members`, `sessions`.
소유 event(producer): 없음 — Event Catalog에 identity가 producer로 등재된 event가 없다(§Event/Job).
소유 job: 없음 — Job Registry에 identity handler가 없다.

## 세션 유효성 상태 (`sessions` 파생)

`sessions`에는 status enum 컬럼이 없다(§5). 유효성은 `expires_at`/`revoked_at`에서 파생한다.

```
issue_session
  → valid                issued_at ≤ now < expires_at, revoked_at is null
valid
  → expired              now ≥ expires_at (자연 만료)
valid
  → revoked              revoked_at 세팅 (로그아웃·강제 만료, 즉시 무효화)
```

판정 규칙:
- `revoked`가 `expired`보다 우선 — 강제 로그아웃은 만료를 기다리지 않고 즉시 발효.
- 만료·폐기 세션은 다른 상태로 복귀 없음. 재인증은 새 `sessions` row(issue_session).
- 재로그인 시 이전 세션을 폐기할지는 **[미확정: 다중 기기 세션 정책]** — POC는 이전 세션 유지(revoke 안 함).

---

## 동작: `google_login`

- 소유 테이블: `users`(insert 또는 `last_login_at` update), `workspaces`(신규만 insert), `workspace_members`(신규만 insert, role=owner)
- 발행 event: 없음(Event Catalog에 identity producer 미등재). 흐름 1은 mail_sources의 `gmail_source_connected`에서 outbox가 시작하고, identity 단계는 context 확립까지만 담당.
- 산출물: issue_session(서명된 JWT)
- 입력 → 결과: `{oauth callback profile: google_subject, email, display_name}` → user/workspace/membership 확정 + 발급된 세션
- API: `POST /auth/google/callback`

체크리스트:
- **[정상]** 신규 `google_subject` → `users` insert(google_subject unique) + `workspaces` insert 1개 + `workspace_members` insert(role=`owner`) + `last_login_at=now()` → issue_session. user+workspace+membership는 한 트랜잭션.
- **[멱등]** 재로그인(같은 google_subject). `users` insert 안 함 — 기존 user 조회 후 기존 workspace 재사용(새 workspace/membership 생성 금지), `last_login_at`만 갱신, 새 세션 발급. `google_subject` unique가 "같은 사람" 판단 키(Task 2 relogin test).
- **[동시]** 같은 `google_subject`로 두 콜백 동시(더블클릭·재시도). `users.google_subject` unique가 두 번째 insert를 DB 레벨에서 거부(IntegrityError) → 두 번째 요청은 기존 user 조회로 폴백. workspace/membership은 한 벌만.
- **[선행조건]** callback profile에 `google_subject`/`email` 누락 → 422, 아무 insert 없음. Google code 교환 실패(원격 오류) → 401/502, user 생성 안 함. Google client 미준비 단계는 mocked profile로 계약 검증(module-boundaries 차단조건).
- **[부분실패]** user insert 성공·workspace insert 실패 → 전체 롤백(user+workspace+membership 한 트랜잭션). membership 없이 user만 남거나 workspace 없이 membership만 남는 상태 불가.
- **[권한]** N/A — 로그인은 인증 진입점이라 선행 세션이 없다. 다만 workspace 배정은 이 user 전용이며, 다른 user의 workspace에 membership을 붙이지 않는다.
- **[데이터경계]** 재로그인이 절대 다른 user의 workspace를 재사용하지 않음 — `google_subject`로만 매칭한다. `email`이 같아도 `google_subject`가 다르면 별개 user(Google 계정 교체 대비). 1 user=1 workspace 유지.
- 검증: `tests/domains/identity/test_google_login.py::{test_new_subject_creates_user_workspace_membership, test_relogin_reuses_existing_workspace, test_same_email_different_subject_is_a_new_user}`. 테스트 부재 — `test_concurrent_login_single_user`([동시] google_subject 동시 insert 방어).

## 동작: `issue_session` / `verify_session`

- 소유 테이블: `sessions`(issue 시 insert, revoke 시 `revoked_at` update)
- 산출물: JWT claims `{user_id, workspace_id, issuer=maily, issued_at, expires_at}`
- 서명/검증 위치: `app/core/security.py`(Task 2 Files, identity가 생성)
- API: 발급은 `google_login` 결과로 반환. 검증은 독립 엔드포인트가 아니라 모든 인증 요청의 dependency(§resolve_request_context)로 호출. revoke(로그아웃) 엔드포인트는 §3에 미기재 — POC에서 확정 전까지 `revoked_at` 세팅 연산으로만 정의.

체크리스트:
- **[정상]** issue: 로그인 성공 시 `sessions` insert(`user_id`, `workspace_id`, `issuer='maily'`, `issued_at`, `expires_at`) + 동일 claim의 서명 JWT 발급. verify: 요청 JWT 서명 검증 → `issuer='maily'` 대조 → `expires_at` 미경과 → 해당 세션 `revoked_at is null` 확인 → 통과.
- **[멱등]** verify는 순수 읽기 — 같은 토큰을 여러 번 검증해도 상태 변화 없음. issue는 매 로그인마다 새 세션(의도적으로 멱등 아님 — 세션은 로그인 이벤트 단위 발급). 이전 세션 revoke 여부는 §세션 상태의 [미확정] 정책을 따름.
- **[동시]** 같은 user가 여러 기기에서 동시 세션 발급 가능 — 각 세션 독립 row. `revoked_at` 세팅과 verify가 동시에 나면 verify가 `revoked_at`을 확인하므로 revoke 이후 요청은 거부(즉시 무효화 invariant).
- **[선행조건]** verify에서 JWT 없음/서명 불일치/`issuer≠maily`/`expires_at` 경과/`revoked_at` 세팅 중 하나라도 걸리면 401. JWT의 `workspace_id` claim이 세션 row 값과 불일치 → 401(토큰 변조 방어).
- **[부분실패]** `sessions` insert 성공·JWT 서명 실패(`MAILY_JWT_SECRET` 미설정) → 500, 세션 발급 자체 롤백(토큰 없이 세션 row만 남는 상태 방지). verify 중 DB 조회 실패 → 500, 요청 거부(fail-closed — 인증을 통과시키지 않는다).
- **[권한]** verify가 인증 게이트 그 자체. 유효 토큰 없으면 인증 API 접근 불가. `issuer` claim으로 타 시스템 발급 토큰을 거부한다.
- **[데이터경계]** JWT의 `workspace_id`는 세션 발급 시점 workspace로 고정 — 요청자가 claim을 바꿔도 서명 검증에서 걸린다. `revoked_at`은 `expires_at` 미경과보다 우선 적용.
- 검증: `tests/domains/identity/test_workspace_resolution.py::{test_session_claims_contain_user_workspace_issuer, test_expired_session_rejected, test_revoked_session_rejected}`, `tests/core/test_security.py::test_verify_rejects_foreign_issuer`.

## 동작: `resolve_request_context`

- 성격: 모든 인증 API가 의존하는 request dependency. verify_session 결과로 `(user_id, workspace_id)` context를 확정하고, workspace isolation을 강제하는 지점.
- 소유 테이블: 읽기만 — `sessions`, `users`, `workspaces`
- 산출물: `RequestContext{user_id, workspace_id}` — 이후 모든 도메인 쿼리의 `workspace_id` 스코프 근거.
- API: 독립 엔드포인트 아님. 인증이 필요한 모든 라우터가 이 dependency를 통과.

체크리스트:
- **[정상]** 유효 세션 → `RequestContext(user_id, workspace_id)` 반환. 이후 핸들러는 이 `workspace_id`로만 데이터를 조회·변경한다.
- **[멱등]** 순수 읽기 dependency — 부수효과 없음, 매 요청 재평가. N/A(상태 변화 없음).
- **[동시]** 동시 요청은 각각 독립적으로 context를 해석 — 공유 상태 없음. N/A(공유 상태 없음).
- **[선행조건]** verify_session 실패(§verify) → 401, context 미생성 → 핸들러 진입 자체 차단. 세션의 `workspace_id`가 삭제된 workspace를 가리키는 경우는 POC에선 미발생(1 user=1 workspace, workspace 삭제 경로 없음).
- **[부분실패]** context 해석 중 DB 오류 → 500, fail-closed(핸들러 진입 금지). user만 있고 workspace 없는 부분 context 반환 금지.
- **[권한]** 핵심 — workspace isolation. 유저 A 세션으로 유저 B workspace 리소스를 요청해도, 모든 도메인 쿼리가 `context.workspace_id`(=A)로 스코프되므로 B 리소스는 결과에서 빠진다. `context.workspace_id`는 세션 claim이 유일 근거이며 요청 파라미터로 덮어쓸 수 없다(Task 2 isolation test).
- **[데이터경계]** `context.workspace_id` ≠ 조회 대상 리소스의 `workspace_id` → 빈 결과 또는 404(존재 노출 방지). URL/body의 `workspace_id` 파라미터는 무시 — 항상 세션 claim 우선.
- 검증: `tests/domains/identity/test_workspace_isolation.py::test_user_a_session_never_resolves_to_user_b_workspace`, `tests/domains/identity/test_workspace_resolution.py::test_context_scopes_to_session_workspace`. 테스트 부재 — `test_workspace_id_not_overridable_by_param`(요청 파라미터의 workspace_id를 세션 claim이 무시하는지 검증).

## Event / Job (N/A)

- 발행 event: 없음. Event Catalog에 identity가 producer인 event가 없다 — identity는 context를 확립할 뿐, outbox 발행은 mail_sources(`gmail_source_connected`)부터 시작한다. 따라서 event idempotency key도 N/A.
- 소유 job: 없음. Job Registry(§2)에 identity handler가 없다.
- PURGE_HANDLER: `None`. 서비스 로그인 계정 데이터는 Gmail 계정 disconnect purge(Task 13, 흐름 8) 대상이 아니다 — 서비스 로그인은 Gmail 연결과 독립적으로 유지된다.
- 노출 심볼(§4): `router`=APIRouter(있음), `JOB_HANDLERS`={}, `EVENT_CONSUMERS`={}, `PURGE_HANDLER`=None.

## Read API (경량 — 6축 대신 정상/필터/빈상태/권한)

### `GET /auth/session` (현재 세션 컨텍스트)
- **[정상]** 현재 세션의 user/workspace 요약(`user_id`, `email`, `display_name`, `workspace_id`, workspace `name`) 반환.
- **[필터]** N/A — 목록이 아니라 현재 세션 단건 조회.
- **[빈상태]** 유효 세션 없음 → 401(빈 바디 아님 — 미인증은 에러로 응답).
- **[권한]** 자기 세션만 — 다른 user 세션을 조회하는 경로 없음. JWT claim 외 파라미터로 대상을 지정할 수 없다.
- 검증: `tests/domains/identity/test_router.py::{test_google_callback_creates_session_and_get_session_returns_summary, test_get_session_without_token_returns_401}`.

---

## 워크트리 격리 노트

- 마이그레이션: `0002_identity`(down `0001_core`). core 머지 후 머지(§1 표). 생성 테이블 `users`, `workspaces`, `workspace_members`, `sessions`.
- `app/core/security.py`(JWT sign/verify)는 이 Task(2)가 생성한다 — core 슬라이스가 먼저 제공하는 것이 아니라 identity Files에 포함(Task 2). JWT secret은 env `MAILY_JWT_SECRET`, 미설정 시 발급/검증 실패(fail-closed).
- `_integration-contract.md §3` prefix `/auth` 고정(`POST /auth/google/callback`, `GET /auth/session`), §4 노출 심볼 규칙 준수.
- §5 status: identity 테이블은 status enum 컬럼이 없다 — 세션 유효성은 `expires_at`/`revoked_at` 파생이라 별도 값 집합이 불필요.
- Google 로그인 client 미준비 시 mocked Google profile + JWT/session test로 구현(module-boundaries 차단조건).
- 미정 의존: 다중 기기 세션·재로그인 시 이전 세션 revoke 정책 **[미확정: POC는 이전 세션 유지]**.
