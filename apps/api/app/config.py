from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./starry.db"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    admin_token: str = ""
    allowed_origins: str = "https://starry-journey.github.io,http://localhost:4000,http://127.0.0.1:4000"
    daily_message_limit: int = 20


settings = Settings()
