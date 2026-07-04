import hmac
import logging
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, is_within_rop_scope, require_roles, verify_bot_secret
from api.timeutil import today_local
from api.schemas import (
    CRMWebhookPayload,
    DailyResultManualCreate,
    DailyResultOut,
    DailyResultTodayOut,
)
from crm import get_crm_adapter
from db.models import AuditLog, DailyResult, DailyResultSource, Norm, Role, User
from db.upsert import upsert

logger = logging.getLogger(__name__)

router = APIRouter(tags=["daily-results"])


async def _current_norm(db: AsyncSession, user_id: int, metric_type: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric_type)
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


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
    if not is_within_rop_scope(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning jamoangizga tegishli emas")

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
    if not is_within_rop_scope(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning jamoangizga tegishli emas")

    query = (
        select(DailyResult)
        .where(DailyResult.user_id == user_id)
        .order_by(DailyResult.date.desc())
        .limit(60)
    )
    return list(await db.scalars(query))


@router.get(
    "/daily-results/today/{telegram_id}",
    response_model=DailyResultTodayOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def today_daily_result(telegram_id: int, db: AsyncSession = Depends(get_db)) -> DailyResultTodayOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    from api.routers.stats import today_metric_rows

    today = today_local()
    result = await db.scalar(select(DailyResult).where(DailyResult.user_id == user.id, DailyResult.date == today))

    return DailyResultTodayOut(
        conversations_count=result.conversations_count if result else 0,
        visits_count=result.visits_count if result else 0,
        suhbat_norm=await _current_norm(db, user.id, "suhbat"),
        tashrif_norm=await _current_norm(db, user.id, "tashrif"),
        # Lavozimga moslashgan ro'yxat — bot endi shu ro'yxatni ko'rsatadi
        metrics=await today_metric_rows(db, user),
    )


@router.post("/daily-results/sync", dependencies=[Depends(verify_bot_secret)])
async def sync_daily_results(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan soatlik chaqiriladi (webhook mavjud bo'lmagan holat uchun zaxira).
    CRM_TYPE=none bo'lsa hech narsa qilmaydi (qo'lda kiritish yetarli)."""
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
    for emp in employees:
        data = await adapter.get_daily_results(emp, today)
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

        await _upsert_daily_result(
            db, emp.id, today, data["conversations"], data["visits"], DailyResultSource.crm.value
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
