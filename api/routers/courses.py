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

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
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

#  ⚠️ BOT ENDPOINTLARI UCHUN SIR QO'RIQCHISI — MAJBURIY.
#  Bu yo'llar xodimni `telegram_id` bo'yicha topadi, ya'ni JWT yo'q.
#  Sir tekshirilmasa istalgan kishi begona `telegram_id` yuborib
#  o'sha xodimning ma'lumotini o'qiy va uning NOMIDAN amal qila
#  olardi. Router darajasida qo'yib bo'lmaydi — shu routerda JWT
#  bilan ishlaydigan yo'llar ham bor.
_BOT_SIR = [Depends(verify_bot_secret)]

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
    #  ── S-37 hisoboti (cron'da hisoblanadi) ──
    not_started: int = 0
    in_progress: int = 0
    finished: int = 0
    passed: int = 0
    failed: int = 0
    pending_review: int = 0
    overdue: int = 0
    #  Raqamlar qachon hisoblangani. `None` — hali hisoblanmagan
    #  (kurs yangi yaratilgan va cron hali ishlamagan).
    stats_at: datetime | None = None


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


def _course_out(c, *, materials=0, questions=0, assigned=0, stat=None) -> CourseOut:
    """`stat` — `course_stats` qatori (S-37). Berilsa raqamlar
    SHUNDAN olinadi; berilmasa chaqiruvchi o'zi sanagan qiymatlar."""
    out = CourseOut(
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
    if stat is not None:
        out.material_count = stat.material_count
        out.question_count = stat.question_count
        out.assigned_count = stat.assigned_count
        out.not_started = stat.not_started
        out.in_progress = stat.in_progress
        out.finished = stat.finished
        out.passed = stat.passed
        out.failed = stat.failed
        out.pending_review = stat.pending_review
        out.overdue = stat.overdue
        out.stats_at = stat.computed_at
    return out


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


@router.get("/report")
async def course_report(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> dict:
    """Umumiy hisobot — TAYYOR raqamlardan (S-37).

    ⚠️ Bu yerda hech narsa HISOBLANMAYDI: cron `course_report_tick`
    da hisoblab qo'ygan qatorlar yig'iladi. Ma'lumot bir necha daqiqa
    eskirishi mumkin — bu hisobot, real vaqt emas."""
    rows = await svc.list_courses(db)
    stats = await svc.stats_map(db)
    jami = {
        "courses": len(rows),
        "mandatory": sum(1 for c in rows if c.is_mandatory),
        "published": sum(1 for c in rows if c.is_published),
        "assigned": 0,
        "not_started": 0,
        "in_progress": 0,
        "finished": 0,
        "passed": 0,
        "failed": 0,
        "pending_review": 0,
        "overdue": 0,
    }
    eng_eski = None
    for c in rows:
        st = stats.get(c.id)
        if st is None:
            continue
        jami["assigned"] += st.assigned_count
        for k in ("not_started", "in_progress", "finished", "passed",
                  "failed", "pending_review", "overdue"):
            jami[k] += getattr(st, k)
        if eng_eski is None or st.computed_at < eng_eski:
            eng_eski = st.computed_at
    #  Majburiy kurs tugatish foizi (TZ 3.31 uchun ham kerak bo'ladi).
    majburiy_tayinlangan = sum(
        stats[c.id].assigned_count for c in rows
        if c.is_mandatory and c.id in stats
    )
    majburiy_otgan = sum(
        stats[c.id].passed for c in rows if c.is_mandatory and c.id in stats
    )
    jami["mandatory_assigned"] = majburiy_tayinlangan
    jami["mandatory_passed"] = majburiy_otgan
    jami["mandatory_percent"] = (
        round(majburiy_otgan * 100 / majburiy_tayinlangan)
        if majburiy_tayinlangan
        else None
    )
    #  Raqamlar qachonlik — HR eskirganini bilsin.
    jami["computed_at"] = eng_eski
    return jami


@router.get("", response_model=list[CourseOut])
async def list_courses(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> list[CourseOut]:
    #  ⚠️ ILGARI bu yerda N+1 bor edi: har kurs uchun material, savol
    #  va tayinlash ALOHIDA so'rov bilan sanalardi (S-34). cPanel'da
    #  konkurentlik = 1 — bitta sekin sahifa BUTUN saytni kutdiradi.
    #  Endi raqamlar cron'da hisoblanadi (S-37) va bu yerda BITTA
    #  qo'shimcha so'rov bo'ladi.
    rows = await svc.list_courses(db)
    stats = await svc.stats_map(db)
    return [_course_out(c, stat=stats.get(c.id)) for c in rows]


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


# ═════════════════════════════════════════════════════════════
# XODIM TOMONI (S-35 bot · S-36 kabinet)
#
# ⚠️ IKKALASI BITTA HOLATNI o'qiydi (S-36 qabul mezoni): quyidagi
# `_me_*` funksiyalari YAGONA mantiq, ustidan ikkita yupqa adapter —
# JWT (sayt/kabinet) va `telegram_id` (bot). Ikki nusxa yozilsa,
# xodim botda bir joyda, saytda boshqa joyda turardi.
#
# ⚠️ HOLAT FSM DA EMAS, BAZADA. Bot restart bo'lsa ham xodim qolgan
# joyidan davom etadi (S-35 qabul mezoni) — `current_material` va
# `current_q` bazada.
#
# ⚠️ Bu marshrutlar `/{course_id}` dan OLDIN e'lon qilinadi: aks holda
# «me» so'zi kurs raqami deb o'qilib 422 qaytarardi (S-28 tuzog'i).
# ═════════════════════════════════════════════════════════════


class AnswerIn(BaseModel):
    text: str | None = None
    choice: int | None = None


def _progress_out(p: dict, assignment) -> dict:
    """Xodimga ko'rsatiladigan holat. Joriy band turiga qarab
    boshqacha maydonlar qaytadi."""
    joriy = p.get("current")
    band = None
    if joriy is not None and p["stage"] == "material":
        band = {
            "id": joriy.id,
            "kind": joriy.kind,
            "kind_label": COURSE_MATERIAL_KIND_LABELS.get(joriy.kind, joriy.kind),
            "title": joriy.title,
            "body": joriy.body,
            "file_id": joriy.file_id,
            "url": joriy.url,
        }
    elif joriy is not None and p["stage"] == "savol":
        band = {
            "id": joriy.id,
            "text": joriy.text,
            "options": joriy.options or [],
            "points": joriy.points,
            #  ⚠️ To'g'ri javob XODIMGA YUBORILMAYDI — aks holda uni
            #  brauzer/bot javobidan o'qib olish mumkin bo'lardi.
            "is_open": not (joriy.options or []),
        }
    return {
        "assignment_id": assignment.id,
        "course_id": assignment.course_id,
        "status": assignment.status,
        "stage": p["stage"],
        "item": band,
        "material_index": p["material_index"],
        "material_total": p["material_total"],
        "question_index": p["question_index"],
        "question_total": p["question_total"],
        "attempt_no": p["attempt_no"],
    }


async def _my_assignment(db: AsyncSession, user: User, assignment_id: int):
    """Tayinlashni oladi va EGALIGINI tekshiradi.

    ⚠️ Begona tayinlash uchun 404 (403 emas) — id ketma-ket son, 403
    uning mavjudligini tasdiqlardi (S-06 qoidasi)."""
    from db.models import CourseAssignment

    row = await db.scalar(
        svc.alive(CourseAssignment).where(CourseAssignment.id == assignment_id)
    )
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    return row


async def _me_list(db: AsyncSession, user: User) -> list[dict]:
    """Menga tayinlangan kurslar.

    ⚠️ FAQAT o'zimniki (S-36 qabul mezoni). Nashrdan olingan kurs ham
    ko'rinadi — xodim uni boshlagan bo'lishi mumkin va yarim yo'lda
    yo'qolib qolmasin."""
    rows = await svc.my_assignments(db, user.id)
    natijalar = await svc.latest_results(db, [a.id for a in rows])
    out = []
    for a in rows:
        kurs = await svc.get_course(db, a.course_id)
        if kurs is None:
            continue  # kurs o'chirilgan
        r = natijalar.get(a.id)
        out.append(
            {
                "assignment_id": a.id,
                "course_id": kurs.id,
                "title": kurs.title,
                "description": kurs.description,
                "is_mandatory": kurs.is_mandatory,
                "pass_percent": kurs.pass_percent,
                "status": a.status,
                "attempt_no": a.attempt_no,
                "due_date": a.due_date,
                "percent": r.percent if r else None,
                "passed": r.passed if r else None,
                "pending_review": r.pending_review if r else None,
            }
        )
    return out


async def _me_progress(db: AsyncSession, user: User, assignment_id: int) -> dict:
    a = await _my_assignment(db, user, assignment_id)
    return _progress_out(await svc.progress(db, a), a)


async def _me_next_material(db: AsyncSession, user: User, assignment_id: int) -> dict:
    a = await _my_assignment(db, user, assignment_id)
    try:
        p = await svc.next_material(db, a)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    out = _progress_out(p, a)
    await db.commit()
    return out


async def _me_answer(
    db: AsyncSession, user: User, assignment_id: int, payload: AnswerIn
) -> dict:
    a = await _my_assignment(db, user, assignment_id)
    try:
        res = await svc.submit_answer(db, assignment=a, text=payload.text,
                                      choice=payload.choice)
    except ValueError as e:
        #  «Avval materiallarni ko'rib chiqing» — 409: bu holat xatosi,
        #  noto'g'ri so'rov emas (S-35 qabul mezoni: test material
        #  ko'rilmaguncha ochilmaydi).
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    togri = res.pop("correct", None)
    out = {**_progress_out(res, a), "correct": togri}
    await db.commit()
    return out


async def _me_finish(db: AsyncSession, user: User, assignment_id: int) -> dict:
    a = await _my_assignment(db, user, assignment_id)
    try:
        r = await svc.finish(db, a)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    kurs = await svc.get_course(db, a.course_id)
    out = {
        "score": r.score,
        "max_score": r.max_score,
        "percent": r.percent,
        "passed": r.passed,
        "pending_review": r.pending_review,
        "attempt_no": r.attempt_no,
        "pass_percent": kurs.pass_percent if kurs else None,
        #  Qayta urinish MUMKINmi — bot/kabinet tugmani shunga qarab
        #  ko'rsatadi. Mantiq `retry()` bilan bir xil bo'lishi uchun
        #  shu yerda hisoblanadi, mijozda emas.
        "can_retry": (
            not r.passed
            and not r.pending_review
            and (not kurs or not kurs.max_attempts
                 or r.attempt_no < kurs.max_attempts)
        ),
    }
    await db.commit()
    return out


async def _me_retry(db: AsyncSession, user: User, assignment_id: int) -> dict:
    a = await _my_assignment(db, user, assignment_id)
    try:
        await svc.retry(db, a)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    out = _progress_out(await svc.progress(db, a), a)
    await db.commit()
    return out


# ── JWT adapteri (sayt / kabinet) ──


@router.get("/me/assignments")
async def my_courses(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await _me_list(db, user)


@router.get("/me/{assignment_id}/progress")
async def my_progress(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_progress(db, user, assignment_id)


@router.post("/me/{assignment_id}/next-material")
async def my_next_material(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_next_material(db, user, assignment_id)


@router.post("/me/{assignment_id}/answer")
async def my_answer(
    assignment_id: int,
    payload: AnswerIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_answer(db, user, assignment_id, payload)


@router.post("/me/{assignment_id}/finish")
async def my_finish(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_finish(db, user, assignment_id)


@router.post("/me/{assignment_id}/retry")
async def my_retry(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_retry(db, user, assignment_id)


async def _me_send_material(db: AsyncSession, user: User, assignment_id: int) -> dict:
    """Joriy materialning FAYLINI xodimning Telegramiga yuboradi.

    ⚠️ NEGA SHUNDAY, brauzerda ko'rsatmasdan: material fayli Telegram
    `file_id` sifatida saqlanadi (serverda fayl YO'Q) va `file_id` ni
    brauzer o'qiy olmaydi. Faylni serverdan oqizib berish esa
    Passenger'ni bloklardi — konkurentlik = 1, ya'ni bitta video
    yuklanayotganda BUTUN sayt kutib turardi.

    Shuning uchun kadr hujjatlaridagi naqsh takrorlanadi
    (`employee_documents.bot_send_document`): fayl xodimning o'z
    Telegramiga yuboriladi, sayt esa faqat so'rovni beradi."""
    from api.telegram_notify import send_file_id

    a = await _my_assignment(db, user, assignment_id)
    p = await svc.progress(db, a)
    if p["stage"] != "material":
        raise HTTPException(status.HTTP_409_CONFLICT, "Hozir material bosqichi emas")
    m = p["current"]
    if not m.file_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu materialda fayl yo'q")
    if not user.telegram_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Telegram ulanmagan — faylni botdan oching",
        )
    resp = await send_file_id(
        user.telegram_id, m.file_id, m.kind, caption=f"📖 {m.title}"
    )
    #  `resp is None` — bildirishnomalar o'chiq (test rejimi) yoki token
    #  yo'q. Bu XATO emas, shuning uchun bayroq bilan qaytariladi.
    return {"ok": True, "delivered": resp is not None}


@router.post("/me/{assignment_id}/send-material")
async def my_send_material(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _me_send_material(db, user, assignment_id)


# ── Bot adapteri (`telegram_id`) ──


async def _bot_user(db: AsyncSession, telegram_id: int) -> User:
    u = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return u


class BotIdIn(BaseModel):
    telegram_id: int
    assignment_id: int


class BotAnswerIn(BotIdIn):
    text: str | None = None
    choice: int | None = None


class BotTextIn(BaseModel):
    telegram_id: int
    text: str


@router.get("/bot/my", dependencies=_BOT_SIR)
async def bot_my_courses(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await _me_list(db, await _bot_user(db, telegram_id))


@router.post("/bot/progress", dependencies=_BOT_SIR)
async def bot_progress(payload: BotIdIn, db: AsyncSession = Depends(get_db)) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _me_progress(db, u, payload.assignment_id)


@router.post("/bot/next-material", dependencies=_BOT_SIR)
async def bot_next_material(
    payload: BotIdIn, db: AsyncSession = Depends(get_db)
) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _me_next_material(db, u, payload.assignment_id)


@router.post("/bot/answer", dependencies=_BOT_SIR)
async def bot_answer(payload: BotAnswerIn, db: AsyncSession = Depends(get_db)) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _me_answer(
        db, u, payload.assignment_id, AnswerIn(text=payload.text, choice=payload.choice)
    )


@router.post("/bot/finish", dependencies=_BOT_SIR)
async def bot_finish(payload: BotIdIn, db: AsyncSession = Depends(get_db)) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _me_finish(db, u, payload.assignment_id)


@router.post("/bot/retry", dependencies=_BOT_SIR)
async def bot_retry(payload: BotIdIn, db: AsyncSession = Depends(get_db)) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _me_retry(db, u, payload.assignment_id)


@router.post("/bot/answer-text", dependencies=_BOT_SIR)
async def bot_answer_text(payload: BotTextIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Xodimning ERKIN MATNI — OCHIQ savolga javobmi?

    ⚠️ ANKETA PROTOKOLI (`/anketa/answer` naqshi): botda FSM saqlanmaydi,
    javob kutilayotgani BAZADAN aniqlanadi. Mos holat bo'lmasa
    `{"handled": false}` qaytadi va bot xabarni keyingi oqimlarga
    (AI sabab va h.k.) o'tkazib yuboradi. Aks holda kurs oqimi
    boshqa modullarning matnlarini o'g'irlab qolardi."""
    matn = (payload.text or "").strip()
    if not matn:
        return {"handled": False}
    u = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if u is None or not u.is_active:
        return {"handled": False}

    from db.models import CourseAssignmentStatus

    for a in await svc.my_assignments(db, u.id):
        #  ⚠️ `in_progress` YETARLI EMAS. Materialsiz kurs to'g'ridan-
        #  to'g'ri savoldan boshlanadi va holat `assigned` bo'lib qoladi
        #  (`in_progress` ga o'tkazadigan `next_material` chaqirilmaydi).
        #  Faqat `in_progress` tekshirilsa, bunday kursning ochiq savoli
        #  UMUMAN javob ololmasdi — testda aynan shu ushlandi.
        if a.status == CourseAssignmentStatus.finished.value:
            continue
        p = await svc.progress(db, a)
        #  Faqat OCHIQ savol kutilayotgan bo'lsa ushlaymiz. Variantli
        #  savol tugma bilan javob beriladi va matn unga tegishli emas.
        if p["stage"] != "savol" or (p["current"].options or []):
            continue
        res = await _me_answer(db, u, a.id, AnswerIn(text=matn))
        return {"handled": True, **res}
    return {"handled": False}


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
