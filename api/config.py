import logging
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_JWT_SECRET = "please-change-this-secret"
_PLACEHOLDER_BOT_SECRET = "please-change-this-bot-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        extra="ignore",
    )

    debug: bool = False
    timezone: str = "Asia/Tashkent"

    bot_token: str = ""
    bot_shared_secret: str = _PLACEHOLDER_BOT_SECRET

    database_url: str = "sqlite+aiosqlite:///./app.db"

    jwt_secret: str = _PLACEHOLDER_JWT_SECRET
    jwt_expire_minutes: int = 1440

    frontend_url: str = "http://localhost:5173"
    telegram_login_bot_username: str = ""
    telegram_group_chat_id: int = 0

    crm_type: str = "none"
    crm_webhook_secret: str = ""

    # Soatlik reja avtomatik eslatmasi — haqiqiy xodimlarga Telegram xabar yuboradi,
    # shuning uchun default O'CHIQ. Ishga tushirishga tayyor bo'lganda .env'da
    # HOURLY_PLAN_ENABLED=true qo'ying. (Botdagi "Bugungi rejam" tugmasi bundan
    # qat'i nazar ishlaydi — u xodimning o'zi ochishi, push emas.)
    hourly_plan_enabled: bool = False

    # Operator AI tizimi (Claude Opus 4.8) — avto-reja, kompozit kuzatuv, sabab
    # halqasi va guruh xulosasini odam tiliga o'giradi. Default O'CHIQ: yoqilmaganda
    # butun AI qatlami deterministik (kod) shablonlarga qaytadi va Claude API'ga
    # umuman murojaat qilmaydi (xarajat/xavfsizlik). Yoqish uchun .env'da
    # AI_ENABLED=true + ANTHROPIC_API_KEY qo'ying.
    ai_enabled: bool = False
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"

    @field_validator("telegram_group_chat_id", mode="before")
    @classmethod
    def _empty_group_id_to_zero(cls, value: object) -> object:
        if value == "":
            return 0
        return value

    @model_validator(mode="after")
    def _warn_on_placeholder_secrets(self) -> "Settings":
        placeholders = []
        if self.jwt_secret == _PLACEHOLDER_JWT_SECRET:
            placeholders.append("JWT_SECRET")
        if self.bot_shared_secret == _PLACEHOLDER_BOT_SECRET:
            placeholders.append("BOT_SHARED_SECRET")

        if placeholders:
            message = (
                f"XAVFSIZLIK OGOHLANTIRISHI: {', '.join(placeholders)} hali standart "
                "(placeholder) qiymatda turibdi — .env faylida haqiqiy maxfiy "
                "qiymatlar bilan almashtiring."
            )
            if self.debug:
                logger.error(message)
            else:
                raise RuntimeError(message)

        # AI yoqilgan bo'lsa kalit shart — aks holda har chaqiruv jimgina fallback'ga
        # tushib, "AI ishlayapti" degan noto'g'ri taassurot beradi. Erta va aniq xato.
        if self.ai_enabled and not self.anthropic_api_key:
            message = "AI_ENABLED=true, lekin ANTHROPIC_API_KEY bo'sh — .env' da kalit qo'ying yoki AI_ENABLED=false qiling."
            if self.debug:
                logger.error(message)
            else:
                raise RuntimeError(message)
        return self


settings = Settings()
