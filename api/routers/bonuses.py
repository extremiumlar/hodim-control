from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.routers.payroll import can_view_payroll
from api.schemas import BonusMyOut, BonusOut
from api.services.bonus import calculate_bonus
from api.notify import notify_user
from api.services.push import Category
from api.timeutil import today_local
from db.models import AuditLog, Bonus, Role, User
from db.upsert import upsert

router = APIRouter(prefix="/bonuses", tags=["bonuses"])


class CalculateMonthlyRequest(BaseModel):
    period: str | None = None  # "YYYY-MM"; berilmasa joriy oy ishlatiladi


async def recalculate_period(
    db: AsyncSession,
    period: str,
    *,
    actor_id: int | None = None,
    notify: bool = True,
) -> dict:
    """Berilgan oy uchun barcha kuzatiladigan xodimlarning KPI bonusini
    qayta hisoblab saqlaydi. IDEMPOTENT (upsert) — qayta chaqirilsa dublikat
    yaratmaydi, faqat summani yangilaydi.

    QAMROV — `PAYROLL_TRACKED_ROLES` (§2.5): ilgari FAQAT `employee` roli
    hisoblanardi, payroll esa Boshliqdan tashqari hammaga payslip yasaydi.
    Ya'ni HR/ROP/Dasturchi payslip'ida bonus qatori HECH QACHON chiqmasdi.
    Lavozimida ko'rsatkich bo'lmaganlar baribir 0 oladi (`metrics_for` bo'sh),
    ya'ni qamrovni kengaytirish hech kimga ortiqcha pul bermaydi.

    `notify=False` — oylik hisobi ichidan chaqirilganda ishlatiladi: xodim
    «bonusingiz hisoblandi» xabarini oyning o'rtasida HR har «Hisoblash»
    bosganida qayta-qayta olmasin (oy oxiridagi cron esa yuboradi)."""
    tracked_roles = [r.value for r in Role if r is not Role.boss]
    employees = list(
        await db.scalars(
            select(User).where(User.role.in_(tracked_roles), User.is_active.is_(True))
        )
    )

    calculated = 0
    for emp in employees:
        result = await calculate_bonus(db, emp, period)

        existing = await db.scalar(select(Bonus).where(Bonus.user_id == emp.id, Bonus.period == period))
        before_amount = float(existing.amount) if existing else None

        calculated_at = datetime.utcnow()
        stmt = (
            upsert(Bonus)
            .values(
                user_id=emp.id,
                period=period,
                amount=result["amount"],
                breakdown=result["breakdown"],
                calculated_at=calculated_at,
            )
            .on_conflict_do_update(
                index_elements=[Bonus.user_id, Bonus.period],
                set_={"amount": result["amount"], "breakdown": result["breakdown"], "calculated_at": calculated_at},
            )
        )
        await db.execute(stmt)

        db.add(
            AuditLog(
                actor_id=actor_id,  # cron/scheduler chaqirsa None
                action="bonus_calculated",
                target_user_id=emp.id,
                before={"amount": before_amount},
                after={"amount": result["amount"], "period": period},
            )
        )
        await db.commit()
        calculated += 1

        if notify and emp.telegram_id:
            await notify_user(
                db, emp, Category.DECISIONS,
                f"💰 Bonusingiz ({period}) hisoblandi. Tafsilot uchun saytga kiring.",
                data={"path": "/me/kpi"},
            )

    return {"period": period, "calculated": calculated}


@router.post("/calculate-monthly", dependencies=[Depends(verify_bot_secret)])
async def calculate_monthly(payload: CalculateMonthlyRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan har oy oxirida chaqiriladi — barcha faol xodimlar uchun
    bonusni hisoblab, natijani saqlaydi va botga push-xabar yuboradi (summasiz)."""
    period = payload.period or today_local().strftime("%Y-%m")
    return await recalculate_period(db, period, actor_id=None, notify=True)


@router.post("/recalculate")
async def recalculate(
    payload: CalculateMonthlyRequest,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SAYTDAN (JWT bilan) KPI bonusini qayta hisoblash — §2.3.

    NEGA KERAK: `bonuses` jadvaliga yozuv yaratadigan yagona yo'l bot/cron
    edi (oyning oxirgi kuni 23:30). Oylik hisobi esa `bonuses` dan TAYYOR
    qatorni o'qiydi — ya'ni oy o'rtasida HR «Hisoblash» bossa bonus qatori
    umuman yo'q bo'lib, KPI puli jimgina 0 chiqardi.

    Xabar YUBORILMAYDI: HR buni kuniga bir necha marta bosishi mumkin,
    xodimga har safar «bonusingiz hisoblandi» borsa spam bo'lardi."""
    period = payload.period or today_local().strftime("%Y-%m")
    return await recalculate_period(db, period, actor_id=actor.id, notify=False)


@router.get("", response_model=list[BonusOut])
async def list_bonuses(
    user_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[Bonus]:
    # XAVFSIZLIK: ilgari faqat ROL tekshirilardi, EGALIK esa yo'q edi
    # (`actor` hatto `_` ga bog'langan va ishlatilmasdi) — ya'ni ROP istalgan
    # `user_id` ni berib, jumladan Boshliqning bonus summasi va breakdown'ini
    # o'qib olardi. Bonus — oylik bilan bir xil darajadagi ma'lumot,
    # shuning uchun qamrov ham `can_view_payroll` bilan bir xil.
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    if not can_view_payroll(actor, target):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bu xodimning bonus ma'lumotini ko'rish huquqingiz yo'q"
        )

    query = select(Bonus).where(Bonus.user_id == user_id).order_by(Bonus.period.desc())
    return list(await db.scalars(query))


async def _bonuses_for_user(db: AsyncSession, user: User) -> list[Bonus]:
    """Xodimning barcha bonuslari, yangi davr birinchi.

    Bot ham, web ham shu so'rovdan foydalanadi — farqi javob SHAKLIDA:
    bot faqat `BonusMyOut` (davr nomi) oladi, web esa to'liq `BonusOut`
    (summa + breakdown). So'rov ikki joyda takrorlanmasin."""
    return list(
        await db.scalars(select(Bonus).where(Bonus.user_id == user.id).order_by(Bonus.period.desc()))
    )


@router.get("/me", response_model=list[BonusOut])
async def my_bonuses_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Bonus]:
    """Web (JWT) versiyasi — xodim kabineti «Oylik KPI'm» uchun. Shaxs
    TOKENDAN olinadi (rahbar varianti `GET /bonuses?user_id=N` — u boshqa
    xodimni so'raydi va rahbar roli talab qilinadi).

    Bot summani ATAYLAB ko'rsatmaydi va "tafsilot uchun saytga kiring" deydi
    — shu sahifa aynan o'sha va'daning bajarilishi. `breakdown` ichida faqat
    XODIMNING O'Z ma'lumoti bor (o'z jamlari va stavkalar), boshqa birovniki
    emas."""
    return await _bonuses_for_user(db, user)


@router.get("/my/{telegram_id}", response_model=BonusMyOut, dependencies=[Depends(verify_bot_secret)])
async def my_latest_bonus(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BonusMyOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    latest = await db.scalar(
        select(Bonus).where(Bonus.user_id == user.id).order_by(Bonus.period.desc()).limit(1)
    )
    if not latest:
        return BonusMyOut(calculated=False)

    return BonusMyOut(calculated=True, period=latest.period, calculated_at=latest.calculated_at)
