import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from db.models import AuditLog, Role, User
from api.schemas import (
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


@router.get("", response_model=list[UserOut])
async def list_users(
    role: str | None = None,
    include_inactive: bool = False,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> UserCreateOut:
    if payload.role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri rol")

    token = secrets.token_urlsafe(16)
    user = User(
        full_name=payload.full_name,
        role=payload.role,
        team_id=payload.team_id,
        manager_id=payload.manager_id,
        invite_token=token,
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
    _: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
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

        conflicting = await db.scalar(
            select(User).where(User.telegram_id == payload.telegram_id, User.id != user.id)
        )
        if conflicting:
            return TelegramStartResponse(status="telegram_already_linked")

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
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    before = user.crm_external_id
    user.crm_external_id = payload.crm_external_id or None

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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> User:
    if payload.role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri rol")

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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
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
    actor: User = Depends(require_roles(Role.hr.value, Role.boss.value)),
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
