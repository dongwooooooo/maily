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
