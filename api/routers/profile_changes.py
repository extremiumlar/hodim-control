"""Xodim o'z ma'lumotini yangilashi (yangi TZ 3.26 / S-26).

⚠️ TO'G'RIDAN-TO'G'RI O'ZGARTIRISH YO'Q (TZ qabul mezoni). Telefon va
manzil kadr hujjatlariga tushadi; xodim ularni o'zi o'zgartira olsa,
hujjatdagi va bazadagi ma'lumot bir-biriga mos kelmay qoladi va buni
hech kim payqamaydi. HR tasdig'i — nomuvofiqlikni to'sadigan yagona
nuqta.

⚠️ OQ RO'YXAT SERVERDA. Ro'yxatdan tashqari maydon so'rovi rad etiladi:
aks holda xodim `role` yoki `is_active` ni «so'rab» yuborishi mumkin
bo'lardi va HR e'tiborsiz tasdiqlab qo'yishi mumkin edi.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from db.models import (
    PROFILE_FIELD_LABELS,
    PROFILE_FIELDS_SENSITIVE,
    AuditLog,
    ProfileChangeRequest,
    ProfileChangeStatus,
    Role,
    User,
)

router = APIRouter(prefix="/profile-changes", tags=["profile-changes"])

#  Tasdiqlash — kadr ishi. ROP ataylab chetda (shaxsiy ma'lumot).
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class ChangeOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    field: str
    field_label: str
    old_value: str | None
    new_value: str
    status: str
    #  HR ga tasdiqlashdan oldin ogohlantirish kerakmi (F.I.Sh. kabi
    #  hujjatga ta'sir qiladigan maydon).
    sensitive: bool
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class ChangeIn(BaseModel):
    field: str
    new_value: str = Field(min_length=1, max_length=300)


class DecideIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class MyProfileOut(BaseModel):
    """Xodim o'zgartira oladigan maydonlarning JORIY qiymati."""

    full_name: str
    phone: str | None
    address: str | None
    marital_status: str | None
    emergency_contact: str | None
    #  Kutilayotgan so'rovlar — xodim ikkinchi marta yubormasin.
    pending_fields: list[str]


def _out(r: ProfileChangeRequest, ismlar: dict[int, str]) -> ChangeOut:
    return ChangeOut(
        id=r.id,
        user_id=r.user_id,
        user_name=ismlar.get(r.user_id, "—"),
        field=r.field,
        field_label=PROFILE_FIELD_LABELS.get(r.field, r.field),
        old_value=r.old_value,
        new_value=r.new_value,
        status=r.status,
        sensitive=r.field in PROFILE_FIELDS_SENSITIVE,
        decision_note=r.decision_note,
        created_at=r.created_at,
        decided_at=r.decided_at,
    )


@router.get("/fields")
async def fields(_user: User = Depends(get_current_user)) -> list[dict]:
    """O'zgartirish so'ralishi mumkin bo'lgan maydonlar.

    Mijoz shu ro'yxatdan forma quradi — oq ro'yxat ikki joyda
    yozilmasin."""
    return [
        {"value": k, "label": v, "sensitive": k in PROFILE_FIELDS_SENSITIVE}
        for k, v in PROFILE_FIELD_LABELS.items()
    ]


@router.get("/me/profile", response_model=MyProfileOut)
async def my_profile(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MyProfileOut:
    kutilyapti = [
        r
        for r in await db.scalars(
            select(ProfileChangeRequest.field).where(
                ProfileChangeRequest.user_id == user.id,
                ProfileChangeRequest.status == ProfileChangeStatus.pending.value,
            )
        )
    ]
    return MyProfileOut(
        full_name=user.full_name,
        phone=user.phone,
        address=user.address,
        marital_status=user.marital_status,
        emergency_contact=user.emergency_contact,
        pending_fields=kutilyapti,
    )


@router.get("/me", response_model=list[ChangeOut])
async def my_requests(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ChangeOut]:
    rows = list(
        await db.scalars(
            select(ProfileChangeRequest)
            .where(ProfileChangeRequest.user_id == user.id)
            .order_by(ProfileChangeRequest.created_at.desc())
        )
    )
    return [_out(r, {user.id: user.full_name}) for r in rows]


@router.post("/me", response_model=ChangeOut, status_code=status.HTTP_201_CREATED)
async def request_change(
    payload: ChangeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangeOut:
    """So'rov yuborish. Baza SHU YERDA o'zgarmaydi — HR tasdig'idan
    keyin o'zgaradi."""
    if payload.field not in PROFILE_FIELD_LABELS:
        #  ⚠️ Oq ro'yxatdan tashqari maydon (TZ qabul mezoni).
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"«{payload.field}» maydonini o'zgartirish so'rovi qabul qilinmaydi. "
            "Mumkin: " + ", ".join(PROFILE_FIELD_LABELS.values()),
        )

    yangi = payload.new_value.strip()
    hozirgi = getattr(user, payload.field, None)
    if (hozirgi or "") == yangi:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Yangi qiymat hozirgisi bilan bir xil"
        )

    #  Bir maydon bo'yicha bitta ochiq so'rov — HR ikkita qarama-qarshi
    #  so'rovni ko'rib chalkashmasin.
    bor = await db.scalar(
        select(ProfileChangeRequest).where(
            ProfileChangeRequest.user_id == user.id,
            ProfileChangeRequest.field == payload.field,
            ProfileChangeRequest.status == ProfileChangeStatus.pending.value,
        )
    )
    if bor is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"«{PROFILE_FIELD_LABELS[payload.field]}» bo'yicha so'rovingiz "
            "allaqachon ko'rib chiqilmoqda",
        )

    r = ProfileChangeRequest(
        user_id=user.id,
        field=payload.field,
        old_value=hozirgi,
        new_value=yangi,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return _out(r, {user.id: user.full_name})


@router.get("", response_model=list[ChangeOut])
async def list_requests(
    pending_only: bool = True,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[ChangeOut]:
    q = select(ProfileChangeRequest).order_by(ProfileChangeRequest.created_at.desc())
    if pending_only:
        q = q.where(ProfileChangeRequest.status == ProfileChangeStatus.pending.value)
    rows = list(await db.scalars(q))
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return [_out(r, ismlar) for r in rows]


@router.post("/{request_id}/decide", response_model=ChangeOut)
async def decide(
    request_id: int,
    payload: DecideIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> ChangeOut:
    """HR qarori. Tasdiqlansa — SHU YERDA `users` ga yoziladi.

    ⚠️ ESKI QIYMAT AUDITGA tushadi (TZ qabul mezoni): «bu odam
    telefonini qachon o'zgartirgan edi?» degan savolga javob kerak
    bo'ladi va so'rov qatori keyin o'chirilsa ham audit qoladi."""
    r = await db.get(ProfileChangeRequest, request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    if r.status != ProfileChangeStatus.pending.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu so'rov allaqachon hal qilingan"
        )

    target = await db.get(User, r.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    r.status = (
        ProfileChangeStatus.approved.value
        if payload.approve
        else ProfileChangeStatus.rejected.value
    )
    r.decided_by = actor.id
    r.decided_at = datetime.utcnow()
    r.decision_note = (payload.note or "").strip() or None

    if payload.approve:
        #  ⚠️ Eski qiymat BAZADAN qayta o'qiladi: so'rov yuborilgandan
        #  keyin HR uni qo'lda o'zgartirgan bo'lishi mumkin va auditda
        #  haqiqiy oldingi qiymat turishi kerak.
        oldingi = getattr(target, r.field, None)
        setattr(target, r.field, r.new_value)
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="profile_change_approved",
                target_user_id=target.id,
                before={r.field: oldingi},
                after={r.field: r.new_value, "request_id": r.id},
            )
        )
    else:
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="profile_change_rejected",
                target_user_id=target.id,
                before={r.field: r.old_value},
                after={"requested": r.new_value, "request_id": r.id},
            )
        )

    await db.commit()
    await db.refresh(r)

    from api.notify import notify_user
    from api.services.push import Category

    verdikt = "✅ tasdiqlandi" if payload.approve else "❌ rad etildi"
    await notify_user(
        db,
        target,
        Category.DECISIONS,
        f"{PROFILE_FIELD_LABELS.get(r.field, r.field)} o'zgartirish so'rovingiz "
        f"{verdikt}." + (f"\nIzoh: {r.decision_note}" if r.decision_note else ""),
        data={"path": "/me/profile"},
    )
    return _out(r, {target.id: target.full_name})
