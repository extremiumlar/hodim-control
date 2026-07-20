"""Sotuv AI markazi — yagona boshqaruv dashboardi (X-Bot-Secret, faqat
Boshliq/Dasturchi).

Anketa → Bilim bazasi → Sotuv playbook → Sotuv AI to'rttasi ilgari bot ichida
alohida-alohida joyda (ba'zisi reply-klaviatura tugmasi, ba'zisi boshqasining
ichiga joylashgan) yashar edi — bu yerda hammasi BITTA holat ko'rinishiga
yig'ilib, keyingi eng mantiqiy qadam (`recommendation`) hisoblanadi. Bot shu
ma'lumotni bitta dashboard ekraniga chizadi; har bo'limning o'z ichki
ekranlaridan "orqaga" tugmasi ham shu dashboardga qaytadi (bot/handlers/
anketa.py, knowledge.py, playbook.py'dagi mos joylarga qarang)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.routers.anketa import ACTIVE_STATUSES
from api.services import knowledge as ksvc
from api.services import sales_playbook as psvc
from api.services.knowledge import MANAGER_ROLES
from db.models import (
    AnketaAnswer,
    AnketaAssignment,
    AnketaSession,
    AnketaTemplate,
    KnowledgeStatus,
    PlaybookEntry,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-center", tags=["ai-center"], dependencies=[Depends(verify_bot_secret)])


async def _require_manager(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Boshliq/Dasturchi uchun")
    return user


async def _anketa_summary(db: AsyncSession) -> dict:
    session = await db.scalar(
        select(AnketaSession).order_by(AnketaSession.id.desc())
    )
    if session is None:
        return {"exists": False, "active": False, "status": None, "done": 0, "total": 0}

    assignments = list(
        await db.scalars(select(AnketaAssignment).where(AnketaAssignment.session_id == session.id))
    )
    done = sum(1 for a in assignments if a.status in ("done", "stopped"))
    return {
        "exists": True,
        "active": session.status in ACTIVE_STATUSES,
        "status": session.status,
        "done": done,
        "total": len(assignments),
    }


async def _pending_ingest_count(db: AsyncSession) -> int:
    """Yakunlangan/to'xtatilgan javoblar orasida hali bilim bazasiga
    yuklanmaganlari — anketa tugagach "🔄 Anketadan yuklash" bosilganmi
    yo'qmi shuni bildiradi."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(AnketaAnswer)
            .join(AnketaAssignment, AnketaAssignment.id == AnketaAnswer.assignment_id)
            .where(
                AnketaAnswer.ingested_at.is_(None),
                AnketaAssignment.status.in_(("done", "stopped")),
            )
        )
        or 0
    )


def _recommend(templates: int, anketa: dict, pending_ingest: int, kb: dict, pb: dict) -> str:
    """Quvurning qaysi bosqichida turganini hisoblab, keyingi ANIQ qadamni
    bitta jumlada aytadi — foydalanuvchi 4 bo'limni qo'lda tekshirib
    yurmasin."""
    if templates == 0:
        return "Word (.docx) faylni shu chatga tashlang — birinchi savol to'plami shundan yaratiladi."
    if anketa["active"]:
        return (
            f"Anketa davom etmoqda ({anketa['done']}/{anketa['total']} xodim javob berdi) — "
            "kutish yoki «2️⃣ Anketa»dan yakunlash mumkin."
        )
    if not anketa["exists"]:
        return "Anketani boshlang — «2️⃣ Anketa» bo'limidan kimlarga yuborishni tanlang."
    if pending_ingest:
        return f"{pending_ingest} ta yangi javob bilim bazasiga hali yuklanmagan — «3️⃣ Bilim bazasi»dan yuklang."
    if kb["counts"].get("draft"):
        return f"Bilim bazasi AI ishlovida ({kb['counts']['draft']} ta) — biroz kuting."
    if kb["review_pending"]:
        return f"«3️⃣ Bilim bazasi»da {kb['review_pending']} ta yozuvni ko'rib chiqing va tasdiqlang."
    if not kb["counts"].get("verified"):
        return "Hali tasdiqlangan bilim yo'q — anketa/qo'lda ma'lumot qo'shishni tekshiring."
    if pb.get("building"):
        return f"Sotuv playbook qurilmoqda ({pb['building']['label']}) — biroz kuting."
    if not pb["counts"]:
        return "Endi «4️⃣ Sotuv playbook»ni qurish tavsiya etiladi."
    if pb["counts"].get("unverified"):
        return f"«4️⃣ Sotuv playbook»da {pb['counts']['unverified']} ta yozuvni tasdiqlang."
    return "Hammasi tayyor — «🤖 Sotuv AI»da sinab ko'ring yoki bilim bazasidan datasetni yuklab oling."


@router.get("/overview/{telegram_id}")
async def overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_manager(db, telegram_id)

    templates = (
        await db.scalar(
            select(func.count()).select_from(AnketaTemplate).where(AnketaTemplate.is_active.is_(True))
        )
        or 0
    )
    anketa = await _anketa_summary(db)
    pending_ingest = await _pending_ingest_count(db)
    kb_counts = await ksvc.status_counts(db)
    kb_review_pending = sum(
        kb_counts.get(s, 0)
        for s in (
            KnowledgeStatus.unverified.value,
            KnowledgeStatus.conflict.value,
            KnowledgeStatus.unknown.value,
        )
    )
    kb = {"counts": kb_counts, "review_pending": kb_review_pending}

    pb_rows = list(await db.execute(select(PlaybookEntry.status, func.count()).group_by(PlaybookEntry.status)))
    pb_counts = {s: c for s, c in pb_rows}
    pb_build = await psvc.active_build(db)
    pb = {
        "counts": pb_counts,
        "building": (
            {"status": pb_build.status, "label": psvc.BUILD_STAGE_LABELS.get(pb_build.status, pb_build.status)}
            if pb_build
            else None
        ),
    }

    return {
        "templates": templates,
        "anketa": anketa,
        "pending_ingest": pending_ingest,
        "knowledge": kb,
        "playbook": pb,
        "ai_enabled": ksvc.ai_available(),
        "recommendation": _recommend(templates, anketa, pending_ingest, kb, pb),
    }
