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
