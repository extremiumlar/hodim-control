"""Foydalanuvchi ko'radigan BO'LIMLAR — tizimdagi YAGONA manba (TZ 2.6, S-04).

MUAMMO NIMA EDI
───────────────
«Kim nimani ko'radi» UCH joyda, uch xil tilda yozilgan edi:

  1. `web/src/Layout.tsx`        — `NAV_GROUPS` (rahbar yon paneli)
  2. `web/src/lib/employeeNav.ts` — `EMPLOYEE_SECTIONS` (xodim kabineti)
  3. `bot/keyboards.py`          — `main_menu` (bot klaviaturasi)

Ikkinchi fayl boshida shunday ogohlantirish turibdi: «ko'rinish shartlari
`bot/keyboards.py` bilan AYNAN bir xil bo'lishi shart» — ya'ni muvofiqlik
INSON e'tiboriga qolgan edi. Har yangi modul uchta joyga qo'shilishi kerak,
biri unutilsa xodim botda bir menyu, saytda boshqasini ko'radi.

Endi manba shu fayl. Mijozlar `GET /me/sections` orqali oladi (S-05 da
uchalasi ham shu yo'lga o'tkaziladi).

TAMOYILLAR
──────────
• `visible()` — SOF funksiya, faqat `SectionCtx` ga qaraydi. Bazaga
  murojaat qilmaydi: ro'yxat bitta so'rovda, keshlanadigan bo'lib qolsin.
• Bu ro'yxat — NAVIGATSIYA, ruxsat EMAS. Haqiqiy tekshiruv har doim
  endpointda (S-06 markazlashgan filtri). Bo'limni yashirish — qulaylik,
  himoya emas.
• `order` — 10 qadam bilan: oraga yangi bo'lim qo'shish uchun joy qolsin.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from db.models import User

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}
PAYROLL_MANAGER_ROLES = {"hr", "boss", "dasturchi"}

# `bot/keyboards.py: DEFAULT_MENU_FLAGS` — lavozim yo'q bo'lsa hammasi ochiq.
DEFAULT_MENU_FLAGS = {"tasks": True, "norm": True, "kpi": True, "excused": True, "payroll": True}
# `api/routers/norms.py: metrics_for` defaulti.
DEFAULT_METRICS = ["suhbat", "tashrif"]
SALES_METRICS = {"suhbat", "tashrif"}
TRACKABLE_METRICS = {"suhbat", "tashrif", "oddiy_video", "dumaloq_video"}


@dataclass(frozen=True)
class SectionCtx:
    """`visible()` ga beriladigan yagona kontekst."""

    role: str
    is_manager: bool
    is_dasturchi: bool
    can_manage_positions: bool
    can_manage_payroll: bool
    can_edit_fine_policy: bool
    #  Kadr hujjatlari (TZ 3.4) — MAXFIY modul. `can_manage_payroll` dan
    #  ATAYLAB alohida: u shaxsiy bayroq bilan kengayadi, bu esa
    #  QAT'IY rol ro'yxati — backend `_HR` bilan bir xil bo'lishi shart.
    can_view_hr_docs: bool
    can_edit_attendance: bool
    flags: dict
    metrics: list[str]

    @property
    def has_sales_metric(self) -> bool:
        return bool(SALES_METRICS & set(self.metrics))

    @property
    def has_trackable_metric(self) -> bool:
        return bool(TRACKABLE_METRICS & set(self.metrics))


def build_ctx(user: User) -> SectionCtx:
    position = getattr(user, "position", None)
    flags = {**DEFAULT_MENU_FLAGS, **((position.menu_flags if position else None) or {})}
    # ⚠️ `metrics is None` (lavozim biriktirilmagan) → default ro'yxat;
    # `[]` (ATAYLAB bo'sh, masalan Bugalter) → bo'sh qoladi. Shuning uchun
    # `or` EMAS, aniq `None` tekshiruvi (loyihaning ma'lum tuzog'i).
    metrics = position.metrics if position is not None and position.metrics is not None else DEFAULT_METRICS
    manager = user.role in MANAGER_ROLES
    payroll_manager = user.role in PAYROLL_MANAGER_ROLES
    return SectionCtx(
        role=user.role,
        is_manager=manager,
        is_dasturchi=user.role == "dasturchi",
        can_manage_positions=payroll_manager,
        can_manage_payroll=payroll_manager,
        # `can_manage_payroll` dan ATAYLAB alohida: bayroq faqat ushlanma
        # qoidasini ochadi, «Qo'shimcha ish» ni OCHMAYDI (backend 403 beradi).
        can_edit_fine_policy=payroll_manager or bool(user.can_edit_fine_policy),
        can_view_hr_docs=user.role in ("hr", "boss", "dasturchi"),
        can_edit_attendance=bool(user.can_edit_attendance),
        flags=flags,
        metrics=list(metrics),
    )


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    path: str
    icon: str  # lucide-react ikonasi nomi (mijozda map qilinadi)
    order: int
    #  "manager" — rahbar yon paneli · "employee" — xodim kabineti
    audience: str
    group: str = ""  # yon panel guruhi (xodimda bo'sh)
    #  Bot `ReplyKeyboardMarkup` ishlatadi — u `path` EMAS, tugma MATNINI
    #  biladi. Shuning uchun tugma matni ham shu yerda (TZ S-04 tuzog'i).
    bot_button: str | None = None
    #  `/` uchun `end=True` kerak (aks holda hamma yo'l unga mos keladi).
    exact: bool = False
    visible: Callable[[SectionCtx], bool] = field(default=lambda c: True)


def _har_doim(_c: SectionCtx) -> bool:
    return True


# ─────────────────────────────────────────────────────────────
# RAHBAR yon paneli — `web/src/Layout.tsx: NAV_GROUPS` nusxasi
# ─────────────────────────────────────────────────────────────
_MANAGER: list[Section] = [
    Section("home", "Bosh sahifa", "/", "LayoutDashboard", 10, "manager", "Boshqaruv", exact=True),
    Section("statistics", "Statistika", "/statistics", "BarChart3", 20, "manager", "Boshqaruv"),
    Section("reports", "Hisobotlar", "/reports", "FileSpreadsheet", 30, "manager", "Boshqaruv"),

    Section("attendance", "Davomat", "/attendance", "CalendarCheck", 40, "manager", "Davomat"),
    Section("excused-days", "Sababli kunlar", "/excused-days", "CalendarX", 50, "manager", "Davomat"),
    Section("work-schedule", "Ish jadvali", "/work-schedule", "Clock", 60, "manager", "Davomat"),
    Section("work-log", "Ish kundaligi", "/work-log", "NotebookPen", 70, "manager", "Davomat"),
    Section("offices", "Ofislar", "/offices", "MapPin", 80, "manager", "Davomat"),

    Section("lead-stats", "Lidlar", "/lead-stats", "TrendingUp", 90, "manager", "Sotuv"),
    Section("funnel", "Voronka", "/funnel", "Filter", 100, "manager", "Sotuv"),
    Section("norms", "Normalar", "/norms", "Target", 110, "manager", "Sotuv"),

    Section("payroll", "Ish haqi", "/payroll", "Banknote", 120, "manager", "Ish haqi"),
    Section("overtime", "Qo'shimcha ish", "/overtime", "TimerReset", 130, "manager", "Ish haqi",
            visible=lambda c: c.can_manage_payroll),
    Section("payroll-settings", "Sozlamalar", "/payroll/settings", "Settings", 140, "manager",
            "Ish haqi", visible=lambda c: c.can_edit_fine_policy),

    Section("users", "Foydalanuvchilar", "/users", "Users", 150, "manager", "Ma'muriyat"),
    #  Kadr hujjatlari MAXFIY: ROP ataylab ko'rmaydi (TZ 3.4).
    #  `can_edit_fine_policy` = HR/Boshliq/Dasturchi — aynan shu qamrov.
    Section("employee-documents", "Kadr hujjatlari", "/employee-documents", "FolderArchive",
            155, "manager", "Ma'muriyat", bot_button="📎 Hujjat yuklash",
            visible=lambda c: c.can_view_hr_docs),
    #  Muddatlar ham kadr ma'lumoti — bir xil qamrov (TZ 3.5).
    Section("deadlines", "Muddatlar", "/deadlines", "CalendarClock", 157, "manager",
            "Ma'muriyat", visible=lambda c: c.can_view_hr_docs),
    Section("offers", "Ish takliflari", "/offers", "UserPlus", 158, "manager",
            "Ma'muriyat", visible=lambda c: c.can_view_hr_docs),
    Section("certificates", "Ma'lumotnomalar", "/certificates", "ScrollText", 159,
            "manager", "Ma'muriyat", visible=lambda c: c.can_view_hr_docs),
    Section("assets", "Mol-mulk", "/assets", "Package", 160, "manager",
            "Ma'muriyat", visible=lambda c: c.can_view_hr_docs),
    #  E'lonni ROP ham yozadi (o'z jamoasiga xabar) — shuning uchun
    #  `can_view_hr_docs` emas, `is_manager`.
    Section("announcements", "E'lonlar", "/announcements", "Megaphone", 161, "manager",
            "Ma'muriyat", visible=lambda c: c.is_manager),
    #  Shtat jadvali — ROP ham ko'radi (faqat o'z qamrovi, backend
    #  filtrlaydi), lekin oddiy xodim UMUMAN ko'rmaydi.
    Section("staff", "Shtat jadvali", "/staff", "Briefcase", 162, "manager",
            "Ma'muriyat", visible=lambda c: c.is_manager),
    Section("probation", "Sinov muddati", "/probation", "UserCheck", 163, "manager",
            "Ma'muriyat", visible=lambda c: c.can_view_hr_docs),
    Section("requests", "Arizalar", "/requests", "FileText", 160, "manager", "Ma'muriyat",
            visible=lambda c: c.can_manage_payroll),
    Section("appeals", "E'tiroz/Shikoyat", "/appeals", "Scale", 170, "manager", "Ma'muriyat",
            visible=lambda c: c.can_manage_payroll),
    Section("positions", "Lavozimlar", "/positions", "Briefcase", 180, "manager", "Ma'muriyat",
            visible=lambda c: c.can_manage_positions),
    Section("celebration", "Tabrik videolari", "/celebration", "Clapperboard", 190, "manager",
            "Ma'muriyat", visible=lambda c: c.can_manage_payroll),
    Section("audit-logs", "Audit", "/audit-logs", "ScrollText", 200, "manager", "Ma'muriyat"),
    Section("dasturchi", "Dasturchi rejimi", "/dasturchi", "ShieldAlert", 210, "manager",
            "Ma'muriyat", visible=lambda c: c.is_dasturchi),

    # Yon panel ostidagi alohida havola (guruhsiz).
    Section("my-checkin", "Mening davomatim", "/check-in", "UserCheck", 900, "manager"),
]

# ─────────────────────────────────────────────────────────────
# XODIM kabineti — `employeeNav.ts` + `bot/keyboards.py` nusxasi.
# TARTIB MUHIM: tab-barga birinchi 4 tasi tushadi, qolgani «Yana» ga.
# ─────────────────────────────────────────────────────────────
_EMPLOYEE: list[Section] = [
    Section("checkin", "Davomat", "/check-in", "UserCheck", 10, "employee",
            bot_button="✅ Keldim / Ketdim"),
    # Dasturchi SHAXSAN huquq bergan xodim — boshqalarning vaqtini tuzatadi.
    Section("attendance-edit", "Davomat tuzatish", "/attendance", "PencilLine", 20, "employee",
            visible=lambda c: c.can_edit_attendance),
    Section("schedule", "Ish jadvali", "/me/schedule", "Clock", 30, "employee"),
    Section("payroll", "Mening oyligim", "/me/payroll", "Banknote", 40, "employee",
            visible=lambda c: bool(c.flags.get("payroll")) and c.role != "boss"),
    Section("stats", "Statistikam", "/me/stats", "BarChart3", 50, "employee"),
    Section("tasks", "Vazifalarim", "/me/tasks", "ListTodo", 60, "employee",
            visible=lambda c: bool(c.flags.get("tasks"))),
    Section("norm", "Bugungi normam", "/me/norm", "Target", 70, "employee",
            visible=lambda c: bool(c.flags.get("norm"))),
    Section("hourly", "Bugungi rejam", "/me/hourly-plan", "ClipboardList", 80, "employee",
            visible=lambda c: not c.is_manager and c.has_trackable_metric),
    Section("kpi", "Oylik KPI'm", "/me/kpi", "TrendingUp", 90, "employee",
            visible=lambda c: bool(c.flags.get("kpi"))),
    Section("leads", "Lidlar statistikasi", "/me/lead-stats", "TrendingUp", 100, "employee",
            visible=lambda c: not c.is_manager and c.has_sales_metric),
    Section("excused", "Sababli kun so'rash", "/me/excused", "CalendarX", 110, "employee",
            visible=lambda c: bool(c.flags.get("excused"))),
    Section("work-log", "Ish kundaligi", "/me/work-log", "NotebookPen", 120, "employee",
            visible=lambda c: c.role != "boss"),
    Section("documents", "Hujjatlarim", "/me/documents", "FolderOpen", 125, "employee",
            bot_button="📁 Hujjatlarim"),
    Section("my-assets", "Menga biriktirilgan", "/me/assets", "Package", 127, "employee"),
    Section("my-announcements", "E'lonlar", "/me/announcements", "Megaphone", 128,
            "employee"),
    #  Ish haqi tarixi — faqat O'ZINIKI. Boshliqda «Mening oyligim»
    #  ko'rinmagani kabi bu ham unga keraksiz.
    Section("my-salary-history", "Ish haqim tarixi", "/me/salary-history",
            "TrendingUp", 129, "employee", visible=lambda c: c.role != "boss"),
    Section("requests", "Arizalarim", "/me/requests", "FileText", 130, "employee",
            visible=lambda c: c.role != "boss"),
    Section("appeals", "E'tiroz / Shikoyat", "/me/appeals", "Scale", 140, "employee",
            visible=lambda c: c.role != "boss"),
]

ALL_SECTIONS: list[Section] = _MANAGER + _EMPLOYEE


def sections_for(user: User) -> list[Section]:
    """Shu foydalanuvchi KO'RADIGAN bo'limlar, tartibi bilan.

    Rahbar — yon panel to'plamini, xodim — kabinet to'plamini oladi. Ikkovi
    bir vaqtda qaytmaydi: mijozda ham ikki xil qobiq bor (yon panel va
    tab-bar), aralashsa menyu ikki barobar bo'lib ketardi."""
    ctx = build_ctx(user)
    kerakli = "manager" if ctx.is_manager else "employee"
    return sorted(
        (s for s in ALL_SECTIONS if s.audience == kerakli and s.visible(ctx)),
        key=lambda s: s.order,
    )


# ─────────────────────────────────────────────────────────────
# BOT KLAVIATURASI (S-05b)
# ─────────────────────────────────────────────────────────────
# Bot `ReplyKeyboardMarkup` ishlatadi — unda `path` emas, tugma MATNI va
# QATOR tuzilishi muhim (ikkita tugma yonma-yon turishi mumkin). Shuning
# uchun bot uchun alohida quruvchi: u SHU fayldagi `SectionCtx` ni
# ishlatadi, ya'ni ko'rinish shartlari saytdagi bilan BIR MANBADAN.
#
# NEGA BOT MENYUSI SAYTNIKIDAN FARQ QILADI: bot — SHAXSIY vosita, sayt esa
# boshqaruv konsoli. Botda rahbar ham «Vazifalarim», «Mening oyligim» kabi
# shaxsiy tugmalarni ko'radi; saytda esa u yon panelni ko'radi, kabinetni
# emas. Bu mahsulot qarori, texnik nomuvofiqlik emas.

BTN_TASKS = "📋 Vazifalarim"
BTN_NORM = "📊 Bugungi normam"
BTN_KPI = "💰 Oylik KPI'm"
BTN_PAYROLL = "💵 Mening oyligim"
BTN_PANEL = "📈 Panelim"
BTN_EXCUSED = "🙋 Sababli kun so'rash"
BTN_WORK_LOG = "📝 Ish kundaligi"
BTN_REQUESTS = "📮 Murojaatlarim"
BTN_ASSIGN_TASK = "📤 Vazifa berish"
BTN_MY_STATS = "📈 Statistikam"
BTN_GLOBAL_STATS = "📊 Umumiy statistika"
BTN_ATTENDANCE_STATS = "🕐 Davomat statistikasi"
BTN_LEAD_STATS = "🧲 Lidlar statistikasi"
BTN_SCHEDULE = "🗓 Ish jadvali"
BTN_HOURLY_PLAN = "📋 Bugungi rejam"
BTN_HOURLY_PLAN_CONTROL = "📋 Xodim rejasi"
BTN_CHANGE_NORM = "🎯 Norma o'zgartirish"
BTN_TASK_CONTROL = "📋 Vazifalar nazorati"
BTN_CALC_KPI = "💰 Oylik KPI hisoblash"
BTN_REPORT = "📥 Hisobot (Excel)"
BTN_AUDIT = "🧾 Audit jurnali"
BTN_AI_CENTER = "🧠 Sotuv AI markazi"
BTN_CELEBRATION = "🎬 Tabrik videolari"
BTN_MY_DOCS = "📁 Hujjatlarim"
BTN_DOC_UPLOAD = "📎 Hujjat yuklash"
BTN_SET_BUSY = "⏸ Band qilish"
BTN_MARK_EXCUSED = "🙋 Xodim uchun sababli kun"
BTN_SALES_AI = "🤖 Sotuv AI"
BTN_CHECKIN = "✅ Keldim / Ketdim"


def bot_menu_rows(user: User) -> list[list[str]]:
    """Bot asosiy menyusi — tugma matnlari, QATORLARGA bo'lingan holda.

    Tartib va qator tuzilishi `bot/keyboards.py::main_menu` ning avvalgi
    ko'rinishini AYNAN takrorlaydi (S-05b qabul mezoni: «bot menyusi eski
    ko'rinish bilan aynan bir xil»)."""
    c = build_ctx(user)
    rows: list[list[str]] = []

    # ── Shaxsiy qism (rahbarda ham bor) ──
    if c.role != "boss":
        rows.append([BTN_CHECKIN])
    if c.flags.get("tasks"):
        rows.append([BTN_TASKS])
    if c.role != "boss":
        rows.append([BTN_WORK_LOG])

    metrics_row = []
    if c.flags.get("norm"):
        metrics_row.append(BTN_NORM)
    if c.flags.get("kpi"):
        metrics_row.append(BTN_KPI)
    if metrics_row:
        rows.append(metrics_row)

    stats_row = [BTN_MY_STATS]
    if c.flags.get("excused"):
        stats_row.append(BTN_EXCUSED)
    rows.append(stats_row)

    if c.role != "boss":
        rows.append([BTN_REQUESTS, BTN_MY_DOCS])
    else:
        rows.append([BTN_MY_DOCS])
    rows.append([BTN_SCHEDULE])
    if c.flags.get("payroll") and c.role != "boss":
        rows.append([BTN_PAYROLL])
    if not c.is_manager and c.has_trackable_metric:
        rows.append([BTN_HOURLY_PLAN])

    show_lead_stats = c.is_manager or c.has_sales_metric
    if show_lead_stats and not c.is_manager:
        rows.append([BTN_LEAD_STATS])
    if not c.is_manager and c.has_sales_metric:
        rows.append([BTN_SALES_AI])

    # ── Boshqaruv qismi ──
    if c.is_manager:
        rows.append([BTN_ASSIGN_TASK, BTN_CHANGE_NORM])
        rows.append([BTN_TASK_CONTROL, BTN_GLOBAL_STATS])
        rows.append([BTN_LEAD_STATS, BTN_HOURLY_PLAN_CONTROL])
        rows.append([BTN_ATTENDANCE_STATS])
        if c.role in {"hr", "boss", "dasturchi"}:
            rows.append([BTN_MARK_EXCUSED])
            rows.append([BTN_DOC_UPLOAD])
        if c.role in {"rop", "boss", "dasturchi"}:
            rows.append([BTN_SALES_AI])
        if c.role in {"boss", "dasturchi"}:
            rows.append([BTN_CALC_KPI, BTN_REPORT])
            rows.append([BTN_AUDIT, BTN_PANEL])
            rows.append([BTN_SET_BUSY])
            rows.append([BTN_AI_CENTER])
            rows.append([BTN_CELEBRATION])
        else:
            rows.append([BTN_REPORT, BTN_PANEL])
            if c.role == "hr":
                rows.append([BTN_CELEBRATION])

    return rows


# ─────────────────────────────────────────────────────────────
# BOT SLASH-BUYRUQLARI (Telegram «/» menyusi + ruxsat nazorati)
# ─────────────────────────────────────────────────────────────
# Bo'limlar (yuqorida) bilan AYNI TAMOYIL: «kim qaysi buyruqni ko'radi va
# ishlata oladi» qoidasi SHU YERDA, bitta joyda. Bot faqat chizadi va
# tayyor javobga qarab to'sadi — o'zi rol hisoblamaydi.
#
# NEGA KERAK EDI: ilgari har handler o'z tekshiruvini o'zi yozardi va
# ko'pchiligi RUXSAT YO'Q holatida JIMGINA `return` qilardi (masalan
# `/guruhlar`, `/norm_set`, `/att_fix`) — xodim buyruqni bosardi, bot esa
# umuman javob bermasdi. Telegram «/» menyusi esa atigi 4 ta buyruqni
# ko'rsatardi, ya'ni qolgani faqat hujjatdan bilinardi.
#
# `scopes` — buyruq QAYERDA ishlaydi. Bu ruxsatdan ALOHIDA: Dasturchi
# `/guruh_biriktir` ni shaxsiy chatda yozsa, u «ruxsat yo'q» emas, «bu
# buyruq guruh ichida ishlaydi» degan javob olishi kerak.

PRIVATE = "private"
GROUP = "group"

@dataclass(frozen=True)
class BotCmd:
    """Bitta slash-buyruq: nomi, izohi, qayerda ishlashi va kim ishlata olishi."""

    name: str  # slashsiz: "statistika"
    description: str  # Telegram «/» menyusidagi qisqa izoh (≤256 belgi)
    scopes: frozenset[str]
    order: int
    #  Kim ishlata oladi. `SectionCtx` — bo'limlar bilan AYNI kontekst.
    visible: Callable[[SectionCtx], bool] = field(default=lambda c: True)
    #  Xato matnida: «bu buyruq {audience} uchun».
    audience: str = "hamma xodim"
    #  Guruhda: faqat shu maqsadga biriktirilgan guruhlarda ishlaydi
    #  (`/guruh_biriktir` bilan belgilangan). Bo'sh — istalgan guruhda.
    group_purposes: frozenset[str] = frozenset()


def _har_kim(_c: SectionCtx) -> bool:
    return True


def _rahbar(c: SectionCtx) -> bool:
    return c.is_manager


def _boshliq(c: SectionCtx) -> bool:
    return c.role in {"boss", "dasturchi"}


def _dasturchi(c: SectionCtx) -> bool:
    return c.is_dasturchi


def _sotuv(c: SectionCtx) -> bool:
    """`bot_menu_rows` dagi «🤖 Sotuv AI» tugmasi bilan AYNI shart:
    sotuv ko'rsatkichi bor xodim yoki ROP/Boshliq/Dasturchi."""
    return c.has_sales_metric or c.role in {"rop", "boss", "dasturchi"}


_RAHBAR_L = "rahbarlar (HR / ROP / Boshliq)"
_BOSHLIQ_L = "Boshliq va Dasturchi"
_DASTURCHI_L = "faqat Dasturchi"
_SOTUV_L = "sotuv xodimlari va rahbarlar"

ALL_COMMANDS: list[BotCmd] = [
    BotCmd("start", "Botni ishga tushirish va bosh menyu",
           frozenset({PRIVATE}), 10),
    BotCmd("buyruqlar", "Menga ruxsat etilgan buyruqlar ro'yxati",
           frozenset({PRIVATE, GROUP}), 20),

    # ── Statistika va hisobotlar ──
    BotCmd("statistika", "Kunlik hisobotni shu guruhga yuborish",
           frozenset({GROUP}), 30, _rahbar, _RAHBAR_L,
           group_purposes=frozenset({"main", "stats"})),
    BotCmd("statistika_vaqt", "Kunlik hisobot vaqtini ko'rish/o'zgartirish",
           frozenset({PRIVATE, GROUP}), 40, _boshliq, _BOSHLIQ_L),
    BotCmd("oylik", "Oylik yakuniy hisobot",
           frozenset({PRIVATE, GROUP}), 50, _rahbar, _RAHBAR_L),
    BotCmd("davomat_vaqt", "Davomat hisoboti vaqti (ko'rish/sozlash)",
           frozenset({PRIVATE}), 60, _rahbar, _RAHBAR_L),
    BotCmd("reja", "Xodimning bugungi soatlik ish rejasi",
           frozenset({PRIVATE, GROUP}), 70, _rahbar, _RAHBAR_L),
    BotCmd("norma_ozgartir", "Xodimga norma belgilash",
           frozenset({PRIVATE}), 80, _rahbar, _RAHBAR_L),

    # ── Sotuv AI ──
    BotCmd("ai_sozlama", "Operator AI kuzatuvi sozlamalari",
           frozenset({PRIVATE}), 90, _rahbar, _RAHBAR_L),
    BotCmd("ai_markazi", "Sotuv AI boshqaruv markazi",
           frozenset({PRIVATE}), 100, _boshliq, _BOSHLIQ_L),
    BotCmd("bilim", "Sotuv bilim bazasi",
           frozenset({PRIVATE}), 110, _boshliq, _BOSHLIQ_L),
    BotCmd("playbook", "Sotuv playbook (vaziyat → texnika)",
           frozenset({PRIVATE}), 120, _boshliq, _BOSHLIQ_L),
    BotCmd("sotuv_ai", "Mijoz savoliga AI javobi",
           frozenset({PRIVATE}), 130, _sotuv, _SOTUV_L),

    # ── Dasturchi ──
    BotCmd("anketa", "Xodimlar anketasini boshqarish",
           frozenset({PRIVATE}), 140, _dasturchi, _DASTURCHI_L),
    BotCmd("guruhlar", "Bot biriktirilgan guruhlar ro'yxati",
           frozenset({PRIVATE}), 150, _dasturchi, _DASTURCHI_L),
    BotCmd("guruh_biriktir", "Shu guruhni maqsadga biriktirish",
           frozenset({GROUP}), 160, _dasturchi, _DASTURCHI_L),
    BotCmd("guruh_ochir", "Shu guruhni maqsaddan olib tashlash",
           frozenset({GROUP}), 170, _dasturchi, _DASTURCHI_L),
    BotCmd("norm_set", "Normani cheklovsiz belgilash",
           frozenset({PRIVATE}), 180, _dasturchi, _DASTURCHI_L),
    BotCmd("norm_del", "Norma yozuvlarini o'chirish",
           frozenset({PRIVATE}), 190, _dasturchi, _DASTURCHI_L),
    BotCmd("att_fix", "Davomat vaqtini qo'lda tuzatish",
           frozenset({PRIVATE}), 200, _dasturchi, _DASTURCHI_L),
    BotCmd("unlock", "Qulflangan oylik davrni ochish",
           frozenset({PRIVATE}), 210, _dasturchi, _DASTURCHI_L),
    BotCmd("undo", "O'chirilgan norma yozuvini tiklash",
           frozenset({PRIVATE}), 220, _dasturchi, _DASTURCHI_L),
]

COMMANDS_BY_NAME: dict[str, BotCmd] = {c.name: c for c in ALL_COMMANDS}


def commands_for(user: User, chat_type: str) -> list[BotCmd]:
    """Shu xodim SHU turdagi chatda ishlata oladigan buyruqlar, tartibi bilan."""
    ctx = build_ctx(user)
    scope = PRIVATE if chat_type == PRIVATE else GROUP
    return sorted(
        (c for c in ALL_COMMANDS if scope in c.scopes and c.visible(ctx)),
        key=lambda c: c.order,
    )


def bot_commands_payload(user: User) -> list[dict]:
    """`UserOut.bot_commands` — botga beriladigan TO'LIQ ro'yxat.

    ATAYLAB to'liq (faqat ruxsat etilganlari emas): bot ikkala ish uchun
    ham shu bitta javobdan foydalanadi —
      · «/» menyusini chizish → `allowed=True` bo'lganlari;
      · ruxsati yo'q buyruq bosilganda ANIQ sabab aytish → qolganlari
        (`audience` va `scopes` bilan).
    Aks holda bot rol shartlarini o'zi takrorlashi kerak bo'lardi — bu esa
    aynan `sections.py` bartaraf etgan ikkinchi manba muammosi."""
    ctx = build_ctx(user)
    return [
        {
            "command": c.name,
            "description": c.description,
            "scopes": sorted(c.scopes),
            "allowed": c.visible(ctx),
            "audience": c.audience,
            "group_purposes": sorted(c.group_purposes),
        }
        for c in sorted(ALL_COMMANDS, key=lambda c: c.order)
    ]
