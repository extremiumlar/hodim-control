import html
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import (
    ExcusedDayCreate,
    ExcusedDayDecide,
    ExcusedDayDecideMe,
    ExcusedDayForUserBotCreate,
    ExcusedDayForUserCreate,
    ExcusedDayMeCreate,
    ExcusedDayOut,
    UserOut,
)
from api.timeutil import today_local
from api.notify import notify_user
from api.services.push import Category
from api.telegram_notify import inline_keyboard
from db.models import AuditLog, ExcusedDay, ExcusedStatus, Role, User

router = APIRouter(prefix="/excused-days", tags=["excused-days"])

# HR nomidan sababli kun BELGILAY oladigan rollar — decide_excused_day bilan bir
# xil qamrov (ROP bu yerda ham chetda: faqat hr/boss/dasturchi qaror chiqara oladi).
MANAGER_RECORD_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


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


async def _request_excused_day_for_user(
    db: AsyncSession, user: User, reason: str, day_in: date | None
) -> ExcusedDayOut:
    """Sababli kun so'rovini yaratadi va HR'ga (yo'q bo'lsa Boshliqqa) yuboradi.

    Bot ham, web ham shu yordamchidan o'tadi — dublikat nazorati va HR'ga
    xabar bir joyda qoladi, aks holda web orqali yuborilgan so'rov HR'ga
    bormay qolishi mumkin edi."""
    # Sana berilmasa bugungi (Toshkent) kun olinadi — kun chegarasi bot yoki
    # serverning mahalliy vaqtiga emas, har doim backend timezone'iga bog'liq.
    day = day_in or today_local()

    # 5.7-band: bitta xodim bitta kunga cheksiz so'rov yuborishi mumkin edi —
    # har biri BARCHA HR'larga alohida xabar (spam) va dublikat yozuv yaratardi.
    # Faqat allaqachon PENDING yoki APPROVED so'rov bo'lsa rad etiladi — REJECTED
    # bo'lgandan keyin qayta so'rash (masalan sababni tuzatib) hali ham mumkin.
    existing = await db.scalar(
        select(ExcusedDay).where(
            ExcusedDay.user_id == user.id,
            ExcusedDay.date == day,
            ExcusedDay.status.in_((ExcusedStatus.pending.value, ExcusedStatus.approved.value)),
        )
    )
    if existing is not None:
        status_uz = "tasdiqlangan" if existing.status == ExcusedStatus.approved.value else "ko'rib chiqilmoqda"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Siz {day.isoformat()} kuni uchun allaqachon so'rov yuborgansiz ({status_uz}).",
        )

    item = ExcusedDay(user_id=user.id, date=day, reason=reason)
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
        # Qaror tugmalari hozircha faqat botda (web tasdiqlash keyingi
        # bosqichda qo'shiladi) — shuning uchun Telegram majburiy.
        await notify_user(
            db, hr, Category.APPROVALS, text,
            reply_markup=keyboard, force_telegram=True,
            data={"path": "/excused-days"},
        )

    return await _to_out(item, db)


async def _record_excused_day_for_user(
    db: AsyncSession, target: User, actor: User, reason: str, day_in: date | None
) -> ExcusedDayOut:
    """HR/Boshliq/Dasturchi boshqa xodim NOMIDAN sababli kunni to'g'ridan-to'g'ri
    BELGILAYDI — `_request_excused_day_for_user`dan farqli, HR'ga xabar
    YUBORILMAYDI (o'zi kirityapti) va darhol 'approved' holatda yaratiladi:
    kirituvchi allaqachon qaror chiqarishga vakolatli, qayta tasdiq so'rash
    ortiqcha bosqich bo'lardi. Faqat 'Xodim' rolidagilarga qo'llanadi — ROP/HR/
    Boshliqning bir-birini "sababli kun"ga chiqarib qo'yishi kabi noto'g'ri
    ishlatilishning oldi olinadi."""
    if target.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faqat 'Xodim' rolidagi foydalanuvchi uchun belgilash mumkin")

    day = day_in or today_local()

    existing = await db.scalar(
        select(ExcusedDay).where(
            ExcusedDay.user_id == target.id,
            ExcusedDay.date == day,
            ExcusedDay.status.in_((ExcusedStatus.pending.value, ExcusedStatus.approved.value)),
        )
    )
    if existing is not None:
        status_uz = "tasdiqlangan" if existing.status == ExcusedStatus.approved.value else "ko'rib chiqilmoqda"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{target.full_name} uchun {day.isoformat()} kunida allaqachon yozuv bor ({status_uz}).",
        )

    item = ExcusedDay(
        user_id=target.id,
        date=day,
        reason=reason,
        status=ExcusedStatus.approved.value,
        decided_by=actor.id,
        decided_at=datetime.utcnow(),
    )
    db.add(item)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="excused_day_recorded_by_manager",
            target_user_id=target.id,
            before=None,
            after={"date": item.date.isoformat(), "reason": item.reason},
        )
    )
    await db.commit()
    await db.refresh(item)

    if target.telegram_id:
        await notify_user(
            db, target, Category.DECISIONS,
            f"🙋 Sizning nomingizdan sababli kun belgilandi: {item.date} — "
            f"{html.escape(item.reason)} (kiritdi: {actor.full_name}).",
            data={"path": "/me/excused"},
        )

    return await _to_out(item, db)


@router.get("/targets/{telegram_id}", response_model=list[UserOut], dependencies=[Depends(verify_bot_secret)])
async def excused_day_targets(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[User]:
    """Bot uchun: HR/Boshliq/Dasturchi xodim nomidan sababli kun belgilay
    oladigan nishonlar ro'yxati — ish jadvali kabi GLOBAL (norma/lavozimga
    bog'liq tor qamrov emas), chunki HR odatda kim kasal/ta'tilda ekanini
    biladi va buni ORQADAN qayd etadi."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in MANAGER_RECORD_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return list(
        await db.scalars(
            select(User)
            .where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
            .order_by(User.full_name)
        )
    )


@router.post("/for-user", response_model=ExcusedDayOut)
async def record_excused_day_for_user(
    payload: ExcusedDayForUserCreate,
    actor: User = Depends(require_roles(*MANAGER_RECORD_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ExcusedDayOut:
    """Web (JWT) versiyasi."""
    target = await db.get(User, payload.user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    return await _record_excused_day_for_user(db, target, actor, payload.reason, payload.date)


@router.post("/for-user/bot", response_model=ExcusedDayOut, dependencies=[Depends(verify_bot_secret)])
async def record_excused_day_for_user_bot(
    payload: ExcusedDayForUserBotCreate, db: AsyncSession = Depends(get_db)
) -> ExcusedDayOut:
    """Bot versiyasi — aktyor `manager_telegram_id`dan yechiladi."""
    actor = await db.scalar(select(User).where(User.telegram_id == payload.manager_telegram_id))
    if not actor or actor.role not in MANAGER_RECORD_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    target = await db.get(User, payload.target_user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    return await _record_excused_day_for_user(db, target, actor, payload.reason, payload.date)


@router.post("", response_model=ExcusedDayOut, dependencies=[Depends(verify_bot_secret)])
async def request_excused_day(payload: ExcusedDayCreate, db: AsyncSession = Depends(get_db)) -> ExcusedDayOut:
    """Bot uchun — shaxsni tanadagi `telegram_id`dan yechadi."""
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _request_excused_day_for_user(db, user, payload.reason, payload.date)


@router.post("/me", response_model=ExcusedDayOut)
async def request_my_excused_day(
    payload: ExcusedDayMeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExcusedDayOut:
    """Web (JWT) versiyasi — xodim kabineti uchun. Sxema ATAYLAB boshqa
    (`ExcusedDayMeCreate`): unda `telegram_id` YO'Q, shaxs tokendan olinadi,
    ya'ni mijoz boshqa birov nomidan so'rov yubora olmaydi."""
    return await _request_excused_day_for_user(db, user, payload.reason, payload.date)


@router.get("/me", response_model=list[ExcusedDayOut])
async def list_my_excused_days(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ExcusedDayOut]:
    """Xodimning O'Z so'rovlari (yangi birinchi). Rahbar varianti
    `GET /excused-days` — u HAMMANING so'rovlarini beradi va rol talab qiladi."""
    items = list(
        await db.scalars(
            select(ExcusedDay).where(ExcusedDay.user_id == user.id).order_by(ExcusedDay.created_at.desc()).limit(20)
        )
    )
    return await _to_out_many(items, db)


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


DECIDE_ROLES = {Role.hr.value, Role.boss.value, Role.dasturchi.value}


async def _decide_excused_day(
    db: AsyncSession, item: ExcusedDay, decider: User, decision: str, override_reason: str | None
) -> ExcusedDayOut:
    """Qaror chiqarish mantig'i — bot va web adapterlari SHU yordamchiga
    boradi (naqsh: `payroll.py: _late_status_for_user`). Ikki nusxa qolsa,
    biri tuzatilib ikkinchisi eskirardi — masalan Dasturchi override qoidasi
    faqat bir kanalda ishlab qolardi."""
    # 5.7-band: idempotentlik — allaqachon hal qilingan so'rov ODDIY yo'l bilan
    # qayta o'zgartirilmaydi (masalan eski xabardagi tugma ikkinchi marta
    # bosilsa, yoki ikki HR bir vaqtda javob bersa — "approved" bo'lgan kun
    # qayta "rejected" bo'lib qolmasin). Bosqich 3.5 QAROR: Dasturchi buni
    # majburiy sabab (`override_reason`) bilan bekor qila oladi (11.4-band).
    is_override = item.status != ExcusedStatus.pending.value
    if is_override:
        if decider.role != Role.dasturchi.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu so'rov allaqachon hal qilingan")
        if not override_reason or len(override_reason.strip()) < 5:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Allaqachon hal qilingan so'rovni qayta hal qilish uchun sabab kerak (kamida 5 belgi)",
            )

    if decision not in {ExcusedStatus.approved.value, ExcusedStatus.rejected.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri qaror")

    before_status = item.status
    item.status = decision
    item.decided_by = decider.id
    item.decided_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=decider.id,
            action="excused_day_override_decided" if is_override else "excused_day_decided",
            target_user_id=item.user_id,
            before={"status": before_status},
            after={"status": item.status, "override_reason": override_reason if is_override else None},
        )
    )
    await db.commit()
    await db.refresh(item)

    employee = await db.get(User, item.user_id)
    if employee and employee.telegram_id:
        verdict = "✅ tasdiqlandi" if item.status == ExcusedStatus.approved.value else "❌ rad etildi"
        await notify_user(
            db, employee, Category.DECISIONS,
            f"Sababli kun so'rovingiz ({item.date}) {verdict}.",
            data={"path": "/me/excused"},
        )

    return await _to_out(item, db)


@router.post("/{item_id}/decide", response_model=ExcusedDayOut, dependencies=[Depends(verify_bot_secret)])
async def decide_excused_day(
    item_id: int, payload: ExcusedDayDecide, db: AsyncSession = Depends(get_db)
) -> ExcusedDayOut:
    """Bot uchun — qaror chiqaruvchi `decider_telegram_id`dan yechiladi."""
    item = await db.get(ExcusedDay, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")
    decider = await db.scalar(select(User).where(User.telegram_id == payload.decider_telegram_id))
    if not decider or decider.role not in DECIDE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return await _decide_excused_day(db, item, decider, payload.decision, payload.override_reason)


@router.post("/{item_id}/decide/me", response_model=ExcusedDayOut)
async def decide_excused_day_web(
    item_id: int,
    payload: ExcusedDayDecideMe,
    decider: User = Depends(require_roles(*DECIDE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ExcusedDayOut:
    """Web/ilova uchun — shaxs FAQAT tokendan olinadi (mijozdan qabul
    qilinmaydi). Ilgari qaror faqat botda chiqarilardi va push bosilganda
    oqim uzilib qolardi (2026-07-31 qarori)."""
    item = await db.get(ExcusedDay, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")
    return await _decide_excused_day(db, item, decider, payload.decision, payload.override_reason)
