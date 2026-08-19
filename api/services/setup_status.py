"""«Sozlanmagan modullar» — mexanizmi tayyor, lekin QIYMATI yo'q modullar
ro'yxati (yangi TZ 2.7 / S-08).

MUAMMO
──────
Tizimda kamida to'rt modul JIM turibdi: kod yozilgan, endpointlar bor,
lekin HR bironta qiymat kiritmagani uchun natija doim 0 chiqadi. Va bu
holat HECH QAYERDA ko'rinmaydi — «nega KPI bonusi nol?» degan savol
oyiga bir marta qaytadi.

Jonli isbot (2026-08-17): `kpi_rates` jadvali BUTUNLAY bo'sh edi. Kod
to'g'ri ishlardi, ko'paytiriladigan stavka yo'q edi — buni topguncha
oylik tekshiruvi kerak bo'ldi.

KENGAYTIRISH
────────────
Yangi modul qo'shish uchun `_TEKSHIRUVLAR` ga BITTA qator yetadi:
nomi, tekshiruvchi funksiya, nima yetishmayotgani va sozlash havolasi.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CelebrationMedia,
    FinePolicy,
    FunnelMonth,
    KpiRate,
    Norm,
    OvertimeProfile,
    SalaryRate,
)


@dataclass(frozen=True)
class SetupItem:
    key: str
    label: str
    ready: bool
    missing: str  # nima yetishmayapti (foydalanuvchi tilida)
    link: str  # sozlash sahifasi
    #  `True` — bu modulsiz PUL noto'g'ri hisoblanadi. Panelda tepada
    #  va qizil rangda ko'rsatiladi.
    critical: bool = False


# (kalit, nomi, tekshiruvchi, yetishmasa nima deyish, havola, muhimmi)
_Tekshiruv = tuple[str, str, Callable[[AsyncSession], Awaitable[bool]], str, str, bool]


async def _bor(db: AsyncSession, model, *shartlar) -> bool:
    q = select(func.count()).select_from(model)
    for sh in shartlar:
        q = q.where(sh)
    return bool((await db.scalar(q)) or 0)


async def _kpi_rates(db: AsyncSession) -> bool:
    return await _bor(db, KpiRate)


async def _salary_rates(db: AsyncSession) -> bool:
    return await _bor(db, SalaryRate, SalaryRate.deleted_at.is_(None))


async def _video_norm(db: AsyncSession) -> bool:
    """Mobilograf kunlik video normasi — mexanizm tayyor, qiymat yo'q edi."""
    return await _bor(
        db,
        Norm,
        Norm.metric_type.in_(["oddiy_video", "dumaloq_video"]),
        Norm.deleted_at.is_(None),
    )


async def _overtime(db: AsyncSession) -> bool:
    return await _bor(db, OvertimeProfile, OvertimeProfile.enabled.is_(True))


async def _celebration(db: AsyncSession) -> bool:
    return await _bor(db, CelebrationMedia, CelebrationMedia.is_active.is_(True))


async def _fine_policy(db: AsyncSession) -> bool:
    return await _bor(db, FinePolicy)


async def _funnel_target(db: AsyncSession) -> bool:
    return await _bor(db, FunnelMonth, FunnelMonth.target_contracts.isnot(None))


async def _ad_spend(db: AsyncSession) -> bool:
    from db.models import AdSpend

    return await _bor(db, AdSpend)


async def _holidays(db: AsyncSession) -> bool:
    """Bayramlar jadvali — S-09 da qo'shiladi. Jadval hali yo'q bo'lsa
    modul «sozlanmagan» deb ko'rsatiladi (to'g'ri holat)."""
    try:
        from db.models import Holiday  # type: ignore[attr-defined]
    except ImportError:
        return False
    return await _bor(db, Holiday)


_TEKSHIRUVLAR: list[_Tekshiruv] = [
    ("salary_rates", "Oylik stavkalar", _salary_rates,
     "Birorta xodimga oylik stavka kiritilmagan — ularga oylik hisoblanmaydi",
     "/payroll", True),
    ("kpi_rates", "KPI stavkalari", _kpi_rates,
     "Suhbat/tashrif/video uchun stavka yo'q — KPI bonusi doim 0 chiqadi",
     "/payroll", True),
    ("fine_policy", "Ushlanma qoidasi", _fine_policy,
     "Qoida yo'q — kechikish va kelmagan kun uchun ushlanma hisoblanmaydi",
     "/payroll/settings", True),
    ("overtime", "Qo'shimcha ish", _overtime,
     "Birorta profil yoqilmagan — qo'shimcha ish doim 0 chiqadi",
     "/payroll/settings", True),
    ("video_norm", "Mobilograf video normasi", _video_norm,
     "Kunlik video normasi belgilanmagan — bajarilish foizi hisoblanmaydi",
     "/norms", False),
    ("celebration", "Tabrik videolari", _celebration,
     "Video yuklanmagan — tashrif va shartnomada guruhga tabrik chiqmaydi",
     "/celebration", False),
    ("funnel_target", "Voronka maqsadi", _funnel_target,
     "Oylik shartnoma maqsadi qo'yilmagan — teskari hisob ishlamaydi",
     "/funnel", False),
    ("ad_spend", "Reklama xarajati", _ad_spend,
     "Xarajat kiritilmagan — bitta lid va bitta sotuv qancha turgani (CPL/CAC) noma'lum",
     "/funnel", False),
    ("holidays", "Bayramlar jadvali", _holidays,
     "Bayram kunlari kiritilmagan — ular ish kuni sifatida sanaladi",
     "/work-schedule", False),
]


async def collect_setup_status(db: AsyncSession) -> list[SetupItem]:
    """Barcha modullar holati — sozlanmaganlari BIRINCHI, muhimlari tepada."""
    items: list[SetupItem] = []
    for key, label, checker, missing, link, critical in _TEKSHIRUVLAR:
        try:
            ready = await checker(db)
        except Exception:  # noqa: BLE001
            # Jadval hali yo'q (yangi modul) — «sozlanmagan» deb ko'rsatamiz.
            # Bosh sahifa BITTA modul tufayli yiqilmasligi kerak.
            ready = False
        items.append(
            SetupItem(key=key, label=label, ready=ready, missing=missing,
                      link=link, critical=critical)
        )
    # Sozlanmaganlar tepada; ular ichida muhimlari birinchi.
    items.sort(key=lambda i: (i.ready, not i.critical, i.label))
    return items
