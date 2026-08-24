"""Onboarding — «birinchi kunlar» mantiqi (yangi TZ 3.2 / S-45).

Shablon → reja → progress. Shablon lavozim yoki rol uchun; reja
yaratilganda qadamlar NUSXALANADI.

═══════════════════════════════════════════════════════════════
⚠️ IKKI QAT'IY QOIDA
═══════════════════════════════════════════════════════════════
1. QADAMLAR NUSXALANADI, HAVOLA QILINMAYDI. Shablon keyin
   tahrirlansa, YO'LDA turgan xodimning ro'yxati o'zgarmasligi
   kerak: u kecha ko'rgan qadam bugun yo'qolmasin, muddat siljib
   ketmasin. Bu loyihadagi tanish naqsh —
   `AnketaTemplate.questions` muzlatilishi va
   `Acknowledgement.title` nusxasi bilan bir xil sabab.

2. HOLAT IKKI JOYDA SAQLANMAYDI. «Kurs o'tildimi?» degan savolga
   javobni ONBOARDING emas, KURS moduli beradi
   (`CourseAssignment`); «hujjat topshirildimi?» degan savolga —
   hujjatlar moduli. Onboarding faqat BOG'LANISHNI (`ref_id`)
   saqlaydi. Aks holda xodim kursni o'tib, onboardingda hamon
   «bajarilmagan» bo'lib turardi va ikkita haqiqat paydo bo'lardi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CourseAssignment,
    CourseAssignmentStatus,
    CourseResult,
    EmployeeDocument,
    OnboardingPlan,
    OnboardingProgress,
    OnboardingStatus,
    OnboardingStep,
    OnboardingStepKind,
    OnboardingTemplate,
    Role,
    User,
)

#  Yumshoq o'chirishli jadvallar — `courses.alive` naqshi.
_SOFT_DELETE_MODELS = (OnboardingTemplate, OnboardingStep)


def alive(model) -> Select:
    """Shablon jadvallaridan o'qishning YAGONA to'g'ri yo'li.

    ⚠️ To'g'ridan-to'g'ri `select(OnboardingTemplate)` yozilsa
    o'chirilgan shablon ham qaytardi va HR uni ro'yxatda ko'rardi."""
    if model not in _SOFT_DELETE_MODELS:
        raise ValueError(f"{model} yumshoq o'chirishli jadval emas")
    return select(model).where(model.deleted_at.is_(None))


# ─────────────────────────────────────────────────────────────
# SHABLON TANLASH
# ─────────────────────────────────────────────────────────────


async def pick_template(db: AsyncSession, user: User) -> OnboardingTemplate | None:
    """Xodimga mos shablon.

    ⚠️ ANIQROQ MOSLIK USTUN: avval LAVOZIM, keyin ROL, keyin
    UMUMIY (ikkalasi ham bo'sh). Aks holda umumiy shablon
    lavozimga atalganini bosib ketardi va sotuvchi bilan
    prorabga bir xil ro'yxat berilardi."""
    nomzodlar = list(
        await db.scalars(
            alive(OnboardingTemplate).where(OnboardingTemplate.is_active.is_(True))
        )
    )
    if not nomzodlar:
        return None

    def ball(t: OnboardingTemplate) -> int:
        if user.position_id and t.position_id == user.position_id:
            return 3
        if t.role and t.role == user.role:
            return 2
        if t.position_id is None and t.role is None:
            return 1
        return 0

    baholangan = [(ball(t), -t.id, t) for t in nomzodlar]
    baholangan = [b for b in baholangan if b[0] > 0]
    if not baholangan:
        return None
    #  Bir xil ballda YANGISI (katta `id`) olinadi.
    baholangan.sort(reverse=True)
    return baholangan[0][2]


async def steps_of(db: AsyncSession, template_id: int) -> list[OnboardingStep]:
    return list(
        await db.scalars(
            alive(OnboardingStep)
            .where(OnboardingStep.template_id == template_id)
            .order_by(OnboardingStep.order_index, OnboardingStep.id)
        )
    )


# ─────────────────────────────────────────────────────────────
# REJA
# ─────────────────────────────────────────────────────────────


async def active_plan(db: AsyncSession, user_id: int) -> OnboardingPlan | None:
    return await db.scalar(
        select(OnboardingPlan).where(
            OnboardingPlan.user_id == user_id,
            OnboardingPlan.status == OnboardingStatus.active.value,
        )
    )


async def _owner_for_role(db: AsyncSession, role: str | None) -> int | None:
    """Mas'ul ROLdan aniq ODAMNI topadi.

    ⚠️ Shablonda ROL yoziladi (u uzoq yashaydi), reja yaratilganda
    esa aniq odam hisoblanadi. Shu rolda bir necha odam bo'lsa
    eng eskisi (kichik `id`) olinadi — barqaror tanlov, har safar
    boshqa odamga tushib qolmasin."""
    if not role:
        return None
    return await db.scalar(
        select(User.id)
        .where(User.role == role, User.is_active.is_(True))
        .order_by(User.id)
        .limit(1)
    )


async def create_plan(
    db: AsyncSession,
    *,
    user: User,
    template: OnboardingTemplate | None = None,
    start_date: date | None = None,
    actor_id: int | None = None,
) -> OnboardingPlan:
    """Shablondan reja yaratadi va qadamlarni NUSXALAYDI.

    ⚠️ Chaqiruvchi COMMIT qiladi — reja va uning bandlari BITTA
    tranzaksiyada bo'lishi kerak, aks holda «reja bor, lekin
    qadamlari yo'q» degan holat paydo bo'lardi.

    Xatolar `ValueError` bilan (chaqiruvchi 400 ga aylantiradi)."""
    from api.timeutil import today_local

    if await active_plan(db, user.id) is not None:
        raise ValueError("Bu xodimda allaqachon faol onboarding rejasi bor")

    tpl = template or await pick_template(db, user)
    if tpl is None:
        raise ValueError("Bu xodimga mos onboarding shabloni topilmadi")

    boshlanish = start_date or today_local()
    plan = OnboardingPlan(
        user_id=user.id,
        template_id=tpl.id,
        template_name=tpl.name,
        start_date=boshlanish,
        status=OnboardingStatus.active.value,
        created_by=actor_id,
    )
    db.add(plan)
    await db.flush()

    for step in await steps_of(db, tpl.id):
        band = OnboardingProgress(
            plan_id=plan.id,
            step_id=step.id,
            order_index=step.order_index,
            title=step.title,
            description=step.description,
            kind=step.kind,
            owner_role=step.owner_role,
            owner_user_id=await _owner_for_role(db, step.owner_role),
            #  Muddat SHU YERDA hisoblanadi: shablonda mutlaq sana
            #  bo'lishi mumkin emas (u hamma uchun umumiy).
            due_date=boshlanish + timedelta(days=step.due_offset_days or 0),
            ref_text=step.ref_text,
        )
        db.add(band)
        await db.flush()
        await _link_step(db, band, step, user, actor_id)

    return plan


async def _link_step(
    db: AsyncSession,
    band: OnboardingProgress,
    step: OnboardingStep,
    user: User,
    actor_id: int | None,
) -> None:
    """Qadam turiga qarab BOSHQA MODULGA ulaydi (TZ 3.2 qabul mezoni).

    ⚠️ Ulanish MUVAFFAQIYATSIZ bo'lsa reja YIQILMAYDI. Kurs
    o'chirilgan bo'lishi mumkin (`ref_id` eskirgan) — bunda butun
    onboarding rejasi yaratilmay qolsa, yangi xodim umuman
    ro'yxatsiz qolardi. Band oddiy vazifa bo'lib qoladi va HR
    uni qo'lda belgilaydi."""
    import logging

    logger = logging.getLogger(__name__)

    if step.kind != OnboardingStepKind.course.value or not step.ref_id:
        return
    try:
        from api.services import courses as csvc

        await csvc.assign(
            db,
            course_id=step.ref_id,
            user_ids=[user.id],
            assigned_by=actor_id,
            due_date=band.due_date,
        )
        tayinlov = await csvc.assignment_for(
            db, course_id=step.ref_id, user_id=user.id
        )
        band.ref_id = tayinlov.id if tayinlov else None
        await db.flush()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Onboarding qadami kursga ulanmadi (plan=%s, course=%s)",
            band.plan_id,
            step.ref_id,
        )


# ─────────────────────────────────────────────────────────────
# PROGRESS
# ─────────────────────────────────────────────────────────────


async def _auto_done(db: AsyncSession, plan: OnboardingPlan, band: OnboardingProgress) -> bool:
    """Band boshqa modulda BAJARILGANMI.

    ⚠️ HOLAT SHU YERDA SAQLANMAYDI — har safar manba moduldan
    so'raladi. Aks holda kurs o'tilgach onboardingda hamon
    «bajarilmagan» turardi va ikkita haqiqat paydo bo'lardi."""
    if band.kind == OnboardingStepKind.course.value and band.ref_id:
        #  ⚠️ «O'tdi» bayrog'i `CourseAssignment` da EMAS, urinish
        #  natijasida (`CourseResult.passed`). Kurs bir necha marta
        #  urinilishi mumkin, shuning uchun BIRORTA urinish o'tgan
        #  bo'lsa yetarli — `courses.retry` ham shu qoidada
        #  («o'tgan kursni qayta topshirish shart emas»).
        a = await db.get(CourseAssignment, band.ref_id)
        if a is None or a.status != CourseAssignmentStatus.finished.value:
            return False
        otdi = await db.scalar(
            select(CourseResult.id).where(
                CourseResult.assignment_id == a.id,
                CourseResult.passed.is_(True),
            ).limit(1)
        )
        return otdi is not None
    if band.kind == OnboardingStepKind.document.value and band.ref_text:
        topildi = await db.scalar(
            select(EmployeeDocument.id).where(
                EmployeeDocument.user_id == plan.user_id,
                EmployeeDocument.doc_type == band.ref_text,
                EmployeeDocument.deleted_at.is_(None),
            ).limit(1)
        )
        return topildi is not None
    return False


async def progress(db: AsyncSession, plan: OnboardingPlan) -> dict:
    """Reja holati — bandlar, bajarilgan soni, kechikkanlar."""
    from api.timeutil import today_local

    bugun = today_local()
    bandlar = list(
        await db.scalars(
            select(OnboardingProgress)
            .where(OnboardingProgress.plan_id == plan.id)
            .order_by(OnboardingProgress.order_index, OnboardingProgress.id)
        )
    )
    chiqish = []
    bajarilgan = kechikkan = 0
    for b in bandlar:
        tugadi = b.done_at is not None or await _auto_done(db, plan, b)
        kech = bool(not tugadi and b.due_date and b.due_date < bugun)
        bajarilgan += int(tugadi)
        kechikkan += int(kech)
        chiqish.append(
            {
                "id": b.id,
                "order_index": b.order_index,
                "title": b.title,
                "description": b.description,
                "kind": b.kind,
                "owner_role": b.owner_role,
                "owner_user_id": b.owner_user_id,
                "due_date": b.due_date,
                "ref_id": b.ref_id,
                "ref_text": b.ref_text,
                "done": tugadi,
                #  ⚠️ `done_at` bo'sh, lekin `done=True` bo'lishi
                #  MUMKIN — band boshqa modulda bajarilgan.
                "done_at": b.done_at,
                "overdue": kech,
                "note": b.note,
            }
        )
    jami = len(bandlar)
    return {
        "plan_id": plan.id,
        "user_id": plan.user_id,
        "template_name": plan.template_name,
        "start_date": plan.start_date,
        "status": plan.status,
        "finished_at": plan.finished_at,
        "total": jami,
        "done": bajarilgan,
        "overdue": kechikkan,
        "percent": round(bajarilgan * 100 / jami) if jami else 0,
        "items": chiqish,
    }


async def mark_done(
    db: AsyncSession,
    *,
    band: OnboardingProgress,
    actor_id: int | None,
    note: str | None = None,
) -> OnboardingProgress:
    """Qadamni QO'LDA bajarilgan deb belgilaydi.

    ⚠️ IDEMPOTENT: qayta bosilsa BIRINCHI vaqt saqlanadi —
    `Acknowledgement.mark_ack` bilan bir xil qoida."""
    if band.done_at is None:
        band.done_at = datetime.utcnow()
        band.done_by = actor_id
    if note is not None:
        band.note = note.strip() or None
    await db.flush()
    return band


async def finish_if_complete(db: AsyncSession, plan: OnboardingPlan) -> bool:
    """Barcha qadam bajarilgan bo'lsa rejani yakunlaydi (S-47 asosi).

    Qaytaradi: yakunlandimi."""
    holat = await progress(db, plan)
    if holat["total"] == 0 or holat["done"] < holat["total"]:
        return False
    plan.status = OnboardingStatus.done.value
    plan.finished_at = datetime.utcnow()
    await db.flush()
    return True
