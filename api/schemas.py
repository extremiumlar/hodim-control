import datetime as dt
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


# Lavozim uchun qo'llab-quvvatlanadigan ko'rsatkichlar va bot menyu tugmalari.
# Bu ro'yxatlar backend hisob-kitobi mavjud bo'lgan qiymatlar bilan cheklangan —
# ixtiyoriy satr qabul qilinsa, hech qayerda hisoblanmaydigan "o'lik" norma paydo
# bo'lar edi (avvalgi audit shuni ko'rsatgan).
POSITION_METRICS = ["suhbat", "tashrif", "video"]
POSITION_MENU_KEYS = ["tasks", "norm", "kpi", "excused"]
POSITION_MANAGER_ROLES = ["rop", "hr"]


class PositionBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    menu_flags: dict[str, bool] | None = None
    metrics: list[str] | None = None
    managed_by_roles: list[str] | None = None

    @field_validator("metrics")
    @classmethod
    def _check_metrics(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            bad = [m for m in v if m not in POSITION_METRICS]
            if bad:
                raise ValueError(f"Noma'lum ko'rsatkich(lar): {', '.join(bad)}")
        return v

    @field_validator("managed_by_roles")
    @classmethod
    def _check_managers(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            bad = [r for r in v if r not in POSITION_MANAGER_ROLES]
            if bad:
                raise ValueError(f"Noma'lum boshqaruvchi rol(lar): {', '.join(bad)}")
        return v

    @field_validator("menu_flags")
    @classmethod
    def _check_menu_flags(cls, v: dict[str, bool] | None) -> dict[str, bool] | None:
        if v is not None:
            bad = [k for k in v if k not in POSITION_MENU_KEYS]
            if bad:
                raise ValueError(f"Noma'lum menyu kaliti(lari): {', '.join(bad)}")
        return v


class PositionCreate(PositionBase):
    pass


class PositionUpdate(PositionBase):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class PositionOut(BaseModel):
    id: int
    name: str
    menu_flags: dict | None
    metrics: list | None
    managed_by_roles: list | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionBrief(BaseModel):
    """UserOut ichida yuboriladigan qisqa lavozim ma'lumoti — bot menyusi va
    norma oqimi shu ma'lumotga qarab moslashadi."""

    id: int
    name: str
    menu_flags: dict | None
    metrics: list | None
    managed_by_roles: list | None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    telegram_id: int | None
    full_name: str
    role: str
    team_id: int | None
    manager_id: int | None
    position_id: int | None = None
    position: PositionBrief | None = None
    bot_started: bool
    is_active: bool
    crm_external_id: str | None
    crm_visit_external_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCrmIdUpdate(BaseModel):
    crm_external_id: str | None = None
    crm_visit_external_id: str | None = None


class UserRoleUpdate(BaseModel):
    role: str


class UserPositionUpdate(BaseModel):
    position_id: int | None = None


class UserCreate(BaseModel):
    full_name: str
    role: str
    team_id: int | None = None
    manager_id: int | None = None
    crm_external_id: str | None = None


class UserCreateOut(BaseModel):
    user: UserOut
    invite_link: str


class CrmOperatorRow(BaseModel):
    crm_external_id: str
    calls_today: int
    matched_user: UserOut | None = None
    # Email manzilining "@"dan oldingi qismida xodim ismi uchrasa (masalan
    # "nurlidiyorkamola@..." ichida "kamola"), taklif sifatida ko'rsatiladi.
    suggested_user: UserOut | None = None


class CrmVisitOperatorRow(BaseModel):
    responsible_id: str
    responsible_name: str
    visits_today: int
    matched_user: UserOut | None = None
    # Ism bo'yicha eng yaqin mos keladigan (hali bog'lanmagan, Telegram orqali ulangan)
    # foydalanuvchi — qo'lda tanlashni osonlashtirish uchun taklif sifatida.
    suggested_user: UserOut | None = None


class DevLoginRequest(BaseModel):
    telegram_id: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TelegramStartRequest(BaseModel):
    telegram_id: int
    invite_token: str | None = None


class TelegramStartResponse(BaseModel):
    status: str  # ok | invalid_token | already_linked | no_account
    user: UserOut | None = None


class TaskCreate(BaseModel):
    assigned_to: int
    title: str
    description: str | None = None
    deadline: datetime | None = None


class TaskBotCreate(BaseModel):
    assigner_telegram_id: int
    assigned_to: int
    title: str
    description: str | None = None
    deadline: datetime | None = None


# Ommaviy vazifa nishonlari: barcha xodimlar / rol bo'yicha (rop, hr, rop+hr,
# employee) / lavozim bo'yicha. Faqat Boshliq/Dasturchi ishlata oladi.
BULK_TARGET_TYPES = ["all_employees", "role", "position"]


class TaskBulkCreate(BaseModel):
    target_type: str  # all_employees | role | position
    target_roles: list[str] | None = None  # target_type="role" uchun, masalan ["rop", "hr"]
    position_id: int | None = None  # target_type="position" uchun
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    deadline: datetime | None = None

    @field_validator("target_type")
    @classmethod
    def _check_target_type(cls, v: str) -> str:
        if v not in BULK_TARGET_TYPES:
            raise ValueError(f"Noma'lum nishon turi: {v}")
        return v


class TaskBulkBotCreate(TaskBulkCreate):
    assigner_telegram_id: int


class TaskOut(BaseModel):
    id: int
    assigned_by: int
    assigned_to: int
    assigned_to_name: str
    title: str
    description: str | None
    deadline: datetime | None
    status: str
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCompleteRequest(BaseModel):
    telegram_id: int


class ExcusedDayCreate(BaseModel):
    telegram_id: int
    # Berilmasa backend bugungi (Toshkent) sanani o'zi qo'yadi — bot server
    # vaqtiga tayanmasligi uchun sanani yubormaydi. (`dt.date` to'liq yo'l bilan,
    # chunki `date: date | None = None` ko'rinishida class tanasi avval `date=None`
    # defaultni saqlab, keyin anotatsiyani baholaydi — tip nomi maydon nomiga to'qnashadi.)
    date: dt.date | None = None
    reason: str


class ExcusedDayOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str
    date: date
    reason: str
    status: str
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExcusedDayDecide(BaseModel):
    decider_telegram_id: int
    decision: str  # approved | rejected


class NormCreate(BaseModel):
    user_id: int
    metric_type: str = Field(min_length=1, max_length=50)  # suhbat | tashrif | custom
    value: int = Field(ge=0)


class NormBotUpdate(BaseModel):
    changer_telegram_id: int
    target_user_id: int
    metric_type: str = Field(min_length=1, max_length=50)
    value: int = Field(ge=0)


class NormOut(BaseModel):
    id: int
    user_id: int
    metric_type: str
    value: int
    changed_by: int
    effective_from: date
    created_at: datetime

    model_config = {"from_attributes": True}


class MetricProgressRow(BaseModel):
    """Bitta ko'rsatkich bo'yicha jonli holat: bugungi (yoki joriy) qiymat va
    belgilangan norma. Bot ("Bugungi normam"/"Statistikam") va sayt (jamoa normalari
    jadvali) shu bir xil shaklni ishlatadi — CRM/qo'lda kiritilgan haqiqiy natija
    har doim norma bilan yonma-yon ko'rinishi uchun."""

    key: str  # suhbat | tashrif | video
    label: str
    value: int  # bugungi haqiqiy qiymat (CRM yoki qo'lda kiritilgan)
    norm: int | None  # joriy belgilangan norma (yo'q bo'lsa None)


class TeamNormRow(BaseModel):
    user_id: int
    full_name: str
    position_name: str | None = None
    # Joriy foydalanuvchi (aktyor) shu xodimning normalarini o'zgartira oladimi —
    # ROP faqat o'z jamoasini, HR faqat o'ziga biriktirilgan lavozimlarni.
    can_edit: bool = False
    # Lavozimga qarab kuzatiladigan ko'rsatkichlar (default: suhbat+tashrif), har biri
    # bugungi haqiqiy (CRM/qo'lda) qiymat bilan birga — shu API orqali normani "tekshirish".
    metrics: list[MetricProgressRow] = []


class MobilografCreate(BaseModel):
    telegram_id: int
    telegram_message_id: int
    group_chat_id: int


class MobilografReact(BaseModel):
    group_chat_id: int
    telegram_message_id: int
    reactor_telegram_id: int
    action: str  # add | remove


class MobilografOut(BaseModel):
    id: int
    user_id: int
    telegram_message_id: int | None
    group_chat_id: int | None
    sent_at: datetime
    status: str
    source: str
    confirmed_by: int | None
    confirmed_at: datetime | None

    model_config = {"from_attributes": True}


class MobilografManualCreate(BaseModel):
    """Guruh reaksiyasi ishlamay qolganda (yoki umuman sozlanmaganda) HR/rahbar
    kunlik tasdiqlangan videolar sonini qo'lda belgilashi uchun."""

    user_id: int
    date: date
    confirmed_count: int = Field(ge=0)


class DailyResultManualCreate(BaseModel):
    user_id: int
    date: date
    conversations_count: int = Field(ge=0)
    visits_count: int = Field(ge=0)


class DailyResultOut(BaseModel):
    id: int
    user_id: int
    date: date
    conversations_count: int
    visits_count: int
    source: str
    raw_data: dict | None

    model_config = {"from_attributes": True}


class DailyResultTodayOut(BaseModel):
    conversations_count: int
    visits_count: int
    # Lavozimga qarab moslashgan ko'rsatkichlar ro'yxati — bot shu ro'yxatni ko'rsatadi.
    metrics: list[MetricProgressRow] = []


class MyStatsOut(BaseModel):
    """Xodimning botdagi "📈 Statistikam" tugmasi uchun shaxsiy statistika."""

    period: str  # joriy oy, "YYYY-MM"
    today: list[MetricProgressRow]
    month_totals: dict[str, int]  # {"suhbat": 120, "tashrif": 8, "video": 5}
    tasks_done: int
    tasks_total: int
    excused_days: int  # shu oyda tasdiqlangan sababli kunlar


class LeadStageRow(BaseModel):
    """Bitta pipeline bosqichi bo'yicha kunlik lidlar soni (CRM snapshot'idan)."""

    pipe_status_id: int
    stage_name: str
    count: int


class LeadOperatorRow(BaseModel):
    """Bir operatorning shu kundagi ko'rsatkichlari — kunlik ko'rinishda operator tanlash
    ro'yxati uchun. `calls` — gaplashilgan (suhbatlar); `total` — ishlangan lidlar."""

    responsible_id: int
    responsible_name: str
    calls: int  # gaplashilgan (kiruvchi+chiquvchi qo'ng'iroqlar)
    calls_in: int
    calls_out: int
    total: int  # ishlangan (yangilangan) lidlar
    visits: int


class LeadStageDayOut(BaseModel):
    """Bir kunning statistikasi — botdagi "Lidlar statistikasi" kun tafsiloti.
    `calls*` — gaplashilgan (qo'ng'iroqlar); `total`/`stages` — lidlar. `operators` —
    shu kun ishlagan operatorlar (tanlash uchun). `responsible_*` — bitta operator uchun."""

    date: date
    calls: int  # gaplashilgan lidlar (jami qo'ng'iroq)
    calls_in: int
    calls_out: int
    total: int  # shu kunda ishlangan (yangilangan) lidlar jami
    visits: int  # "Tashrif" bosqichidagi lidlar
    stages: list[LeadStageRow]
    operators: list[LeadOperatorRow] = []
    responsible_id: int | None = None
    responsible_name: str | None = None
    last_updated: datetime | None = None  # snapshot oxirgi yangilangan vaqti (naive-UTC)


class LeadStageDaySummary(BaseModel):
    date: date
    calls: int
    total: int
    visits: int


class LeadStageMonthOut(BaseModel):
    """Oylik ko'rinish: har kun uchun gaplashilgan (qo'ng'iroq), lidlar va tashriflar."""

    month: str  # "YYYY-MM"
    calls: int
    total: int
    visits: int
    days: list[LeadStageDaySummary]
    last_updated: datetime | None = None


class CRMWebhookPayload(BaseModel):
    crm_external_id: str
    date: date
    conversations: int
    visits: int


class BonusOut(BaseModel):
    id: int
    user_id: int
    period: str
    amount: float
    calculated_at: datetime
    breakdown: dict | None

    model_config = {"from_attributes": True}


class BonusMyOut(BaseModel):
    calculated: bool
    period: str | None = None
    calculated_at: datetime | None = None


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    target_user_id: int | None
    target_name: str | None
    before: dict | None
    after: dict | None
    created_at: datetime


# --- Ish jadvali (work schedule) ---

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class WorkDayEntry(BaseModel):
    """Haftalik andozaning bitta kuni (0=Dush ... 6=Yak)."""

    weekday: int = Field(ge=0, le=6)
    is_working: bool = True
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    end_time: str | None = Field(default=None, pattern=TIME_PATTERN)


class WorkWeeklyIn(BaseModel):
    days: list[WorkDayEntry]


class WorkWeeklyOut(BaseModel):
    user_id: int
    user_full_name: str
    days: list[WorkDayEntry]


class WorkOverrideIn(BaseModel):
    date: date
    is_working: bool = True
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    end_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    note: str | None = None


class WorkOverrideOut(BaseModel):
    id: int
    date: date
    is_working: bool
    start_time: str | None
    end_time: str | None
    note: str | None

    model_config = {"from_attributes": True}


class EffectiveDay(BaseModel):
    """Aniq sana uchun amaldagi jadval: override bo'lsa undan, aks holda haftalik
    andozadan; hech biri bo'lmasa `source="unset"`."""

    date: date
    weekday: int
    is_working: bool
    start_time: str | None
    end_time: str | None
    source: str  # "override" | "weekly" | "unset"
    note: str | None = None


class WorkWeekOut(BaseModel):
    user_id: int
    user_full_name: str
    days: list[EffectiveDay]
