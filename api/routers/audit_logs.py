from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.schemas import AuditLogOut
from db.models import AuditLog, Role, User

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    action: str | None = None,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
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
