from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, is_within_rop_scope, require_roles, verify_bot_secret
from api.schemas import NormBotUpdate, NormCreate, NormOut, TeamNormRow
from db.models import AuditLog, Norm, Role, User

router = APIRouter(prefix="/norms", tags=["norms"])

TEAM_METRICS = ["suhbat", "tashrif"]


async def _current_value(db: AsyncSession, user_id: int, metric_type: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric_type)
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


async def _create_norm(db: AsyncSession, actor: User, target_user: User, metric_type: str, value: int) -> Norm:
    before = await _current_value(db, target_user.id, metric_type)

    norm = Norm(
        user_id=target_user.id,
        metric_type=metric_type,
        value=value,
        changed_by=actor.id,
        effective_from=date.today(),
    )
    db.add(norm)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="norm_changed",
            target_user_id=target_user.id,
            before={"metric_type": metric_type, "value": before},
            after={"metric_type": metric_type, "value": value},
        )
    )
    await db.commit()
    await db.refresh(norm)
    return norm


@router.get("/team", response_model=list[TeamNormRow])
async def team_norms(
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[TeamNormRow]:
    query = select(User).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
    if actor.role == Role.rop.value:
        query = query.where(User.manager_id == actor.id)
    employees = list(await db.scalars(query.order_by(User.full_name)))
    rows = []
    for emp in employees:
        rows.append(
            TeamNormRow(
                user_id=emp.id,
                full_name=emp.full_name,
                suhbat=await _current_value(db, emp.id, "suhbat"),
                tashrif=await _current_value(db, emp.id, "tashrif"),
            )
        )
    return rows


@router.post("", response_model=NormOut)
async def create_norm(
    payload: NormCreate,
    actor: User = Depends(require_roles(Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> Norm:
    target = await db.get(User, payload.user_id)
    if not target or target.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not is_within_rop_scope(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning jamoangizga tegishli emas")

    return await _create_norm(db, actor, target, payload.metric_type, payload.value)


@router.post("/bot-update", response_model=NormOut, dependencies=[Depends(verify_bot_secret)])
async def bot_update_norm(payload: NormBotUpdate, db: AsyncSession = Depends(get_db)) -> Norm:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.changer_telegram_id))
    if not actor or actor.role not in {Role.rop.value, Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    target = await db.get(User, payload.target_user_id)
    if not target or target.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not is_within_rop_scope(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning jamoangizga tegishli emas")

    return await _create_norm(db, actor, target, payload.metric_type, payload.value)
