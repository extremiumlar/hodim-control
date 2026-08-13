"""CRM (Uysot) kunlik natijalar sinxronizatsiyasi — SERVIS qatlami.

NEGA ALOHIDA MODUL (2026-08-13, SAYT_QOTISHI_TAHLIL.md Bosqich 2):
bu ish ilgari FAQAT HTTP endpoint sifatida mavjud edi va cron uni SAYTGA
HTTP so'rov yuborib chaqirardi. Deploy'da konkurentlik = 1, sinxronizatsiya
esa ~30-40 soniya davom etadi — ya'ni har 2 daqiqada sayt shuncha vaqtga
BUTUNLAY javob bermay qolardi. Jonli o'lchov: bitta so'rov 40.3 soniya
kutdi.

Endi mantiq shu yerda, ikkita chaqiruvchi bilan:
  - `POST /daily-results/sync` — Docker/scheduler rejimi uchun SAQLANADI;
  - `scripts/cron_tick.py` — cPanel rejimida shu funksiyani O'Z jarayonida
    chaqiradi, saytga umuman tegmaydi.

Naqsh `hot_lead`/`idle_watch` bilan bir xil (ular allaqachon shunday
ishlaydi) — yangi qolip o'ylab topilmadi.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services.lead_diff import visit_stats_range
from api.timeutil import today_local
from crm import get_crm_adapter
from crm.config import CRM_UYSOT_VISIT_PIPE_STATUS_IDS
from db.models import DailyResult, DailyResultSource, Role, User
from db.upsert import upsert

logger = logging.getLogger(__name__)


async def upsert_daily_result(
    db: AsyncSession, user_id: int, day: date, conversations: int, visits: int, source: str
) -> DailyResult:
    stmt = (
        upsert(DailyResult)
        .values(user_id=user_id, date=day, conversations_count=conversations, visits_count=visits, source=source)
        .on_conflict_do_update(
            index_elements=[DailyResult.user_id, DailyResult.date],
            set_={"conversations_count": conversations, "visits_count": visits, "source": source},
        )
    )
    await db.execute(stmt)
    await db.commit()

    # populate_existing=True: agar shu qatorga mos ORM obyekt sessiyada allaqachon
    # (masalan chaqiruvchi "before" auditi uchun) yuklangan bo'lsa, identity map eski
    # qiymatlarni qaytarib yubormasin — yangi UPDATE'dan keyingi haqiqiy qiymatlarni oling.
    return await db.scalar(
        select(DailyResult)
        .where(DailyResult.user_id == user_id, DailyResult.date == day)
        .execution_options(populate_existing=True)
    )



async def sync_daily_results(db: AsyncSession) -> dict:
    """Scheduler tomonidan soatlik chaqiriladi (webhook mavjud bo'lmagan holat uchun zaxira).
    CRM_TYPE=none bo'lsa hech narsa qilmaydi (qo'lda kiritish yetarli).

    ⚠️ TASHRIF HISOBI TUZATILDI (2026-08-12, egasining talabi). Ilgari tashrif
    CRM'dagi `updatedTimestamp` bo'yicha sanalardi: "Tashrif bosqichida turgan
    va BUGUN tahrirlangan lid". Bu ikki tomonlama noto'g'ri edi —
      (a) 3 kun oldin tashrifga o'tgan lidga bugun izoh qo'shilsa, u YANA
          tashrif deb sanalardi (jonli misol 08-11: Shahnoza'ga 4 ta tashrif
          yozilgan, aslida o'sha kuni bironta ham tashrif voqeasi yo'q);
      (b) lidni TASHRIFGA OLIB KELGAN, keyin boshqa mas'ulga o'tkazgan xodim
          umuman hisobga olinmasdi (08-12: Hayot 2 ta tashrif qilgan, KPI'da 0).
    Endi manba — `LeadEvent` voqealari (`lead_diff.daily_operator_breakdown`):
    "lid Tashrif bosqichiga YANGI kirdi" hodisasi, dual-kredit bilan (yopgan
    + olib kelgan). Statistika/guruh digesti allaqachon shu manbadan o'qiydi —
    endi KPI/norma/bonus ham AYNAN SHU raqamni ko'radi (ilgari ikki bo'lim
    ikki xil son ko'rsatardi)."""
    adapter = get_crm_adapter(settings.crm_type)
    if not adapter:
        return {"synced": 0, "skipped_reason": "CRM_TYPE sozlanmagan"}

    today = today_local()
    employees = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                (User.crm_external_id.isnot(None) | User.crm_visit_external_id.isnot(None)),
            )
        )
    )

    synced = 0
    failed = 0
    skipped_manual = 0
    # Kunlik CRM ma'lumoti BITTA chaqiruvda olinadi: u faqat kunga bog'liq, shuning
    # uchun har xodim uchun alohida so'rash o'sha og'ir yuklashni N marta
    # takrorlardi (jonli o'lchov: 4 xodimda ~4.4s). cPanel'da Passenger'ning yagona
    # ishchisi shu vaqt band bo'lib, sayt so'rovlari navbatda kutardi.
    results = await adapter.get_daily_results_bulk(employees, today)

    # Tashrif — VOQEA asosidan (yuqoridagi izoh). `days_with_events` bo'sh
    # bo'lsa diff-engine shu kuni umuman ishlamagan degani: bunday paytda
    # tashrifni 0 ga tushirib yubormaymiz (mavjud qiymat saqlanadi), aks holda
    # CRM/diff uzilishi xodimning kunlik natijasini nolga yechib yuborardi.
    visit_series = await visit_stats_range(db, today, today, set(CRM_UYSOT_VISIT_PIPE_STATUS_IDS))
    events_exist = today in visit_series["days_with_events"]
    visits_by_crm_id = {
        str(rid): cnt for rid, cnt in visit_series["daily_by_operator"].get(today, {}).items()
    }

    for emp in employees:
        data = results.get(emp.id)
        if data is None:
            # CRM'dan ma'lumot olib bo'lmadi (xatolik) — mavjud yozuvni ustidan
            # yozib yubormaslik uchun bu xodimni butunlay o'tkazib yuboramiz.
            logger.warning("CRM sinxronizatsiyasi o'tkazib yuborildi (user_id=%s) — CRM xatosi", emp.id)
            failed += 1
            continue

        existing = await db.scalar(
            select(DailyResult).where(DailyResult.user_id == emp.id, DailyResult.date == today)
        )
        if existing and existing.source == DailyResultSource.manual.value:
            # Qo'lda kiritilgan yozuvni CRM sync avtomatik ustidan yozmaydi — qo'lda
            # kiritilgan qiymat qasddan CRM'dan farq qilishi mumkin (masalan tuzatish).
            logger.info("CRM sinxronizatsiyasi o'tkazib yuborildi (user_id=%s) — qo'lda kiritilgan yozuv", emp.id)
            skipped_manual += 1
            continue

        # Tashrif: voqea-asosli (aniq). Voqea jurnali shu kunga bo'sh bo'lsa —
        # eski qiymat saqlanadi (yuqoridagi izoh), CRM'ning taxminiy soniga
        # QAYTILMAYDI: u yolg'on ko'paytirardi.
        if events_exist:
            visits = (
                visits_by_crm_id.get(emp.crm_visit_external_id, 0)
                if emp.crm_visit_external_id
                else 0
            )
        else:
            visits = existing.visits_count if existing else 0

        await upsert_daily_result(
            db, emp.id, today, data["conversations"], visits, DailyResultSource.crm.value
        )
        synced += 1

    return {
        "synced": synced,
        "failed": failed,
        "skipped_manual": skipped_manual,
        "total_employees_with_crm_id": len(employees),
    }
