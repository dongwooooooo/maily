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
