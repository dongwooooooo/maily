# LLM Provider Infra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a provider-agnostic LLM client slice (`app/core/llm/`) exposing one `LLMPort.complete(request) -> LLMResult` behind anthropic/openai/google-genai adapters, with typed error normalization and a deterministic fake.

**Architecture:** A common `LLMRequest`/`LLMResult` contract is normalized by per-provider adapters. Domains build requests and read results; they depend only on the `LLMPort` Protocol, never on a concrete adapter. Retry lives in the job dispatcher — adapters only classify errors as retryable or not. Structured output uses each provider's native schema-guaranteed mode.

**Tech Stack:** Python 3.14, Pydantic 2.13, anthropic 0.116, openai 2.44, google-genai 2.10, structlog 26, pytest 9.

Spec: `docs/areas/backend/llm-provider-infra.md`.

## Global Constraints

- Python `>=3.14,<3.15`; ruff line-length 100, target py314; mypy on `app`.
- No hardcoded secrets. Provider keys come from env via pydantic-settings only.
- Provider layer never logs message content values — only field names, model, token usage, latency, finish_reason.
- `LLMResult` never carries the raw provider response object.
- Docs/discussion Korean; code, identifiers, commit messages English.
- Retry loops are forbidden inside adapters — raise typed errors with a `retryable` flag; the dispatcher (`app/core/jobs/retry.py`, separate work) owns retry.
- No streaming (batch job path only).
- Every task: red → green → refactor, commit at the end. Run commands from `development/backend`.

Install note: after editing `pyproject.toml` dependencies, sync the env with
`cd development/backend && uv pip install -e ".[dev]"` (fallback: `python -m pip install -e ".[dev]"`).

---

### Task 1: Dependencies and core contracts

**Files:**
- Modify: `development/backend/pyproject.toml`
- Create: `development/backend/app/core/llm/__init__.py`
- Create: `development/backend/app/core/llm/port.py`
- Test: `development/backend/tests/core/llm/__init__.py`, `development/backend/tests/core/llm/test_port_contract.py`

**Interfaces:**
- Produces:
  - `LLMMessage(BaseModel)`: `role: Literal["user","assistant"]`, `content: str`
  - `TokenUsage(BaseModel)`: `input_tokens: int`, `output_tokens: int`
  - `LLMRequest(BaseModel)`: `model: str`, `system: str | None = None`, `messages: list[LLMMessage]`, `output_schema: type[BaseModel] | None = None`, `max_output_tokens: int = 1024`, `temperature: float = 0.0`, `metadata: dict[str, str] = {}`
  - `LLMResult(BaseModel)`: `text: str | None = None`, `parsed: BaseModel | None = None`, `model_name: str`, `usage: TokenUsage`, `finish_reason: Literal["stop","length","refusal","tool"]`
  - `LLMPort(Protocol)`: `async def complete(self, request: LLMRequest) -> LLMResult: ...`

- [ ] **Step 1: Add SDK dependencies to pyproject**

In `development/backend/pyproject.toml`, add to the `dependencies` list (after `"structlog==26.1.0"`, add a comma to that line):

```toml
  "structlog==26.1.0",
  "anthropic==0.116.0",
  "openai==2.44.0",
  "google-genai==2.10.0"
```

- [ ] **Step 2: Sync environment**

Run: `cd development/backend && uv pip install -e ".[dev]"`
Expected: installs anthropic, openai, google-genai without error.

- [ ] **Step 3: Write the failing contract test**

Create `development/backend/tests/core/llm/__init__.py` (empty file).
Create `development/backend/tests/core/llm/test_port_contract.py`:

```python
from pydantic import BaseModel

from app.core.llm import (
    LLMMessage,
    LLMPort,
    LLMRequest,
    LLMResult,
    TokenUsage,
)


class _Sample(BaseModel):
    value: str


def test_request_defaults_and_fields():
    req = LLMRequest(model="m", messages=[LLMMessage(role="user", content="hi")])
    assert req.system is None
    assert req.output_schema is None
    assert req.max_output_tokens == 1024
    assert req.temperature == 0.0
    assert req.metadata == {}


def test_request_accepts_output_schema():
    req = LLMRequest(
        model="m",
        messages=[LLMMessage(role="user", content="hi")],
        output_schema=_Sample,
    )
    assert req.output_schema is _Sample


def test_result_holds_text_or_parsed():
    usage = TokenUsage(input_tokens=1, output_tokens=2)
    text_result = LLMResult(text="ok", model_name="m", usage=usage, finish_reason="stop")
    assert text_result.text == "ok"
    assert text_result.parsed is None

    parsed_result = LLMResult(
        parsed=_Sample(value="v"), model_name="m", usage=usage, finish_reason="stop"
    )
    assert parsed_result.parsed.value == "v"


def test_a_class_can_satisfy_llmport():
    class _Impl:
        async def complete(self, request: LLMRequest) -> LLMResult:
            return LLMResult(
                text="x",
                model_name=request.model,
                usage=TokenUsage(input_tokens=0, output_tokens=0),
                finish_reason="stop",
            )

    impl: LLMPort = _Impl()
    assert isinstance(impl, LLMPort)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_port_contract.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.llm'`.

- [ ] **Step 5: Implement the contracts**

Create `development/backend/app/core/llm/port.py`:

```python
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

FinishReason = Literal["stop", "length", "refusal", "tool"]


class LLMMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class LLMRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    system: str | None = None
    messages: list[LLMMessage]
    output_schema: type[BaseModel] | None = None
    max_output_tokens: int = 1024
    temperature: float = 0.0
    metadata: dict[str, str] = Field(default_factory=dict)


class LLMResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str | None = None
    parsed: BaseModel | None = None
    model_name: str
    usage: TokenUsage
    finish_reason: FinishReason


@runtime_checkable
class LLMPort(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResult: ...
```

Create `development/backend/app/core/llm/__init__.py`:

```python
from app.core.llm.port import (
    FinishReason,
    LLMMessage,
    LLMPort,
    LLMRequest,
    LLMResult,
    TokenUsage,
)

__all__ = [
    "FinishReason",
    "LLMMessage",
    "LLMPort",
    "LLMRequest",
    "LLMResult",
    "TokenUsage",
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_port_contract.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
cd development/backend && git add pyproject.toml app/core/llm tests/core/llm
git commit -m "feat(llm): add provider-agnostic request/result contracts and LLMPort"
```

---

### Task 2: Typed error hierarchy

**Files:**
- Create: `development/backend/app/core/llm/errors.py`
- Modify: `development/backend/app/core/llm/__init__.py`
- Test: `development/backend/tests/core/llm/test_errors.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LLMError(Exception)`: base, attribute `retryable: bool = False`
  - `LLMAuthError(LLMError)`: `retryable = False`
  - `LLMRateLimitError(LLMError)`: `retryable = True`, `__init__(self, message="", retry_after: float | None = None)`, attribute `retry_after`
  - `LLMTransientError(LLMError)`: `retryable = True`
  - `LLMInvalidRequestError(LLMError)`: `retryable = False`
  - `LLMRefusalError(LLMError)`: `retryable = False`

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_errors.py`:

```python
import pytest

from app.core.llm import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)


def test_base_defaults_not_retryable():
    assert LLMError().retryable is False


@pytest.mark.parametrize(
    "exc_cls, retryable",
    [
        (LLMAuthError, False),
        (LLMRateLimitError, True),
        (LLMTransientError, True),
        (LLMInvalidRequestError, False),
        (LLMRefusalError, False),
    ],
)
def test_retryable_flags(exc_cls, retryable):
    assert exc_cls().retryable is retryable
    assert isinstance(exc_cls(), LLMError)


def test_rate_limit_carries_retry_after():
    err = LLMRateLimitError("slow down", retry_after=1.5)
    assert err.retry_after == 1.5
    assert err.retryable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_errors.py -q`
Expected: FAIL with `ImportError` on `LLMAuthError`.

- [ ] **Step 3: Implement the errors**

Create `development/backend/app/core/llm/errors.py`:

```python
class LLMError(Exception):
    retryable: bool = False


class LLMAuthError(LLMError):
    retryable = False


class LLMRateLimitError(LLMError):
    retryable = True

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMTransientError(LLMError):
    retryable = True


class LLMInvalidRequestError(LLMError):
    retryable = False


class LLMRefusalError(LLMError):
    retryable = False
```

Add to `development/backend/app/core/llm/__init__.py` imports and `__all__`:

```python
from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)
```

Add these names to `__all__`: `"LLMError"`, `"LLMAuthError"`, `"LLMRateLimitError"`, `"LLMTransientError"`, `"LLMInvalidRequestError"`, `"LLMRefusalError"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_errors.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm tests/core/llm/test_errors.py
git commit -m "feat(llm): add typed error hierarchy with retryable classification"
```

---

### Task 3: Deterministic fake

**Files:**
- Create: `development/backend/app/core/llm/fake.py`
- Modify: `development/backend/app/core/llm/__init__.py`
- Test: `development/backend/tests/core/llm/test_fake.py`

**Interfaces:**
- Consumes: `LLMPort`, `LLMRequest`, `LLMResult`, `TokenUsage` (Task 1).
- Produces:
  - `FakeLLM`: implements `LLMPort`. Constructor `FakeLLM(text: str = "fake-summary", structured: dict | None = None)`. When `request.output_schema` is set, returns `LLMResult.parsed = request.output_schema.model_validate(structured or {})`; otherwise `LLMResult.text = text`. `model_name = request.model`, `usage = TokenUsage(input_tokens=0, output_tokens=0)`, `finish_reason = "stop"`. Records the last request on `self.last_request`.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_fake.py`:

```python
import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMPort, LLMRequest
from app.core.llm.fake import FakeLLM


class _Band(BaseModel):
    band: str
    reason: str


def _req(**kw):
    return LLMRequest(model="fake-model", messages=[LLMMessage(role="user", content="x")], **kw)


def test_fake_satisfies_port():
    assert isinstance(FakeLLM(), LLMPort)


@pytest.mark.asyncio
async def test_fake_returns_text_when_no_schema():
    fake = FakeLLM(text="hello")
    result = await fake.complete(_req())
    assert result.text == "hello"
    assert result.parsed is None
    assert result.model_name == "fake-model"
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_returns_parsed_schema_instance():
    fake = FakeLLM(structured={"band": "urgent", "reason": "boss"})
    result = await fake.complete(_req(output_schema=_Band))
    assert isinstance(result.parsed, _Band)
    assert result.parsed.band == "urgent"
    assert result.text is None


@pytest.mark.asyncio
async def test_fake_is_deterministic_and_records_request():
    fake = FakeLLM(text="same")
    r1 = await fake.complete(_req())
    r2 = await fake.complete(_req())
    assert r1.text == r2.text == "same"
    assert fake.last_request is not None
    assert fake.last_request.model == "fake-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_fake.py -q`
Expected: FAIL with `ModuleNotFoundError` on `app.core.llm.fake`.

(If the run instead errors on `asyncio` marks, ensure `pytest-asyncio` is configured — see Task 3 Step 3 note.)

- [ ] **Step 3: Implement the fake**

If `pytest-asyncio` is not yet a dependency, add `"pytest-asyncio==1.2.0"` to the `dev` extras in `pyproject.toml`, add under `[tool.pytest.ini_options]` the line `asyncio_mode = "auto"`, then re-sync with `uv pip install -e ".[dev]"`. (Remove the `@pytest.mark.asyncio` decorators only if `asyncio_mode = "auto"` is set — either is fine; keep them for clarity.)

Create `development/backend/app/core/llm/fake.py`:

```python
from app.core.llm.port import LLMRequest, LLMResult, TokenUsage


class FakeLLM:
    def __init__(self, text: str = "fake-summary", structured: dict | None = None) -> None:
        self._text = text
        self._structured = structured or {}
        self.last_request: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.last_request = request
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        if request.output_schema is not None:
            return LLMResult(
                parsed=request.output_schema.model_validate(self._structured),
                model_name=request.model,
                usage=usage,
                finish_reason="stop",
            )
        return LLMResult(
            text=self._text,
            model_name=request.model,
            usage=usage,
            finish_reason="stop",
        )
```

Add to `development/backend/app/core/llm/__init__.py`:

```python
from app.core.llm.fake import FakeLLM
```

Add `"FakeLLM"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_fake.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add pyproject.toml app/core/llm tests/core/llm/test_fake.py
git commit -m "feat(llm): add deterministic FakeLLM for tests"
```

---

### Task 4: Provider config

**Files:**
- Modify: `development/backend/app/core/config.py`
- Test: `development/backend/tests/core/test_llm_config.py`

**Interfaces:**
- Consumes: existing `Settings` (pydantic-settings `BaseSettings`).
- Produces: `Settings` gains `anthropic_api_key: str = ""`, `openai_api_key: str = ""`, `google_api_key: str = ""`, `llm_default_model: str = "claude-sonnet-5"`. Env names (pydantic-settings uppercases automatically): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `LLM_DEFAULT_MODEL`.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/test_llm_config.py`:

```python
from app.core.config import Settings


def test_llm_keys_default_empty():
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == ""
    assert s.openai_api_key == ""
    assert s.google_api_key == ""
    assert s.llm_default_model == "claude-sonnet-5"


def test_llm_keys_read_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "gpt-5")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.llm_default_model == "gpt-5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/test_llm_config.py -q`
Expected: FAIL — `AttributeError`/assertion on `anthropic_api_key`.

- [ ] **Step 3: Implement the config fields**

In `development/backend/app/core/config.py`, add inside `Settings` (after `google_oauth_client_secret`):

```python
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    llm_default_model: str = "claude-sonnet-5"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/test_llm_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/config.py tests/core/test_llm_config.py
git commit -m "feat(llm): add provider key and default model settings"
```

---

### Task 5: Content-safe completion logging

**Files:**
- Create: `development/backend/app/core/llm/observability.py`
- Test: `development/backend/tests/core/llm/test_privacy.py`

**Interfaces:**
- Consumes: `LLMRequest`, `LLMResult` (Task 1), structlog.
- Produces: `log_completion(request: LLMRequest, result: LLMResult, latency_ms: float) -> None`. Emits one structlog info event `"llm.complete"` with keys: `model`, `model_name`, `input_tokens`, `output_tokens`, `finish_reason`, `latency_ms`, `message_roles` (list of roles), `has_output_schema` (bool). It MUST NOT include any message `content`, `system`, `text`, or `parsed` value.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_privacy.py`:

```python
import structlog

from app.core.llm import LLMMessage, LLMRequest, LLMResult, TokenUsage
from app.core.llm.observability import log_completion


def test_log_completion_excludes_content(capsys):
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    secret = "SENSITIVE-BODY-TEXT"
    req = LLMRequest(
        model="m",
        system="SECRET-SYSTEM",
        messages=[LLMMessage(role="user", content=secret)],
    )
    result = LLMResult(
        text="SECRET-OUTPUT",
        model_name="m-2026",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        finish_reason="stop",
    )

    log_completion(req, result, latency_ms=12.3)

    out = capsys.readouterr().out
    assert "llm.complete" in out
    assert "m-2026" in out
    assert "SENSITIVE-BODY-TEXT" not in out
    assert "SECRET-SYSTEM" not in out
    assert "SECRET-OUTPUT" not in out
    assert '"input_tokens": 10' in out or '"input_tokens":10' in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_privacy.py -q`
Expected: FAIL with `ModuleNotFoundError` on `observability`.

- [ ] **Step 3: Implement the logger**

Create `development/backend/app/core/llm/observability.py`:

```python
import structlog

from app.core.llm.port import LLMRequest, LLMResult

_log = structlog.get_logger("app.core.llm")


def log_completion(request: LLMRequest, result: LLMResult, latency_ms: float) -> None:
    _log.info(
        "llm.complete",
        model=request.model,
        model_name=result.model_name,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        finish_reason=result.finish_reason,
        latency_ms=round(latency_ms, 1),
        message_roles=[m.role for m in request.messages],
        has_output_schema=request.output_schema is not None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_privacy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm/observability.py tests/core/llm/test_privacy.py
git commit -m "feat(llm): add content-safe completion logging"
```

---

### Task 6: Anthropic adapter

**Files:**
- Create: `development/backend/app/core/llm/adapters/__init__.py`
- Create: `development/backend/app/core/llm/adapters/anthropic.py`
- Test: `development/backend/tests/core/llm/test_adapter_anthropic.py`

**Interfaces:**
- Consumes: `LLMPort`, `LLMRequest`, `LLMResult`, `TokenUsage`, error types, `log_completion`.
- Produces: `AnthropicAdapter`: implements `LLMPort`. Constructor `AnthropicAdapter(client)` takes an `anthropic.AsyncAnthropic`-shaped object (injectable for tests). `complete()`:
  - Structured (`output_schema` set): call `client.messages.create` with a single forced tool whose `input_schema = output_schema.model_json_schema()`, `tool_choice={"type": "tool", "name": "emit"}`; parse the `tool_use` block input → `output_schema.model_validate(...)`; `finish_reason="stop"`.
  - Text: call `client.messages.create`; read first `text` block; map `stop_reason`.
  - Map exceptions via `_map_error`.
- Produces: `_map_error(exc) -> LLMError` mapping `anthropic.AuthenticationError`/`PermissionDeniedError`→`LLMAuthError`, `RateLimitError`→`LLMRateLimitError`, `BadRequestError`→`LLMInvalidRequestError`, `APITimeoutError`/`APIConnectionError`/5xx `APIStatusError`→`LLMTransientError`.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_adapter_anthropic.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.anthropic import AnthropicAdapter
from app.core.llm.errors import LLMAuthError, LLMRateLimitError


class _Band(BaseModel):
    band: str
    reason: str


def _text_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="a summary")],
        stop_reason="end_turn",
        model="claude-sonnet-5-2026",
        usage=SimpleNamespace(input_tokens=11, output_tokens=4),
    )


def _tool_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="emit", input={"band": "urgent", "reason": "boss"})],
        stop_reason="tool_use",
        model="claude-sonnet-5-2026",
        usage=SimpleNamespace(input_tokens=11, output_tokens=4),
    )


def _req(**kw):
    return LLMRequest(model="claude-sonnet-5", messages=[LLMMessage(role="user", content="hi")], **kw)


@pytest.mark.asyncio
async def test_text_completion_maps_result():
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=_text_response())))
    adapter = AnthropicAdapter(client)
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.parsed is None
    assert result.model_name == "claude-sonnet-5-2026"
    assert result.usage.input_tokens == 11
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion_returns_parsed():
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=_tool_response())))
    adapter = AnthropicAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    # forced tool_choice was sent
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"]["name"] == "emit"
    assert kwargs["tools"][0]["input_schema"]["properties"]["band"]


@pytest.mark.asyncio
async def test_rate_limit_maps_to_typed_error():
    import anthropic

    err = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    Exception.__init__(err, "429")
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=err)))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMRateLimitError):
        await adapter.complete(_req())


@pytest.mark.asyncio
async def test_auth_error_maps_to_typed_error():
    import anthropic

    err = anthropic.AuthenticationError.__new__(anthropic.AuthenticationError)
    Exception.__init__(err, "401")
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=err)))
    adapter = AnthropicAdapter(client)
    with pytest.raises(LLMAuthError):
        await adapter.complete(_req())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_anthropic.py -q`
Expected: FAIL with `ModuleNotFoundError` on `adapters.anthropic`.

- [ ] **Step 3: Implement the adapter**

Create `development/backend/app/core/llm/adapters/__init__.py` (empty file).
Create `development/backend/app/core/llm/adapters/anthropic.py`:

```python
import time

import anthropic

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import LLMRequest, LLMResult, TokenUsage

_TOOL_NAME = "emit"


def _map_error(exc: Exception) -> LLMError:
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LLMAuthError(str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return LLMTransientError(str(exc))
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return LLMTransientError(str(exc))
    return LLMTransientError(str(exc))


class AnthropicAdapter:
    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        kwargs: dict = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system is not None:
            kwargs["system"] = request.system
        if request.output_schema is not None:
            kwargs["tools"] = [
                {
                    "name": _TOOL_NAME,
                    "description": "Return the structured result.",
                    "input_schema": request.output_schema.model_json_schema(),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": _TOOL_NAME}

        try:
            resp = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise _map_error(exc) from exc

        usage = TokenUsage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
        if request.output_schema is not None:
            block = next(b for b in resp.content if b.type == "tool_use")
            result = LLMResult(
                parsed=request.output_schema.model_validate(block.input),
                model_name=resp.model,
                usage=usage,
                finish_reason="stop",
            )
        else:
            text = next((b.text for b in resp.content if b.type == "text"), "")
            result = LLMResult(
                text=text,
                model_name=resp.model,
                usage=usage,
                finish_reason=_STOP_REASON.get(resp.stop_reason, "stop"),
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result


_STOP_REASON = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool",
    "refusal": "refusal",
    "stop_sequence": "stop",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_anthropic.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm/adapters tests/core/llm/test_adapter_anthropic.py
git commit -m "feat(llm): add anthropic adapter with structured output and error mapping"
```

---

### Task 7: OpenAI adapter

**Files:**
- Create: `development/backend/app/core/llm/adapters/openai.py`
- Test: `development/backend/tests/core/llm/test_adapter_openai.py`

**Interfaces:**
- Consumes: same shared types as Task 6.
- Produces: `OpenAIAdapter(client)` implements `LLMPort`. Structured: `client.chat.completions.parse(response_format=output_schema)`, read `choices[0].message.parsed`; if `message.refusal` set → raise `LLMRefusalError`. Text: `client.chat.completions.create(...)`, read `choices[0].message.content`. Map `finish_reason` (`stop`→`stop`, `length`→`length`, `content_filter`→`refusal`, `tool_calls`→`tool`). `_map_error` maps openai exceptions to typed errors.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_adapter_openai.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.openai import OpenAIAdapter
from app.core.llm.errors import LLMInvalidRequestError, LLMRefusalError


class _Band(BaseModel):
    band: str
    reason: str


def _choice(message, finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        model="gpt-5-2026",
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3),
    )


def _req(**kw):
    return LLMRequest(model="gpt-5", messages=[LLMMessage(role="user", content="hi")], **kw)


@pytest.mark.asyncio
async def test_text_completion():
    msg = SimpleNamespace(content="a summary", refusal=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.model_name == "gpt-5-2026"
    assert result.usage.output_tokens == 3
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion():
    msg = SimpleNamespace(parsed=_Band(band="urgent", reason="boss"), refusal=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    kwargs = client.chat.completions.parse.call_args.kwargs
    assert kwargs["response_format"] is _Band


@pytest.mark.asyncio
async def test_refusal_raises():
    msg = SimpleNamespace(parsed=None, refusal="I can't help with that")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=_choice(msg))))
    )
    adapter = OpenAIAdapter(client)
    with pytest.raises(LLMRefusalError):
        await adapter.complete(_req(output_schema=_Band))


@pytest.mark.asyncio
async def test_bad_request_maps():
    import openai

    err = openai.BadRequestError.__new__(openai.BadRequestError)
    Exception.__init__(err, "400")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=err)))
    )
    adapter = OpenAIAdapter(client)
    with pytest.raises(LLMInvalidRequestError):
        await adapter.complete(_req())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_openai.py -q`
Expected: FAIL with `ModuleNotFoundError` on `adapters.openai`.

- [ ] **Step 3: Implement the adapter**

Create `development/backend/app/core/llm/adapters/openai.py`:

```python
import time

import openai

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import LLMRequest, LLMResult, TokenUsage

_FINISH = {
    "stop": "stop",
    "length": "length",
    "content_filter": "refusal",
    "tool_calls": "tool",
}


def _map_error(exc: Exception) -> LLMError:
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMAuthError(str(exc))
    if isinstance(exc, openai.RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, openai.BadRequestError):
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return LLMTransientError(str(exc))
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return LLMTransientError(str(exc))
    return LLMTransientError(str(exc))


class OpenAIAdapter:
    def __init__(self, client: openai.AsyncOpenAI) -> None:
        self._client = client

    def _messages(self, request: LLMRequest) -> list[dict]:
        msgs: list[dict] = []
        if request.system is not None:
            msgs.append({"role": "system", "content": request.system})
        msgs.extend({"role": m.role, "content": m.content} for m in request.messages)
        return msgs

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        common = {
            "model": request.model,
            "messages": self._messages(request),
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        try:
            if request.output_schema is not None:
                resp = await self._client.chat.completions.parse(
                    response_format=request.output_schema, **common
                )
            else:
                resp = await self._client.chat.completions.create(**common)
        except openai.APIError as exc:
            raise _map_error(exc) from exc

        choice = resp.choices[0]
        usage = TokenUsage(
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )
        if request.output_schema is not None:
            if getattr(choice.message, "refusal", None):
                raise LLMRefusalError(choice.message.refusal)
            result = LLMResult(
                parsed=choice.message.parsed,
                model_name=resp.model,
                usage=usage,
                finish_reason="stop",
            )
        else:
            result = LLMResult(
                text=choice.message.content or "",
                model_name=resp.model,
                usage=usage,
                finish_reason=_FINISH.get(choice.finish_reason, "stop"),
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_openai.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm/adapters/openai.py tests/core/llm/test_adapter_openai.py
git commit -m "feat(llm): add openai adapter with parse-based structured output"
```

---

### Task 8: Gemini adapter

**Files:**
- Create: `development/backend/app/core/llm/adapters/gemini.py`
- Test: `development/backend/tests/core/llm/test_adapter_gemini.py`

**Interfaces:**
- Consumes: same shared types.
- Produces: `GeminiAdapter(client)` implements `LLMPort`. Uses `client.aio.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(...))`. Roles map `assistant`→`model`. Structured: set `response_mime_type="application/json"`, `response_schema=output_schema`; read `resp.parsed`. Text: read `resp.text`. Usage from `resp.usage_metadata` (`prompt_token_count`, `candidates_token_count`). `finish_reason` from `resp.candidates[0].finish_reason` name. `_map_error` maps `google.genai.errors.ClientError`/`ServerError`/`APIError` by `.code`.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_adapter_gemini.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.adapters.gemini import GeminiAdapter
from app.core.llm.errors import LLMAuthError, LLMTransientError


class _Band(BaseModel):
    band: str
    reason: str


def _response(text=None, parsed=None, finish="STOP"):
    return SimpleNamespace(
        text=text,
        parsed=parsed,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        usage_metadata=SimpleNamespace(prompt_token_count=8, candidates_token_count=2),
        model_version="gemini-2.5-pro-2026",
    )


def _client(response=None, side_effect=None):
    gen = AsyncMock(return_value=response) if side_effect is None else AsyncMock(side_effect=side_effect)
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))


def _req(**kw):
    return LLMRequest(model="gemini-2.5-pro", messages=[LLMMessage(role="user", content="hi")], **kw)


@pytest.mark.asyncio
async def test_text_completion():
    adapter = GeminiAdapter(_client(_response(text="a summary")))
    result = await adapter.complete(_req())
    assert result.text == "a summary"
    assert result.model_name == "gemini-2.5-pro-2026"
    assert result.usage.output_tokens == 2
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_structured_completion():
    client = _client(_response(parsed=_Band(band="urgent", reason="boss")))
    adapter = GeminiAdapter(client)
    result = await adapter.complete(_req(output_schema=_Band))
    assert result.parsed.band == "urgent"
    kwargs = client.aio.models.generate_content.call_args.kwargs
    assert kwargs["config"].response_schema is _Band
    assert kwargs["config"].response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_max_tokens_maps_to_length():
    adapter = GeminiAdapter(_client(_response(text="partial", finish="MAX_TOKENS")))
    result = await adapter.complete(_req())
    assert result.finish_reason == "length"


@pytest.mark.asyncio
async def test_client_error_maps():
    from google.genai import errors

    err = errors.ClientError.__new__(errors.ClientError)
    Exception.__init__(err, "403 forbidden")
    err.code = 403
    adapter = GeminiAdapter(_client(side_effect=err))
    with pytest.raises(LLMAuthError):
        await adapter.complete(_req())


@pytest.mark.asyncio
async def test_server_error_maps_transient():
    from google.genai import errors

    err = errors.ServerError.__new__(errors.ServerError)
    Exception.__init__(err, "503")
    err.code = 503
    adapter = GeminiAdapter(_client(side_effect=err))
    with pytest.raises(LLMTransientError):
        await adapter.complete(_req())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_gemini.py -q`
Expected: FAIL with `ModuleNotFoundError` on `adapters.gemini`.

- [ ] **Step 3: Implement the adapter**

Create `development/backend/app/core/llm/adapters/gemini.py`:

```python
import time

from google import genai
from google.genai import errors, types

from app.core.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMTransientError,
)
from app.core.llm.observability import log_completion
from app.core.llm.port import LLMRequest, LLMResult, TokenUsage

_FINISH = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "refusal",
    "RECITATION": "refusal",
}
_ROLE = {"user": "user", "assistant": "model"}


def _map_error(exc: Exception) -> LLMError:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return LLMAuthError(str(exc))
    if code == 429:
        return LLMRateLimitError(str(exc))
    if code == 400:
        return LLMInvalidRequestError(str(exc))
    if isinstance(exc, errors.ServerError) or (isinstance(code, int) and code >= 500):
        return LLMTransientError(str(exc))
    return LLMTransientError(str(exc))


class GeminiAdapter:
    def __init__(self, client: genai.Client) -> None:
        self._client = client

    async def complete(self, request: LLMRequest) -> LLMResult:
        started = time.perf_counter()
        contents = [
            types.Content(role=_ROLE[m.role], parts=[types.Part(text=m.content)])
            for m in request.messages
        ]
        config_kwargs: dict = {
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.system is not None:
            config_kwargs["system_instruction"] = request.system
        if request.output_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = request.output_schema

        try:
            resp = await self._client.aio.models.generate_content(
                model=request.model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except errors.APIError as exc:
            raise _map_error(exc) from exc

        usage = TokenUsage(
            input_tokens=resp.usage_metadata.prompt_token_count,
            output_tokens=resp.usage_metadata.candidates_token_count,
        )
        finish_name = resp.candidates[0].finish_reason.name
        if request.output_schema is not None:
            result = LLMResult(
                parsed=resp.parsed,
                model_name=resp.model_version,
                usage=usage,
                finish_reason="stop",
            )
        else:
            result = LLMResult(
                text=resp.text or "",
                model_name=resp.model_version,
                usage=usage,
                finish_reason=_FINISH.get(finish_name, "stop"),
            )
        log_completion(request, result, (time.perf_counter() - started) * 1000)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_adapter_gemini.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm/adapters/gemini.py tests/core/llm/test_adapter_gemini.py
git commit -m "feat(llm): add gemini adapter with response_schema structured output"
```

---

### Task 9: Registry and factory

**Files:**
- Create: `development/backend/app/core/llm/registry.py`
- Modify: `development/backend/app/core/llm/__init__.py`
- Test: `development/backend/tests/core/llm/test_registry.py`

**Interfaces:**
- Consumes: `LLMPort`, adapters (Tasks 6-8), `Settings` (Task 4), `LLMInvalidRequestError`, `LLMAuthError`.
- Produces:
  - `PROVIDER_BY_MODEL: dict[str, str]` mapping logical model id → provider name (`"anthropic"`/`"openai"`/`"gemini"`). Keys include at least `"claude-sonnet-5"`, `"claude-opus-4-8"`, `"gpt-5"`, `"gemini-2.5-pro"`.
  - `resolve_provider(model: str) -> str` — returns provider, raises `LLMInvalidRequestError` for unknown model.
  - `build_llm(model: str, settings) -> LLMPort` — constructs the provider adapter with a lazily-created SDK client from the matching key; raises `LLMAuthError` when the key is empty.

- [ ] **Step 1: Write the failing test**

Create `development/backend/tests/core/llm/test_registry.py`:

```python
import pytest

from app.core.config import Settings
from app.core.llm.adapters.anthropic import AnthropicAdapter
from app.core.llm.adapters.gemini import GeminiAdapter
from app.core.llm.adapters.openai import OpenAIAdapter
from app.core.llm.errors import LLMAuthError, LLMInvalidRequestError
from app.core.llm.registry import build_llm, resolve_provider


def test_resolve_known_models():
    assert resolve_provider("claude-sonnet-5") == "anthropic"
    assert resolve_provider("gpt-5") == "openai"
    assert resolve_provider("gemini-2.5-pro") == "gemini"


def test_resolve_unknown_raises():
    with pytest.raises(LLMInvalidRequestError):
        resolve_provider("no-such-model")


def test_build_llm_returns_matching_adapter():
    settings = Settings(
        _env_file=None,
        anthropic_api_key="k",
        openai_api_key="k",
        google_api_key="k",
    )
    assert isinstance(build_llm("claude-sonnet-5", settings), AnthropicAdapter)
    assert isinstance(build_llm("gpt-5", settings), OpenAIAdapter)
    assert isinstance(build_llm("gemini-2.5-pro", settings), GeminiAdapter)


def test_build_llm_missing_key_raises_auth():
    settings = Settings(_env_file=None)  # all keys empty
    with pytest.raises(LLMAuthError):
        build_llm("claude-sonnet-5", settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd development/backend && python -m pytest tests/core/llm/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError` on `registry`.

- [ ] **Step 3: Implement the registry**

Create `development/backend/app/core/llm/registry.py`:

```python
from app.core.config import Settings
from app.core.llm.errors import LLMAuthError, LLMInvalidRequestError
from app.core.llm.port import LLMPort

PROVIDER_BY_MODEL: dict[str, str] = {
    "claude-sonnet-5": "anthropic",
    "claude-opus-4-8": "anthropic",
    "gpt-5": "openai",
    "gpt-5-mini": "openai",
    "gemini-2.5-pro": "gemini",
    "gemini-2.5-flash": "gemini",
}


def resolve_provider(model: str) -> str:
    try:
        return PROVIDER_BY_MODEL[model]
    except KeyError as exc:
        raise LLMInvalidRequestError(f"unknown model: {model}") from exc


def build_llm(model: str, settings: Settings) -> LLMPort:
    provider = resolve_provider(model)
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMAuthError("ANTHROPIC_API_KEY is not set")
        import anthropic

        from app.core.llm.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter(anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key))
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMAuthError("OPENAI_API_KEY is not set")
        import openai

        from app.core.llm.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(openai.AsyncOpenAI(api_key=settings.openai_api_key))
    if not settings.google_api_key:
        raise LLMAuthError("GOOGLE_API_KEY is not set")
    from google import genai

    from app.core.llm.adapters.gemini import GeminiAdapter

    return GeminiAdapter(genai.Client(api_key=settings.google_api_key))
```

Add to `development/backend/app/core/llm/__init__.py`:

```python
from app.core.llm.registry import PROVIDER_BY_MODEL, build_llm, resolve_provider
```

Add `"PROVIDER_BY_MODEL"`, `"build_llm"`, `"resolve_provider"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd development/backend && python -m pytest tests/core/llm/test_registry.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd development/backend && git add app/core/llm tests/core/llm/test_registry.py
git commit -m "feat(llm): add model registry and lazy adapter factory"
```

---

### Task 10: Live provider contract test (env-gated)

**Files:**
- Create: `development/backend/tests/core/llm/test_live_contract.py`

**Interfaces:**
- Consumes: `build_llm`, `Settings`, `LLMRequest`, `LLMMessage`.
- Produces: nothing runtime — a test skipped unless `MAILY_RUN_LIVE_LLM_TESTS=1`, mirroring the Gmail live gate. It sends one real completion per configured provider and asserts a non-empty structured result.

- [ ] **Step 1: Write the gated test**

Create `development/backend/tests/core/llm/test_live_contract.py`:

```python
import os

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.llm import LLMMessage, LLMRequest
from app.core.llm.registry import build_llm

pytestmark = pytest.mark.skipif(
    os.getenv("MAILY_RUN_LIVE_LLM_TESTS") != "1",
    reason="live LLM tests require MAILY_RUN_LIVE_LLM_TESTS=1 and provider keys",
)


class _Band(BaseModel):
    band: str
    reason: str


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["claude-sonnet-5", "gpt-5", "gemini-2.5-pro"])
async def test_live_structured_completion(model):
    settings = Settings()
    llm = build_llm(model, settings)
    result = await llm.complete(
        LLMRequest(
            model=model,
            system="Classify importance. band is one of urgent|normal.",
            messages=[LLMMessage(role="user", content="Subject: Server on fire. From: ops@corp")],
            output_schema=_Band,
            max_output_tokens=200,
        )
    )
    assert isinstance(result.parsed, _Band)
    assert result.parsed.band
    assert result.usage.output_tokens >= 0
```

- [ ] **Step 2: Verify it is skipped by default**

Run: `cd development/backend && python -m pytest tests/core/llm/test_live_contract.py -q`
Expected: skipped (3 skipped), no network call.

- [ ] **Step 3: Commit**

```bash
cd development/backend && git add tests/core/llm/test_live_contract.py
git commit -m "test(llm): add env-gated live provider contract test"
```

---

### Task 11: Full-suite gate and lint

**Files:**
- None new — verification only.

- [ ] **Step 1: Run the whole LLM suite**

Run: `cd development/backend && python -m pytest tests/core/llm -q`
Expected: all pass except the 3 skipped live tests.

- [ ] **Step 2: Run the entire test suite**

Run: `cd development/backend && python -m pytest -q`
Expected: all green (health test + llm suite), live tests skipped.

- [ ] **Step 3: Lint and type-check**

Run: `cd development/backend && python -m ruff check . && python -m mypy app`
Expected: no errors. Fix any ruff/mypy findings in `app/core/llm/` (common: unused imports, missing return annotations) and re-run until clean.

- [ ] **Step 4: Commit any lint fixes**

```bash
cd development/backend && git add -A && git commit -m "chore(llm): satisfy ruff and mypy for llm slice" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- Scope (provider layer only) → Tasks 1-11; assistant_decisions wiring explicitly excluded (no task) ✓
- `LLMRequest`/`LLMResult`/`LLMMessage`/`TokenUsage`/`LLMPort` → Task 1 ✓
- Typed errors + retryable + retry-owned-by-dispatcher → Task 2 (retry loop intentionally absent from adapters) ✓
- Fake → Task 3 ✓
- Config keys → Task 4 ✓
- Content-safe logging → Task 5 ✓
- 3 adapters with native structured output → Tasks 6-8 ✓
- registry + lazy client + unknown-model/missing-key errors → Task 9 ✓
- Live gate → Task 10 ✓
- Dependencies pinned → Task 1 Step 1 ✓
- No streaming → not implemented (correct) ✓

**Type consistency:** `complete(request) -> LLMResult` used identically across fake and all adapters. `build_llm(model, settings) -> LLMPort` and `resolve_provider(model) -> str` match Task 9 tests. `log_completion(request, result, latency_ms)` matches Task 5 usage in adapters. `TokenUsage(input_tokens, output_tokens)` consistent everywhere.

**Placeholder scan:** No TBD/TODO; every code step shows full code. Version pins concrete (anthropic 0.116.0, openai 2.44.0, google-genai 2.10.0). SDK response-shape assumptions (`resp.model`, `resp.usage`, `choice.message.parsed`, `resp.parsed`, `resp.model_version`) are validated against mocks in unit tests and against reality in the Task 10 live gate; if a real SDK field name differs at implementation time, fix the adapter and its mock together.
