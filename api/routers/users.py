import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.timeutil import today_local
from crm import get_crm_adapter
from db.models import (
    AuditLog,
    Bonus,
    DailyResult,
    ExcusedDay,
    MobilografVideo,
    Norm,
    Role,
    TaskModel,
    User,
)
from api.schemas import (
    CrmOperatorRow,
    TelegramStartRequest,
    TelegramStartResponse,
    UserCreate,
    UserCreateOut,
    UserCrmIdUpdate,
    UserOut,
    UserRoleUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


def _invite_link(token: str) -> str:
    username = settings.telegram_login_bot_username or "your_bot"
    return f"https://t.me/{username}?start={token}"


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/employees", response_model=list[UserOut], dependencies=[Depends(verify_bot_secret)])
async def list_employees_for_bot(db: AsyncSession = Depends(get_db)) -> list[User]:
    query = select(User).where(User.role == Role.employee.value, User.is_active == True).order_by(User.full_name)  # noqa: E712
    return list(await db.scalars(query))


@router.get("/crm-operators", response_model=list[CrmOperatorRow])
async def list_crm_operators(
    _: User = Depends(require_roles(Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[CrmOperatorRow]:
    """CRM'dagi (hozircha Uysot) bugungi qo'ng'iroq qilgan operatorlarni, har biri
    tizimdagi qaysi (Telegram orqali ulangan) foydalanuvchiga bog'langanini ko'rsatadi —
    qo'lda email yozish o'rniga, shu ro'yxatdan to'g'ridan-to'g'ri bog'lash uchun."""
    adapter = get_crm_adapter(settings.crm_type)
    if not adapter:
        return []

    counts = await adapter.get_all_daily_call_counts(today_local())
    if not counts:
        return []

    users = list(await db.scalars(select(User).where(User.crm_external_id.isnot(None))))
    user_by_external_id = {u.crm_external_id: u for u in users}

    rows = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [
        CrmOperatorRow(
            crm_external_id=external_id,
            calls_today=count,
            matched_user=UserOut.model_validate(user_by_external_id[external_id])
            if external_id in user_by_external_id
            else None,
        )
        for external_id, count in rows
    ]


@router.get("", response_model=list[UserOut])
async def list_users(
    role: str | None = None,
    include_inactive: bool = False,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    query = select(User)
    if not include_inactive:
        query = query.where(User.is_active == True)  # noqa: E712
    if role:
        roles = [r.strip() for r in role.split(",") if r.strip()]
        query = query.where(User.role.in_(roles))
    result = await db.scalars(query.order_by(User.full_name))
    return list(result)


@router.post("", response_model=UserCreateOut)
async def create_user(
    payload: UserCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> UserCreateOut:
    if payload.role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri rol")

    # HR faqat "employee" rolida foydalanuvchi yarata oladi — rop/hr/boss/dasturchi
    # darajasidagi rollarni faqat Boshliq yoki Dasturchi bera oladi (privilege escalation
    # oldini olish uchun).
    if actor.role == Role.hr.value and payload.role != Role.employee.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR faqat 'Xodim' rolida foydalanuvchi yarata oladi")

    new_crm_id = payload.crm_external_id if actor.role in {Role.boss.value, Role.dasturchi.value} else None
    if new_crm_id:
        duplicate = await db.scalar(select(User).where(User.crm_external_id == new_crm_id))
        if duplicate:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bu CRM ID allaqachon '{duplicate.full_name}' foydalanuvchisiga bog'langan",
            )

    token = secrets.token_urlsafe(16)
    user = User(
        full_name=payload.full_name,
        role=payload.role,
        team_id=payload.team_id,
        manager_id=payload.manager_id,
        invite_token=token,
        # CRM ID faqat Boshliq tomonidan belgilanishi mumkin — boshqa rol yuborsa jim
        # e'tiborsiz qoldiriladi (frontendda ham hr uchun bu maydon ko'rsatilmaydi).
        crm_external_id=new_crm_id,
    )
    db.add(user)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_created",
            target_user_id=user.id,
            before=None,
            after={"full_name": user.full_name, "role": user.role},
        )
    )
    await db.commit()
    await db.refresh(user)

    return UserCreateOut(user=UserOut.model_validate(user), invite_link=_invite_link(token))


@router.get("/by-telegram/{telegram_id}", response_model=UserOut, dependencies=[Depends(verify_bot_secret)])
async def get_user_by_telegram(telegram_id: int, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


@router.get("/{user_id}/invite-link")
async def get_invite_link(
    user_id: int,
    _: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    if user.bot_started:
        return {"invite_link": None, "already_started": True}

    if not user.invite_token:
        user.invite_token = secrets.token_urlsafe(16)
        await db.commit()

    return {"invite_link": _invite_link(user.invite_token), "already_started": False}


@router.post("/telegram-start", response_model=TelegramStartResponse, dependencies=[Depends(verify_bot_secret)])
async def telegram_start(payload: TelegramStartRequest, db: AsyncSession = Depends(get_db)) -> TelegramStartResponse:
    if payload.invite_token:
        user = await db.scalar(select(User).where(User.invite_token == payload.invite_token))
        if not user:
            return TelegramStartResponse(status="invalid_token")

        # Bitta Telegram akkaunt bir vaqtda faqat bitta foydalanuvchiga tegishli bo'lishi
        # mumkin. Agar bu akkaunt ilgari boshqa foydalanuvchiga bog'langan bo'lsa — yangi
        # havola orqali kirish "haqiqiy" hisoblanadi: eski bog'lanish avtomatik bekor
        # qilinadi (o'sha foydalanuvchi keyinroq o'ziga alohida yangi havola olishi kerak
        # bo'ladi), va akkaunt shu (yangi) foydalanuvchiga o'tkaziladi.
        conflicting = await db.scalar(
            select(User).where(User.telegram_id == payload.telegram_id, User.id != user.id)
        )
        if conflicting:
            db.add(
                AuditLog(
                    actor_id=None,
                    action="telegram_account_transferred",
                    target_user_id=conflicting.id,
                    before={"telegram_id": conflicting.telegram_id},
                    after={"telegram_id": None, "transferred_to_user_id": user.id},
                )
            )
            conflicting.telegram_id = None
            conflicting.bot_started = False
            # Eski bog'lanishni avval bazaga yozib qo'yamiz — aks holda SQLite/PostgreSQL
            # UNIQUE(telegram_id) cheklovi ikkala UPDATE bir xil tranzaksiyada noto'g'ri
            # tartibda bajarilsa xato berishi mumkin.
            await db.flush()

        user.telegram_id = payload.telegram_id
        user.bot_started = True
        user.invite_token = None
        await db.commit()
        await db.refresh(user)
        return TelegramStartResponse(status="ok", user=UserOut.model_validate(user))

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        return TelegramStartResponse(status="no_account")

    if not user.bot_started:
        user.bot_started = True
        await db.commit()
        await db.refresh(user)

    return TelegramStartResponse(status="ok", user=UserOut.model_validate(user))


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


@router.patch("/{user_id}/crm-external-id", response_model=UserOut)
async def update_crm_external_id(
    user_id: int,
    payload: UserCrmIdUpdate,
    actor: User = Depends(require_roles(Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    new_crm_id = payload.crm_external_id or None
    if new_crm_id is not None:
        duplicate = await db.scalar(
            select(User).where(User.crm_external_id == new_crm_id, User.id != user_id)
        )
        if duplicate:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bu CRM ID allaqachon '{duplicate.full_name}' foydalanuvchisiga bog'langan",
            )

    before = user.crm_external_id
    user.crm_external_id = new_crm_id

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="crm_external_id_changed",
            target_user_id=user.id,
            before={"crm_external_id": before},
            after={"crm_external_id": user.crm_external_id},
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/role", response_model=UserOut)
async def update_role(
    user_id: int,
    payload: UserRoleUpdate,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    if payload.role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri rol")

    if user_id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O'zingizning rolingizni o'zgartira olmaysiz")

    # HR faqat "employee" rolini bera oladi — rop/hr/boss/dasturchi darajasidagi rollarni
    # faqat Boshliq yoki Dasturchi bera oladi (privilege escalation oldini olish uchun).
    if actor.role == Role.hr.value and payload.role != Role.employee.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HR faqat 'Xodim' rolini bera oladi")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    before = user.role
    user.role = payload.role

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_role_changed",
            target_user_id=user.id,
            before={"role": before},
            after={"role": user.role},
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    if user_id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O'zingizni o'chira olmaysiz")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    user.is_active = False

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_deactivated",
            target_user_id=user.id,
            before={"is_active": True},
            after={"is_active": False},
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/activate", response_model=UserOut)
async def activate_user(
    user_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    user.is_active = True

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_activated",
            target_user_id=user.id,
            before={"is_active": False},
            after={"is_active": True},
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-account", response_model=UserCreateOut)
async def reset_account(
    user_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> UserCreateOut:
    """Foydalanuvchining eski Telegram bog'lanishini bekor qiladi va yangi bot-havola
    yaratadi — masalan xodim telefon/Telegram akkauntini almashtirganda ishlatiladi."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    before_telegram_id = user.telegram_id
    token = secrets.token_urlsafe(16)
    user.telegram_id = None
    user.bot_started = False
    user.invite_token = token

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_account_reset",
            target_user_id=user.id,
            before={"telegram_id": before_telegram_id},
            after={"telegram_id": None},
        )
    )
    await db.commit()
    await db.refresh(user)

    return UserCreateOut(user=UserOut.model_validate(user), invite_link=_invite_link(token))


async def _has_dependent_records(db: AsyncSession, user_id: int) -> bool:
    checks = [
        select(TaskModel.id).where((TaskModel.assigned_to == user_id) | (TaskModel.assigned_by == user_id)),
        select(Norm.id).where((Norm.user_id == user_id) | (Norm.changed_by == user_id)),
        select(DailyResult.id).where(DailyResult.user_id == user_id),
        select(MobilografVideo.id).where(
            (MobilografVideo.user_id == user_id) | (MobilografVideo.confirmed_by == user_id)
        ),
        select(ExcusedDay.id).where((ExcusedDay.user_id == user_id) | (ExcusedDay.decided_by == user_id)),
        select(Bonus.id).where(Bonus.user_id == user_id),
        select(AuditLog.id).where((AuditLog.actor_id == user_id) | (AuditLog.target_user_id == user_id)),
    ]
    for query in checks:
        if await db.scalar(query.limit(1)) is not None:
            return True
    return False


async def _force_delete_dependent_records(db: AsyncSession, user_id: int) -> None:
    """Dasturchi uchun: foydalanuvchini o'chirishdan oldin unga bog'liq BARCHA yozuvlarni
    tozalaydi (norma, vazifa, kunlik natija, mobilograf, sababli kun, bonus) — shu tufayli
    Dasturchi biror xodimga norma belgilangan yoki topshiriq berilganidan qat'i nazar uni
    to'liq o'chira oladi. Audit jurnali (AuditLog) esa o'chirilmaydi — faqat shu
    foydalanuvchiga bo'lgan bog'lanish uzatiladi (NULL), chunki audit tarixi doimiy
    saqlanishi kerak."""
    await db.execute(update(AuditLog).where(AuditLog.actor_id == user_id).values(actor_id=None))
    await db.execute(update(AuditLog).where(AuditLog.target_user_id == user_id).values(target_user_id=None))

    await db.execute(delete(TaskModel).where((TaskModel.assigned_to == user_id) | (TaskModel.assigned_by == user_id)))
    await db.execute(delete(Norm).where((Norm.user_id == user_id) | (Norm.changed_by == user_id)))
    await db.execute(delete(DailyResult).where(DailyResult.user_id == user_id))
    await db.execute(
        delete(MobilografVideo).where(
            (MobilografVideo.user_id == user_id) | (MobilografVideo.confirmed_by == user_id)
        )
    )
    await db.execute(delete(ExcusedDay).where((ExcusedDay.user_id == user_id) | (ExcusedDay.decided_by == user_id)))
    await db.execute(delete(Bonus).where(Bonus.user_id == user_id))


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    actor: User = Depends(require_roles(Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Foydalanuvchini bazadan butunlay o'chiradi.

    Boshliq uchun: faqat hech qanday tarixiy ma'lumot (vazifa, norma, kunlik natija va
    h.k.) yo'q bo'lsa ishlaydi — aks holda o'chirish o'sha ma'lumotlarni yetim (orphan)
    qoldirar edi. Bunday hollarda "O'chirish" (faolsizlantirish) tugmasidan foydalaning.

    Dasturchi uchun: yuqoridagi tekshiruv o'tkazib yuboriladi — norma belgilangan yoki
    vazifa berilgan bo'lsa ham, foydalanuvchi va unga bog'liq barcha yozuvlar (audit
    jurnalidan tashqari) to'liq o'chiriladi."""
    if user_id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O'zingizni o'chira olmaysiz")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    is_dasturchi = actor.role == Role.dasturchi.value
    if not is_dasturchi and await _has_dependent_records(db, user_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu foydalanuvchida tarixiy ma'lumotlar bor (vazifa, norma va h.k.), shuning "
            "uchun butunlay o'chirib bo'lmaydi. Buning o'rniga 'O'chirish' (faolsizlantirish) "
            "tugmasidan foydalaning.",
        )

    if is_dasturchi:
        await _force_delete_dependent_records(db, user_id)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user_force_deleted" if is_dasturchi else "user_deleted",
            target_user_id=None,
            before={"id": user.id, "full_name": user.full_name, "role": user.role},
            after=None,
        )
    )
    await db.delete(user)
    await db.commit()
    return {"deleted": True}
