from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Maily API"
    database_url: str = "postgresql+asyncpg://maily:maily@localhost:5432/maily"
    redis_url: str = "redis://localhost:6379/0"
    jwt_issuer: str = "maily"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""


settings = Settings()
