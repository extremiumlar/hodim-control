"""Onboarding — API (yangi TZ 3.2 / S-45).

HR shablonlarni boshqaradi, rejani ochadi va qadamlarni belgilaydi.
Xodim tomoni («📋 Birinchi kunlarim») S-47 da.

⚠️ Marshrut tartibi: so'zli yo'llar `/{id}` dan OLDIN (S-28 da jonli
uchragan tuzoq — `/bot/answer` `/{inquiry_id}/answer` ga tushib
ketgan edi).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.services import onboarding as svc
from db.models import (
    OnboardingProgress,
    OnboardingStep,
    OnboardingStepKind,
    OnboardingTemplate,
    Role,
    User,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

#  Shablon va rejani BOSHQARISH — HR/Boshliq/Dasturchi.
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class StepIn(BaseModel):
    title: str
    description: str | None = None
    kind: str = OnboardingStepKind.task.value
    owner_role: str | None = None
    due_offset_days: int = 0
    ref_id: int | None = None
    ref_text: str | None = None


class TemplateIn(BaseModel):
    name: str
    position_id: int | None = None
    role: str | None = None
    is_active: bool = True
    steps: list[StepIn] = []


class PlanIn(BaseModel):
    user_id: int
    template_id: int | None = None
    start_date: date | None = None


class DoneIn(BaseModel):
    note: str | None = None


def _step_out(s: OnboardingStep) -> dict:
    return {
        "id": s.id,
        "order_index": s.order_index,
        "title": s.title,
        "description": s.description,
        "kind": s.kind,
        "owner_role": s.owner_role,
        "due_offset_days": s.due_offset_days,
        "ref_id": s.ref_id,
        "ref_text": s.ref_text,
    }


# ─────────────────────────────────────────────────────────────
# SHABLONLAR
# ─────────────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    tpls = list(
        await db.scalars(
            svc.alive(OnboardingTemplate).order_by(OnboardingTemplate.name)
        )
    )
    natija = []
    for t in tpls:
        qadamlar = await svc.steps_of(db, t.id)
        natija.append(
            {
                "id": t.id,
                "name": t.name,
                "position_id": t.position_id,
                "role": t.role,
                "is_active": t.is_active,
                "step_count": len(qadamlar),
                "steps": [_step_out(s) for s in qadamlar],
            }
        )
    return natija


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Shablon + qadamlar — BITTA tranzaksiyada.

    ⚠️ Qadamsiz shablon foydasiz: undan yaratilgan reja bo'sh
    bo'lardi va `finish_if_complete` uni darhol «tugadi» deb
    yopardi. Shuning uchun bo'sh ro'yxat rad etiladi."""
    if not payload.steps:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Kamida bitta qadam kiritilishi kerak"
        )
    turlar = {k.value for k in OnboardingStepKind}
    for s in payload.steps:
        if s.kind not in turlar:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Noma'lum qadam turi: {s.kind}"
            )

    tpl = OnboardingTemplate(
        name=payload.name.strip(),
        position_id=payload.position_id,
        role=payload.role,
        is_active=payload.is_active,
        created_by=actor.id,
    )
    db.add(tpl)
    await db.flush()
    for i, s in enumerate(payload.steps):
        db.add(
            OnboardingStep(
                template_id=tpl.id,
                order_index=i,
                title=s.title.strip(),
                description=(s.description or "").strip() or None,
                kind=s.kind,
                owner_role=s.owner_role,
                due_offset_days=s.due_offset_days,
                ref_id=s.ref_id,
                ref_text=s.ref_text,
            )
        )
    out = {"id": tpl.id, "name": tpl.name, "step_count": len(payload.steps)}
    await db.commit()
    return out


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YUMSHOQ o'chirish — undan yaratilgan REJALAR tirik qoladi."""
    from datetime import datetime

    tpl = await db.get(OnboardingTemplate, template_id)
    if tpl is None or tpl.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")
    tpl.deleted_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# REJALAR
# ─────────────────────────────────────────────────────────────


@router.get("/plans")
async def list_plans(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """HR ekrani uchun: hozir onboardingda kim bor (S-47 asosi)."""
    from db.models import OnboardingPlan, OnboardingStatus

    rejalar = list(
        await db.scalars(
            select(OnboardingPlan)
            .where(OnboardingPlan.status == OnboardingStatus.active.value)
            .order_by(OnboardingPlan.start_date)
        )
    )
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    natija = []
    for p in rejalar:
        holat = await svc.progress(db, p)
        holat["full_name"] = ismlar.get(p.user_id, "—")
        holat.pop("items", None)  # ro'yxat sahifasiga bandlar kerak emas
        natija.append(holat)
    #  Kechikkanlar TEPADA — HR aynan ularni qidiradi.
    natija.sort(key=lambda x: (-x["overdue"], x["start_date"]))
    return natija


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    tpl = None
    if payload.template_id:
        tpl = await db.get(OnboardingTemplate, payload.template_id)
        if tpl is None or tpl.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")
    try:
        plan = await svc.create_plan(
            db,
            user=user,
            template=tpl,
            start_date=payload.start_date,
            actor_id=actor.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = await svc.progress(db, plan)
    await db.commit()
    return out


@router.get("/plans/{plan_id}")
async def read_plan(
    plan_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reja tafsiloti.

    ⚠️ Xodim FAQAT O'Z rejasini ko'radi; begonasi uchun 404
    (403 EMAS — S-06 qoidasi: ketma-ket `id` larning mavjudligini
    oshkor qilmaslik)."""
    from db.models import OnboardingPlan

    plan = await db.get(OnboardingPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reja topilmadi")
    if actor.role not in _HR and plan.user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reja topilmadi")
    return await svc.progress(db, plan)


@router.post("/items/{item_id}/done")
async def mark_item_done(
    item_id: int,
    payload: DoneIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Qadamni bajarilgan deb belgilash.

    ⚠️ Xodim O'Z rejasidagi qadamni belgilay oladi (TZ 3.2: xodim
    kabinetida chekbox ro'yxati), HR esa hammasini. Begona reja —
    404."""
    from db.models import OnboardingPlan

    band = await db.get(OnboardingProgress, item_id)
    if band is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qadam topilmadi")
    plan = await db.get(OnboardingPlan, band.plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qadam topilmadi")
    if actor.role not in _HR and plan.user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qadam topilmadi")

    await svc.mark_done(db, band=band, actor_id=actor.id, note=payload.note)
    await svc.finish_if_complete(db, plan)
    out = await svc.progress(db, plan)
    await db.commit()
    return out
