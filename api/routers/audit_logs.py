from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.schemas import AuditLogOut
from db.models import AuditLog, Role, User

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


async def _serialize_logs(db: AsyncSession, logs: list[AuditLog]) -> list[AuditLogOut]:
    """actor/target ismlarini bitta so'rovda yuklab, AuditLogOut ro'yxatiga o'giradi."""
    user_ids = {log.actor_id for log in logs if log.actor_id} | {
        log.target_user_id for log in logs if log.target_user_id
    }
    users = {}
    if user_ids:
        result = await db.scalars(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u.full_name for u in result}

    return [
        AuditLogOut(
            id=log.id,
            actor_id=log.actor_id,
            actor_name=users.get(log.actor_id) if log.actor_id else None,
            action=log.action,
            target_user_id=log.target_user_id,
            target_name=users.get(log.target_user_id) if log.target_user_id else None,
            before=log.before,
            after=log.after,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    action: str | None = None,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogOut]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if target_user_id:
        query = query.where(AuditLog.target_user_id == target_user_id)
    if date_from:
        query = query.where(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.where(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))

    logs = list(await db.scalars(query))
    return await _serialize_logs(db, logs)


@router.get(
    "/for-bot/{telegram_id}", response_model=list[AuditLogOut], dependencies=[Depends(verify_bot_secret)]
)
async def list_audit_logs_for_bot(
    telegram_id: int, limit: int = 15, db: AsyncSession = Depends(get_db)
) -> list[AuditLogOut]:
    """Bot "🧾 Audit jurnali" tugmasi uchun oxirgi yozuvlar — faqat
    Boshliq/Dasturchi (botda ixcham ko'rinish, to'liq filtrlar saytda)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in {Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    limit = min(max(limit, 1), 50)
    logs = list(await db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)))
    return await _serialize_logs(db, logs)
