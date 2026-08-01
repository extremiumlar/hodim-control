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
    # Telegram webhook sekreti — `bot_shared_secret`DAN ALOHIDA bo'lishi kerak.
    #
    # NEGA AJRATILDI: `bot_shared_secret` — bu `X-Bot-Secret`, ya'ni ~100 ta
    # ichki endpointning kaliti VA `/auth/bot-token` orqali to'liq Dasturchi
    # JWT'sini beradi. Webhook sekreti esa tashqi tomonga (Telegram) beriladi
    # va sizib chiqish ehtimoli yuqoriroq (eski `/bot/webhook/{secret}` yo'li
    # uni access_log'ga yozib qo'yardi). Ikkalasi bir xil bo'lsa, bitta log
    # qatori butun tizimni ochib berardi.
    #
    # Bo'sh bo'lsa — orqaga moslik uchun `bot_shared_secret` ishlatiladi, lekin
    # .env'da ALOHIDA qiymat qo'ying va `scripts/set_webhook.py` ni qayta
    # ishga tushiring.
    telegram_webhook_secret: str = ""
    # cPanel deploy: bot alohida polling jarayoni sifatida emas, shu API ichida
    # webhook orqali ishlaydi (shared hostingda doimiy jarayon yo'q). Default
    # O'CHIQ — Docker/VPS'da bot alohida polling qiladi, ikki marta ishlanmasin.
    bot_webhook_enabled: bool = False

    # ── Push bildirishnomalar (Firebase Cloud Messaging) ──
    # To'g'ridan-to'g'ri FCM, Expo relay'i EMAS: (1) `getExpoPushTokenAsync`
    # EAS `projectId` talab qiladi, bizda esa build butunlay lokal
    # (MOBIL_ILOVA_REJASI 8.5); (2) bildirishnoma matnida oylik/bonus summasi
    # bo'ladi — uni ortiqcha uchinchi tomon relay'idan o'tkazmaymiz.
    # Ikkalasi ham bo'sh bo'lsa push JIM o'chiq turadi (Telegram ishlayveradi).
    fcm_project_id: str = ""
    fcm_service_account_file: str = ""

    database_url: str = "sqlite+aiosqlite:///./app.db"

    jwt_secret: str = _PLACEHOLDER_JWT_SECRET
    # 30 kun. Ilgari 1440 (24 soat) edi — kuniga 2 marta ishlatiladigan
    # davomat ilovasi uchun xodim HAR KUNI qaytadan login qilardi.
    # Refresh-token yo'q, lekin bekor qilish yo'li BOR: get_current_user
    # har so'rovda `is_active`ni tekshiradi (api/deps.py), ya'ni xodimni
    # o'chirish (ishdan ketsa, telefoni yo'qolsa) tokenni darhol kesadi.
    jwt_expire_minutes: int = 43200

    # Oldimizda nechta ISHONCHLI proxy turibdi (nginx, LiteSpeed, CDN...).
    # `rate_limit` mijoz IP'sini `X-Forwarded-For` dan shu songa qarab OLADI.
    #
    # NEGA KERAK: nginx `$proxy_add_x_forwarded_for` bilan sarlavhaga QO'SHADI,
    # ya'ni ro'yxatning BIRINCHI qiymati — mijozning O'ZI yozgan qiymat.
    # Ilgari aynan birinchisi olinardi: hujumchi har so'rovda tasodifiy
    # `X-Forwarded-For` yozib, barcha rate-limit cheklovlarini aylanib
    # o'tardi (va har so'rov `LoginAttempt` qatori yaratgani uchun bazani
    # shishirardi). Oxiridan sanaganda faqat bizning proxy yozgan qiymat olinadi.
    #
    # cPanel'da nginx + LiteSpeed bo'lsa 2 bo'lishi mumkin — `/health` ga
    # so'rov yuborib, log'dagi X-Forwarded-For uzunligini tekshiring.
    trusted_proxy_count: int = 1

    frontend_url: str = "http://localhost:5173"
    telegram_login_bot_username: str = ""
    # Taklif havolasi (invite_token) muddati — shu kundan keyin token yaroqsiz
    # bo'ladi (Telegram login xavfsizlik arxitekturasi, Layer 3). Eski (bu
    # sozlama qo'shilishidan oldingi) qatorlarda invite_expires_at NULL qoladi —
    # ular orqaga moslik uchun muddatsiz.
    invite_token_ttl_days: int = 7
    # Asosiy guruh — mobilograf videolari va issiq lid xabarlari shu yerga tushadi.
    telegram_group_chat_id: int = 0
    # Statistika uchun QO'SHIMCHA guruh(lar). Kunlik/haftalik digest doim asosiy
    # guruhga chiqadi; bu yerga yozilgan guruh(lar)ga ham HAM yuboriladi (nusxa).
    # Bir nechta bo'lsa vergul bilan: "-100111,-100222". Bo'sh — faqat asosiy guruh.
    telegram_stats_group_chat_id: str = ""

    crm_type: str = "none"
    crm_webhook_secret: str = ""

    # Tashqi chatbot uchun bilim bazasi dataseti (GET /knowledge/dataset?key=...).
    # Bo'sh — endpoint o'chiq (404). Tasodifiy uzun qiymat qo'ying:
    # python3 -c "import secrets;print(secrets.token_urlsafe(32))"
    knowledge_dataset_key: str = ""

    # Kelib-ketish davomati (verifix'dan birlashtirilgan) — kechikishga ruxsat (grace).
    # Ish oynasi boshlanishidan shu daqiqadan keyin kelinsagina kechikish hisoblanadi.
    attendance_grace_minutes: int = 5
    # Face ID chegaralari (hodim_crm bilan bir xil): similarity = 1 - evklid masofa;
    # liveness = tiriklik (bir nechta freym harakati). Ikkalasi ham >= bo'lishi shart.
    face_similarity_threshold: float = 0.5
    face_liveness_threshold: float = 0.5
    # GPS aniqligi (brauzer `position.coords.accuracy`, metrda). Bundan yomonroq
    # (masalan IP-asosidagi zaxira geolokatsiya, ba'zan 1000+ metr) o'qish rad etiladi —
    # aks holda ofisdan uzoqdagi kishi "aniqlik yo'q" bahonasida ham check-in qila oladi.
    attendance_max_gps_accuracy_m: int = 100

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

    @property
    def webhook_secret(self) -> str:
        """Telegram webhook uchun amaldagi sekret. Alohida qiymat berilmagan
        bo'lsa — orqaga moslik uchun `bot_shared_secret`ga tushadi."""
        return self.telegram_webhook_secret or self.bot_shared_secret

    @model_validator(mode="after")
    def _warn_on_placeholder_secrets(self) -> "Settings":
        # DIQQAT: BO'SH qiymat ham rad etiladi, nafaqat placeholder.
        # Sabab: `hmac.compare_digest("", "")` -> True. Sekret bo'sh bo'lsa
        # `/bot/webhook` butunlay ochilib ketardi va istalgan kishi SOXTA
        # Telegram update yuborib, istalgan foydalanuvchini (jumladan
        # Dasturchini) taqlid qila olardi. Ilgari faqat placeholder
        # tekshirilgani uchun `BOT_SHARED_SECRET=` bilan tizim jimgina
        # ishga tushib ketardi.
        _MIN_SECRET_LEN = 16
        placeholders = []
        if not self.jwt_secret or self.jwt_secret == _PLACEHOLDER_JWT_SECRET:
            placeholders.append("JWT_SECRET")
        elif len(self.jwt_secret) < _MIN_SECRET_LEN:
            placeholders.append(f"JWT_SECRET (juda qisqa, kamida {_MIN_SECRET_LEN} belgi)")
        if not self.bot_shared_secret or self.bot_shared_secret == _PLACEHOLDER_BOT_SECRET:
            placeholders.append("BOT_SHARED_SECRET")
        elif len(self.bot_shared_secret) < _MIN_SECRET_LEN:
            placeholders.append(f"BOT_SHARED_SECRET (juda qisqa, kamida {_MIN_SECRET_LEN} belgi)")
        # Alohida webhook sekreti IXTIYORIY (bo'sh bo'lsa bot_shared_secret'ga
        # tushadi), lekin berilgan bo'lsa — u ham jiddiy bo'lsin.
        if self.telegram_webhook_secret and len(self.telegram_webhook_secret) < _MIN_SECRET_LEN:
            placeholders.append(f"TELEGRAM_WEBHOOK_SECRET (juda qisqa, kamida {_MIN_SECRET_LEN} belgi)")

        if placeholders:
            message = (
                f"XAVFSIZLIK OGOHLANTIRISHI: {', '.join(placeholders)} bo'sh, standart "
                "(placeholder) yoki juda qisqa qiymatda turibdi — .env faylida haqiqiy "
                "maxfiy qiymatlar bilan almashtiring."
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
