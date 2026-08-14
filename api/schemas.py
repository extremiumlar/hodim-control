import datetime as dt
import re
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator


# Lavozim uchun qo'llab-quvvatlanadigan ko'rsatkichlar va bot menyu tugmalari.
# Bu ro'yxatlar backend hisob-kitobi mavjud bo'lgan qiymatlar bilan cheklangan —
# ixtiyoriy satr qabul qilinsa, hech qayerda hisoblanmaydigan "o'lik" norma paydo
# bo'lar edi (avvalgi audit shuni ko'rsatgan).
POSITION_METRICS = ["suhbat", "tashrif", "oddiy_video", "dumaloq_video"]
POSITION_MENU_KEYS = ["tasks", "norm", "kpi", "excused", "payroll"]
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
    is_seat: bool = False
    # Frontend shu bayroqqa qarab davomat tahriri tugmasini ko'rsatadi
    # (rol bo'yicha huquqi bo'lmagan, lekin shaxsan ruxsat berilgan odam uchun).
    can_edit_attendance: bool = False
    # Joylashuvsiz check-in ruxsati — frontend GPS so'ramasligi uchun kerak.
    skip_location_check: bool = False
    # Kechikish/jarima qoidasini o'zgartirish huquqi — frontend
    # /payroll/settings sahifasiga kirishni shu bo'yicha ochadi.
    can_edit_fine_policy: bool = False
    # Issiq lid taqsimotida qatnashadimi (bot mas'ulsiz lidni faqat
    # yoqilganlarga beradi) — HR/Boshliq bir bosishda o'chirib qo'yadi.
    hot_lead_enabled: bool = False
    crm_external_id: str | None
    crm_visit_external_id: str | None = None
    has_face: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCrmIdUpdate(BaseModel):
    crm_external_id: str | None = None
    crm_visit_external_id: str | None = None


class UserRoleUpdate(BaseModel):
    role: str


class UserPositionUpdate(BaseModel):
    position_id: int | None = None


class UserSeatUpdate(BaseModel):
    is_seat: bool


class UserHotLeadUpdate(BaseModel):
    """Issiq lid taqsimotida qatnashish bayrog'i (2026-08-06)."""

    hot_lead_enabled: bool


class UserCreate(BaseModel):
    full_name: str
    role: str
    team_id: int | None = None
    manager_id: int | None = None
    crm_external_id: str | None = None
    # "O'rin" (masalan Mobilogrof) — faqat Boss/Dasturchi belgilay oladi (create_user
    # ichida tekshiriladi, xuddi crm_external_id kabi).
    is_seat: bool = False


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


class AppLoginStartRequest(BaseModel):
    # Kirish qaysi klientdan boshlangani. "mobile" (standart — eski ilova
    # versiyalari body yubormaydi) → kod ilova ekranida ko'rsatiladi;
    # "web" → kod sayt sahifasida KO'RINMAYDI, bot ochilganda foydalanuvchining
    # mobil ilovasiga push bilan yuboriladi (`AppLoginToken.code_delivery`).
    client: str = "mobile"


class AppLoginStartOut(BaseModel):
    login_token: str
    deep_link: str
    expires_at: datetime
    # Ilova ekranida KO'RSATILADI, foydalanuvchi esa uni botga yozadi.
    # `db/models.py: AppLoginToken.pairing_code` izohiga qarang.
    # Saytga ham qaytariladi, lekin sayt uni FAQAT push imkonsiz bo'lgan
    # zaxira holatda ko'rsatadi (poll'dagi `code_delivery` "screen" bo'lsa).
    pairing_code: str


class AppLoginRequestCodeIn(BaseModel):
    login_token: str
    telegram_id: int


class AppLoginRequestCodeOut(BaseModel):
    # sent — kod mobil ilovaga push bilan ketdi;
    # screen — kod kirish ekranida ko'rsatilgan (mobil ilova oqimi);
    # screen_fallback — push qurilma topilmadi, kod endi SAYTDA ko'rsatiladi;
    # no_account | invalid — hisob yo'q / token yaroqsiz-eskirgan.
    status: str


class AppLoginConfirmRequest(BaseModel):
    login_token: str
    telegram_id: int
    # Foydalanuvchi botga yozgan kod. Bo'sh/noto'g'ri bo'lsa tasdiqlanmaydi.
    pairing_code: str = ""


class AppLoginConfirmOut(BaseModel):
    # ok | invalid | no_account | wrong_code — `wrong_code` bilan birga
    # `attempts_left` keladi, bot foydalanuvchiga nechta urinish qolganini
    # ko'rsatadi.
    status: str
    attempts_left: int | None = None


class AppLoginPollRequest(BaseModel):
    login_token: str


class AppLoginPollOut(BaseModel):
    status: str  # pending | confirmed | expired
    token: TokenOut | None = None
    # "pending" holatida kod hozir qayerdan yetkazilayotgani (screen | push).
    # Sayt shu maydonga qarab zaxira holatni biladi: push qurilma topilmay
    # qiymat "screen"ga tushsa, kodni sahifada o'zi ko'rsatadi.
    code_delivery: str | None = None


class TelegramStartRequest(BaseModel):
    telegram_id: int
    invite_token: str | None = None


class TelegramStartResponse(BaseModel):
    status: str  # ok | invalid_token | token_expired | already_linked | no_account
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
    # UX2-C10: bo'sh yoki "." kabi sabab HR'ga borib o'tirmasin
    reason: str = Field(min_length=3, max_length=500)


class ExcusedDayMeCreate(BaseModel):
    """Web/mobil (JWT) uchun — `telegram_id` YO'Q. Shaxs tokendan olinadi,
    ya'ni mijoz boshqa birov nomidan so'rov yubora olmaydi. `ExcusedDayCreate`
    ni qayta ishlatib bo'lmaydi, chunki unda `telegram_id` majburiy."""

    date: dt.date | None = None
    reason: str = Field(min_length=3, max_length=500)


class ExcusedDayOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str
    date: date
    reason: str
    status: str
    # To'lovlimi — payslipdagi ayirmani tushuntirish uchun ro'yxatda ham
    # ko'rinadi («o'z hisobidan» kunlar ajratib turadi).
    is_paid: bool = True
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExcusedDayDecide(BaseModel):
    decider_telegram_id: int
    decision: str  # approved | rejected
    # Bosqich 3.5: allaqachon hal qilingan so'rovni Dasturchi QAYTA hal
    # qilmoqchi bo'lsa majburiy (11.2-band, "har bir override — sabab").
    # Oddiy (birinchi marta) qarorda ishlatilmaydi.
    override_reason: str | None = Field(default=None, max_length=500)


class ExcusedDayForUserCreate(BaseModel):
    """Web (JWT) — HR/Boshliq/Dasturchi boshqa xodim NOMIDAN sababli kunni
    to'g'ridan-to'g'ri BELGILAYDI (so'rov emas — kirituvchining o'zi tasdiqlashga
    vakolatli, shuning uchun darhol 'approved' holatda yoziladi)."""

    user_id: int
    date: dt.date | None = None
    reason: str = Field(min_length=3, max_length=500)
    # To'lovlimi (2026-08-13). Default `True` — bugungi xatti-harakat.
    # `False` («o'z hisobidan») bo'lsa monthly stavkadan kunlik ulush
    # ayiriladi (`payroll.compute_base`). Xodim O'ZI so'raganda bu maydon
    # YO'Q — to'lov qarorini faqat HR chiqaradi.
    is_paid: bool = True


class ExcusedDayForUserBotCreate(BaseModel):
    """Bot versiyasi — aktyor shaxsi `manager_telegram_id`dan yechiladi
    (`ExcusedDayForUserCreate`ni qayta ishlatib bo'lmaydi, u tokendan oladi)."""

    manager_telegram_id: int
    target_user_id: int
    date: dt.date | None = None
    reason: str = Field(min_length=3, max_length=500)


class ExcusedDayDecideMe(BaseModel):
    """Web/ilova versiyasi — `decider_telegram_id` YO'Q, shaxs tokendan
    olinadi (mijoz kim nomidan qaror chiqarayotganini ayta olmaydi)."""

    decision: str  # approved | rejected
    override_reason: str | None = Field(default=None, max_length=500)


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
    tracked: bool = True  # False — bu ko'rsatkich uchun ma'lumot manbai (CRM ID) yo'q, value har doim 0


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
    video_type: str = "oddiy"  # oddiy | dumaloq


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
    video_type: str
    confirmed_by: int | None
    confirmed_at: datetime | None

    model_config = {"from_attributes": True}


class MobilografManualCreate(BaseModel):
    """Guruh reaksiyasi ishlamay qolganda (yoki umuman sozlanmaganda) HR/rahbar
    kunlik tasdiqlangan videolar sonini qo'lda belgilashi uchun."""

    user_id: int
    date: date
    metric_type: str = "oddiy_video"  # oddiy_video | dumaloq_video
    confirmed_count: int = Field(ge=0)


class MonitoredGroupOut(BaseModel):
    purpose: str
    chat_id: int
    title: str | None = None

    model_config = {"from_attributes": True}


class MonitoredGroupSet(BaseModel):
    """Dasturchi guruh ICHIDA `/guruh_biriktir <purpose>` yuborganda ishlatiladi —
    joriy chatni shu maqsadga belgilaydi (mobilograf/main uchun eskisi almashadi)."""

    telegram_id: int
    purpose: str
    chat_id: int
    title: str | None = None


class MonitoredGroupRemove(BaseModel):
    telegram_id: int
    purpose: str
    chat_id: int


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
    # Shu hafta (dushanbadan bugungacha) jami — kalitlar month_totals bilan bir xil.
    week_totals: dict[str, int] = {}
    month_totals: dict[str, int]  # {"suhbat": 120, "tashrif": 8, "oddiy_video": 5, "dumaloq_video": 2}
    tasks_done: int
    tasks_total: int
    excused_days: int  # shu oyda tasdiqlangan sababli kunlar
    # UX2-W4 (C9): davomat bloki — xodim jarimaga ta'sir qiladigan raqamlarni
    # endi botdan ham ko'radi (ilgari faqat «Mening oyligim» ostida 3 bosishda).
    attendance_present_days: int = 0  # shu oyda kelgan kunlar
    attendance_late_minutes: int = 0  # shu oyda jami kechikish (daqiqa)
    attendance_absent_days: int = 0  # shu oyda yozilgan «kelmadi» kunlar


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


# --- Soatlik reja (hourly plan) ---


class HourlyMetricStatus(BaseModel):
    key: str
    label: str
    norm: int  # kunlik norma (nominal, to'liq kun uchun belgilangan)
    effective_norm: int  # bugungi ish soatiga moslashtirilgan norma (qisqa kunda kamaytiriladi)
    per_hour: float  # soatiga o'rtacha (effective_norm asosida)
    this_hour_target: int  # bu soatda qilish kerak (kumulyativ qoldiqni taqsimlash orqali, min-1 majburlanmaydi)
    cumulative_target: int  # shu paytgacha bo'lishi kerak (effective_norm asosida)
    actual: int  # haqiqatda bajarilgan (CRM)
    delta: int  # actual - cumulative_target (+ oldinda, - orqada) — faqat tracked bo'lsa ma'noli
    tracked: bool = True  # False — ma'lumot manbai (CRM ID) yo'q, actual/delta e'tiborga olinmasin


class HourlyPlanOut(BaseModel):
    date: date
    is_working: bool
    in_lunch: bool = False
    start_time: str | None = None
    end_time: str | None = None
    now: str | None = None  # "HH:MM"
    metrics: list[HourlyMetricStatus] = []
    text: str  # botga tayyor HTML matn


# --- Davomat (kelib-ketish, verifix'dan birlashtirilgan) ---


class OfficeBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_meters: int = Field(default=150, ge=10, le=5000)
    is_active: bool = True


class OfficeCreate(OfficeBase):
    pass


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: int | None = Field(default=None, ge=10, le=5000)
    is_active: bool | None = None


class OfficeOut(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    radius_meters: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MeCheckRequest(BaseModel):
    """Web (kirgan xodim) orqali Keldim/Ketdim — GPS + Face ID.

    `latitude`/`longitude` NULL bo'lishi mumkin: «bez lokatsiya» ruxsati
    (`User.skip_location_check`) berilgan xodim koordinata umuman
    yubormaydi. 0,0 yuborish ATAYLAB rad etildi — u ma'lumotda
    "Atlantika okeanida check-in qildi" degan soxta iz qoldirardi.
    Ruxsati YO'Q xodim NULL yuborsa, servis xato beradi (pastda)."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    face_descriptor: list[float] = Field(min_length=128, max_length=128)
    liveness: float = Field(default=0.0, ge=0.0, le=1.0)
    # Brauzer `position.coords.accuracy` (metr) — berilmasa (eski frontend) tekshiruv
    # o'tkazib yuboriladi, lekin berilgan bo'lsa juda yomon (masalan IP-asosidagi
    # zaxira geolokatsiya) o'qish rad etiladi.
    accuracy: float | None = Field(default=None, ge=0)


class RegisterFaceRequest(BaseModel):
    """Yuzni ro'yxatdan o'tkazish — 128-o'lchamli deskriptor (face-api.js)."""

    face_descriptor: list[float] = Field(min_length=128, max_length=128)


class RegisterFaceOut(BaseModel):
    """register-face javobi: birinchi marta darhol yoziladi, QAYTA ro'yxatdan
    o'tishda esa rahbar tasdig'ini kutadi (Savol A — yumshoq choralar)."""

    status: str  # "registered" | "pending_approval"
    user: UserOut


class FaceReregOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FaceReregDecide(BaseModel):
    decider_telegram_id: int
    decision: str  # approved | rejected


class AttendanceOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str | None = None
    date: dt.date
    check_in_time: datetime | None
    check_out_time: datetime | None
    check_in_distance_m: int | None
    late_minutes: int
    early_leave_minutes: int
    worked_minutes: int
    status: str
    is_weekend: bool
    note: str | None = None


class EmployeeAttendanceSummary(BaseModel):
    user_id: int
    full_name: str
    present_days: int
    late_count: int
    late_minutes: int
    early_minutes: int
    worked_minutes: int


class AttendanceManualUpdate(BaseModel):
    """HR/Boshliq qo'lda davomat tuzatishi. Vaqtlar MAHALLIY devor-soati
    ("HH:MM") — server ularni yozuv sanasi bo'yicha naive-UTC ga o'giradi.
    `null` — o'sha vaqtni tozalash (masalan "aslida kelmagan" deb belgilash).

    `late_minutes`/`worked_minutes` bevosita kiritilmaydi — ular kelish/ketish
    vaqti va o'sha kungi ish jadvalidan qayta hisoblanadi. Kechikishni "kechirish"
    uchun sabab (`ExcusedDay`) mexanizmi bor; vaqtni soxtalashtirish emas."""

    user_id: int
    date: dt.date
    check_in: str | None = None
    check_out: str | None = None
    note: str | None = Field(default=None, max_length=1000)
    # Majburiy: qo'lda o'zgartirish har doim izohlanadi va audit jurnaliga tushadi.
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("check_in", "check_out")
    @classmethod
    def _valid_hm(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("Vaqt formati «HH:MM» bo'lishi kerak (masalan 09:15)")
        return v


class AdminAttendanceManualUpdate(AttendanceManualUpdate):
    """Dasturchining JIM tuzatishi — `reason` MAJBURIY EMAS.

    Sababi: bu endpoint hech qanday `AuditLog` yozmaydi (egasining talabi
    "auditlarga tushmasdan"), ya'ni sabab yozilib qoladigan joy YO'Q.
    Uni baribir majburiy qilish — hech qayerga bormaydigan matnni yozishga
    majburlash bo'lardi. Vaqt formati tekshiruvi ota sinfdan meros qoladi."""

    reason: str = ""


class ReadinessIssue(BaseModel):
    """Davomat ma'lumotidagi bitta "e'tibor bering" holati."""

    user_id: int
    full_name: str
    date: dt.date | None = None
    detail: str | None = None


class AttendanceReadiness(BaseModel):
    """Davr bo'yicha davomat ma'lumotining tayyorlik hisoboti — oylik/jarima
    hisobidan OLDIN ko'riladi (payroll `preflight` shu ustiga quriladi)."""

    date_from: dt.date
    date_to: dt.date
    ok: bool
    no_schedule: list[ReadinessIssue]
    open_checkouts: list[ReadinessIssue]
    auto_closed: list[ReadinessIssue]
    pending_excused: list[ReadinessIssue]
    no_face: list[ReadinessIssue]


class LateDayEntry(BaseModel):
    """Bitta kechikkan kun — sana va necha daqiqa kech qolgani."""

    date: dt.date
    late_minutes: int


class LateStatRow(BaseModel):
    """Bir xodimning davr bo'yicha kechikish statistikasi (kunma-kun ro'yxat bilan)."""

    user_id: int
    full_name: str
    late_days: int  # nechta kun kechikkan
    total_late_minutes: int  # jami kechikish (daqiqa)
    avg_late_minutes: float  # o'rtacha (kechikkan kunlarga nisbatan)
    max_late_minutes: int  # eng katta kechikish
    days: list[LateDayEntry]  # faqat kechikkan kunlar, sana bo'yicha o'sish tartibida


# ─────────────────────────────────────────────
# Payroll (oylik ish haqi + kechikish jarimasi + qo'shimcha ish) — Bosqich 3
# ─────────────────────────────────────────────


class FinePolicyIn(BaseModel):
    """Jarima qoidasi kiritish/yangilash — faqat HR/Boshliq/Dasturchi.
    `scope='global'`da `scope_id` bo'lmaydi; `position`/`user`da MAJBURIY.
    Cap (`monthly_cap_percent`/`monthly_cap_amount`) — 9-bo'lim QARORI
    bo'yicha ikkalasidan KAMIDA BITTASI majburiy."""

    scope: str
    scope_id: int | None = None
    grace_minutes: int | None = Field(default=None, ge=0)
    free_late_minutes_per_month: int = Field(ge=0)
    fine_mode: str = "per_day"
    fine_per_day: float | None = Field(default=None, ge=0)
    absent_mode: str = "fixed"
    absent_fine: float | None = Field(default=None, ge=0)
    early_leave_enabled: bool = False
    early_leave_per_minute: float | None = Field(default=None, ge=0)
    monthly_cap_percent: float | None = Field(default=None, ge=0, le=100)
    monthly_cap_amount: float | None = Field(default=None, ge=0)
    fine_applies_to: str = "net_salary"
    # Issiq lid qoidasi (2026-08-06): lid necha daqiqada "sovuydi" va har bir
    # sovutilgan lid uchun jarima. Faqat GLOBAL qoidada o'qiladi (hot_lead.py:
    # hot_lead_rules) — lavozim/xodim darajasida hozircha ishlatilmaydi.
    hot_lead_cool_minutes: int | None = Field(default=None, ge=1, le=240)
    hot_lead_fine: float | None = Field(default=None, ge=0)
    is_active: bool = True

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, v: str) -> str:
        if v not in {"global", "position", "user"}:
            raise ValueError("scope 'global', 'position' yoki 'user' bo'lishi kerak")
        return v

    @field_validator("fine_mode")
    @classmethod
    def _valid_fine_mode(cls, v: str) -> str:
        if v not in {"per_day", "per_minute", "tiered", "percent_of_daily"}:
            raise ValueError("noto'g'ri fine_mode")
        return v

    @field_validator("absent_mode")
    @classmethod
    def _valid_absent_mode(cls, v: str) -> str:
        if v not in {"none", "fixed", "deduct_daily"}:
            raise ValueError("noto'g'ri absent_mode")
        return v

    @field_validator("fine_applies_to")
    @classmethod
    def _valid_applies_to(cls, v: str) -> str:
        if v not in {"bonus_first", "net_salary"}:
            raise ValueError("noto'g'ri fine_applies_to")
        return v

    @model_validator(mode="after")
    def _check_combination(self):
        if self.scope == "global":
            self.scope_id = None
        elif self.scope_id is None:
            raise ValueError("'position'/'user' scope uchun scope_id majburiy")
        if self.monthly_cap_percent is None and self.monthly_cap_amount is None:
            raise ValueError(
                "Oylik jarima chegarasi (cap) majburiy — foiz yoki qat'iy summa kiriting"
            )
        if self.fine_mode == "per_day" and self.fine_per_day is None:
            raise ValueError("fine_mode='per_day' uchun fine_per_day majburiy")
        if self.absent_mode == "fixed" and self.absent_fine is None:
            raise ValueError("absent_mode='fixed' uchun absent_fine majburiy")
        return self


class FinePolicyOut(BaseModel):
    id: int
    scope: str
    scope_id: int | None
    scope_label: str | None = None
    grace_minutes: int | None
    free_late_minutes_per_month: int | None
    fine_mode: str
    fine_per_day: float | None
    absent_mode: str
    absent_fine: float | None
    early_leave_enabled: bool
    early_leave_per_minute: float | None
    monthly_cap_percent: float | None
    monthly_cap_amount: float | None
    fine_applies_to: str
    hot_lead_cool_minutes: int | None = None
    hot_lead_fine: float | None = None
    is_active: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class SalaryRateIn(BaseModel):
    user_id: int
    amount: float = Field(gt=0)
    pay_basis: str = "monthly"
    effective_from: dt.date
    note: str | None = Field(default=None, max_length=500)

    @field_validator("pay_basis")
    @classmethod
    def _valid_basis(cls, v: str) -> str:
        if v not in {"monthly", "daily", "hourly"}:
            raise ValueError("pay_basis 'monthly', 'daily' yoki 'hourly' bo'lishi kerak")
        return v


class SalaryRateUpdate(BaseModel):
    """Kiritilgan stavkani TAHRIRLASH (2026-08-13).

    NEGA KERAK: `POST /rates` bir sanaga ikkinchi stavka kiritilsa
    «avval eskisini o'zgartiring» deb rad etardi, lekin o'zgartiradigan yo'l
    faqat Dasturchining `/admin/records` sahifasida bor edi — HR uchun bu
    boshi berk ko'cha edi (xato summani hech qanday yo'l bilan tuzatib
    bo'lmasdi).

    Barcha maydon ixtiyoriy — faqat yuborilgani o'zgaradi (PATCH semantikasi).
    `note` uchun `None` yuborish izohni TOZALASH degani, shuning uchun
    "yuborilmagan" holatini `model_fields_set` orqali ajratamiz."""

    amount: float | None = Field(default=None, gt=0)
    pay_basis: str | None = None
    effective_from: dt.date | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("pay_basis")
    @classmethod
    def _valid_basis(cls, v: str | None) -> str | None:
        if v is not None and v not in {"monthly", "daily", "hourly"}:
            raise ValueError("pay_basis 'monthly', 'daily' yoki 'hourly' bo'lishi kerak")
        return v


class KpiRateIn(BaseModel):
    """KPI stavkasi kiritish. `scope='global'`da `scope_id` bo'lmaydi,
    `position`/`user`da MAJBURIY (`FinePolicyIn` bilan bir xil qoida)."""

    scope: str
    scope_id: int | None = None
    metric: str
    amount: float = Field(ge=0)
    effective_from: dt.date
    note: str | None = Field(default=None, max_length=500)

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, v: str) -> str:
        if v not in {"global", "position", "user"}:
            raise ValueError("scope 'global', 'position' yoki 'user' bo'lishi kerak")
        return v

    @field_validator("metric")
    @classmethod
    def _valid_metric(cls, v: str) -> str:
        # Ro'yxat `api/routers/norms.py::METRIC_LABELS` bilan bir xil bo'lishi
        # SHART — aks holda hech qachon qo'llanmaydigan stavka kiritilardi.
        if v not in {"suhbat", "tashrif", "oddiy_video", "dumaloq_video"}:
            raise ValueError("Bunday ko'rsatkich yo'q")
        return v

    @model_validator(mode="after")
    def _scope_id_required(self):
        if self.scope == "global" and self.scope_id is not None:
            raise ValueError("'global' qamrovda scope_id bo'lmaydi")
        if self.scope != "global" and self.scope_id is None:
            raise ValueError("'position'/'user' qamrovda scope_id majburiy")
        return self


class KpiRateOut(BaseModel):
    id: int
    scope: str
    scope_id: int | None
    scope_label: str | None = None
    metric: str
    amount: float
    effective_from: dt.date
    changed_by: int
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SalaryRateOut(BaseModel):
    id: int
    user_id: int
    amount: float
    pay_basis: str
    effective_from: dt.date
    changed_by: int
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OvertimeProfileIn(BaseModel):
    enabled: bool = False
    mode: str = "derived"
    fixed_rate_per_hour: float | None = Field(default=None, ge=0)
    multiplier: float | None = Field(default=None, gt=0)
    norm_hours_source: str = "schedule"
    fixed_norm_hours_per_month: int | None = Field(default=None, gt=0)
    min_minutes: int = Field(default=15, ge=0)
    daily_cap_minutes: int | None = Field(default=None, ge=0)
    monthly_cap_minutes: int | None = Field(default=None, ge=0)

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        if v not in {"derived", "fixed_rate"}:
            raise ValueError("mode 'derived' yoki 'fixed_rate' bo'lishi kerak")
        return v

    @model_validator(mode="after")
    def _check(self):
        # 9-bo'lim, savol 6, QAROR: tizimda default YO'Q — `derived' rejim
        # yoqilsa multiplier MAJBURIY (HR har xodim/lavozim uchun o'zi kiritadi).
        if self.enabled and self.mode == "derived" and self.multiplier is None:
            raise ValueError("'derived' rejimda multiplier majburiy (tizim darajasida default yo'q)")
        if self.enabled and self.mode == "fixed_rate" and self.fixed_rate_per_hour is None:
            raise ValueError("'fixed_rate' rejimda fixed_rate_per_hour majburiy")
        return self


class OvertimeProfileOut(BaseModel):
    user_id: int
    user_full_name: str | None = None
    enabled: bool
    mode: str
    fixed_rate_per_hour: float | None
    multiplier: float | None
    norm_hours_source: str
    fixed_norm_hours_per_month: int | None
    min_minutes: int
    daily_cap_minutes: int | None
    monthly_cap_minutes: int | None
    updated_at: datetime


class OvertimeEntryIn(BaseModel):
    """HR/rahbar qo'lda qo'shimcha ish kiritishi."""

    user_id: int
    date: dt.date
    minutes: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class OvertimeEntryDecide(BaseModel):
    status: str  # approved | rejected

    @field_validator("status")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in {"approved", "rejected"}:
            raise ValueError("status 'approved' yoki 'rejected' bo'lishi kerak")
        return v


class OvertimeEntryOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str | None = None
    date: dt.date
    minutes: int
    source: str
    status: str
    note: str | None
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime


class PayrollAdjustmentIn(BaseModel):
    user_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    kind: str
    amount: float = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        if v not in {"plus", "minus"}:
            raise ValueError("kind 'plus' yoki 'minus' bo'lishi kerak")
        return v


class PayrollAdjustmentOut(BaseModel):
    id: int
    user_id: int
    period: str
    kind: str
    amount: float
    reason: str
    created_by: int
    created_at: datetime
    # ── Avans (2026-08-13) ──
    category: str
    status: str
    issued_on: dt.date | None
    decided_by: int | None
    decided_at: datetime | None
    decided_note: str | None
    # Ro'yxatda ism ko'rsatish uchun (jadval har qator uchun alohida so'rov
    # yubormasin) — router to'ldiradi, modelda yo'q.
    full_name: str | None = None
    created_by_name: str | None = None
    decided_by_name: str | None = None

    model_config = {"from_attributes": True}


class AdvanceIn(BaseModel):
    """Avans kiritish (HR). Summa musbat — yo'nalish (`minus`) serverda
    qo'yiladi, mijoz uni tanlay olmaydi: avans HAR DOIM ushlanma."""

    user_id: int
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount: float = Field(gt=0)
    issued_on: dt.date
    reason: str = Field(min_length=3, max_length=500)


class AdvanceDecision(BaseModel):
    """Boshliq qarori. `approve=False` — rad etiladi va oylikka KIRMAYDI."""

    approve: bool
    note: str | None = Field(default=None, max_length=500)


class PayslipItemOut(BaseModel):
    kind: str
    label: str
    quantity: float | None
    rate: float | None
    amount: float
    sort_order: int

    model_config = {"from_attributes": True}


class PayslipRow(BaseModel):
    """Davr jadvali — bitta xodim, bitta qator (`GET /payroll/{period}`)."""

    user_id: int
    full_name: str
    status: str
    base_amount: float
    late_days: int
    fined_late_days: int
    fine_amount: float
    absent_days: int
    absent_deduction: float
    overtime_minutes: int
    overtime_amount: float
    bonus_amount: float
    gross: float
    net: float


class PayslipDetailOut(BaseModel):
    """Bitta xodim, bitta oy — to'liq tafsilot (qatorlar + kunma-kun breakdown)."""

    id: int
    user_id: int
    full_name: str
    period: str
    status: str
    base_amount: float
    pay_basis: str
    rate_snapshot: float | None
    scheduled_days: int
    worked_days: int
    absent_days: int
    excused_days: int
    scheduled_minutes: int
    worked_minutes: int
    late_days: int
    late_minutes: int
    fined_late_days: int
    fined_late_minutes: int
    fine_amount: float
    absent_deduction: float
    overtime_minutes: int
    overtime_amount: float
    overtime_rate_snapshot: float | None
    bonus_amount: float
    adjustments_plus: float
    adjustments_minus: float
    gross: float
    net: float
    currency: str
    calculated_at: datetime | None
    approved_at: datetime | None
    items: list[PayslipItemOut]
    breakdown: dict | None


class PayrollPreflightOut(BaseModel):
    """Oylik hisobdan OLDINGI tayyorlik: davomat tayyorligi (Bosqich 0) +
    payrollga xos qo'shimcha tekshiruvlar (stavkasiz xodim, hal qilinmagan
    qo'shimcha ish so'rovi)."""

    period: str
    ok: bool
    attendance: AttendanceReadiness
    no_salary_rate: list[ReadinessIssue]
    pending_overtime: list[ReadinessIssue]


class PayrollCalculateRequest(BaseModel):
    user_ids: list[int] | None = None


class PayrollPeriodOut(BaseModel):
    period: str
    status: str
    locked: bool
    calculated_at: datetime | None
    # HR bosqichi — Boshliq tasdiqlash oynasida "kim tekshirdi" ko'rinsin.
    hr_approved_at: datetime | None = None
    hr_approved_name: str | None = None
    approved_at: datetime | None
    employee_count: int
    total_net: float


class BotPayslipOut(BaseModel):
    """Bot `/payroll/my/{telegram_id}` — faqat oxirgi TASDIQLANGAN varaqa."""

    calculated: bool
    period: str | None = None
    base_amount: float | None = None
    fine_amount: float | None = None
    absent_deduction: float | None = None
    overtime_amount: float | None = None
    bonus_amount: float | None = None
    # Avans va boshqa qo'lda kiritilgan qo'shimcha/ushlanmalar (2026-08-13).
    # ILGARI YO'Q EDI va bu XATO edi: ushlanma `net`ni kamaytirar, lekin
    # xodimga ko'rsatilgan qatorlar yig'indisi `Jami`ga to'g'ri kelmasdi —
    # ya'ni xodim "nega kam?" degan savolga javob topa olmasdi.
    # `advance_amount` alohida: avans eng ko'p uchraydigan holat va u
    # xodimning o'zi olgan puli, boshqa ushlanmalar bilan aralashmasin.
    advance_amount: float | None = None
    adjustments_plus: float | None = None
    adjustments_minus: float | None = None
    net: float | None = None
    currency: str | None = None
    approved_at: datetime | None = None


class BotLateStatusOut(BaseModel):
    """Bot uchun: joriy oyda kechikish holati — «2/3 kechikish ishlatildi» kabi
    oldindan ogohlantirish (1.5-band)."""

    period: str
    free_limit_minutes: int | None
    used_minutes: int
    remaining_minutes: int | None
    fined_days_so_far: int
    fine_per_day: float | None


# ─────────────────────────────────────────────
# Dasturchi rejimi (super-admin) — Bosqich 3.5
# ─────────────────────────────────────────────


class AdminOverrideReason(BaseModel):
    """Sabab talab qiladigan sof override amallar uchun umumiy body
    (o'chirish, qulfni ochish va h.k.) — 11.2-band: har bir override
    majburiy sabab bilan."""

    override_reason: str = Field(min_length=5, max_length=500)


class AdminNormSet(BaseModel):
    value: int
    override_reason: str = Field(min_length=5, max_length=500)


class AdminRecordPatch(BaseModel):
    """Universal yozuv tahrirlash — `fields` faqat entity uchun oq
    ro'yxatdagi kalitlarni o'z ichiga olishi kerak (router darajasida
    tekshiriladi, bu yerda emas — chunki oq ro'yxat entity'ga bog'liq)."""

    fields: dict
    override_reason: str = Field(min_length=5, max_length=500)


class AdminForceRole(BaseModel):
    role: str
    override_reason: str = Field(min_length=5, max_length=500)


class AdminAttendanceEditorGrant(BaseModel):
    """Davomat vaqtini tuzatish huquqini berish/olib qo'yish (faqat Dasturchi).
    Sabab majburiy — huquq berish auditga tushadi (tuzatishning O'ZI emas)."""

    granted: bool
    override_reason: str = Field(min_length=5, max_length=500)


class PushTokenIn(BaseModel):
    """FCM qurilma tokeni va platforma.

    `web` — brauzer/PWA tokeni (iPhone uchun asosiy yo'l: iOS'da nativ
    ilovamiz yo'q, xodimlar saytni bosh ekranga qo'shib ishlatadi).
    FCM web push tokenlari ham xuddi shu `messages:send` API orqali
    yuboriladi, ya'ni backendda alohida yuborish yo'li kerak emas."""

    token: str = Field(min_length=10, max_length=255)
    platform: str = Field(pattern="^(android|ios|web)$")


class PushSettingsOut(BaseModel):
    """Toifa -> yoqiqmi + ko'rsatiladigan nomlar va tinch soatlar oynasi.
    Nomlar serverdan keladi — ilova va sayt ro'yxatni o'zi takrorlamasin."""

    categories: dict[str, bool]
    labels: dict[str, str]
    quiet_from: int
    quiet_to: int


class PushSettingsUpdate(BaseModel):
    categories: dict[str, bool]


# ─── Ish kundaligi (KUNDALIK_ETIROZ_REJASI.md, Bosqich 1) ───────────────────────


class WorkLogBotCreate(BaseModel):
    """Bot — shaxs `telegram_id`dan. Sana YO'Q: yozuv HAR DOIM bugungi
    (Toshkent) kunga tushadi — mijoz o'tgan kunga yozuv qo'sha olmasligi
    qulf qoidasining asosi."""

    telegram_id: int
    text: str = Field(min_length=3, max_length=2000)


class WorkLogMeCreate(BaseModel):
    """Web/mobil (JWT) — `telegram_id` YO'Q, shaxs tokendan olinadi."""

    text: str = Field(min_length=3, max_length=2000)


class WorkLogMePatch(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class WorkLogEntryOut(BaseModel):
    id: int
    user_id: int
    date: dt.date
    text: str
    source: str
    created_at: datetime
    updated_at: datetime | None
    # Server hisoblaydi (date == bugun): bot ham, web ham "tahrirlash mumkinmi"
    # qoidasini o'zi takrorlamasin — kun chegarasi faqat backend timezone'ida.
    editable: bool

    model_config = {"from_attributes": True}


class WorkLogDayOut(BaseModel):
    """Oylik ko'rinishning bitta kuni. `is_working` ish jadvalidan
    (attendance_month.build_month_cells bilan bir manba) — kalendarda
    "ish kuni-yu yozmagan" kunni qizil ko'rsatish uchun."""

    date: dt.date
    is_working: bool
    entries: list[WorkLogEntryOut]


class WorkLogMonthOut(BaseModel):
    month: str  # "YYYY-MM"
    user_id: int
    user_full_name: str
    days: list[WorkLogDayOut]
    # Qamrov: o'tgan (bugungacha) ish kunlari va shulardan nechtasida yozuv bor.
    work_days: int
    logged_days: int
    entries_count: int


class WorkLogCoverageRow(BaseModel):
    user_id: int
    full_name: str
    work_days: int
    logged_days: int
    entries_count: int


class WorkLogCoverageOut(BaseModel):
    month: str
    rows: list[WorkLogCoverageRow]


# ─── E'tiroz / Shikoyat (KUNDALIK_ETIROZ_REJASI.md, Bosqich 4) ─────────────────

_APPEAL_KINDS = {"objection", "complaint"}
_APPEAL_TOPICS = {"attendance", "payroll", "work_env", "team", "other"}
# E'tiroz — HAR DOIM aniq qarorga qarshi, ya'ni mavzusi ham aniq bo'lishi shart.
_OBJECTION_TOPICS = {"attendance", "payroll"}


class AppealCreateBase(BaseModel):
    """Bot va web sxemalarining umumiy tanasi. `telegram_id` bu yerda YO'Q —
    u faqat bot variantida qo'shiladi (web'da shaxs tokendan olinadi)."""

    kind: str
    topic: str = "other"
    text: str = Field(min_length=10, max_length=3000)
    is_anonymous: bool = False
    recipient_role: str = "hr"
    ref_date: dt.date | None = None
    ref_period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    file_id: str | None = Field(default=None, max_length=200)
    file_type: str | None = Field(default=None, pattern="^(photo|document)$")

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in _APPEAL_KINDS:
            raise ValueError("kind: objection yoki complaint bo'lishi kerak")
        return v

    @field_validator("topic")
    @classmethod
    def _check_topic(cls, v: str) -> str:
        if v not in _APPEAL_TOPICS:
            raise ValueError(f"Noma'lum mavzu: {v}")
        return v

    @field_validator("recipient_role")
    @classmethod
    def _check_recipient(cls, v: str) -> str:
        if v not in {"hr", "boss"}:
            raise ValueError("recipient_role: hr yoki boss bo'lishi kerak")
        return v

    @model_validator(mode="after")
    def _check_shape(self):
        """E'tiroz MANZILLI bo'lishi shart — aks holda HR nima haqida
        ekanini bilmaydi va yozishmalar boshlanadi. Anonimlik esa faqat
        shikoyatda: e'tiroz aniq odamning aniq kuni/oyligi haqida, anonim
        bo'lishi mantiqan mumkin emas."""
        if self.kind == "objection":
            if self.topic not in _OBJECTION_TOPICS:
                raise ValueError("E'tiroz mavzusi 'attendance' yoki 'payroll' bo'lishi kerak")
            if self.topic == "attendance" and self.ref_date is None:
                raise ValueError("Davomat e'tirozi uchun sana (ref_date) ko'rsatilishi shart")
            if self.topic == "payroll" and not self.ref_period:
                raise ValueError("Oylik e'tirozi uchun davr (ref_period) ko'rsatilishi shart")
            if self.is_anonymous:
                raise ValueError("E'tiroz anonim bo'lishi mumkin emas")
        else:
            if self.topic in _OBJECTION_TOPICS:
                raise ValueError("Shikoyat mavzusi 'work_env', 'team' yoki 'other' bo'lishi kerak")
        return self


class AppealBotCreate(AppealCreateBase):
    telegram_id: int


class AppealMeCreate(AppealCreateBase):
    """Web/mobil (JWT) — `telegram_id` YO'Q, shaxs tokendan olinadi."""


class AppealOut(BaseModel):
    id: int
    user_id: int | None  # anonim shikoyatda NULL (backend yashiradi)
    user_full_name: str | None
    kind: str
    topic: str
    text: str
    is_anonymous: bool
    recipient_role: str
    ref_date: dt.date | None
    ref_period: str | None
    file_id: str | None
    file_type: str | None
    status: str
    review_started_at: datetime | None
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class AppealDecide(BaseModel):
    """Qaror + MAJBURIY izoh. Izohsiz rad etish shaffoflikni buzadi — xodim
    nega rad etilganini bilmaydi va nizо qaytadan boshlanadi (1.2-band)."""

    decision: str  # accepted | rejected | resolved
    note: str = Field(min_length=5, max_length=2000)

    @field_validator("decision")
    @classmethod
    def _check_decision(cls, v: str) -> str:
        if v not in {"accepted", "rejected", "resolved"}:
            raise ValueError("decision: accepted, rejected yoki resolved")
        return v


class AppealDecideBot(AppealDecide):
    telegram_id: int


class AppealActorBot(BaseModel):
    """Botdagi «O'rganyapman» tugmasi uchun — faqat aktyor kerak."""

    telegram_id: int


class AppealAttendanceTarget(BaseModel):
    """E'tiroz uchun nishon: xodimning oxirgi kunlaridagi kechikish/kelmaslik.
    Bot shu ro'yxatni tugma qilib ko'rsatadi — xodim sanani qo'lda termaydi."""

    date: dt.date
    status: str  # late | absent
    late_minutes: int


class AppealSlaTick(BaseModel):
    dry_run: bool = False


class WorkLogReminderTick(BaseModel):
    """Scheduler tick. `dry_run` — hech kimga YUBORMASDAN kimga ketishini
    qaytaradi (attendance reminder-tick bilan bir xil sinov naqshi)."""

    dry_run: bool = False
