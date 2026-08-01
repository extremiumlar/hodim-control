from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.schemas import PositionCreate, PositionOut, PositionUpdate
from db.models import AuditLog, Position, Role, User

router = APIRouter(prefix="/positions", tags=["positions"])

# Lavozimlarni HR/Boshliq/Dasturchi yaratadi va o'zgartiradi; ROP ro'yxatni
# faqat o'qiy oladi (masalan xodimga lavozim biriktirishda).
MANAGE_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)
READ_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


@router.get("", response_model=list[PositionOut])
async def list_positions(
    include_inactive: bool = False,
    _: User = Depends(require_roles(*READ_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[Position]:
    query = select(Position).order_by(Position.name)
    if not include_inactive:
        query = query.where(Position.is_active == True)  # noqa: E712
    return list(await db.scalars(query))


@router.get("/for-bot", response_model=list[PositionOut], dependencies=[Depends(verify_bot_secret)])
async def list_positions_for_bot(db: AsyncSession = Depends(get_db)) -> list[Position]:
    """Bot ommaviy vazifa oqimida "Lavozim: X" tugmalarini qurish uchun faol
    lavozimlar ro'yxati."""
    return list(await db.scalars(select(Position).where(Position.is_active == True).order_by(Position.name)))  # noqa: E712


@router.post("", response_model=PositionOut)
async def create_position(
    payload: PositionCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Position:
    duplicate = await db.scalar(select(Position).where(Position.name == payload.name))
    if duplicate:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu nomdagi lavozim allaqachon mavjud")

    # `update_position` bilan bir xil sabab: `managed_by_roles` avtorizatsiya
    # kirish ma'lumoti. Aks holda HR shu maydon bilan YANGI lavozim yaratib,
    # keyin xodimni o'sha lavozimga o'tkazib, o'ziga huquq berardi — ya'ni
    # tahrirdagi cheklov aylanib o'tilardi.
    if payload.managed_by_roles and actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Lavozimning boshqaruv rollarini faqat Boshliq yoki Dasturchi belgilay oladi",
        )

    position = Position(
        name=payload.name,
        menu_flags=payload.menu_flags,
        metrics=payload.metrics,
        managed_by_roles=payload.managed_by_roles,
        is_active=True,
    )
    db.add(position)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="position_created",
            target_user_id=None,
            before=None,
            after={
                "id": position.id,
                "name": position.name,
                "metrics": position.metrics,
                "managed_by_roles": position.managed_by_roles,
            },
        )
    )
    await db.commit()
    await db.refresh(position)
    return position


@router.patch("/{position_id}", response_model=PositionOut)
async def update_position(
    position_id: int,
    payload: PositionUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Position:
    position = await db.get(Position, position_id)
    if not position:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")

    if payload.name is not None and payload.name != position.name:
        duplicate = await db.scalar(
            select(Position).where(Position.name == payload.name, Position.id != position_id)
        )
        if duplicate:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu nomdagi lavozim allaqachon mavjud")

    before = {
        "name": position.name,
        "menu_flags": position.menu_flags,
        "metrics": position.metrics,
        "managed_by_roles": position.managed_by_roles,
        "is_active": position.is_active,
    }

    # Faqat yuborilgan maydonlar yangilanadi (None yuborilmagan degani emas —
    # exclude_unset bilan farqlaymiz, masalan menu_flags'ni null qilish ham mumkin).
    updates = payload.model_dump(exclude_unset=True)

    # XAVFSIZLIK: `managed_by_roles` — oddiy sozlama emas, AVTORIZATSIYA
    # kirish ma'lumoti: `can_manage_norms`, `can_view_payroll`, `_can_assign`
    # va `_can_manage_existing_task` aynan shunga qaraydi. Bu endpoint esa
    # HR'ga ochiq va `model_dump`ni ko'r-ko'rona `setattr` qilardi — ya'ni HR
    # `PATCH /positions/3 {"managed_by_roles": ["hr"]}` bilan O'ZIGA o'sha
    # lavozimdagi xodimlarning normasi/vazifasi/oyligi ustidan huquq bera
    # olardi. O'z-o'ziga huquq berish — hech qachon past rolning ishi emas.
    if "managed_by_roles" in updates and actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Lavozimning boshqaruv rollarini faqat Boshliq yoki Dasturchi o'zgartira oladi",
        )

    for field, value in updates.items():
        setattr(position, field, value)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="position_updated",
            target_user_id=None,
            before=before,
            after={
                "name": position.name,
                "menu_flags": position.menu_flags,
                "metrics": position.metrics,
                "managed_by_roles": position.managed_by_roles,
                "is_active": position.is_active,
            },
        )
    )
    await db.commit()
    await db.refresh(position)
    return position
