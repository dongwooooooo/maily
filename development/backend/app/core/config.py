from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Maily API"
    # 프론트 dev 서버 origin. 운영 배포 origin은 Task15에서 env로 주입한다.
    # env 주입 시 JSON 배열 문자열 형식 필수(pydantic-settings 복합 타입 규칙):
    #   CORS_ALLOW_ORIGINS='["https://app.example.com"]'  — 콤마 구분 문자열 아님.
    cors_allow_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    database_url: str = "postgresql+asyncpg://maily:maily@localhost:5432/maily"
    redis_url: str = "redis://localhost:6379/0"
    jwt_issuer: str = "maily"
    jwt_secret: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    token_encryption_key: str = ""
    pubsub_webhook_token: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    llm_default_model: str = "claude-sonnet-5"


settings = Settings()
