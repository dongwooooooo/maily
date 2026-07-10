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
