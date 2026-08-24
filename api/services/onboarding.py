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
    TaskModel,
    TaskStatus,
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

    #  ⚠️ HAR QADAM VAZIFA YARATADI (TZ 3.2 / S-46): bildirishnoma,
    #  muddat va «bajardim» tugmasi TAYYOR keladi — onboarding uchun
    #  alohida xabar mexanizmi qurilmaydi.
    await _create_task(db, band, user, actor_id)

    #  ⚠️ INSTRUKTAJ QADAMI (TZ 3.6 / S-49): yangi xodimga KIRISH
    #  instruktaji aynan onboardingdan tushadi. Shablon qadamida
    #  `ref_id` — mavjud instruktaj yozuvi; undan xodimdan
    #  tanishish SO'RALADI (S-20 mexanizmi). Yangi instruktaj
    #  yozuvi YARATILMAYDI: u HR o'tkazgan real voqea va uni kod
    #  o'ylab topmasligi kerak.
    if step.kind == OnboardingStepKind.briefing.value and step.ref_id:
        try:
            from api.services import acknowledgements as ack
            from api.services import briefings as bsvc

            await ack.request_ack(
                db,
                object_type=bsvc.ACK_TYPE,
                object_id=step.ref_id,
                version=bsvc.ACK_VERSION,
                user_ids=[user.id],
                title=f"Instruktaj — {band.title}",
                link="/me/briefings",
                requested_by=actor_id,
            )
            band.ref_id = step.ref_id
            await db.flush()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Onboarding qadami instruktajga ulanmadi (plan=%s, briefing=%s)",
                band.plan_id,
                step.ref_id,
            )
        return

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
    if band.kind == OnboardingStepKind.briefing.value and band.ref_id:
        #  ⚠️ Holat `acknowledgements` da — onboarding uni NUSXA
        #  qilmaydi (S-45 qoidasi). Xodim botda «Tanishdim» bossa
        #  onboarding qadami ham o'zi bajarilgan bo'ladi.
        from api.services import briefings as bsvc
        from db.models import Acknowledgement

        iz = await db.scalar(
            select(Acknowledgement.acknowledged_at).where(
                Acknowledgement.user_id == plan.user_id,
                Acknowledgement.object_type == bsvc.ACK_TYPE,
                Acknowledgement.object_id == band.ref_id,
            ).limit(1)
        )
        return iz is not None

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


async def progress_with_next(db: AsyncSession, plan: OnboardingPlan) -> dict:
    """`progress` + yakunlangandan keyin ochiladigan bosqich."""
    holat = await progress(db, plan)
    holat["next_stage"] = await next_stage(db, plan)
    return holat


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
    #  Bog'langan vazifa ham yopiladi (ikki tomonlama sinxron).
    await close_task_for(db, band)
    return band


async def finish_if_complete(db: AsyncSession, plan: OnboardingPlan) -> bool:
    """Barcha qadam bajarilgan bo'lsa rejani yakunlaydi (TZ 3.2 / S-47).

    ⚠️ YAKUNLANGANDA KEYINGI BOSQICH OCHILADI — sinov muddati
    baholashi. Muddatning O'ZI bu yerda YARATILMAYDI: u
    `deadlines` modulida `hire_date + probation_days` bo'yicha
    ALLAQACHON hisoblanadi (S-12). Ikkinchi joyda yaratsak bitta
    xodimda ikkita sinov muddati paydo bo'lardi. Bu yerda faqat
    HR ga xabar beriladi — ya'ni «ochilish» ko'rinadigan bo'ladi.

    Qaytaradi: SHU CHAQIRUVDA yakunlandimi (idempotent — allaqachon
    yakunlangan reja uchun `False`, aks holda HR ga har safar
    takroriy xabar ketardi)."""
    if plan.status != OnboardingStatus.active.value:
        return False
    holat = await progress(db, plan)
    if holat["total"] == 0 or holat["done"] < holat["total"]:
        return False
    plan.status = OnboardingStatus.done.value
    plan.finished_at = datetime.utcnow()
    await db.flush()
    await _notify_finished(db, plan)
    return True


async def _notify_finished(db: AsyncSession, plan: OnboardingPlan) -> None:
    """HR ga «onboarding tugadi» xabari.

    ⚠️ Xabar yiqilsa REJA YAKUNLANGAN bo'lib qolaveradi — holat
    xabardan muhimroq. Shuning uchun butun blok qo'riqlangan."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        from api.notify import notify_user
        from api.services.push import Category

        xodim = await db.get(User, plan.user_id)
        if xodim is None:
            return
        hrlar = list(
            await db.scalars(
                select(User).where(
                    User.role.in_((Role.hr.value, Role.boss.value)),
                    User.is_active.is_(True),
                    User.telegram_id.isnot(None),
                )
            )
        )
        matn = (
            f"✅ <b>Onboarding tugadi</b> — {xodim.full_name}\n\n"
            f"«{plan.template_name or 'Reja'}» bo'yicha barcha qadam "
            "bajarildi.\n"
            "Keyingi bosqich — <b>sinov muddati baholashi</b> "
            "(«Muddatlar» bo'limida ko'rinadi)."
        )
        for hr in hrlar:
            await notify_user(db, hr, Category.APPROVALS, matn,
                              data={"path": "/onboarding"})
    except Exception:  # noqa: BLE001
        logger.exception("Onboarding yakuni haqida xabar berib bo'lmadi")


async def next_stage(db: AsyncSession, plan: OnboardingPlan) -> dict | None:
    """Reja tugagach ochiladigan bosqich — sinov muddati.

    ⚠️ Sana `deadlines` modulining O'Z hisobidan olinadi
    (`hire_date + probation_days`), bu yerda qayta hisoblanmaydi —
    ikkita manba bo'lmasin."""
    if plan.status != OnboardingStatus.done.value:
        return None
    xodim = await db.get(User, plan.user_id)
    if xodim is None or not xodim.hire_date:
        return None
    from datetime import timedelta as _td

    from api.services import deadlines as dsvc

    cfg = await dsvc.get_config(db)
    return {
        "kind": "probation",
        "label": "Sinov muddati baholashi",
        "due_date": xodim.hire_date + _td(days=cfg.probation_days),
    }


# ─────────────────────────────────────────────────────────────
# VAZIFALARGA ULANISH (yangi TZ 3.2 / S-46)
# ─────────────────────────────────────────────────────────────

#  ⚠️ `tasks.source` shu qiymat bilan belgilanadi va aynan shu
#  qiymat STATISTIKADAN chiqarib tashlanadi
#  (`db.models.TASK_STATS_EXCLUDED_SOURCES`).
TASK_SOURCE = "onboarding"


async def _create_task(
    db: AsyncSession,
    band: OnboardingProgress,
    user: User,
    actor_id: int | None,
) -> TaskModel:
    """Qadam uchun vazifa yozuvi.

    ⚠️ KIMGA: mas'ul belgilangan bo'lsa MAS'ULGA, aks holda
    XODIMNING O'ZIGA. Ba'zi qadamlar («ish joyini tayyorlash»,
    «kirish huquqlarini ochish») xodimning emas, HR yoki IT ning
    ishi — ularni xodimga berish uni bajara olmaydigan ish bilan
    yuklardi.

    ⚠️ `source="onboarding"` — VAZIFA STATISTIKASIGA KIRMASIN
    (TZ 3.2). Batafsil izoh `db/models.py::TaskModel.source` da.

    ⚠️ Muddat — kun OXIRI. `due_date` sana, `deadline` esa vaqt;
    kun boshi qo'yilsa vazifa o'sha kuni ertalabdanoq «muddati
    o'tgan» bo'lib ko'rinardi."""
    from datetime import time as _time

    kimga = band.owner_user_id or user.id
    muddat = (
        datetime.combine(band.due_date, _time(23, 59))
        if band.due_date
        else None
    )
    task = TaskModel(
        assigned_by=actor_id or kimga,
        assigned_to=kimga,
        title=band.title[:500],
        description=band.description,
        deadline=muddat,
        status=TaskStatus.pending.value,
        source=TASK_SOURCE,
        source_id=band.id,
    )
    db.add(task)
    await db.flush()
    return task


async def task_completed(db: AsyncSession, task: TaskModel) -> bool:
    """Onboarding vazifasi bajarildi -> QADAM ham bajarilgan.

    ⚠️ IKKI TOMONLAMA SINXRON. Xodim vazifani botda «✅» qilsa,
    kabinetdagi «Birinchi kunlarim» ro'yxatida ham belgilanishi
    kerak — aks holda u bir joyda bajarilgan, boshqasida
    bajarilmagan bo'lib turardi.

    ⚠️ HOKIMIYAT QADAMDA. Vazifa — KO'ZGU (bildirishnoma va tugma
    uchun); haqiqat `OnboardingProgress.done_at` da. Shuning uchun
    sinxron shu yo'nalishda yoziladi, teskarisi emas.

    Qaytaradi: qadam belgilandimi."""
    if task.source != TASK_SOURCE or not task.source_id:
        return False
    band = await db.get(OnboardingProgress, task.source_id)
    if band is None or band.done_at is not None:
        return False
    band.done_at = task.completed_at or datetime.utcnow()
    band.done_by = task.assigned_to
    await db.flush()
    plan = await db.get(OnboardingPlan, band.plan_id)
    if plan is not None:
        await finish_if_complete(db, plan)
    return True


async def close_task_for(db: AsyncSession, band: OnboardingProgress) -> bool:
    """Qadam bajarilgach BOG'LANGAN vazifani ham yopadi.

    ⚠️ Teskari yo'nalish: xodim kabinetdagi chekboxni belgilasa,
    botdagi vazifa ochiq qolmasligi kerak — aks holda unga
    muddat eslatmasi kelaverardi."""
    task = await db.scalar(
        select(TaskModel).where(
            TaskModel.source == TASK_SOURCE,
            TaskModel.source_id == band.id,
            TaskModel.status != TaskStatus.done.value,
        )
    )
    if task is None:
        return False
    task.status = TaskStatus.done.value
    task.completed_at = band.done_at or datetime.utcnow()
    await db.flush()
    return True
