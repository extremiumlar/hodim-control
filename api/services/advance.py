"""Avans chegarasi — «bu xodim bugun eng ko'pi bilan qancha avans olishi mumkin».

NEGA KERAK (Avans TZ #2): hozir avansga HECH QANDAY chegara yo'q. HR
xohlagan summani kiritadi, Boshliq tasdiqlaydi va oy oxirida payslip
manfiy chiqishi mumkin — ya'ni xodim oylikdan ko'p pul olib bo'lgan.
Bunday holat qaytarib olinmaydi: pul allaqachon qo'lda.

FORMULA (TZ):

    maksimal = (sof oylik ÷ oydagi ish kuni) × ishlangan kun × koeffitsient
    maksimal = min(maksimal, sof oylik × cap_foiz)
    maksimal −= shu oyda olingan avanslar (tasdiqlangan + kutilayotgan)
    maksimal −= shu oydagi boshqa ushlanmalar
    agar maksimal < 0 → 0

⚠️ IKKINCHI HISOB YO'LI YARATILMAYDI. «Sof oylik», «oydagi ish kuni» va
«ishlangan kun» — hammasi `payroll.build_payslip` dan olinadi, ya'ni
payroll qanday hisoblasa avans ham AYNAN shundan oladi. Aks holda
«payslipda boshqa, avansda boshqa» degan eng yomon holat chiqadi.

«Sof oylik» deganda bu yerda **ushlanmalardan OLDINGI** netto tushuniladi
(`net + adjustments_minus`) — chunki formulaning oxirgi ikki qatori
avans va ushlanmani ALOHIDA ayiradi. Aks holda ular ikki marta ayirilardi.

SOZLAMA (B-01): `resolve_advance_settings(user)` — xodim > lavozim >
global. `limit_for()` uni O'ZI yechadi; sozlama topilmasa quyidagi
default qiymatlar ishlatiladi, ya'ni HR ning qo'lda kiritish yo'li
sozlamasiz ham ishlayveradi. Botning avans kuni xabari esa sozlamasiz
UMUMAN yuborilmaydi (`announce_ready()` — sozlanmagan holat xavfsiz
tomonga, TZ talabi).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.payroll import _dec, build_payslip, round_money
from db.models import (
    AdvanceSettings,
    PayrollAdjustment,
    PayrollAdjustmentCategory,
    PayrollAdjustmentKind,
    PayrollAdjustmentStatus,
    PayrollPeriod,
    User,
)

# Sozlama TOPILMAGANDA amal qiladigan qiymatlar (TZ jadvalidagi tavsiya).
# Bular «sukut bo'yicha siyosat», bo'shliqni yashirish emas: chegara baribir
# hisoblanadi va HR ning qo'lda kiritish yo'li ishlayveradi.
DEFAULT_COEFFICIENT = Decimal("0.5")   # ishlab bo'lingan pulning yarmi
DEFAULT_CAP_PERCENT = Decimal("50")    # oylikning yarmidan oshmasin
DEFAULT_ADVANCE_DAY = 20
DEFAULT_REMINDER_TIME = "14:00"
DEFAULT_PENDING_ON_CLOSE = "carry"


async def resolve_advance_settings(db: AsyncSession, user: User) -> AdvanceSettings | None:
    """Avans sozlamasi — 3 DARAJALI: xodim > lavozim > global (B-01).

    Naqsh `payroll.resolve_policy` bilan AYNAN bir xil: faqat FAOL
    (`is_active`) qator ishtirok etadi, bir daraja faol qatorsiz bo'lsa
    keyingi (kengroq) darajaga o'tiladi.

    `None` — hech qanday sozlama yo'q. Chaqiruvchilar buni ikki xil
    talqin qiladi va bu ATAYLAB:
      • chegara hisobi — default qiymatlar bilan davom etadi
        (HR ishi to'xtab qolmasin);
      • botning avans kuni xabari — UMUMAN yuborilmaydi
        (sozlanmagan tizim xodimga pul taklif qilmasin)."""
    row = await db.scalar(
        select(AdvanceSettings).where(
            AdvanceSettings.scope == "user",
            AdvanceSettings.scope_id == user.id,
            AdvanceSettings.is_active.is_(True),
        )
    )
    if row is not None:
        return row

    if user.position_id is not None:
        row = await db.scalar(
            select(AdvanceSettings).where(
                AdvanceSettings.scope == "position",
                AdvanceSettings.scope_id == user.position_id,
                AdvanceSettings.is_active.is_(True),
            )
        )
        if row is not None:
            return row

    return await db.scalar(
        select(AdvanceSettings).where(
            AdvanceSettings.scope == "global", AdvanceSettings.is_active.is_(True)
        )
    )


async def announce_ready(db: AsyncSession, user: User) -> AdvanceSettings | None:
    """Bu xodimga avans kuni xabarini yuborish MUMKINMI (B-04/C-01 uchun).

    Sozlama yo'q bo'lsa `None` — xabar yuborilmaydi. Alohida funksiya
    sifatida ajratilgani ataylab: «sozlamasiz jim tur» qoidasi bitta
    joyda tursin, har bir chaqiruvchi uni o'zicha talqin qilmasin."""
    return await resolve_advance_settings(db, user)

# Chegara 0 bo'lishining sabablari — xodim/HR «nega 0?» deb qolmasin.
REASON_NO_RATE = "stavka belgilanmagan"
REASON_PERIOD_LOCKED = "davr qulflangan"
REASON_NO_WORKED_DAYS = "shu oyda hali ishlangan kun yo'q"
REASON_NO_SCHEDULE = "shu oyda ish kuni rejalashtirilmagan"
REASON_ZERO_SALARY = "hisoblangan oylik 0"
REASON_EXHAUSTED = "shu oydagi chegara to'liq ishlatilgan"


@dataclass
class AdvanceLimit:
    """Chegara va uning KELIB CHIQISHI.

    Faqat `limit` qaytarilsa HR «nega shuncha?» deb so'raydi va javob
    yo'q bo'lardi — shuning uchun har bir oraliq qiymat ham qaytariladi
    (forma ularni ostida ko'rsatadi)."""

    limit: float                 # ruxsat etilgan eng katta summa
    net_salary: float            # ushlanmalardan oldingi sof oylik
    scheduled_days: int          # oydagi reja bo'yicha ish kuni
    worked_days: int             # shu kungacha ishlangan kun
    taken: float                 # shu oyda allaqachon olingan avanslar
    deductions: float            # shu oydagi boshqa ushlanmalar
    coefficient: float
    cap_percent: float
    earned: float                # koeffitsientgacha bo'lgan «ishlab olingan»
    cap_amount: float            # cap bo'yicha yuqori chegara
    reason: str | None = None    # `limit == 0` bo'lsa — sababi
    warnings: list[str] = field(default_factory=list)


async def taken_and_deductions(
    db: AsyncSession, user_id: int, period: str
) -> tuple[Decimal, Decimal]:
    """(shu oyda olingan avanslar, boshqa ushlanmalar).

    KUTILAYOTGANI HAM SANALADI: `pending` avans hali oylikka kirmagan, lekin
    tasdiqlanishi ehtimoli yuqori. Uni hisobga olmasak, HR ketma-ket ikkita
    so'rovni chegara ichida ko'rib ikkalasini ham o'tkazib yuborardi va
    yig'indi chegaradan oshib ketardi.

    `rejected` sanalmaydi — u hech qachon oylikka kirmaydi."""
    rows = list(
        await db.scalars(
            select(PayrollAdjustment).where(
                PayrollAdjustment.user_id == user_id,
                PayrollAdjustment.period == period,
                PayrollAdjustment.kind == PayrollAdjustmentKind.minus.value,
                PayrollAdjustment.status != PayrollAdjustmentStatus.rejected.value,
                # O'chirilgan avans chegarani band qilib turmasin (A-05).
                PayrollAdjustment.deleted_at.is_(None),
            )
        )
    )
    taken = sum(
        (_dec(r.amount) for r in rows if r.category == PayrollAdjustmentCategory.advance.value),
        Decimal("0"),
    )
    deductions = sum(
        (_dec(r.amount) for r in rows if r.category != PayrollAdjustmentCategory.advance.value),
        Decimal("0"),
    )
    return taken, deductions


def compute_limit(
    net_salary: Decimal,
    scheduled_days: int,
    worked_days: int,
    taken: Decimal,
    deductions: Decimal,
    coefficient: Decimal = DEFAULT_COEFFICIENT,
    cap_percent: Decimal = DEFAULT_CAP_PERCENT,
) -> tuple[Decimal, Decimal, Decimal, str | None]:
    """Formulaning TOZA qismi (DB'siz) — `(limit, earned, cap_amount, reason)`.

    Alohida ajratilgani ataylab: pul formulasini DB'siz, birma-bir ssenariy
    bilan sinash mumkin bo'lsin."""
    if scheduled_days <= 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), REASON_NO_SCHEDULE
    if net_salary <= 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), REASON_ZERO_SALARY
    if worked_days <= 0:
        return Decimal("0"), Decimal("0"), net_salary * cap_percent / 100, REASON_NO_WORKED_DAYS

    # Ishlangan kun rejadagidan ko'p bo'lishi mumkin emas — aks holda
    # (masalan dam kunida ishlab ketgan xodimda) chegara oylikdan oshardi.
    effective_worked = min(worked_days, scheduled_days)

    earned = (net_salary / scheduled_days) * effective_worked * coefficient
    cap_amount = net_salary * cap_percent / 100
    limit = min(earned, cap_amount) - taken - deductions

    if limit <= 0:
        return Decimal("0"), earned, cap_amount, REASON_EXHAUSTED
    return round_money(limit), earned, cap_amount, None


async def limit_for(
    db: AsyncSession,
    user: User,
    on_date: date | None = None,
    coefficient: Decimal | None = None,
    cap_percent: Decimal | None = None,
    period: str | None = None,
) -> AdvanceLimit:
    """Xodimning `on_date` sanasidagi avans chegarasi (default — bugun).

    `period` berilsa u USTUN turadi — HR o'tgan oyga avans kiritayotganda
    chegara ham o'sha oyning hisobidan olinishi kerak (bugungi oydan emas).

    ⚠️ QIMMAT: ichida `build_payslip` chaqiriladi (oyning har kuni bo'yicha
    davomat va jarima hisobi). Bitta xodim uchun bu normal, lekin butun
    ro'yxat uchun sikl ichida chaqirmang — ko'p xodim kerak bo'lsa natijani
    cron'da hisoblab saqlash kerak (C blokdagi bot oqimi shuni talab qiladi)."""
    on_date = on_date or date.today()
    period = period or on_date.strftime("%Y-%m")

    warnings: list[str] = []
    # Sozlama chaqiruvchidan kelmagan bo'lsa — uni O'ZIMIZ yechamiz.
    # Aks holda har bir chaqiruvchi buni takrorlashi kerak bo'lardi va
    # bittasi unutsa jimgina default bilan ishlab ketardi.
    if coefficient is None or cap_percent is None:
        settings = await resolve_advance_settings(db, user)
        if settings is not None:
            if coefficient is None:
                coefficient = Decimal(str(settings.coefficient))
            if cap_percent is None:
                cap_percent = Decimal(str(settings.cap_percent))

    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    locked = period_row is not None and period_row.locked

    payslip = await build_payslip(db, user, period)
    f = payslip["fields"]

    if f.get("rate_snapshot") is None:
        # Stavkasiz xodimda `net` 0 chiqadi — sabab aniq aytilsin, aks holda
        # «hisoblangan oylik 0» degan javob HR ni chalg'itadi.
        return AdvanceLimit(
            limit=0.0,
            net_salary=0.0,
            scheduled_days=int(f["scheduled_days"]),
            worked_days=int(f["worked_days"]),
            taken=0.0,
            deductions=0.0,
            coefficient=float(coefficient if coefficient is not None else DEFAULT_COEFFICIENT),
            cap_percent=float(cap_percent if cap_percent is not None else DEFAULT_CAP_PERCENT),
            earned=0.0,
            cap_amount=0.0,
            reason=REASON_NO_RATE,
        )

    # Ushlanmalardan OLDINGI netto: formulaning oxirgi ikki qatori avans va
    # ushlanmani alohida ayiradi, `net` esa ularni allaqachon ayirgan.
    net_before = _dec(f["net"]) + _dec(f["adjustments_minus"])

    taken, deductions = await taken_and_deductions(db, user.id, period)
    coef = coefficient if coefficient is not None else DEFAULT_COEFFICIENT
    cap = cap_percent if cap_percent is not None else DEFAULT_CAP_PERCENT

    limit, earned, cap_amount, reason = compute_limit(
        net_before, int(f["scheduled_days"]), int(f["worked_days"]), taken, deductions, coef, cap
    )

    if locked:
        # Qulflangan davrga yozilgan avans hech qachon hisobga kirmaydi —
        # chegara qancha bo'lishidan qat'i nazar 0 bo'lishi kerak.
        limit, reason = Decimal("0"), REASON_PERIOD_LOCKED
    if f["worked_days"] == 0 and f["excused_days"] > 0:
        warnings.append("xodim shu oyda sababli kunda (ta'til/kasallik)")

    return AdvanceLimit(
        limit=float(limit),
        net_salary=float(net_before),
        scheduled_days=int(f["scheduled_days"]),
        worked_days=int(f["worked_days"]),
        taken=float(taken),
        deductions=float(deductions),
        coefficient=float(coef),
        cap_percent=float(cap),
        earned=float(earned),
        cap_amount=float(cap_amount),
        reason=reason,
        warnings=warnings,
    )
