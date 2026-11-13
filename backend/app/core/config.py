from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./finsight.db"
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]
    # Pinned "now" for the whole app so demo recordings are reproducible —
    # every runway/forecast/"this month" calculation reads this, never datetime.now().
    as_of_date: date = date(2026, 11, 14)


settings = Settings()
