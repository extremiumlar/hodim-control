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
