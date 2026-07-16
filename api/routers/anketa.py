"""Bilim bazasi anketasi — bot orqali savol-javob oqimi.

Oqim: Dasturchi botda kun/vaqtni tasdiqlaydi → sessiya yaratiladi (har xodimga
BITTA takrorlanmas to'plam, taqsimot api/services/anketa_data.py'da) → vaqt
yetganda /anketa/tick (cron/scheduler har daqiqa) sessiyani boshlaydi: har
xodimga kirish xabari + 1-savol yuboriladi → xodimning har matn javobi
/anketa/answer orqali yoziladi va keyingi savol yuboriladi → hammasi tugagach
sessiya yopiladi va Dasturchiga xabar boradi.

Barcha endpointlar bot ichki chaqiruvlari (X-Bot-Secret) — web panelga hech
narsa qo'shilmagan (ataylab: frontend deploy'ini o'zgartirmaslik sharti)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ
from db.models import (
    AnketaAnswer,
    AnketaAssignment,
    AnketaSession,
    AnketaSessionStatus,
    AuditLog,
    Role,
    User,
)
from api.services.anketa_data import ANKETA_RULES, ANKETA_TARGETS, toplam_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anketa", tags=["anketa"], dependencies=[Depends(verify_bot_secret)])

ACTIVE_STATUSES = (AnketaSessionStatus.scheduled.value, AnketaSessionStatus.in_progress.value)


class SchedulePayload(BaseModel):
    telegram_id: int
    # Toshkent vaqti "YYYY-MM-DDTHH:MM" ko'rinishida; None — darhol boshlash
    scheduled_at: str | None = None


class ActorPayload(BaseModel):
    telegram_id: int


class AnswerPayload(BaseModel):
    telegram_id: int
    text: str


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


async def _resolve_targets(db: AsyncSession) -> list[tuple[User, int]]:
    """ANKETA_TARGETS taqsimotini bazadagi faol xodimlarga bog'laydi.
    Har ism uchun aynan bitta faol, telegramga ulangan xodim topilishi shart —
    aks holda aniq xabarli 400 (Dasturchi botda ko'radi)."""
    users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    resolved: list[tuple[User, int]] = []
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
                status.HTTP_400_BAD_REQUEST, f"{user.full_name.strip()} botga ulanmagan (telegram_id yo'q)"
            )
        resolved.append((user, toplam))
    return resolved


def _question_text(toplam: int, index: int) -> str:
    questions = toplam_questions(toplam)
    q = questions[index]
    return (
        f"📝 <b>Anketa · To'plam №{toplam}</b> — savol {index + 1}/{len(questions)}\n"
        f"<i>{q['section']}</i>\n\n{q['text']}"
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
    return {
        "id": session.id,
        "status": session.status,
        "scheduled_at_local": _utc_naive_to_local_str(session.scheduled_at),
        "started_at_local": _utc_naive_to_local_str(session.started_at),
        "finished_at_local": _utc_naive_to_local_str(session.finished_at),
        "assignments": [
            {
                "user_id": a.user_id,
                "full_name": name_by_id.get(a.user_id, "?"),
                "toplam": a.toplam,
                "status": a.status,
                "answered": a.current_q,
                "total": len(toplam_questions(a.toplam)),
            }
            for a in assignments
        ],
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
        total = len(toplam_questions(a.toplam))
        intro = (
            f"📝 <b>NURLI DIYOR — bilim bazasi anketasi (To'plam №{a.toplam})</b>\n\n"
            f"Assalomu alaykum, {user.full_name.strip()}! Sizga {total} ta savol beriladi.\n\n"
            f"{ANKETA_RULES}\n\nBoshladik! 👇"
        )
        await send_message(user.telegram_id, intro)
        await send_message(user.telegram_id, _question_text(a.toplam, 0))

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
            {"full_name": u.full_name.strip(), "toplam": t, "bot_started": u.bot_started}
            for u, t in targets
        ]
        targets_error = None
    except HTTPException as exc:
        target_rows = []
        targets_error = exc.detail

    session = await _active_session(db)
    if session is None:
        session = await db.scalar(select(AnketaSession).order_by(AnketaSession.id.desc()))
    return {
        "targets": target_rows,
        "targets_error": targets_error,
        "session": await _session_view(db, session),
    }


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

    targets = await _resolve_targets(db)

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
    for user, toplam in targets:
        db.add(AnketaAssignment(session_id=session.id, user_id=user.id, toplam=toplam))
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="anketa_scheduled",
            after={
                "session_id": session.id,
                "scheduled_at_local": _utc_naive_to_local_str(scheduled_utc),
                "targets": [
                    {"user_id": u.id, "full_name": u.full_name.strip(), "toplam": t}
                    for u, t in targets
                ],
            },
        )
    )
    await db.commit()

    if scheduled_utc <= datetime.utcnow():
        await _start_session(db, session)

    return {"session": await _session_view(db, session)}


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

    questions = toplam_questions(assignment.toplam)
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
        messages.append(_question_text(assignment.toplam, assignment.current_q))
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
            f"📝 {user.full_name.strip()} anketani yakunladi (To'plam №{assignment.toplam}) — "
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
