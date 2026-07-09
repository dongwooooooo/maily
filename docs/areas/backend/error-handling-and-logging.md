# Maily Backend 에러 처리와 로깅 표준

기준 문서: `docs/areas/backend/module-boundaries.md`(core 소유 책임: logging), `docs/goals/backend-implementation-plan.md`(Task 1 core, Task 15 운영 기준)
정리일: 2026-07-09

## 문서 역할

이 문서는 백엔드 도메인 8개(identity, mail_sources, mail_intake, briefing, labels, gmail_actions, assistant_decisions, notifications)가 예외를 던지고, 로그를 남기고, 장애를 추적하는 방식을 하나로 고정한다. `app/core/errors.py`(예외 계층), `app/core/error_handlers.py`(FastAPI 예외 핸들러), `app/core/logging.py`(구조화 로깅, request context)가 이 문서의 구현체이며, 이 세 파일은 core(도메인이 아니라 공통 실행 기반, `docs/goals/backend-plans/core.md`)가 소유한다. 새 도메인을 추가하는 워크트리는 이 문서의 예외 클래스와 로깅 컨텍스트 규칙만 사용한다 — 도메인마다 새 예외 베이스나 로거 설정을 만들지 않는다.

---

## 들어가며

도메인 8개 + core, 총 9개 워크트리가 병렬로 붙는 구조다(`_build-schedule.md` W1~W3). 예외 처리와 로깅을 도메인마다 다르게 짜면 아래 세 가지가 반드시 깨진다.

1. **장애 추적 불가**: 도메인 A는 `raise HTTPException(500)`, 도메인 B는 `raise ValueError`, 도메인 C는 `print()`로 에러를 삼킨다. 프로덕션에서 요청 하나가 실패했을 때 어느 도메인, 어느 계층에서 무엇 때문에 실패했는지 로그로 재구성할 수 없다.
2. **에러 응답 계약 불일치**: 프론트엔드가 도메인마다 다른 에러 바디 형태(`{detail: "..."}`, `{message: "..."}`, `{error: "..."}`)를 각각 파싱해야 한다. 카드 목록 응답에 action/reason을 안 넣는 것과 같은 수준의 "응답 문법" 문제다.
3. **민감 정보 노출 위험**: `MAILY_JWT_SECRET`, `MAILY_TOKEN_ENC_KEY` 같은 설정값이 빠졌을 때 스택 트레이스를 그대로 클라이언트에 돌려주면 내부 구성이 노출된다(`~/.claude/rules/security.md` "스택 트레이스를 사용자에게 노출하지 않는다").

세 문제 모두 "각 도메인이 알아서 처리"로는 못 막는다. core가 예외 계층과 로깅 컨텍스트를 강제하고, 도메인은 거기 올라타기만 한다.

## 문제 정의 — 표준화 전 상태

Task 1~3 구현 시점 기준으로 아래 상태였다.

- `app/main.py`의 `/health`, `/ready`는 예외를 던지지 않는 순수 조회라 문제가 드러나지 않았다.
- `identity/router.py`의 `GET /auth/session`은 `raise HTTPException(status_code=401, detail="invalid session")`으로 FastAPI 기본 예외를 직접 썼다. 응답 바디가 `{"detail": "invalid session"}` — 다른 도메인이 각자 다른 키로 응답하면 프론트엔드 에러 파싱이 도메인마다 갈라진다.
- `app/core/security.py`, `app/core/crypto.py`가 자체 예외(`InvalidSessionTokenError`, `MissingJWTSecretError`, `TokenDecryptionError`)를 던지지만, 이 예외들을 잡아서 HTTP 응답으로 바꾸는 공통 레이어가 없었다 — 라우터마다 `try/except`를 새로 작성해야 하는 구조였다.
- 로그는 `print`나 uvicorn 기본 access log뿐이었다. `request_id`, `workspace_id`, `source_id`를 로그에서 상관시킬 방법이 없었다 — Task 15가 요구하는 "로깅 컨텍스트 테스트(request id, workspace id, source id)"를 만족 못 하는 상태.

## 설계 원칙

1. **도메인 예외는 `MailyError`를 상속한다.** `app/core/errors.py`가 유일한 베이스. 도메인이 `ValueError`, `Exception`, FastAPI `HTTPException`을 직접 던지지 않는다 — 서비스/레포지토리 계층은 항상 `MailyError` 서브클래스만 던진다.
2. **HTTP 상태 코드는 예외 클래스가 소유한다.** 라우터가 `status_code=401`을 직접 쓰지 않는다. `UnauthorizedError.status_code = 401`처럼 예외 클래스 자체가 상태 코드를 갖고, 공통 핸들러(`app/core/error_handlers.py`)가 이걸 읽어 응답을 만든다. 라우터는 `raise UnauthorizedError("invalid session")`만 하면 끝난다.
3. **에러 응답 바디는 한 가지 모양만 존재한다.** `{"error": {"code": "...", "message": "...", "request_id": "..."}}`. `code`는 프론트엔드가 분기하는 안정적인 키(`session_expired`, `duplicate_source` 등)이며 실제 UI에 보여줄 확정 카피는 프론트엔드가 `code`를 보고 자체적으로 고른다(`design/copy-principles.md` 소관). `message`는 프론트엔드에 직접 렌더링되지 않는 개발자용 기술 설명 — 로그 상관, 디버깅, 지원팀 문의 대응이 목적이라 스택 트레이스만 아니면 영어로 남겨도 된다(§8). `request_id`는 사용자가 문의할 때 서버 로그와 대조하는 상관관계 키.
4. **500번대는 메시지를 감춘다.** `ConfigurationError`(설정 누락), 처리 안 된 `Exception` 전부 클라이언트에는 `"Internal server error"`만 내려간다. 원인은 서버 로그에만 `exc_info`로 남는다 — 스택 트레이스나 설정값 이름을 응답 바디에 절대 포함하지 않는다.
5. **모든 요청은 `request_id`를 갖는다.** 클라이언트가 `X-Request-Id` 헤더를 보내면 그대로 쓰고, 없으면 서버가 생성한다. 응답 헤더로 그대로 돌려준다 — 프론트엔드 에러 토스트에 "문의 시 이 번호를 알려주세요" 형태로 노출 가능.
6. **로그는 사람이 아니라 프로그램이 먼저 읽는다.** JSON 구조화 로그(`structlog`)만 쓴다. `print`, f-string 로그 금지 — grep으로는 찾을 수 있어도 로그 수집기(예: 향후 도입될 중앙 로그 시스템)가 파싱을 못 한다.
7. **컨텍스트는 로그 콜마다 반복해서 넘기지 않는다.** `structlog.contextvars`로 요청 시작 시점에 `request_id`를 바인딩하고, 인증 이후 `workspace_id`/`user_id`를 추가 바인딩한다. 이후 그 요청 안에서 발생하는 모든 로그 호출이 파라미터 없이도 컨텍스트를 포함한다.
8. **로그 메시지(첫 인자)는 한국어, 구조화 필드 키는 영어.** 2026-07-09 사용자 결정(대화·개인 전역 설정 반영, 이 문서가 프로젝트 기준의 정본). `logger.info("Gmail 전체 동기화 완료", source_id=..., messages_changed=...)`처럼 사람이 읽는 문장은 한국어, `source_id`/`messages_changed` 같은 필드 이름(코드 식별자)은 영어 snake_case를 유지한다 — 필드 키는 로그 수집기가 필터링·집계하는 스키마라 "코드"에 해당하고, 메시지 문장만 "로그 메시지"에 해당한다. 예외 클래스의 `.message`는 이 규칙 대상이 아니다 — §3에서 규정한 대로 개발자용 기술 설명이라 영어를 유지해도 된다.

## 예외 계층

```
MailyError (500, "internal_error")
├── NotFoundError        (404, "not_found")
├── ConflictError         (409, "conflict")
├── ValidationError       (422, "validation_error")
├── UnauthorizedError     (401, "unauthorized")
├── ForbiddenError        (403, "forbidden")
├── ExternalServiceError  (502, "external_service_error")
└── ConfigurationError    (500, "internal_error")
```

| 예외 | 상태 코드 | 언제 던지나 | 예시 |
|---|---|---|---|
| `NotFoundError` | 404 | 리소스가 없거나, 존재를 노출하면 안 되는 타 workspace 리소스 | `GET /sources/{id}`가 타 workspace 소유 |
| `ConflictError` | 409 | 상태 충돌 — 이미 진행 중인 작업과 겹침 | `disconnecting` 상태 source에 설정 변경 요청 |
| `ValidationError` | 422 | pydantic 스키마 통과 후의 비즈니스 규칙 위반 | OAuth callback profile에 `gmail.modify` scope 없음 |
| `UnauthorizedError` | 401 | 인증 실패 — 세션 없음/만료/폐기 | `resolve_request_context`가 세션을 못 찾음 |
| `ForbiddenError` | 403 | 인증은 됐지만 권한 없음 | 세션 workspace ≠ 요청 대상 workspace |
| `ExternalServiceError` | 502 | Gmail API·Google OAuth 등 외부 호출 실패, 또는 응답이 우리가 처리 가능한 형태가 아님 | `GmailReaderPort` 호출이 5xx/타임아웃, 또는 알 수 없는 history record_type |
| `ConfigurationError` | 500 | 서버 설정 누락 — 클라이언트 잘못이 아님 | `MAILY_JWT_SECRET`/`MAILY_TOKEN_ENC_KEY` 미설정 |

`MailyError`를 직접 던지지 않는다 — 반드시 구체적인 서브클래스를 쓴다. 새로운 실패 유형이 이 표에 없으면 임의로 상태 코드를 고르지 않고, 이 문서에 행을 먼저 추가한다(db-schema.md의 "표에 없는 값을 임의로 채우지 않는다"와 같은 규칙).

`security.InvalidSessionTokenError`, `security.MissingJWTSecretError`, `crypto.MissingTokenEncryptionKeyError`, `crypto.TokenDecryptionError`처럼 `app/core/security.py`·`app/core/crypto.py`가 이미 갖고 있는 저수준 예외는 없애지 않는다. 그 예외들은 라이브러리 경계에서 "무엇이 실패했는지"를 정확히 표현하는 역할을 유지하고, 이걸 잡아서 `UnauthorizedError`/`ConfigurationError`로 다시 던지는 건 그 예외를 호출하는 서비스/라우터 계층의 책임이다 — 계층을 건너뛰고 저수준 예외가 라우터까지 올라가 FastAPI 기본 500으로 새지 않게 한다.

## 로깅 컨텍스트

`app/core/logging.py`의 `RequestContextMiddleware`가 모든 요청에 `request_id`를 바인딩한다. 인증된 요청은 `resolve_request_context` 통과 직후 서비스 계층이 `workspace_id`/`user_id`를 추가 바인딩한다. Gmail 소스 관련 작업(mail_intake, gmail_actions job)은 `source_id`를 추가 바인딩한다 — Task 15가 요구하는 세 값(request id, workspace id, source id)이 이 세 지점에서 각각 채워진다.

```python
import structlog

logger = structlog.get_logger()

# 요청 진입 시점 (미들웨어) — 모든 요청
structlog.contextvars.bind_contextvars(request_id=request_id)

# 인증 통과 시점 (서비스 계층) — 인증된 요청만
structlog.contextvars.bind_contextvars(workspace_id=str(context.workspace_id), user_id=str(context.user_id))

# Gmail 소스 작업 시점 (job handler) — source 관련 작업만
structlog.contextvars.bind_contextvars(source_id=str(source_id))

logger.info("Gmail 계정 연결 완료", gmail_address=masked_address)
# {"event": "Gmail 계정 연결 완료", "request_id": "...", "workspace_id": "...", "gmail_address": "a***@gmail.com", "level": "info", "timestamp": "..."}
```

로그에 남기면 안 되는 값: `access_token_ciphertext`/`refresh_token_ciphertext`(암호문이어도 로그에 안 남긴다), 복호화된 토큰 원문, `MAILY_JWT_SECRET`/`MAILY_TOKEN_ENC_KEY` 값, 메일 본문·요약 원문(`~/.claude/rules/security.md`, module-boundaries.md의 raw body 미보관 invariant와 같은 이유). Gmail 주소처럼 개인식별정보 성격이 있는 값은 로그 레벨에 따라 마스킹을 검토한다 — POC 단계는 workspace 소유자 본인 확인 목적상 전체 노출을 허용하되, 운영 전환 시 재검토 대상으로 남긴다.

## 사용 예시 — Before / After

**Before** (`identity/router.py`, Task 2 시점):

```python
try:
    context = await resolve_request_context(connection, token)
except security.InvalidSessionTokenError as exc:
    raise HTTPException(status_code=401, detail="invalid session") from exc
```

응답: `{"detail": "invalid session"}`, 로그: 없음(예외가 어디서도 기록 안 되고 조용히 401로 변환됨).

**After**:

```python
try:
    context = await resolve_request_context(connection, token)
except security.InvalidSessionTokenError as exc:
    raise UnauthorizedError("invalid session") from exc
```

응답: `{"error": {"code": "unauthorized", "message": "invalid session", "request_id": "..."}}`. `maily_error_handler`가 자동으로 `structlog` warning 로그(`request_id`, `error_code=unauthorized` 포함)를 남기고 상태 코드를 예외 클래스에서 읽는다 — 라우터는 상태 코드를 몰라도 된다.

## 로깅 레벨 기준

| 레벨 | 언제 | 예시 |
|---|---|---|
| `info` | 정상 흐름의 의미 있는 완료 지점 — job 성공, 동기화 완료, 상태 전이 성공 | `logger.info("Gmail 전체 동기화 완료", source_id=..., messages_changed=...)` |
| `warning` | 요청은 실패했지만 시스템 결함은 아님 — 4xx급 도메인 예외(`MailyError`, 500 미만), 재시도로 회복 가능한 job 실패 | `logger.warning("멱등 키 중복으로 커맨드 재사용", command_id=...)` |
| `error` | 원인 불명 예외, 5xx, 재시도해도 회복 안 되는 실패 — `exc_info` 필수 | `logger.error("Gmail mutation 실패", command_id=..., exc_info=exc)` |

`info`를 매 함수 진입/DB 쿼리마다 찍지 않는다 — 의미 있는 상태 변화(동기화 완료, 커맨드 적용, 계정 연결)에만 남긴다. 로그 볼륨이 커지면 실제 장애 신호가 묻힌다.

## 테스트 전략

- `tests/core/test_errors.py`: 예외 클래스 7종 각각이 올바른 상태 코드·`error_code`로 매핑되는지, 처리 안 된 일반 `Exception`이 500 + 제네릭 메시지로 감싸지는지(원인 메시지가 응답 바디에 안 남는지) 검증.
- `tests/core/test_logging.py`: `X-Request-Id`를 클라이언트가 보내면 그대로 응답 헤더에 돌아오는지, 안 보내면 서버가 생성해서 돌려주는지 검증.
- 기존 도메인 테스트(`test_router.py` 등)는 상태 코드 assertion만 하고 있어 응답 바디 형태가 `{"detail": ...}`에서 `{"error": {...}}`로 바뀌어도 깨지지 않는다 — 새 도메인은 응답 바디 형태까지 assert하는 걸 권장한다(카드 문법처럼 "응답 계약"이 이 형태로 고정됐다는 걸 테스트가 증명하도록).

## 하네싱 — 자동 리마인더와 리뷰

- `.claude/hooks/log-guard.mjs`(PostToolUse, `development/backend/**/*.py` Edit/Write 시 실행)가 `print(`, `raise ValueError`/`raise Exception`/`raise HTTPException`, 한국어 문자가 없는 `logger.info/warning/error(...)` 첫 인자를 감지해 리마인더를 띄운다. `doc-guard.mjs`와 동일하게 비차단(reminder-only) — 항상 exit 0.
- `/verify` 스킬의 자동 검증 단계가 이 문서의 체크리스트를 구조 검증 항목으로 포함한다(§구조 검증).
- 새 도메인의 로깅/에러 코드를 짤 때는 이 문서를 먼저 읽고 시작한다 — `docs/CONTEXT.md` 작업 라우팅 표의 "백엔드 예외/로깅 구현" 행이 진입점.

## 체크리스트 (새 도메인 워크트리 착수 전)

- [ ] 서비스/레포지토리 계층에서 `raise ValueError`, `raise Exception`, `raise HTTPException`을 직접 쓰지 않았는가 — `MailyError` 서브클래스만 쓰는가.
- [ ] 새로운 실패 유형이 위 예외 표에 없다면, 표에 행을 먼저 추가했는가(임의로 상태 코드를 고르지 않았는가).
- [ ] 500번대로 응답하는 경로에서 원인 메시지·설정값 이름·스택 트레이스가 응답 바디에 안 남는가.
- [ ] job handler·외부 API 호출부에서 `logger.info`/`logger.warning`/`logger.error`를 `print` 대신 썼는가.
- [ ] 로그 메시지(첫 인자)가 한국어 문장인가 — 필드 키(`source_id` 등)만 영어로 남아있는가.
- [ ] 로그 레벨이 위 표 기준과 맞는가(info 남발 없는가, error에 `exc_info` 있는가).
- [ ] 로그 호출에 토큰 원문·메일 본문·시크릿 값을 넘기지 않았는가.
- [ ] source 관련 job은 `source_id`를 컨텍스트에 바인딩했는가.
