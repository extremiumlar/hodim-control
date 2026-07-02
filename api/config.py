from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        extra="ignore",
    )

    debug: bool = True
    timezone: str = "Asia/Tashkent"

    bot_token: str = ""
    bot_shared_secret: str = "please-change-this-bot-secret"

    database_url: str = "sqlite+aiosqlite:///./app.db"

    jwt_secret: str = "please-change-this-secret"
    jwt_expire_minutes: int = 1440

    frontend_url: str = "http://localhost:5173"
    telegram_login_bot_username: str = ""
    telegram_group_chat_id: int = 0

    crm_type: str = "none"
    crm_webhook_secret: str = ""

    @field_validator("telegram_group_chat_id", mode="before")
    @classmethod
    def _empty_group_id_to_zero(cls, value: object) -> object:
        if value == "":
            return 0
        return value


settings = Settings()
