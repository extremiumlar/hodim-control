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
from db.models import Course, CourseMaterial, CourseQuestion

#  `alive()` qo'llaydigan modellar. Yangi kurs jadvali qo'shilsa shu
#  yerga ham qo'shing — aks holda u filtrsiz o'qiladi.
_SOFT_DELETE_MODELS = (Course, CourseMaterial, CourseQuestion)


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
