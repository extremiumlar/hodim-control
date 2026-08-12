import hmac
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.routers.norms import METRIC_LABELS, can_manage_norms, metrics_for
from api.services.lead_diff import visit_stats_range
from api.timeutil import today_local
from crm.config import CRM_UYSOT_VISIT_PIPE_STATUS_IDS
from api.schemas import (
    CRMWebhookPayload,
    DailyResultManualCreate,
    DailyResultOut,
    DailyResultTodayOut,
)
from crm import get_crm_adapter
from db.models import AuditLog, DailyResult, DailyResultSource, Role, User
from db.upsert import upsert

logger = logging.getLogger(__name__)

router = APIRouter(tags=["daily-results"])


def _validate_manual_metrics(target: User, conversations: int, visits: int) -> None:
    """Lavozimda kuzatilmaydigan ko'rsatkichga ijobiy qiymat kiritishni rad etadi
    (norms.py:_validate_metric bilan bir xil uslub). 0 qiymatga ruxsat beriladi —
    mavjud ish oqimlari (ikkala maydonni birga yuboradigan formalar) buzilmasligi uchun."""
    allowed = metrics_for(target)
    for metric, value in (("suhbat", conversations), ("tashrif", visits)):
        if value > 0 and metric not in allowed:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bu xodimning lavozimi uchun '{METRIC_LABELS[metric]}' ko'rsatkichi kuzatilmaydi",
            )


async def _upsert_daily_result(
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


@router.post("/daily-results/manual", response_model=DailyResultOut)
async def manual_daily_result(
    payload: DailyResultManualCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> DailyResult:
    target = await db.get(User, payload.user_id)
    if not target or target.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimga kunlik natija kiritish huquqingiz yo'q")
    _validate_manual_metrics(target, payload.conversations_count, payload.visits_count)

    existing = await db.scalar(
        select(DailyResult).where(DailyResult.user_id == payload.user_id, DailyResult.date == payload.date)
    )
    before = (
        {"conversations_count": existing.conversations_count, "visits_count": existing.visits_count, "source": existing.source}
        if existing
        else None
    )

    record = await _upsert_daily_result(
        db, payload.user_id, payload.date, payload.conversations_count, payload.visits_count,
        DailyResultSource.manual.value,
    )

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="daily_result_manual_set",
            target_user_id=payload.user_id,
            before=before,
            after={
                "conversations_count": record.conversations_count,
                "visits_count": record.visits_count,
                "source": record.source,
                "date": payload.date.isoformat(),
            },
        )
    )
    await db.commit()

    return record


@router.get("/daily-results", response_model=list[DailyResultOut])
async def list_daily_results(
    user_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[DailyResult]:
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    if not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimning natijalarini ko'rish huquqingiz yo'q")

    query = (
        select(DailyResult)
        .where(DailyResult.user_id == user_id)
        .order_by(DailyResult.date.desc())
        .limit(60)
    )
    return list(await db.scalars(query))


async def _today_result_for_user(db: AsyncSession, user: User) -> DailyResultTodayOut:
    """Xodimning bugungi natijasi + lavozimiga moslashgan ko'rsatkichlar.

    Bot ham, web ham shu yordamchini chaqiradi (`_late_status_for_user` bilan
    bir xil naqsh) — mantiq ikki joyda takrorlanmasligi uchun."""
    from api.routers.stats import today_metric_rows  # circular importdan qochish

    today = today_local()
    result = await db.scalar(select(DailyResult).where(DailyResult.user_id == user.id, DailyResult.date == today))

    return DailyResultTodayOut(
        conversations_count=result.conversations_count if result else 0,
        visits_count=result.visits_count if result else 0,
        # Lavozimga moslashgan ro'yxat — bot shu ro'yxatni ko'rsatadi
        metrics=await today_metric_rows(db, user),
    )


@router.get(
    "/daily-results/today/{telegram_id}",
    response_model=DailyResultTodayOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def today_daily_result(telegram_id: int, db: AsyncSession = Depends(get_db)) -> DailyResultTodayOut:
    """Bot uchun — shaxsni `telegram_id`dan yechadi, mantiq yordamchida."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _today_result_for_user(db, user)


@router.get("/daily-results/me/today", response_model=DailyResultTodayOut)
async def my_today_result_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DailyResultTodayOut:
    """Web (JWT) versiyasi — xodim kabineti «Bugungi normam» uchun. Shaxs
    TOKENDAN olinadi. Bot yo'li `/today/{telegram_id}` — ikkinchi segmenti
    boshqa ("today" vs "me"), to'qnashuv yo'q."""
    return await _today_result_for_user(db, user)


@router.post("/daily-results/recalc-visits")
async def recalc_visits(
    date_from: date,
    date_to: date,
    dry_run: bool = True,
    actor: User = Depends(require_roles(Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O'TGAN kunlarning tashrif sonini VOQEA asosida qayta hisoblaydi.

    Nega kerak: `sync_daily_results` tuzatilgunga qadar tashrif CRM'ning
    `updatedTimestamp`i bo'yicha yozilgan — ya'ni allaqachon yozilgan kunlarda
    yolg'on sonlar qolgan (jonli misol: 08-11 Shahnoza 4, aslida 0). Oylik
    bonus aynan shu jadvaldan hisoblanadi, shuning uchun o'tmish ham
    to'g'rilanishi kerak.

    Xavfsizlik: `dry_run=true` (standart) — faqat farqni ko'rsatadi, yozmaydi.
    QO'LDA kiritilgan yozuvlarga (`source=manual`) TEGILMAYDI. Voqea jurnali
    bo'sh kunlar (diff-engine ishlamagan) ham chetlab o'tiladi — u yerda
    "0 tashrif" degan xulosa chiqarib bo'lmaydi."""
    if date_to < date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "«date_to» «date_from» dan oldin bo'lmasin")
    if (date_to - date_from).days > 92:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oraliq 92 kundan oshmasin")

    series = await visit_stats_range(db, date_from, date_to, set(CRM_UYSOT_VISIT_PIPE_STATUS_IDS))
    users = list(await db.scalars(select(User).where(User.crm_visit_external_id.isnot(None))))
    by_crm = {u.crm_visit_external_id: u for u in users}

    changes: list[dict] = []
    skipped_days: list[str] = []
    day = date_from
    while day <= date_to:
        if day not in series["days_with_events"]:
            skipped_days.append(day.isoformat())
            day += timedelta(days=1)
            continue

        want = {
            by_crm[str(rid)].id: cnt
            for rid, cnt in series["daily_by_operator"].get(day, {}).items()
            if str(rid) in by_crm
        }
        rows = list(await db.scalars(select(DailyResult).where(DailyResult.date == day)))
        by_user = {r.user_id: r for r in rows}

        for uid in set(want) | set(by_user):
            row = by_user.get(uid)
            if row is not None and row.source == DailyResultSource.manual.value:
                continue  # qo'lda kiritilgan — tegmaymiz
            new_v = want.get(uid, 0)
            old_v = row.visits_count if row else 0
            if new_v == old_v:
                continue
            user = await db.get(User, uid)
            changes.append(
                {
                    "date": day.isoformat(),
                    "user": user.full_name.strip() if user else f"#{uid}",
                    "old": old_v,
                    "new": new_v,
                }
            )
            if not dry_run:
                if row is not None:
                    row.visits_count = new_v
                elif new_v:
                    await _upsert_daily_result(
                        db, uid, day, 0, new_v, DailyResultSource.crm.value
                    )
        day += timedelta(days=1)

    if not dry_run and changes:
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="daily_results_visits_recalculated",
                before={"range": f"{date_from}..{date_to}"},
                after={"changed": len(changes)},
            )
        )
        await db.commit()

    return {
        "dry_run": dry_run,
        "changed": len(changes),
        "changes": changes[:100],
        "skipped_days_without_events": skipped_days,
    }


@router.post("/daily-results/sync", dependencies=[Depends(verify_bot_secret)])
async def sync_daily_results(db: AsyncSession = Depends(get_db)) -> dict:
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

        await _upsert_daily_result(
            db, emp.id, today, data["conversations"], visits, DailyResultSource.crm.value
        )
        synced += 1

    return {
        "synced": synced,
        "failed": failed,
        "skipped_manual": skipped_manual,
        "total_employees_with_crm_id": len(employees),
    }


@router.post("/crm/webhook")
async def crm_webhook(
    payload: CRMWebhookPayload,
    x_crm_webhook_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """amoCRM (yoki boshqa CRM) real-vaqtli webhook orqali kunlik natijani yuboradi.
    Haqiqiy amoCRM webhook payload formati (form-encoded, ichma-ich maydonlar) hisobga
    olib, buni shu normallashtirilgan shaklga o'giradigan kichik middleware qo'shilishi
    mumkin — hozircha to'g'ridan-to'g'ri normallashtirilgan JSON qabul qilinadi."""
    if not settings.crm_webhook_secret or not x_crm_webhook_secret or not hmac.compare_digest(
        x_crm_webhook_secret, settings.crm_webhook_secret
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Webhook maxfiy kaliti noto'g'ri")

    user = await db.scalar(select(User).where(User.crm_external_id == payload.crm_external_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CRM ID bo'yicha foydalanuvchi topilmadi")

    existing = await db.scalar(
        select(DailyResult).where(DailyResult.user_id == user.id, DailyResult.date == payload.date)
    )
    before = (
        {"conversations_count": existing.conversations_count, "visits_count": existing.visits_count, "source": existing.source}
        if existing
        else None
    )

    record = await _upsert_daily_result(
        db, user.id, payload.date, payload.conversations, payload.visits, DailyResultSource.crm.value
    )

    db.add(
        AuditLog(
            actor_id=None,  # CRM webhook orqali tizim tomonidan avtomatik
            action="daily_result_crm_webhook",
            target_user_id=user.id,
            before=before,
            after={
                "conversations_count": record.conversations_count,
                "visits_count": record.visits_count,
                "source": record.source,
                "date": payload.date.isoformat(),
            },
        )
    )
    await db.commit()

    return {"status": "ok", "daily_result_id": record.id}
