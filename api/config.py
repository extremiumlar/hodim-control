import logging
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    # Asosiy guruh — mobilograf videolari va issiq lid xabarlari shu yerga tushadi.
    telegram_group_chat_id: int = 0
    # Statistika uchun QO'SHIMCHA guruh(lar). Kunlik/haftalik digest doim asosiy
    # guruhga chiqadi; bu yerga yozilgan guruh(lar)ga ham HAM yuboriladi (nusxa).
    # Bir nechta bo'lsa vergul bilan: "-100111,-100222". Bo'sh — faqat asosiy guruh.
    telegram_stats_group_chat_id: str = ""

    crm_type: str = "none"
    crm_webhook_secret: str = ""

    # Soatlik reja avtomatik eslatmasi — haqiqiy xodimlarga Telegram xabar yuboradi,
    # shuning uchun default O'CHIQ. Ishga tushirishga tayyor bo'lganda .env'da
    # HOURLY_PLAN_ENABLED=true qo'ying. (Botdagi "Bugungi rejam" tugmasi bundan
    # qat'i nazar ishlaydi — u xodimning o'zi ochishi, push emas.)
    hourly_plan_enabled: bool = False

    # Operator AI tizimi — avto-reja, kompozit kuzatuv, sabab halqasi va guruh
    # xulosasini odam tiliga o'giradi. Default O'CHIQ: yoqilmaganda butun AI qatlami
    # deterministik (kod) shablonlarga qaytadi va tashqi API'ga umuman murojaat
    # qilmaydi (xarajat/xavfsizlik). Yoqish: .env'da AI_ENABLED=true + tanlangan
    # provayder kaliti.
    #
    # Provayder tanlovi: "anthropic" (Claude, tavsiya — sabab tahlili/ohang kuchli)
    # yoki "gemini" (bepul tier, oddiy matnlar uchun yetarli). Matn yozishdan boshqa
    # hech narsa modelga topshirilmaydi (hisob-qarorlar kodda), shuning uchun
    # provayderni almashtirish xavfsiz — bitta env qator.
    # DIQQAT: `AI_PROVIDER` va `GEMINI_API_KEY` nomlari juda umumiy — foydalanuvchi
    # kompyuterida boshqa vositalar (masalan ollama) shu nomdagi global muhit
    # o'zgaruvchilarini qo'ygan bo'lishi mumkin va OS env .env'dan USTUN turadi.
    # Shuning uchun bu ikkisi OPERATOR_ prefiksli nom bilan o'qiladi.
    ai_enabled: bool = False
    ai_provider: str = Field("anthropic", validation_alias="OPERATOR_AI_PROVIDER")  # anthropic | gemini
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"
    gemini_api_key: str = Field("", validation_alias="OPERATOR_GEMINI_API_KEY")
    # gemini-2.5-flash: tez (~1s) va barqaror. gemini-3.5-flash yuk ostida sekin
    # (6-18s) va 503 berardi — interaktiv /statistika digestini osiб qo'yardi.
    gemini_model: str = Field("gemini-2.5-flash", validation_alias="OPERATOR_GEMINI_MODEL")
    # Nudge PUSH alohida bayroq (hourly_plan_enabled naqshi): AI_ENABLED faqat matn
    # generatsiyasini yoqadi; haqiqiy operatorlarga Telegram xabar yuborish uchun
    # .env'da AI_NUDGE_ENABLED=true ham kerak. Tick endpointi dry_run=true bilan
    # yubormasdan sinash imkonini beradi.
    ai_nudge_enabled: bool = False
    # Issiq lid (speed-to-lead, 5-bosqich) — yangi CRM lidi haqida operatorga darhol
    # DM + javob tezligi o'lchovi + kechiksa guruhga eskalatsiya. Haqiqiy xabar
    # yuborgani uchun alohida opt-in (default O'CHIQ); AI matni ishlatilmaydi
    # (tezlik uchun shablon), shuning uchun AI_ENABLED'dan MUSTAQIL. Runtime'da
    # boss /ai_sozlama'dan alohida o'chira oladi (ai_config.hot_leads_enabled).
    hot_lead_enabled: bool = False

    @field_validator("telegram_group_chat_id", mode="before")
    @classmethod
    def _empty_group_id_to_zero(cls, value: object) -> object:
        if value == "":
            return 0
        return value

    @property
    def stats_group_ids(self) -> list[int]:
        """Qo'shimcha statistika guruhlari ID'lari — vergul bilan ajratilgan
        `telegram_stats_group_chat_id` dan parse qilinadi. Noto'g'ri/bo'sh qismlar
        tashlanadi, takrorlar chiqariladi."""
        out: list[int] = []
        for part in str(self.telegram_stats_group_chat_id).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                val = int(part)
            except ValueError:
                continue
            if val and val not in out:
                out.append(val)
        return out

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

        # AI yoqilgan bo'lsa tanlangan provayder kaliti shart — aks holda har chaqiruv
        # jimgina fallback'ga tushib, "AI ishlayapti" degan noto'g'ri taassurot beradi.
        if self.ai_enabled:
            message = None
            if self.ai_provider == "anthropic" and not self.anthropic_api_key:
                message = "AI_ENABLED=true (provider=anthropic), lekin ANTHROPIC_API_KEY bo'sh — .env'da kalit qo'ying."
            elif self.ai_provider == "gemini" and not self.gemini_api_key:
                message = "AI_ENABLED=true (provider=gemini), lekin GEMINI_API_KEY bo'sh — .env'da kalit qo'ying."
            elif self.ai_provider not in ("anthropic", "gemini"):
                message = f"AI_PROVIDER noto'g'ri: {self.ai_provider!r} (anthropic yoki gemini bo'lishi kerak)."
            if message:
                if self.debug:
                    logger.error(message)
                else:
                    raise RuntimeError(message)
        return self


settings = Settings()
