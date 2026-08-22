"""O'quv paneli — mantiq (yangi TZ 3.1 / S-32).

⚠️ BU YANGI MEXANIZM EMAS. O'quv paneli ANKETA mexanizmining
kengaytmasi. Qaysi kod qayta ishlatilishi `db/models.py` dagi
«O'QUV PANELI» blokida batafsil yozilgan; qisqacha:

  • savollarni MUZLATISH — `AnketaTemplate.questions` naqshi;
  • holat BAZADA — `AnketaAssignment.current_q` naqshi (S-33);
  • ketma-ket tick va `{"handled": bool}` protokoli (S-35);
  • `.docx` dan savol ajratish — `docx_parse.parse_questions` AYNAN
    o'zi, ikkinchi ajratgich YOZILMAYDI;
  • fayl serverda saqlanmaydi — Telegram `file_id`.

═══════════════════════════════════════════════════════════════
⚠️ O'CHIRISH QOIDASI (S-32 qabul mezoni)
═══════════════════════════════════════════════════════════════
Uchala jadvalda `deleted_at` bor va BARCHA o'qish uni filtrlashi
SHART. Buni «esda tutishga» qoldirib bo'lmaydi — o'chirilgan kurs
xodimga ko'rinib qolsa, u allaqachon bekor qilingan yo'riqnomani
o'qib, noto'g'ri qoidani o'rganardi.

Shuning uchun bu modulda o'qish uchun YAGONA kirish nuqtasi bor:
`alive()`. Har bir so'rov shundan boshlanadi. Chaqiruvchi
`select(Course)` ni O'ZI yozmasin — u filtrni unutishi mumkin.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.docx_parse import parse_questions
from db.models import (
    Course,
    CourseAssignment,
    CourseAssignmentStatus,
    CourseMaterial,
    CourseQuestion,
    CourseResult,
)

#  `alive()` qo'llaydigan modellar. Yangi kurs jadvali qo'shilsa shu
#  yerga ham qo'shing — aks holda u filtrsiz o'qiladi.
_SOFT_DELETE_MODELS = (Course, CourseMaterial, CourseQuestion, CourseAssignment)


def alive(model) -> Select:
    """O'chirilmagan qatorlar uchun `select`.

    ⚠️ Kurs jadvallaridan o'qishning YAGONA to'g'ri yo'li. `select(Course)`
    ni to'g'ridan-to'g'ri yozish — filtrni unutish demakdir."""
    if model not in _SOFT_DELETE_MODELS:
        raise ValueError(
            f"{model.__name__} yumshoq o'chirishni qo'llamaydi — `alive()` kerak emas"
        )
    return select(model).where(model.deleted_at.is_(None))


async def soft_delete(db: AsyncSession, obj) -> None:
    """Yumshoq o'chirish. Qattiq `delete` ATAYLAB ishlatilmaydi:
    o'tilgan kurs natijalari (S-33) unga bog'lanadi va kurs yo'qolsa
    xodimning o'quv tarixi ham yo'qolardi."""
    if obj.deleted_at is None:
        obj.deleted_at = datetime.utcnow()
        await db.flush()


# ─────────────────────────────────────────────────────────────
# KURS
# ─────────────────────────────────────────────────────────────


async def list_courses(
    db: AsyncSession, *, published_only: bool = False
) -> list[Course]:
    q = alive(Course).order_by(Course.created_at.desc())
    if published_only:
        q = q.where(Course.is_published.is_(True))
    return list(await db.scalars(q))


async def get_course(db: AsyncSession, course_id: int) -> Course | None:
    return await db.scalar(alive(Course).where(Course.id == course_id))


async def create_course(
    db: AsyncSession,
    *,
    title: str,
    description: str | None,
    pass_percent: int,
    max_attempts: int,
    actor_id: int,
) -> Course:
    nom = (title or "").strip()
    if not nom:
        raise ValueError("Kurs nomi bo'sh")
    if not 0 <= pass_percent <= 100:
        raise ValueError("O'tish foizi 0 va 100 orasida bo'lishi kerak")
    if max_attempts < 0:
        raise ValueError("Urinishlar soni manfiy bo'la olmaydi")
    row = Course(
        title=nom[:200],
        description=(description or "").strip() or None,
        pass_percent=pass_percent,
        max_attempts=max_attempts,
        created_by=actor_id,
    )
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────────────────────────
# MATERIAL
# ─────────────────────────────────────────────────────────────


async def materials(db: AsyncSession, course_id: int) -> list[CourseMaterial]:
    return list(
        await db.scalars(
            alive(CourseMaterial)
            .where(CourseMaterial.course_id == course_id)
            .order_by(CourseMaterial.position, CourseMaterial.id)
        )
    )


async def next_position(db: AsyncSession, model, course_id: int) -> int:
    """Keyingi tartib raqami — 10 qadam bilan.

    Bo'shliq ataylab: oraga material qo'shish uchun hammasini qayta
    raqamlash shart bo'lmasin (o'rtaga qo'yish uchun 15 yozish kifoya)."""
    oxirgi = await db.scalar(
        alive(model)
        .where(model.course_id == course_id)
        .order_by(model.position.desc())
        .limit(1)
    )
    return (oxirgi.position + 10) if oxirgi is not None else 10


async def add_material(
    db: AsyncSession,
    *,
    course_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    file_id: str | None = None,
    url: str | None = None,
) -> CourseMaterial:
    from db.models import CourseMaterialKind

    if kind not in {k.value for k in CourseMaterialKind}:
        raise ValueError("Noma'lum material turi")
    nom = (title or "").strip()
    if not nom:
        raise ValueError("Material nomi bo'sh")
    #  Fayl talab qiladigan turlar uchun `file_id` SHART — aks holda
    #  material xodimga ochilganda bo'sh chiqardi.
    if kind in {CourseMaterialKind.video.value, CourseMaterialKind.document.value,
                CourseMaterialKind.photo.value} and not file_id:
        raise ValueError("Bu tur uchun fayl yuborish shart")
    if kind == CourseMaterialKind.link.value and not url:
        raise ValueError("Havola turi uchun manzil shart")
    if kind == CourseMaterialKind.text.value and not (body or "").strip():
        raise ValueError("Matn turi uchun matn shart")

    row = CourseMaterial(
        course_id=course_id,
        position=await next_position(db, CourseMaterial, course_id),
        kind=kind,
        title=nom[:200],
        body=(body or "").strip() or None,
        file_id=file_id,
        url=url,
    )
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────────────────────────
# SAVOL
# ─────────────────────────────────────────────────────────────


async def questions(db: AsyncSession, course_id: int) -> list[CourseQuestion]:
    return list(
        await db.scalars(
            alive(CourseQuestion)
            .where(CourseQuestion.course_id == course_id)
            .order_by(CourseQuestion.position, CourseQuestion.id)
        )
    )


async def add_question(
    db: AsyncSession,
    *,
    course_id: int,
    text: str,
    options: list | None = None,
    correct_index: int | None = None,
    points: int = 1,
) -> CourseQuestion:
    matn = (text or "").strip()
    if not matn:
        raise ValueError("Savol matni bo'sh")
    variantlar = [str(o).strip() for o in (options or []) if str(o).strip()]
    if variantlar and len(variantlar) < 2:
        raise ValueError("Test savolida kamida ikkita variant bo'lishi kerak")
    if variantlar:
        if correct_index is None:
            raise ValueError("Test savolida to'g'ri javob ko'rsatilishi shart")
        if not 0 <= correct_index < len(variantlar):
            raise ValueError("To'g'ri javob indeksi variantlar orasida emas")
    else:
        #  ⚠️ OCHIQ savol AVTOMAT baholanmaydi (`correct_index=None`).
        #  Mashina erkin matnni baholasa, xodim noto'g'ri sababdan
        #  kursdan yiqilardi — bu chegara ataylab.
        correct_index = None
    if points < 1:
        raise ValueError("Ball kamida 1 bo'lishi kerak")

    row = CourseQuestion(
        course_id=course_id,
        position=await next_position(db, CourseQuestion, course_id),
        text=matn,
        options=variantlar,
        correct_index=correct_index,
        points=points,
    )
    db.add(row)
    await db.flush()
    return row


async def import_questions_from_file(
    db: AsyncSession, *, course_id: int, data: bytes, filename: str
) -> dict:
    """`.docx`/`.txt` dan savollarni yuklaydi.

    ⚠️ `docx_parse.parse_questions` AYNAN anketanikini ishlatadi —
    ikkinchi ajratgich yozilmaydi (S-32 1-band). Ajratgich variantlarni
    bilmaydi, shuning uchun kelgan savollar OCHIQ javobli bo'ladi;
    HR keyin variant qo'shishi mumkin."""
    natija = parse_questions(data, filename)
    qoshildi = 0
    for q in natija.get("questions", []):
        matn = (q.get("text") or "").strip()
        if not matn:
            continue
        await add_question(db, course_id=course_id, text=matn)
        qoshildi += 1
    return {
        "added": qoshildi,
        "title": natija.get("title"),
        "fallback": natija.get("fallback", False),
    }


# ═════════════════════════════════════════════════════════════
# S-33 · TAYINLASH VA NATIJA (TZ 3.1)
#
# ⚠️ HOLAT BAZADA. `progress()` har safar bazadan o'qiydi va
# `submit_answer()` har javobdan keyin yozadi. Xotirada hech narsa
# saqlanmaydi — Passenger jarayoni har so'rovda qayta ko'tarilishi
# mumkin (anketa `current_q` naqshi).
# ═════════════════════════════════════════════════════════════


async def assign(
    db: AsyncSession,
    *,
    course_id: int,
    user_ids: list[int],
    assigned_by: int | None,
    due_date=None,
) -> dict:
    """Kursni xodimlarga tayinlaydi.

    ⚠️ BIR XODIMGA BIR KURS IKKI MARTA TAYINLANMAYDI (S-33 qabul
    mezoni). Ikki qatlam:
      1. shu yerdagi qo'riqchi — mavjudlarini JIMGINA o'tkazib
         yuboradi (HR «hammaga» tayinlab, keyin bittasini alohida
         tayinlasa, amal xato bermasin);
      2. `uq_course_assignment_active` qisman unique indeksi — kod
         qo'riqchisi unutilsa ham baza dublikatni yozmaydi.

    Qaytaradi: `{"created": n, "skipped": m}`."""
    kurs = await get_course(db, course_id)
    if kurs is None:
        raise ValueError("Kurs topilmadi")
    if not kurs.is_published:
        #  Nashr qilinmagan kurs tayinlanmaydi: xodim ochganda yarim
        #  to'ldirilgan materialni ko'rardi.
        raise ValueError("Kurs hali nashr qilinmagan")

    mavjud = {
        a.user_id
        for a in await db.scalars(
            alive(CourseAssignment).where(CourseAssignment.course_id == course_id)
        )
    }
    yaratildi = 0
    for uid in dict.fromkeys(user_ids):  # takrorlarni tashlaymiz, tartib saqlanadi
        if uid in mavjud:
            continue
        db.add(
            CourseAssignment(
                course_id=course_id,
                user_id=uid,
                assigned_by=assigned_by,
                due_date=due_date,
                status=CourseAssignmentStatus.assigned.value,
            )
        )
        yaratildi += 1
    await db.flush()
    return {"created": yaratildi, "skipped": len(set(user_ids)) - yaratildi}


async def assignment_for(
    db: AsyncSession, *, course_id: int, user_id: int
) -> CourseAssignment | None:
    return await db.scalar(
        alive(CourseAssignment).where(
            CourseAssignment.course_id == course_id,
            CourseAssignment.user_id == user_id,
        )
    )


async def my_assignments(db: AsyncSession, user_id: int) -> list[CourseAssignment]:
    return list(
        await db.scalars(
            alive(CourseAssignment)
            .where(CourseAssignment.user_id == user_id)
            .order_by(CourseAssignment.created_at.desc())
        )
    )


async def progress(db: AsyncSession, assignment: CourseAssignment) -> dict:
    """Xodim qayerda turibdi — HAR SAFAR BAZADAN.

    Materiallar tugagach savollar boshlanadi. Indekslar TIRIK
    ro'yxatga nisbatan: material o'chirilsa ro'yxat qisqaradi va
    xodim keyingi bandga suriladi (indeks id emas)."""
    mats = await materials(db, assignment.course_id)
    savollar = await questions(db, assignment.course_id)
    material_qoldi = max(0, len(mats) - assignment.current_material)
    savol_qoldi = max(0, len(savollar) - assignment.current_q)
    bosqich = (
        "material"
        if assignment.current_material < len(mats)
        else ("savol" if assignment.current_q < len(savollar) else "tugadi")
    )
    joriy = None
    if bosqich == "material":
        joriy = mats[assignment.current_material]
    elif bosqich == "savol":
        joriy = savollar[assignment.current_q]
    return {
        "stage": bosqich,
        "current": joriy,
        "material_index": assignment.current_material,
        "material_total": len(mats),
        "question_index": assignment.current_q,
        "question_total": len(savollar),
        "material_left": material_qoldi,
        "question_left": savol_qoldi,
        "attempt_no": assignment.attempt_no,
    }


async def next_material(db: AsyncSession, assignment: CourseAssignment) -> dict:
    """«Ko'rdim, keyingisi» — material bosqichini bir qadam suradi."""
    if assignment.status == CourseAssignmentStatus.finished.value:
        raise ValueError("Kurs allaqachon yakunlangan")
    mats = await materials(db, assignment.course_id)
    if assignment.current_material >= len(mats):
        raise ValueError("Materiallar allaqachon tugagan")
    if assignment.status == CourseAssignmentStatus.assigned.value:
        assignment.status = CourseAssignmentStatus.in_progress.value
        assignment.started_at = datetime.utcnow()
    assignment.current_material += 1
    await db.flush()
    return await progress(db, assignment)


async def submit_answer(
    db: AsyncSession,
    *,
    assignment: CourseAssignment,
    text: str | None = None,
    choice: int | None = None,
) -> dict:
    """Bitta savolga javob.

    ⚠️ Test savoli DARHOL baholanadi, OCHIQ savol esa `correct=None`
    bilan yoziladi — uni odam ko'radi (S-32 qarori: mashina erkin
    matnni baholasa, xodim noto'g'ri sababdan yiqilardi).

    Javob `assignment.answers` ga yoziladi (joriy urinish), yakunda
    `CourseResult.answers` ga nusxa qilinadi."""
    if assignment.status == CourseAssignmentStatus.finished.value:
        raise ValueError("Kurs allaqachon yakunlangan")
    mats = await materials(db, assignment.course_id)
    if assignment.current_material < len(mats):
        raise ValueError("Avval materiallarni ko'rib chiqing")
    savollar = await questions(db, assignment.course_id)
    if assignment.current_q >= len(savollar):
        raise ValueError("Savollar tugagan — kursni yakunlang")

    q = savollar[assignment.current_q]
    variantlar = q.options or []
    if variantlar:
        if choice is None:
            raise ValueError("Variant tanlanmagan")
        if not 0 <= choice < len(variantlar):
            raise ValueError("Variant ro'yxatda yo'q")
        togri = choice == q.correct_index
    else:
        if not (text or "").strip():
            raise ValueError("Javob bo'sh")
        togri = None  # ochiq javob — odam baholaydi

    #  ⚠️ JSON ustunni JOYIDA o'zgartirish (`.append`) SQLAlchemy
    #  tomonidan SEZILMAYDI — yangi ro'yxat tayinlaymiz, aks holda
    #  javob jimgina yo'qolardi.
    assignment.answers = list(assignment.answers or []) + [
        {
            "q": q.id,
            "question": q.text,
            "text": (text or "").strip() or None,
            "choice": choice,
            "correct": togri,
            "points": q.points,
        }
    ]
    if assignment.status == CourseAssignmentStatus.assigned.value:
        assignment.status = CourseAssignmentStatus.in_progress.value
        assignment.started_at = datetime.utcnow()
    assignment.current_q += 1
    await db.flush()
    return {"correct": togri, **await progress(db, assignment)}


async def finish(db: AsyncSession, assignment: CourseAssignment) -> CourseResult:
    """Urinishni yakunlaydi va natija qatorini yozadi.

    ⚠️ Ochiq savol bo'lsa natija `pending_review=True` bilan yopiladi
    va `passed` BO'LMAYDI — ball hali to'liq emas, odam baholamagan.
    Aks holda xodim baholanmagan javob bilan «o'tdi» bo'lib qolardi."""
    if assignment.status == CourseAssignmentStatus.finished.value:
        raise ValueError("Kurs allaqachon yakunlangan")
    savollar = await questions(db, assignment.course_id)
    if assignment.current_q < len(savollar):
        raise ValueError("Hali javob berilmagan savollar bor")

    kurs = await get_course(db, assignment.course_id)
    javoblar = list(assignment.answers or [])
    max_ball = sum(int(a.get("points") or 1) for a in javoblar)
    ball = sum(
        int(a.get("points") or 1) for a in javoblar if a.get("correct") is True
    )
    kutilmoqda = any(a.get("correct") is None for a in javoblar)
    foiz = round(ball * 100 / max_ball) if max_ball else 0
    otdi = (not kutilmoqda) and kurs is not None and foiz >= kurs.pass_percent

    natija = CourseResult(
        assignment_id=assignment.id,
        attempt_no=assignment.attempt_no,
        score=ball,
        max_score=max_ball,
        percent=foiz,
        passed=otdi,
        pending_review=kutilmoqda,
        answers=javoblar,
    )
    db.add(natija)
    assignment.status = CourseAssignmentStatus.finished.value
    assignment.finished_at = datetime.utcnow()
    await db.flush()
    return natija


async def results(db: AsyncSession, assignment_id: int) -> list[CourseResult]:
    """Urinishlar tarixi — eskisi O'CHIRILMAYDI.

    «Uch marta yiqilib, to'rtinchida o'tdi» degan ma'lumot kadr
    bo'limiga kerak, faqat oxirgi natija emas."""
    return list(
        await db.scalars(
            select(CourseResult)
            .where(CourseResult.assignment_id == assignment_id)
            .order_by(CourseResult.attempt_no)
        )
    )


async def retry(db: AsyncSession, assignment: CourseAssignment) -> CourseAssignment:
    """Yangi urinish boshlaydi.

    Materiallar QAYTA ko'rsatilmaydi (`current_material` tegilmaydi) —
    xodim ularni allaqachon ko'rgan, faqat test qayta topshiriladi.
    Javoblar tozalanadi: ular oldingi urinish natijasiga nusxa
    qilingan."""
    if assignment.status != CourseAssignmentStatus.finished.value:
        raise ValueError("Avval joriy urinishni yakunlang")
    kurs = await get_course(db, assignment.course_id)
    oldingilar = await results(db, assignment.id)
    if any(r.passed for r in oldingilar):
        raise ValueError("Kurs allaqachon o'tilgan")
    if kurs is not None and kurs.max_attempts and len(oldingilar) >= kurs.max_attempts:
        raise ValueError(f"Urinishlar tugadi ({kurs.max_attempts} ta)")

    assignment.attempt_no += 1
    assignment.current_q = 0
    assignment.answers = []
    assignment.status = CourseAssignmentStatus.in_progress.value
    assignment.finished_at = None
    await db.flush()
    return assignment
