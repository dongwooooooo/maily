# LLM Provider Infra 설계 (`app/core/llm/`)

정리일: 2026-07-09
상태: 설계 확정, 구현 대기(writing-plans로 이관)

기준: `docs/goals/backend-plans/assistant_decisions.md`(fake_llm 계약, 최소 payload invariant), `docs/goals/backend-implementation-plan.md`(Task 10 LLM 경계, provider 의도적 보류), `docs/areas/backend/module-boundaries.md`(Port 격리 원칙), 기존 `GmailReaderPort`/`GmailMutationPort` 패턴.

## 목적

서비스가 LLM에 요청하고 응답받는 경로를 하나의 provider-agnostic 슬라이스로 추상화한다. provider는 Claude(anthropic), GPT(openai), Gemini(google-genai) 셋을 교체 가능하게 둔다. request는 호출 서비스가 조립하고, response는 provider별 어댑터가 공통 결과로 정규화한다.

`assistant_decisions/fake_llm.py`가 미러링할 인터페이스를 이 슬라이스가 확정한다(assistant_decisions 플랜 "실 LLM은 core/provider 슬라이스 확정 후 fake와 동일 인터페이스로 교체").

## 범위

포함:
- `app/core/llm/` provider-agnostic 클라이언트, Port, 어댑터 3, registry, config, 타입 에러, fake.
- request/result 계약 확정.
- 어댑터 단위 테스트(SDK client mock) + 라이브 계약 테스트(env 게이트).

미포함(범위 밖):
- assistant_decisions job(`generate_summary`/`classify_importance`/`prepare_cleanup_proposals`) 배선 — 별도 도메인 작업.
- 서비스별 프롬프트·output_schema 정의 — 도메인이 소유.
- `importance_band`/`confidence_band` 값·경계 확정 — LLM POC 실측 시점(db-schema `[미정]` 유지).
- 스트리밍 — 배치 job 경로라 불필요(YAGNI).

## 2계층 구조

호출 방향: 도메인 task → provider 계층. 역참조 없음.

| 계층 | 위치 | 책임 | 소유 |
|---|---|---|---|
| Provider 계층 | `app/core/llm/` | `complete(request) -> LLMResult` 실행, provider 교체, 에러 정규화, 재시도 가능 여부 분류 | 이 슬라이스 |
| 도메인 task 계층 | `app/domains/assistant_decisions/` | service별 `LLMRequest` 조립, output_schema 지정, `LLMResult` 해석 | 도메인(범위 밖) |

user 요구 매핑: "request는 서비스에 따라" = 도메인 task 계층이 조립. "response는 provider에 따라 추상화" = provider 계층 어댑터가 정규화.

## Request 계약 — `LLMRequest`

Pydantic 모델. 도메인이 조립해 `complete()`에 전달.

| 필드 | 타입 | 내용 |
|---|---|---|
| `model` | `str` | 논리 모델 id. registry가 provider·어댑터로 매핑 |
| `system` | `str \| None` | 시스템 지시 |
| `messages` | `list[LLMMessage]` | `role`(`user`/`assistant`) + text content part만 |
| `output_schema` | `type[BaseModel] \| None` | 있으면 구조화 경로, 없으면 free text |
| `max_output_tokens` | `int` | 생성 상한 |
| `temperature` | `float` | 생성 파라미터 |
| `metadata` | `dict[str, str]` | job/trace id 등 — content 아님 |

`LLMMessage`: `role: Literal["user", "assistant"]`, `content: str`(text만 — raw body 유입은 호출자가 차단, 이 계약은 text 필드만 받는 시그니처로 강제).

프라이버시: provider 계층은 content 값을 로깅하지 않는다. structlog에 남기는 것은 필드명·`model`·token usage·latency·finish_reason만. content 문자열은 로그·에러 메시지 어디에도 넣지 않는다. assistant_decisions "raw body/prompt 미저장" invariant와 정합.

## Result 계약 — `LLMResult`

Pydantic 모델. 어댑터가 provider 응답을 이 형태로 정규화.

| 필드 | 타입 | 내용 |
|---|---|---|
| `text` | `str \| None` | free-text 출력(output_schema 없을 때) |
| `parsed` | `BaseModel \| None` | 구조화 인스턴스(output_schema 있을 때) |
| `model_name` | `str` | provider가 반환한 실제 모델 문자열 → assistant_decisions가 `message_summaries.model_name` 등에 저장 |
| `usage` | `TokenUsage` | `input_tokens`, `output_tokens` |
| `finish_reason` | `Literal["stop","length","refusal","tool"]` | provider별 종료 사유 정규화 |

raw provider 응답 객체는 `LLMResult`에 담지 않는다(원문 보존 금지). 필요 시 어댑터 내부에서만 소비.

## Port — `LLMPort`

`GmailReaderPort`/`GmailMutationPort`와 동일한 Protocol 격리.

```python
class LLMPort(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResult: ...
```

어댑터 3 + fake 전부 이 Protocol 구현. 도메인은 `LLMPort`만 의존, 구체 어댑터 미참조.

## 어댑터 3 — 구조화 출력 정규화

각 어댑터가 공통 `LLMRequest` → provider 호출 → `LLMResult`. 구조화 출력은 provider별 native 스키마 보장 모드 사용(셋 다 Pydantic 직접 지원 확인됨).

| 어댑터 | SDK | 구조화 경로 | 종료 사유 매핑 |
|---|---|---|---|
| `adapters/anthropic.py` | `anthropic.AsyncAnthropic` | native json_schema | `stop_reason` → `finish_reason` |
| `adapters/openai.py` | `openai.AsyncOpenAI` | `chat.completions.parse(response_format=output_schema)`; text는 `create` | `finish_reason` 그대로 정규화 |
| `adapters/gemini.py` | `google.genai` `client.aio.models.generate_content` | `GenerateContentConfig(response_schema=output_schema, response_mime_type="application/json")` → `.parsed` | `finish_reason`/`usage_metadata` 매핑 |

근거(2026-07 검증):
- anthropic: `AsyncAnthropic` 동일 API async, httpx 기반, native structured output — https://github.com/anthropics/anthropic-sdk-python
- openai: `client.chat.completions.parse()` v1.92+ stable, Pydantic `response_format` — https://developers.openai.com/api/docs/guides/structured-outputs
- google-genai: `client.aio.models.generate_content`, `response_schema`에 Pydantic BaseModel, `.parsed` 반환 — https://github.com/googleapis/python-genai

## registry + config

- `registry.py`: `model str → (provider, 어댑터 factory)` 명시 테이블. autodiscovery 없음(마이그레이션 registry와 동일 원칙). unknown model → `LLMInvalidRequestError`.
- config 추가(`app/core/config.py`, pydantic-settings): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`(env, 하드코딩 금지 — settings.json deny 대상), `LLM_DEFAULT_MODEL`.
- 어댑터는 사용 시점 lazy-init. provider 키 없으면 그 provider 호출 시에만 `LLMAuthError`(부팅은 키 없이도 됨 — fake로 전체 테스트 가능).

## 에러 정규화 — `errors.py`

어댑터가 provider 예외를 공통 타입으로 매핑. 재시도 정책은 이 계층이 소유하지 않는다.

| 타입 | 조건 | 재시도 |
|---|---|---|
| `LLMError` | base | — |
| `LLMAuthError` | 401/403, 키 없음 | 아니오 |
| `LLMRateLimitError` | 429(retry_after 보유) | 예 |
| `LLMTransientError` | 5xx/timeout | 예 |
| `LLMInvalidRequestError` | 400/schema 위반/unknown model | 아니오 |
| `LLMRefusalError` | 모델 거부 | 아니오 |

재시도 루프는 어댑터 안에 없다. 기존 `app/core/jobs/retry.py`(dispatcher)가 재시도를 소유하고, LLM 계층은 예외에 `retryable` 여부만 실어 던진다. 계층 분리 유지.

## fake — `fake.py`

결정론적 `FakeLLM(LLMPort)`. request → 규칙 기반 `LLMResult`(text 또는 output_schema 인스턴스). 네트워크 0. core llm 테스트 + assistant_decisions `fake_llm` 공용 기반. canned 응답을 model/schema별로 주입 가능.

## 파일 구조

```
app/core/llm/
  __init__.py        # LLMPort, LLMRequest, LLMResult, get_llm() 노출
  port.py            # LLMPort Protocol, LLMRequest, LLMResult, LLMMessage, TokenUsage
  errors.py          # LLMError 계층
  registry.py        # model str → 어댑터 factory
  config.py 반영     # (app/core/config.py에 키 추가)
  adapters/
    __init__.py
    anthropic.py
    openai.py
    gemini.py
  fake.py            # FakeLLM
tests/core/llm/
  test_port_contract.py
  test_registry.py
  test_errors.py
  test_fake.py
  test_adapter_anthropic.py   # SDK client mock
  test_adapter_openai.py
  test_adapter_gemini.py
  test_live_contract.py       # MAILY_RUN_LIVE_LLM_TESTS=1 게이트
  test_privacy.py             # content 값 미로깅
```

## 테스트 전략

| 대상 | 방식 |
|---|---|
| Port 계약 | fake가 `LLMPort` 만족, request/result shape 검증 |
| registry | model→어댑터 매핑, unknown model → `LLMInvalidRequestError` |
| errors | provider 예외 → 타입 에러 분류, `retryable` 플래그 |
| fake | text·parsed 결정론 |
| 어댑터 | 각 SDK client를 mock(monkeypatch/respx), request 변환 + result 정규화 단언, 라이브 호출 0 |
| 라이브 계약 | `MAILY_RUN_LIVE_LLM_TESTS=1`일 때만 실제 provider 1콜(Gmail 라이브 게이트와 동형). 기본 CI는 스킵 |
| privacy | `complete()`가 필드명·usage만 로깅, content 값은 로그·에러에 미포함 |

## 의존성 추가(pyproject)

```
anthropic==<pin>
openai==<pin>
google-genai==<pin>
```

셋 다 async-native, httpx 기반, 공식 SDK. 정확한 pin 버전은 구현 시 최신 안정 버전으로 고정.

## 열린 항목

- 논리 모델 id ↔ 실제 provider 모델 문자열 매핑값: `LLM_DEFAULT_MODEL` 기본값 포함해 구현 시 확정. 모델 상수는 registry 테이블에 명시.
- provider별 구조화 출력의 refusal 표현 차이(anthropic stop_reason vs openai refusal vs gemini): 어댑터에서 `LLMRefusalError`로 통일, 세부 매핑은 라이브 계약 테스트로 실측.
