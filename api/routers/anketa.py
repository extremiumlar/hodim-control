"""Bilim bazasi anketasi — bot orqali savol-javob oqimi.

Oqim: Dasturchi botda kun/vaqtni tasdiqlaydi → sessiya yaratiladi (har xodimga
BITTA takrorlanmas to'plam, taqsimot api/services/anketa_data.py'da) → vaqt
yetganda /anketa/tick (cron/scheduler har daqiqa) sessiyani boshlaydi: har
xodimga kirish xabari + 1-savol yuboriladi → xodimning har matn javobi
/anketa/answer orqali yoziladi va keyingi savol yuboriladi → hammasi tugagach
sessiya yopiladi va Dasturchiga xabar boradi.

Barcha endpointlar bot ichki chaqiruvlari (X-Bot-Secret) — web panelga hech
narsa qo'shilmagan (ataylab: frontend deploy'ini o'zgartirmaslik sharti)."""
import base64
import binascii
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ
from db.models import (
    AnketaAnswer,
    AnketaAssignment,
    AnketaSession,
    AnketaSessionStatus,
    AnketaTemplate,
    AuditLog,
    Position,
    Role,
    User,
)
from api.services.anketa_data import ANKETA_RULES, ANKETA_TARGETS, toplam_questions
from api.services.docx_parse import parse_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anketa", tags=["anketa"], dependencies=[Depends(verify_bot_secret)])

ACTIVE_STATUSES = (AnketaSessionStatus.scheduled.value, AnketaSessionStatus.in_progress.value)


class AssignmentIn(BaseModel):
    user_id: int
    # Yuklangan to'plam id'si; None — ichki 1-5 to'plamdan (aylanma) beriladi
    template_id: int | None = None


class SchedulePayload(BaseModel):
    telegram_id: int
    # Toshkent vaqti "YYYY-MM-DDTHH:MM" ko'rinishida; None — darhol boshlash
    scheduled_at: str | None = None
    # Qatnashchilar (vazifa berishdagi kabi): standart (5 sotuvchi, nomma-nom) |
    # all (barcha faol xodimlar, dasturchi'dan tashqari) | position | role |
    # explicit (har kimga alohida — `assignments` ro'yxati bo'yicha)
    target_type: str = "standart"
    position_id: int | None = None
    role: str | None = None
    # Guruh rejimida: hammaga shu yuklangan to'plam berilsin (None — ichki 1-5)
    template_id: int | None = None
    # explicit rejimida: kim qaysi to'plamni oladi (ro'yxatda yo'q xodim anketa OLMAYDI)
    assignments: list[AssignmentIn] | None = None


class ActorPayload(BaseModel):
    telegram_id: int


class AssignmentEditPayload(BaseModel):
    telegram_id: int
    assignment_id: int
    action: str  # "retemplate" | "remove"
    template_id: int | None = None  # retemplate: yuklangan to'plam
    toplam: int | None = None  # retemplate: ichki 1-5 to'plam (template_id bilan bir vaqtda berilmaydi)


class AnswerPayload(BaseModel):
    telegram_id: int
    text: str


class TemplateUploadPayload(BaseModel):
    telegram_id: int
    filename: str
    content_b64: str
    name: str | None = None


class TemplateActionPayload(BaseModel):
    telegram_id: int
    template_id: int


def _local_to_utc_naive(local: datetime) -> datetime:
    return local.replace(tzinfo=TASHKENT_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def _utc_naive_to_local_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (
        value.replace(tzinfo=timezone.utc)
        .astimezone(TASHKENT_TZ)
        .strftime("%d.%m.%Y %H:%M")
    )


async def _require_dasturchi(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role != Role.dasturchi.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Dasturchi uchun")
    return user


async def _load_template(db: AsyncSession, template_id: int, *, active_only: bool = True) -> AnketaTemplate:
    template = await db.get(AnketaTemplate, template_id)
    if template is None or (active_only and not template.is_active):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Savol to'plami topilmadi")
    return template


async def _resolve_targets(
    db: AsyncSession,
    target_type: str = "standart",
    position_id: int | None = None,
    role: str | None = None,
    template_id: int | None = None,
    assignments: list[AssignmentIn] | None = None,
) -> list[dict]:
    """Qatnashchilarni tanlaydi va har biriga savol to'plamini biriktiradi.

    Qaytaradi: [{"user": User, "toplam": int, "template_id": int|None}].
    `template_id` berilsa (guruh rejimida) hamma shu YUKLANGAN to'plamni oladi;
    berilmasa ichki 1-5 to'plam aylanma tarzda beriladi.
    `explicit` rejimida `assignments` ro'yxati aynan kim nima olishini belgilaydi —
    ro'yxatda yo'q xodimga anketa umuman yuborilmaydi."""
    if template_id is not None:
        await _load_template(db, template_id)

    if target_type == "explicit":
        if not assignments:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hech kim tanlanmagan")
        resolved: list[dict] = []
        seen: set[int] = set()
        for item in assignments:
            if item.user_id in seen:
                continue
            seen.add(item.user_id)
            user = await db.get(User, item.user_id)
            if user is None or not user.is_active or not user.telegram_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Xodim topilmadi yoki botga ulanmagan (id {item.user_id})",
                )
            if item.template_id is not None:
                await _load_template(db, item.template_id)
            resolved.append(
                {
                    "user": user,
                    "toplam": 0 if item.template_id else len(resolved) % 5 + 1,
                    "template_id": item.template_id,
                }
            )
        return resolved

    if target_type == "standart":
        users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
        resolved = []
        for name, toplam in ANKETA_TARGETS:
            matches = [u for u in users if u.full_name.strip().lower().startswith(name)]
            if not matches:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Xodim topilmadi: {name.title()}")
            if len(matches) > 1:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Bir nechta xodim mos keldi: {name.title()}"
                )
            user = matches[0]
            if not user.telegram_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{user.full_name.strip()} botga ulanmagan (telegram_id yo'q)",
                )
            resolved.append(
                {
                    "user": user,
                    "toplam": 0 if template_id else toplam,
                    "template_id": template_id,
                }
            )
        return resolved

    query = select(User).where(User.is_active.is_(True), User.telegram_id.isnot(None))
    if target_type == "all":
        # Texnik akkaunt (dasturchi) anketa olmaydi
        query = query.where(User.role != Role.dasturchi.value)
    elif target_type == "position":
        if position_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lavozim tanlanmagan")
        query = query.where(User.position_id == position_id)
    elif target_type == "role":
        if not role:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol tanlanmagan")
        query = query.where(User.role == role)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum qatnashchi turi")

    users = sorted(await db.scalars(query), key=lambda u: u.full_name.strip().lower())
    if not users:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Tanlangan guruhda botga ulangan faol xodim topilmadi"
        )
    return [
        {"user": u, "toplam": 0 if template_id else i % 5 + 1, "template_id": template_id}
        for i, u in enumerate(users)
    ]


async def _questions_and_label(db: AsyncSession, a: AnketaAssignment) -> tuple[list[dict], str]:
    """Biriktirmaning savollari va ko'rsatiladigan nomi. Yuklangan to'plam
    o'chirilgan bo'lsa ham (yumshoq o'chirish) savollar o'qiladi."""
    if a.template_id:
        template = await db.get(AnketaTemplate, a.template_id)
        if template is not None:
            return list(template.questions or []), template.name
        return [], "Savol to'plami"
    return toplam_questions(a.toplam), f"To'plam №{a.toplam}"


def _question_text(questions: list[dict], label: str, index: int) -> str:
    q = questions[index]
    section = q.get("section") or "Savollar"
    return (
        f"📝 <b>Anketa · {label}</b> — savol {index + 1}/{len(questions)}\n"
        f"<i>{section}</i>\n\n{q['text']}"
    )


async def _active_session(db: AsyncSession) -> AnketaSession | None:
    return await db.scalar(
        select(AnketaSession)
        .where(AnketaSession.status.in_(ACTIVE_STATUSES))
        .order_by(AnketaSession.id.desc())
    )


async def _session_view(db: AsyncSession, session: AnketaSession | None) -> dict | None:
    if session is None:
        return None
    assignments = list(
        await db.scalars(
            select(AnketaAssignment)
            .where(AnketaAssignment.session_id == session.id)
            .order_by(AnketaAssignment.toplam)
        )
    )
    user_ids = {a.user_id for a in assignments}
    users = list(await db.scalars(select(User).where(User.id.in_(user_ids)))) if user_ids else []
    name_by_id = {u.id: u.full_name.strip() for u in users}
    rows = []
    for a in assignments:
        questions, label = await _questions_and_label(db, a)
        rows.append(
            {
                "assignment_id": a.id,
                "user_id": a.user_id,
                "full_name": name_by_id.get(a.user_id, "?"),
                "toplam": a.toplam,
                "template_id": a.template_id,
                "label": label,
                "status": a.status,
                "answered": a.current_q,
                "total": len(questions),
            }
        )
    return {
        "id": session.id,
        "status": session.status,
        "scheduled_at_local": _utc_naive_to_local_str(session.scheduled_at),
        "started_at_local": _utc_naive_to_local_str(session.started_at),
        "finished_at_local": _utc_naive_to_local_str(session.finished_at),
        "assignments": rows,
    }


async def _start_session(db: AsyncSession, session: AnketaSession) -> None:
    """Sessiyani boshlaydi: har xodimga kirish xabari + birinchi savol.
    Xabar yuborishdagi xatolik (masalan xodim botni bloklagan) oqimni
    to'xtatmaydi — send_message o'zi None qaytaradi."""
    session.status = AnketaSessionStatus.in_progress.value
    session.started_at = datetime.utcnow()

    assignments = list(
        await db.scalars(select(AnketaAssignment).where(AnketaAssignment.session_id == session.id))
    )
    for a in assignments:
        a.status = "in_progress"
        a.started_at = datetime.utcnow()
    await db.commit()

    for a in assignments:
        user = await db.get(User, a.user_id)
        if not user or not user.telegram_id:
            continue
        questions, label = await _questions_and_label(db, a)
        if not questions:  # to'plam bo'sh/o'chirilgan — bu xodimni o'tkazamiz
            logger.warning("Anketa: %s uchun savollar topilmadi (assignment %s)", user.id, a.id)
            continue
        intro = (
            f"📝 <b>NURLI DIYOR — bilim bazasi anketasi ({label})</b>\n\n"
            f"Assalomu alaykum, {user.full_name.strip()}! Sizga {len(questions)} ta savol beriladi.\n\n"
            f"{ANKETA_RULES}\n\nBoshladik! 👇"
        )
        await send_message(user.telegram_id, intro)
        await send_message(user.telegram_id, _question_text(questions, label, 0))

    creator = await db.get(User, session.created_by)
    if creator and creator.telegram_id:
        await send_message(
            creator.telegram_id,
            f"🚀 Anketa boshlandi — {len(assignments)} xodimga birinchi savol yuborildi.",
        )


@router.get("/overview/{telegram_id}")
async def overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Dasturchi uchun holat: taqsimot (kim qaysi to'plam) + joriy/oxirgi sessiya."""
    await _require_dasturchi(db, telegram_id)

    try:
        targets = await _resolve_targets(db)
        target_rows = [
            {
                "full_name": t["user"].full_name.strip(),
                "toplam": t["toplam"],
                "bot_started": t["user"].bot_started,
            }
            for t in targets
        ]
        targets_error = None
    except HTTPException as exc:
        target_rows = []
        targets_error = exc.detail

    session = await _active_session(db)
    if session is None:
        session = await db.scalar(select(AnketaSession).order_by(AnketaSession.id.desc()))
    templates = list(
        await db.scalars(
            select(AnketaTemplate)
            .where(AnketaTemplate.is_active.is_(True))
            .order_by(AnketaTemplate.id)
        )
    )
    return {
        "targets": target_rows,
        "targets_error": targets_error,
        "templates": [
            {"id": t.id, "name": t.name, "question_count": t.question_count} for t in templates
        ],
        "session": await _session_view(db, session),
    }


@router.get("/preview-targets/{telegram_id}")
async def preview_targets(
    telegram_id: int,
    target_type: str = "standart",
    position_id: int | None = None,
    role: str | None = None,
    template_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tanlangan guruh bo'yicha kim qaysi to'plamni olishini oldindan ko'rsatadi
    (Dasturchi tasdiqlashdan oldin ro'yxatni ko'radi)."""
    await _require_dasturchi(db, telegram_id)
    targets = await _resolve_targets(db, target_type, position_id, role, template_id)
    label = None
    if template_id:
        label = (await _load_template(db, template_id)).name
    return {
        "targets": [
            {
                "full_name": t["user"].full_name.strip(),
                "toplam": t["toplam"],
                "label": label or f"To'plam №{t['toplam']}",
                "bot_started": t["user"].bot_started,
            }
            for t in targets
        ]
    }


@router.get("/candidates/{telegram_id}")
async def candidates(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Anketa berish mumkin bo'lgan xodimlar (botga ulangan faol) — «har kimga
    alohida» taqsimotida ro'yxat sifatida ko'rsatiladi."""
    await _require_dasturchi(db, telegram_id)
    users = sorted(
        await db.scalars(
            select(User).where(User.is_active.is_(True), User.telegram_id.isnot(None))
        ),
        key=lambda u: u.full_name.strip().lower(),
    )
    positions = {
        p.id: p.name for p in await db.scalars(select(Position))
    }
    return {
        "users": [
            {
                "user_id": u.id,
                "full_name": u.full_name.strip(),
                "role": u.role,
                "position": positions.get(u.position_id) if u.position_id else None,
                "position_id": u.position_id,
                "bot_started": u.bot_started,
            }
            for u in users
        ]
    }


# ─── Savol to'plamlari (Word/.txt yuklash) ───────────────────────────────────

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("/templates/{telegram_id}")
async def list_templates(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_dasturchi(db, telegram_id)
    templates = list(
        await db.scalars(
            select(AnketaTemplate)
            .where(AnketaTemplate.is_active.is_(True))
            .order_by(AnketaTemplate.id)
        )
    )
    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "filename": t.filename,
                "question_count": t.question_count,
                "created_at_local": _utc_naive_to_local_str(t.created_at),
            }
            for t in templates
        ]
    }


@router.get("/templates/{telegram_id}/{template_id}")
async def template_detail(
    telegram_id: int, template_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    await _require_dasturchi(db, telegram_id)
    template = await _load_template(db, template_id, active_only=False)
    return {
        "id": template.id,
        "name": template.name,
        "filename": template.filename,
        "question_count": template.question_count,
        "questions": list(template.questions or []),
    }


_GENERIC_STEM_RE = re.compile(
    r"^(anketa|savol(lar)?|doc(ument)?|new|untitled|scan|img|image|fayl|file|"
    r"hujjat|copy|nusxa|без[ _]?имени|документ)[\s_\-]*\d*$",
    re.I,
)


def _is_generic_stem(stem: str) -> bool:
    """Fayl nomi "anketa.docx", "doc1.docx", "hujjat (2).docx" kabi umumiy
    bo'lsa True — bunday holatda docx sarlavhasi ustuvor bo'ladi (aks holda
    fayl nomi ustuvor: bir nechta faylning docx sarlavhasi bir xil bo'lishi
    juda oddiy holat, lekin fayl nomlarini foydalanuvchi odatda o'zi
    farqlab qo'yadi)."""
    cleaned = re.sub(r"\s*\(\d+\)\s*$", "", stem.strip())
    return not cleaned or bool(_GENERIC_STEM_RE.match(cleaned))


async def _unique_template_name(db: AsyncSession, base_name: str) -> str:
    """Faol to'plamlar orasida nom to'qnashsa "Nomi (2)", "Nomi (3)"... qo'shadi
    — bir xil docx sarlavhali bir nechta fayl yuklanganda ro'yxatda
    ajratib bo'lmay qolmasligi uchun (haqiqiy holat: 3 ta fayl, hammasi bir
    xil sarlavha bilan)."""
    existing = set(
        await db.scalars(select(AnketaTemplate.name).where(AnketaTemplate.is_active.is_(True)))
    )
    if base_name not in existing:
        return base_name
    n = 2
    while f"{base_name} ({n})" in existing:
        n += 1
    return f"{base_name} ({n})"


@router.post("/templates/upload")
async def upload_template(
    payload: TemplateUploadPayload, db: AsyncSession = Depends(get_db)
) -> dict:
    """Botga tashlangan .docx/.txt fayldan savollarni ajratib to'plam yaratadi.

    Nom ustuvorligi: (1) foydalanuvchi qo'lda kiritgan nom; (2) FAYL NOMI
    (agar generik bo'lmasa — "anketa.docx" kabi emas); (3) docx sarlavhasi;
    (4) fayl nomi baribir. Fayl nomi ustuvor, chunki bir nechta fayl bir xil
    docx sarlavhasi bilan yuklanishi (masalan "NURLI DIYOR — 2-BOSQICH
    ANKETA" nomli 3 ta fayl) juda oddiy holat va sarlavhaga tayansak
    tanlash ro'yxatida ajratib bo'lmay qoladi; fayl nomini esa foydalanuvchi
    odatda o'zi farqlab beradi (Manager_anketa.docx, Operator_anketa.docx).
    Har holatda ham to'qnashuv bo'lsa avtomatik "(2)", "(3)" qo'shiladi."""
    actor = await _require_dasturchi(db, payload.telegram_id)
    try:
        data = base64.b64decode(payload.content_b64)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fayl mazmuni buzilgan")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fayl bo'sh")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fayl juda katta (5 MB dan oshmasin)")

    try:
        parsed = parse_questions(data, payload.filename)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    questions = parsed["questions"]
    stem = (payload.filename or "").rsplit("/", 1)[-1]
    for suffix in (".docx", ".txt"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    stem = stem.strip()

    if payload.name:
        base_name = payload.name.strip()
    elif stem and not _is_generic_stem(stem):
        base_name = stem
    else:
        base_name = (parsed.get("title") or stem or "Savol to'plami").strip()
    name = (await _unique_template_name(db, base_name[:240]))[:255]

    template = AnketaTemplate(
        name=name,
        filename=(payload.filename or "")[:255],
        questions=questions,
        question_count=len(questions),
        created_by=actor.id,
    )
    db.add(template)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="anketa_template_upload",
            after={"name": name, "questions": len(questions), "fallback": parsed["fallback"]},
        )
    )
    await db.commit()
    await db.refresh(template)
    return {
        "id": template.id,
        "name": template.name,
        "question_count": template.question_count,
        "fallback": parsed["fallback"],
        "preview": [q["text"] for q in questions[:5]],
    }


@router.post("/templates/delete")
async def delete_template(
    payload: TemplateActionPayload, db: AsyncSession = Depends(get_db)
) -> dict:
    """Yumshoq o'chirish — o'tgan sessiyalarning savollari saqlanib qoladi."""
    actor = await _require_dasturchi(db, payload.telegram_id)
    template = await _load_template(db, payload.template_id)

    active = await _active_session(db)
    if active is not None:
        used = await db.scalar(
            select(AnketaAssignment).where(
                AnketaAssignment.session_id == active.id,
                AnketaAssignment.template_id == template.id,
            )
        )
        if used is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Bu to'plam faol sessiyada ishlatilmoqda — avval sessiyani yakunlang.",
            )

    template.is_active = False
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="anketa_template_delete",
            after={"template_id": template.id, "name": template.name},
        )
    )
    await db.commit()
    return {"deleted": True}


@router.post("/schedule")
async def schedule(payload: SchedulePayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Sessiya yaratish (Dasturchi tasdig'i). scheduled_at berilmasa yoki o'tib
    ketgan bo'lsa — darhol boshlanadi."""
    actor = await _require_dasturchi(db, payload.telegram_id)

    if await _active_session(db) is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Faol anketa sessiyasi allaqachon bor — avval uni yakunlang yoki bekor qiling.",
        )

    targets = await _resolve_targets(
        db,
        payload.target_type,
        payload.position_id,
        payload.role,
        payload.template_id,
        payload.assignments,
    )

    if payload.scheduled_at:
        try:
            local = datetime.strptime(payload.scheduled_at, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vaqt formati noto'g'ri")
        scheduled_utc = _local_to_utc_naive(local)
    else:
        scheduled_utc = datetime.utcnow()

    session = AnketaSession(created_by=actor.id, scheduled_at=scheduled_utc)
    db.add(session)
    await db.flush()
    for t in targets:
        db.add(
            AnketaAssignment(
                session_id=session.id,
                user_id=t["user"].id,
                toplam=t["toplam"],
                template_id=t["template_id"],
            )
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="anketa_scheduled",
            after={
                "session_id": session.id,
                "scheduled_at_local": _utc_naive_to_local_str(scheduled_utc),
                "target_type": payload.target_type,
                "targets": [
                    {
                        "user_id": t["user"].id,
                        "full_name": t["user"].full_name.strip(),
                        "toplam": t["toplam"],
                        "template_id": t["template_id"],
                    }
                    for t in targets
                ],
            },
        )
    )
    await db.commit()

    if scheduled_utc <= datetime.utcnow():
        await _start_session(db, session)

    return {"session": await _session_view(db, session)}


@router.post("/finish")
async def finish(payload: ActorPayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Sessiyani MUDDATIDAN OLDIN yakunlash — to'ldirmaganlarni kutmasdan.
    Bekor qilishdan farqi: yozilgan javoblar SAQLANADI (bilim bazasiga yuklash
    mumkin); tugatmagan xodimlarning anketasi to'xtatiladi (stopped)."""
    actor = await _require_dasturchi(db, payload.telegram_id)
    session = await _active_session(db)
    if session is None or session.status != AnketaSessionStatus.in_progress.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Davom etayotgan sessiya yo'q")

    session.status = AnketaSessionStatus.done.value
    session.finished_at = datetime.utcnow()
    assignments = list(
        await db.scalars(select(AnketaAssignment).where(AnketaAssignment.session_id == session.id))
    )
    stopped_users: list[int] = []
    done_count = 0
    for a in assignments:
        if a.status == "done":
            done_count += 1
            continue
        a.status = "stopped"
        a.finished_at = datetime.utcnow()
        stopped_users.append(a.user_id)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="anketa_finished_early",
            after={"session_id": session.id, "done": done_count, "stopped": len(stopped_users)},
        )
    )
    await db.commit()

    for user_id in stopped_users:
        user = await db.get(User, user_id)
        if user and user.telegram_id:
            await send_message(
                user.telegram_id,
                "ℹ️ Anketa yakunlandi — qolgan savollarga javob yozish shart emas. "
                "Yozgan javoblaringiz uchun rahmat!",
            )
    return {
        "session": await _session_view(db, session),
        "done": done_count,
        "stopped": len(stopped_users),
    }


@router.post("/assignment/edit")
async def edit_assignment(payload: AssignmentEditPayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Xatoni tuzatish: sessiya boshlangandan keyin ham, XODIM HALI JAVOB
    YOZISHNI BOSHLAMAGAN bo'lsa (current_q == 0), uning to'plamini
    almashtirish yoki uni sessiyadan butunlay olib tashlash mumkin. Javob
    yozib ulgurgan xodimga tegilmaydi — bu holatda faqat butun sessiyani
    yakunlash/bekor qilish (mavjud /finish, /cancel) qo'llaniladi."""
    actor = await _require_dasturchi(db, payload.telegram_id)
    assignment = await db.get(AnketaAssignment, payload.assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Biriktirma topilmadi")

    session = await db.get(AnketaSession, assignment.session_id)
    if session is None or session.status != AnketaSessionStatus.in_progress.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sessiya faol emas")
    if assignment.status != "in_progress" or assignment.current_q > 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu xodim allaqachon javob yozishni boshlagan — endi almashtirib bo'lmaydi.",
        )

    user = await db.get(User, assignment.user_id)

    if payload.action == "remove":
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="anketa_assignment_removed",
                after={"assignment_id": assignment.id, "user_id": assignment.user_id},
            )
        )
        await db.delete(assignment)
        await db.flush()

        # Olib tashlangani sessiyadagi YAGONA hali javob kutilayotgan biriktirma
        # bo'lsa — sessiya "osilib" qolmasin (aks holda yangi sessiya ochib
        # bo'lmaydi, _active_session uni hamon faol deb hisoblaydi).
        remaining = list(
            await db.scalars(
                select(AnketaAssignment).where(AnketaAssignment.session_id == session.id)
            )
        )
        if remaining and all(r.status != "in_progress" for r in remaining):
            session.status = AnketaSessionStatus.done.value
            session.finished_at = datetime.utcnow()

        await db.commit()
        if user and user.telegram_id:
            await send_message(
                user.telegram_id, "ℹ️ Anketa sizga endi yuborilmaydi — bekor qilindi. Rahmat!"
            )
        return {"removed": True, "session": await _session_view(db, session)}

    if payload.action == "retemplate":
        if payload.template_id is not None and payload.toplam is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "template_id yoki toplam — faqat bittasi")
        if payload.template_id is not None:
            await _load_template(db, payload.template_id)
            assignment.template_id = payload.template_id
            assignment.toplam = 0
        elif payload.toplam is not None:
            assignment.template_id = None
            assignment.toplam = payload.toplam
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Yangi to'plam ko'rsatilmagan")

        db.add(
            AuditLog(
                actor_id=actor.id,
                action="anketa_assignment_retemplate",
                after={
                    "assignment_id": assignment.id,
                    "template_id": assignment.template_id,
                    "toplam": assignment.toplam,
                },
            )
        )
        await db.commit()

        questions, label = await _questions_and_label(db, assignment)
        if user and user.telegram_id and questions:
            await send_message(
                user.telegram_id,
                f"🔄 <b>Savol to'plamingiz yangilandi</b> — endi: {label}\n\n"
                f"Avvalgi savolni unuting, {len(questions)} ta savol boshidan boshlanadi.",
            )
            await send_message(user.telegram_id, _question_text(questions, label, 0))
        return {"updated": True, "session": await _session_view(db, session)}

    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum amal")


@router.post("/cancel")
async def cancel(payload: ActorPayload, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _require_dasturchi(db, payload.telegram_id)
    session = await _active_session(db)
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faol sessiya yo'q")

    was_in_progress = session.status == AnketaSessionStatus.in_progress.value
    session.status = AnketaSessionStatus.cancelled.value
    session.finished_at = datetime.utcnow()
    assignments = list(
        await db.scalars(select(AnketaAssignment).where(AnketaAssignment.session_id == session.id))
    )
    pending_users: list[int] = []
    for a in assignments:
        if a.status == "in_progress":
            pending_users.append(a.user_id)

    # Bekor qilinganda xodimlar yozib ulgurgan javoblar ham o'chiriladi — sessiya
    # umuman bo'lmagandek, keyingi sinovda toza holatdan boshlanadi.
    assignment_ids = [a.id for a in assignments]
    if assignment_ids:
        await db.execute(delete(AnketaAnswer).where(AnketaAnswer.assignment_id.in_(assignment_ids)))

    db.add(AuditLog(actor_id=actor.id, action="anketa_cancelled", after={"session_id": session.id}))
    await db.commit()

    if was_in_progress:
        for user_id in pending_users:
            user = await db.get(User, user_id)
            if user and user.telegram_id:
                await send_message(
                    user.telegram_id,
                    "ℹ️ Anketa to'xtatildi — hozircha javob yozish shart emas. Rahmat!",
                )
    return {"session": await _session_view(db, session)}


@router.post("/tick")
async def tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Har daqiqa (cron_tick / scheduler) — vaqti kelgan sessiyalarni boshlaydi."""
    due = list(
        await db.scalars(
            select(AnketaSession).where(
                AnketaSession.status == AnketaSessionStatus.scheduled.value,
                AnketaSession.scheduled_at <= datetime.utcnow(),
            )
        )
    )
    for session in due:
        await _start_session(db, session)
    return {"started": len(due)}


@router.post("/answer")
async def answer(payload: AnswerPayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Xodimning matn xabari. Faol savol kutilayotgan bo'lsa javob sifatida
    yoziladi va keyingi savol qaytariladi; aks holda {"handled": false} —
    bot xabarni boshqa oqimlarga (masalan AI sabab) o'tkazib yuboradi."""
    text = (payload.text or "").strip()
    if not text:
        return {"handled": False}

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        return {"handled": False}

    assignment = await db.scalar(
        select(AnketaAssignment)
        .join(AnketaSession, AnketaSession.id == AnketaAssignment.session_id)
        .where(
            AnketaSession.status == AnketaSessionStatus.in_progress.value,
            AnketaAssignment.user_id == user.id,
            AnketaAssignment.status == "in_progress",
        )
        .order_by(AnketaAssignment.id.desc())
    )
    if assignment is None:
        return {"handled": False}

    questions, label = await _questions_and_label(db, assignment)
    index = assignment.current_q
    if index >= len(questions):  # himoya: holat buzilgan bo'lsa yakunlaymiz
        assignment.status = "done"
        await db.commit()
        return {"handled": False}

    db.add(
        AnketaAnswer(
            assignment_id=assignment.id,
            question_index=index,
            question_text=questions[index]["text"],
            answer_text=text,
        )
    )
    assignment.current_q = index + 1
    finished = assignment.current_q >= len(questions)
    if finished:
        assignment.status = "done"
        assignment.finished_at = datetime.utcnow()
    await db.commit()

    messages: list[str] = []
    if not finished:
        messages.append(f"✅ Javob qayd etildi ({assignment.current_q}/{len(questions)}).")
        messages.append(_question_text(questions, label, assignment.current_q))
        return {"handled": True, "messages": messages}

    messages.append(
        f"🎉 Rahmat, {user.full_name.strip()}! Barcha {len(questions)} savolga javob berdingiz — "
        "javoblaringiz bilim bazasiga kiritiladi."
    )

    # Sessiya bo'yicha umumiy holat: Dasturchiga yakun xabari
    session = await db.get(AnketaSession, assignment.session_id)
    all_assignments = list(
        await db.scalars(select(AnketaAssignment).where(AnketaAssignment.session_id == session.id))
    )
    done_count = sum(1 for a in all_assignments if a.status == "done")
    all_done = done_count == len(all_assignments)
    if all_done:
        session.status = AnketaSessionStatus.done.value
        session.finished_at = datetime.utcnow()
        await db.commit()

    creator = await db.get(User, session.created_by)
    if creator and creator.telegram_id:
        await send_message(
            creator.telegram_id,
            f"📝 {user.full_name.strip()} anketani yakunladi ({label}) — "
            f"{done_count}/{len(all_assignments)} tayyor.",
        )
        if all_done:
            await send_message(
                creator.telegram_id,
                "✅ <b>Anketa yakunlandi</b> — barcha xodimlar javob berib bo'ldi. "
                "Javoblarni botdagi «📝 Anketa» bo'limidan yuklab olishingiz mumkin.",
            )

    return {"handled": True, "messages": messages}


@router.get("/results/{telegram_id}")
async def results(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Oxirgi sessiya javoblari (Dasturchi uchun, bot .txt fayl qilib beradi)."""
    await _require_dasturchi(db, telegram_id)
    session = await db.scalar(
        select(AnketaSession)
        .where(AnketaSession.status != AnketaSessionStatus.cancelled.value)
        .order_by(AnketaSession.id.desc())
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hali sessiya yo'q")

    view = await _session_view(db, session)
    assignments = list(
        await db.scalars(
            select(AnketaAssignment)
            .where(AnketaAssignment.session_id == session.id)
            .order_by(AnketaAssignment.toplam)
        )
    )
    result_users = []
    for a in assignments:
        user = await db.get(User, a.user_id)
        _, label = await _questions_and_label(db, a)
        answers = list(
            await db.scalars(
                select(AnketaAnswer)
                .where(AnketaAnswer.assignment_id == a.id)
                .order_by(AnketaAnswer.question_index)
            )
        )
        result_users.append(
            {
                "full_name": user.full_name.strip() if user else "?",
                "toplam": a.toplam,
                "label": label,
                "status": a.status,
                "answers": [
                    {
                        "n": ans.question_index + 1,
                        "question": ans.question_text,
                        "answer": ans.answer_text,
                        "answered_at_local": _utc_naive_to_local_str(ans.answered_at),
                    }
                    for ans in answers
                ],
            }
        )
    return {"session": view, "users": result_users}
