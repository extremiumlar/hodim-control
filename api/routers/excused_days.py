import html
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.schemas import ExcusedDayCreate, ExcusedDayDecide, ExcusedDayOut
from api.timeutil import today_local
from api.telegram_notify import inline_keyboard, send_message
from db.models import AuditLog, ExcusedDay, ExcusedStatus, Role, User

router = APIRouter(prefix="/excused-days", tags=["excused-days"])


async def _to_out(item: ExcusedDay, db: AsyncSession) -> ExcusedDayOut:
    user = await db.get(User, item.user_id)
    return ExcusedDayOut(
        id=item.id,
        user_id=item.user_id,
        user_full_name=user.full_name if user else "?",
        date=item.date,
        reason=item.reason,
        status=item.status,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        created_at=item.created_at,
    )


async def _to_out_many(items: list[ExcusedDay], db: AsyncSession) -> list[ExcusedDayOut]:
    """`_to_out`ning ro'yxat versiyasi — har bir yozuv uchun alohida `user_id` so'rovi
    yubormaslik uchun (N+1) barcha kerakli userlarni bitta so'rovda oladi."""
    user_ids = {i.user_id for i in items}
    users = list(await db.scalars(select(User).where(User.id.in_(user_ids))))
    name_by_id = {u.id: u.full_name for u in users}
    return [
        ExcusedDayOut(
            id=i.id,
            user_id=i.user_id,
            user_full_name=name_by_id.get(i.user_id, "?"),
            date=i.date,
            reason=i.reason,
            status=i.status,
            decided_by=i.decided_by,
            decided_at=i.decided_at,
            created_at=i.created_at,
        )
        for i in items
    ]


@router.post("", response_model=ExcusedDayOut, dependencies=[Depends(verify_bot_secret)])
async def request_excused_day(payload: ExcusedDayCreate, db: AsyncSession = Depends(get_db)) -> ExcusedDayOut:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    # Sana berilmasa bugungi (Toshkent) kun olinadi — kun chegarasi bot yoki
    # serverning mahalliy vaqtiga emas, har doim backend timezone'iga bog'liq.
    item = ExcusedDay(user_id=user.id, date=payload.date or today_local(), reason=payload.reason)
    db.add(item)
    await db.commit()
    await db.refresh(item)

    hr_users = list(await db.scalars(select(User).where(User.role == Role.hr.value, User.telegram_id.isnot(None))))
    if not hr_users:
        hr_users = list(
            await db.scalars(select(User).where(User.role == Role.boss.value, User.telegram_id.isnot(None)))
        )

    text = f"🙋 <b>Sababli kun so'rovi</b>\nXodim: {user.full_name}\nSana: {item.date}\nSabab: {html.escape(item.reason)}"
    keyboard = inline_keyboard(
        [[("✅ Tasdiqlayman", f"excused_decide:{item.id}:approved"), ("❌ Rad etaman", f"excused_decide:{item.id}:rejected")]]
    )
    for hr in hr_users:
        await send_message(hr.telegram_id, text, keyboard)

    return await _to_out(item, db)


@router.get("", response_model=list[ExcusedDayOut])
async def list_excused_days(
    status_filter: str | None = None,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[ExcusedDayOut]:
    query = select(ExcusedDay).order_by(ExcusedDay.created_at.desc())
    if status_filter:
        query = query.where(ExcusedDay.status == status_filter)
    items = list(await db.scalars(query))
    return await _to_out_many(items, db)


@router.post("/{item_id}/decide", response_model=ExcusedDayOut, dependencies=[Depends(verify_bot_secret)])
async def decide_excused_day(item_id: int, payload: ExcusedDayDecide, db: AsyncSession = Depends(get_db)) -> ExcusedDayOut:
    item = await db.get(ExcusedDay, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")

    decider = await db.scalar(select(User).where(User.telegram_id == payload.decider_telegram_id))
    if not decider or decider.role not in {Role.hr.value, Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    if payload.decision not in {ExcusedStatus.approved.value, ExcusedStatus.rejected.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri qaror")

    before_status = item.status
    item.status = payload.decision
    item.decided_by = decider.id
    item.decided_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=decider.id,
            action="excused_day_decided",
            target_user_id=item.user_id,
            before={"status": before_status},
            after={"status": item.status},
        )
    )
    await db.commit()
    await db.refresh(item)

    employee = await db.get(User, item.user_id)
    if employee and employee.telegram_id:
        verdict = "✅ tasdiqlandi" if item.status == ExcusedStatus.approved.value else "❌ rad etildi"
        await send_message(
            employee.telegram_id,
            f"Sababli kun so'rovingiz ({item.date}) {verdict}.",
        )

    return await _to_out(item, db)
