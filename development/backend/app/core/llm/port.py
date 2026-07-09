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
