from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.schemas import BonusMyOut, BonusOut
from api.services.bonus import calculate_bonus
from api.telegram_notify import send_message
from api.timeutil import today_local
from db.models import AuditLog, Bonus, Role, User

router = APIRouter(prefix="/bonuses", tags=["bonuses"])


class CalculateMonthlyRequest(BaseModel):
    period: str | None = None  # "YYYY-MM"; berilmasa joriy oy ishlatiladi


@router.post("/calculate-monthly", dependencies=[Depends(verify_bot_secret)])
async def calculate_monthly(payload: CalculateMonthlyRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan har oy oxirida chaqiriladi — barcha faol xodimlar uchun
    bonusni hisoblab, natijani saqlaydi va botga push-xabar yuboradi (summasiz)."""
    period = payload.period or today_local().strftime("%Y-%m")

    employees = list(
        await db.scalars(select(User).where(User.role == Role.employee.value, User.is_active == True))  # noqa: E712
    )

    calculated = 0
    for emp in employees:
        result = await calculate_bonus(db, emp, period)
        before_amount = None

        existing = await db.scalar(select(Bonus).where(Bonus.user_id == emp.id, Bonus.period == period))
        if existing:
            before_amount = float(existing.amount)
            existing.amount = result["amount"]
            existing.breakdown = result["breakdown"]
            existing.calculated_at = datetime.utcnow()
        else:
            db.add(
                Bonus(
                    user_id=emp.id,
                    period=period,
                    amount=result["amount"],
                    breakdown=result["breakdown"],
                )
            )

        db.add(
            AuditLog(
                actor_id=None,  # scheduler/tizim tomonidan avtomatik hisoblanadi
                action="bonus_calculated",
                target_user_id=emp.id,
                before={"amount": before_amount},
                after={"amount": result["amount"], "period": period},
            )
        )
        await db.commit()
        calculated += 1

        if emp.telegram_id:
            await send_message(
                emp.telegram_id,
                f"💰 Bonusingiz ({period}) hisoblandi. Tafsilot uchun saytga kiring.",
            )

    return {"period": period, "calculated": calculated}


@router.get("", response_model=list[BonusOut])
async def list_bonuses(
    user_id: int,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> list[Bonus]:
    query = select(Bonus).where(Bonus.user_id == user_id).order_by(Bonus.period.desc())
    return list(await db.scalars(query))


@router.get("/my/{telegram_id}", response_model=BonusMyOut, dependencies=[Depends(verify_bot_secret)])
async def my_latest_bonus(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BonusMyOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    latest = await db.scalar(
        select(Bonus).where(Bonus.user_id == user.id).order_by(Bonus.period.desc()).limit(1)
    )
    if not latest:
        return BonusMyOut(calculated=False)

    return BonusMyOut(calculated=True, period=latest.period, calculated_at=latest.calculated_at)
