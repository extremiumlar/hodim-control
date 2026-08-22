"""O'quv paneli — HR API (yangi TZ 3.1 / S-34).

Zanjir: kurs yaratish → material qo'shish → savol qo'shish → nashr
qilish → tayinlash.

⚠️ BU YERDA `select(Course...)` YOZILMAYDI. Kurs jadvallarini o'qish
faqat `api/services/courses.py` orqali — u `deleted_at` ni filtrlaydi
(S-32 qoidasi). Test buni majburlaydi va buzilgan joyni fayl:qator
bilan ko'rsatadi.

⚠️ Marshrut tartibi: so'zli yo'llar (`/assignable`) `/{course_id}` dan
OLDIN e'lon qilinadi — FastAPI e'lon tartibida solishtiradi (S-28 da
jonli uchragan tuzoq).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.services import courses as svc
from api.services.announcements import audience_user_ids
from db.models import (
    COURSE_MATERIAL_KIND_LABELS,
    CourseAudience,
    CourseMaterialKind,
    Role,
    User,
)

router = APIRouter(prefix="/courses", tags=["courses"])

#  O'quv paneli — HR moduli. ROP ataylab ko'rmaydi: kurs mazmuni va
#  kimning qanday ball olgani kadr ma'lumoti (kadr hujjatlari bilan
#  bir xil qamrov, TZ 3.4).
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

#  Yuklanadigan savol faylining chegarasi. `.docx` — ZIP, matn fayli
#  bir necha o'n kilobayt bo'ladi; 5 MB dan kattasi savol ro'yxati
#  emas, xato yuklangan fayl.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


class CourseOut(BaseModel):
    id: int
    title: str
    description: str | None
    pass_percent: int
    max_attempts: int
    is_published: bool
    is_mandatory: bool
    created_at: datetime
    material_count: int = 0
    question_count: int = 0
    assigned_count: int = 0


class MaterialOut(BaseModel):
    id: int
    position: int
    kind: str
    kind_label: str
    title: str
    body: str | None
    file_id: str | None
    url: str | None


class QuestionOut(BaseModel):
    id: int
    position: int
    text: str
    options: list
    correct_index: int | None
    points: int
    is_open: bool


class CourseDetailOut(BaseModel):
    course: CourseOut
    materials: list[MaterialOut]
    questions: list[QuestionOut]


class CourseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    pass_percent: int = Field(default=70, ge=0, le=100)
    max_attempts: int = Field(default=0, ge=0)
    is_mandatory: bool = False


class CoursePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    pass_percent: int | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=0)
    is_mandatory: bool | None = None


class MaterialIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    #  ⚠️ Fayl SERVERGA yuklanmaydi — bot yuborgan Telegram `file_id`
    #  keladi (kadr hujjatlari naqshi). Disk cheklangan, video esa eng
    #  og'ir fayl turi.
    file_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=512)


class QuestionIn(BaseModel):
    text: str = Field(min_length=3)
    options: list[str] = []
    correct_index: int | None = None
    points: int = Field(default=1, ge=1)


class AssignIn(BaseModel):
    audience: str = CourseAudience.all.value
    scope_ids: list | None = None
    due_date: date | None = None


def _course_out(c, *, materials=0, questions=0, assigned=0) -> CourseOut:
    return CourseOut(
        id=c.id,
        title=c.title,
        description=c.description,
        pass_percent=c.pass_percent,
        max_attempts=c.max_attempts,
        is_published=c.is_published,
        is_mandatory=c.is_mandatory,
        created_at=c.created_at,
        material_count=materials,
        question_count=questions,
        assigned_count=assigned,
    )


def _material_out(m) -> MaterialOut:
    return MaterialOut(
        id=m.id,
        position=m.position,
        kind=m.kind,
        kind_label=COURSE_MATERIAL_KIND_LABELS.get(m.kind, m.kind),
        title=m.title,
        body=m.body,
        file_id=m.file_id,
        url=m.url,
    )


def _question_out(q) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        position=q.position,
        text=q.text,
        options=q.options or [],
        correct_index=q.correct_index,
        points=q.points,
        #  Ochiq savol AVTOMAT baholanmaydi — interfeys buni ko'rsatishi
        #  kerak, aks holda HR nega ball chiqmaganini tushunmasdi.
        is_open=not (q.options or []),
    )


# ─────────────────────────────────────────────────────────────
# SO'ZLI MARSHRUTLAR — `/{course_id}` dan OLDIN
# ─────────────────────────────────────────────────────────────


@router.get("/material-kinds")
async def material_kinds(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    return [
        {"value": k.value, "label": COURSE_MATERIAL_KIND_LABELS[k.value]}
        for k in CourseMaterialKind
    ]


@router.get("/audiences")
async def audiences(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    return [
        {"value": CourseAudience.all.value, "label": "Hamma xodim"},
        {"value": CourseAudience.roles.value, "label": "Tanlangan rollar"},
        {"value": CourseAudience.positions.value, "label": "Tanlangan lavozimlar"},
        {"value": CourseAudience.users.value, "label": "Aniq xodimlar"},
    ]


@router.get("", response_model=list[CourseOut])
async def list_courses(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> list[CourseOut]:
    rows = await svc.list_courses(db)
    out = []
    for c in rows:
        out.append(
            _course_out(
                c,
                materials=len(await svc.materials(db, c.id)),
                questions=len(await svc.questions(db, c.id)),
                assigned=len(await svc.assignments_for_course(db, c.id)),
            )
        )
    return out


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CourseOut)
async def create_course(
    payload: CourseIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> CourseOut:
    try:
        c = await svc.create_course(
            db,
            title=payload.title,
            description=payload.description,
            pass_percent=payload.pass_percent,
            max_attempts=payload.max_attempts,
            is_mandatory=payload.is_mandatory,
            actor_id=actor.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = _course_out(c)
    await db.commit()
    return out


# ─────────────────────────────────────────────────────────────
# KURS (id bilan)
# ─────────────────────────────────────────────────────────────


async def _get(db: AsyncSession, course_id: int):
    c = await svc.get_course(db, course_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kurs topilmadi")
    return c


@router.get("/{course_id}", response_model=CourseDetailOut)
async def course_detail(
    course_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> CourseDetailOut:
    c = await _get(db, course_id)
    mats = await svc.materials(db, course_id)
    qs = await svc.questions(db, course_id)
    return CourseDetailOut(
        course=_course_out(
            c,
            materials=len(mats),
            questions=len(qs),
            assigned=len(await svc.assignments_for_course(db, course_id)),
        ),
        materials=[_material_out(m) for m in mats],
        questions=[_question_out(q) for q in qs],
    )


@router.put("/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: int,
    payload: CoursePatch,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> CourseOut:
    c = await _get(db, course_id)
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        await svc.update_course(db, course=c, **fields)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = _course_out(c)
    await db.commit()
    return out


@router.post("/{course_id}/publish")
async def publish_course(
    course_id: int,
    value: bool = True,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    c = await _get(db, course_id)
    try:
        await svc.publish(db, course=c, value=value)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {"ok": True, "is_published": value}


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    c = await _get(db, course_id)
    #  ⚠️ YUMSHOQ o'chirish — o'tilgan kurs natijalari unga bog'langan
    #  va qattiq o'chirilsa xodimning o'quv tarixi yo'qolardi.
    await svc.soft_delete(db, c)
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# MATERIAL
# ─────────────────────────────────────────────────────────────


@router.post("/{course_id}/materials", status_code=status.HTTP_201_CREATED)
async def add_material(
    course_id: int,
    payload: MaterialIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get(db, course_id)
    try:
        m = await svc.add_material(
            db,
            course_id=course_id,
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            file_id=payload.file_id,
            url=payload.url,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = {"id": m.id, "position": m.position}
    await db.commit()
    return out


@router.delete("/{course_id}/materials/{material_id}")
async def delete_material(
    course_id: int,
    material_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    m = await svc.get_material(db, course_id=course_id, material_id=material_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material topilmadi")
    await svc.soft_delete(db, m)
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# SAVOL
# ─────────────────────────────────────────────────────────────


@router.post("/{course_id}/questions", status_code=status.HTTP_201_CREATED)
async def add_question(
    course_id: int,
    payload: QuestionIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get(db, course_id)
    try:
        q = await svc.add_question(
            db,
            course_id=course_id,
            text=payload.text,
            options=payload.options,
            correct_index=payload.correct_index,
            points=payload.points,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = {"id": q.id, "position": q.position, "is_open": not (q.options or [])}
    await db.commit()
    return out


@router.post("/{course_id}/questions/import")
async def import_questions(
    course_id: int,
    file: UploadFile = File(...),
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """`.docx`/`.txt` dan savollarni yuklaydi.

    ⚠️ Ajratgich ANKETANIKI (`docx_parse.parse_questions`) — ikkinchi
    nusxa yozilmagan (S-32 qoidasi). U variantlarni bilmaydi, shuning
    uchun savollar OCHIQ javobli bo'lib keladi; HR keyin variant
    qo'shishi mumkin."""
    await _get(db, course_id)
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fayl bo'sh")
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Fayl juda katta ({len(data) // 1024} KB) — savol ro'yxati emasga o'xshaydi",
        )
    try:
        res = await svc.import_questions_from_file(
            db, course_id=course_id, data=data, filename=file.filename or ""
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return res


@router.delete("/{course_id}/questions/{question_id}")
async def delete_question(
    course_id: int,
    question_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = await svc.get_question(db, course_id=course_id, question_id=question_id)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Savol topilmadi")
    await svc.soft_delete(db, q)
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# TAYINLASH
# ─────────────────────────────────────────────────────────────


@router.post("/{course_id}/assign")
async def assign_course(
    course_id: int,
    payload: AssignIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kursni qamrov bo'yicha tayinlaydi.

    ⚠️ Qamrovni `announcements.audience_user_ids()` hal qiladi —
    YAGONA joyda (S-21). Uchinchi nusxa yozilsa, biri o'zgarib
    ikkinchisi eskirardi."""
    await _get(db, course_id)
    if payload.audience not in {a.value for a in CourseAudience}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum qamrov")
    if payload.audience != CourseAudience.all.value and not payload.scope_ids:
        #  Bo'sh ro'yxat «hamma» EMAS — hech kim. HR xatosini darhol
        #  bilsin, kurs jimgina hech kimga tayinlanmasin.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Qamrov tanlangan, lekin ro'yxat bo'sh — kurs hech kimga tayinlanmaydi",
        )
    kimga = await audience_user_ids(db, payload.audience, payload.scope_ids)
    try:
        res = await svc.assign(
            db,
            course_id=course_id,
            user_ids=kimga,
            assigned_by=actor.id,
            due_date=payload.due_date,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {**res, "audience_size": len(kimga)}


@router.get("/{course_id}/assignments")
async def course_assignments(
    course_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Kim tayinlangan va qay holatda."""
    await _get(db, course_id)
    rows = await svc.assignments_for_course(db, course_id)
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    natijalar = await svc.latest_results(db, [a.id for a in rows])
    out = []
    for a in rows:
        r = natijalar.get(a.id)
        out.append(
            {
                "id": a.id,
                "user_id": a.user_id,
                "user_name": ismlar.get(a.user_id),
                "status": a.status,
                "attempt_no": a.attempt_no,
                "due_date": a.due_date,
                "percent": r.percent if r else None,
                "passed": r.passed if r else None,
                "pending_review": r.pending_review if r else None,
            }
        )
    return out
