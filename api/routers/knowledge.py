"""Sotuv bilim bazasi — bot endpointlari (X-Bot-Secret).

Boshqaruv faqat rahbarlar (boss/dasturchi) uchun: anketadan yuklash (ingest),
ko'rib chiqish (tasdiqlash/tahrirlash/o'chirish), qo'lda yozuv qo'shish, .txt
eksport. /tick va /stale-tick — cron/scheduler chaqiruvlari.
Web panelga ataylab hech narsa qo'shilmagan (frontend deploy'i o'zgarmasin)."""
import hmac
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.services import knowledge as svc
from db.models import AuditLog, KnowledgeEntry, KnowledgeStatus, PlaybookEntry, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(verify_bot_secret)])

# Tashqi chatbot uchun ochiq (bot-secret'siz) router — faqat /dataset, o'z kaliti
# bilan himoyalangan (KNOWLEDGE_DATASET_KEY). api/main.py alohida include qiladi.
public_router = APIRouter(prefix="/knowledge", tags=["knowledge"])

REVIEW_STATUSES = (
    KnowledgeStatus.unverified.value,
    KnowledgeStatus.conflict.value,
    KnowledgeStatus.unknown.value,
)


class ActorPayload(BaseModel):
    telegram_id: int


class DecidePayload(BaseModel):
    telegram_id: int
    entry_id: int
    action: str  # approve | delete | edit | toggle_date
    answer: str | None = None  # edit uchun yangi javob matni


class AddPayload(BaseModel):
    telegram_id: int
    question: str
    answer: str
    category: str = "umumiy"
    date_sensitive: bool = False


async def _require_manager(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in svc.MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Boshliq/Dasturchi uchun")
    return user


def _entry_view(e: KnowledgeEntry) -> dict:
    return {
        "id": e.id,
        "kind": e.kind,
        "category": e.category,
        "question": e.question,
        "answer": e.answer,
        "status": e.status,
        "date_sensitive": e.date_sensitive,
        "needs_recheck": e.needs_recheck,
        "source": e.source,
        "review_note": e.review_note,
    }


@router.get("/overview/{telegram_id}")
async def overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_manager(db, telegram_id)
    counts = await svc.status_counts(db)
    recheck = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.needs_recheck.is_(True)
        )
    )
    return {
        "counts": counts,
        "review_pending": sum(counts.get(s, 0) for s in REVIEW_STATUSES),
        "needs_recheck": recheck or 0,
        "ai_enabled": svc.ai_available(),
    }


@router.post("/ingest")
async def ingest(payload: ActorPayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Anketa javoblaridan draft'lar yaratadi (tez, AI'siz) — tugallanmagan
    sessiyalarning yozilgan javoblari ham olinadi (javob darajasida idempotent).
    AI ishlovi keyingi daqiqalarda /tick orqali bo'lib-bo'lib boradi."""
    actor = await _require_manager(db, payload.telegram_id)
    result = await svc.create_drafts(db)
    if not result["created"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Yangi javob yo'q — anketalarning barcha yozilgan javoblari allaqachon yuklangan.",
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="knowledge_ingest",
            after={"created": result["created"], "sessions": result["sessions"]},
        )
    )
    await db.commit()
    return result


@router.post("/tick")
async def tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Har daqiqa (cron/scheduler): draft yozuvlarni chegaralangan AI to'plamida
    qayta ishlaydi. Draft bo'lmasa yengil no-op."""
    pending = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.status == KnowledgeStatus.draft.value
        )
    )
    if not pending:
        return {"processed": 0, "remaining": 0}
    return await svc.process_batch(db)


@router.get("/review-next/{telegram_id}")
async def review_next(
    telegram_id: int, after_id: int = 0, db: AsyncSession = Depends(get_db)
) -> dict:
    """Ko'rib chiqiladigan navbatdagi yozuv (unverified/conflict/unknown).
    `after_id` — "o'tkazib yuborish" uchun: shu id'dan keyingisi olinadi."""
    await _require_manager(db, telegram_id)
    entry = await db.scalar(
        select(KnowledgeEntry)
        .where(KnowledgeEntry.status.in_(REVIEW_STATUSES), KnowledgeEntry.id > after_id)
        .order_by(KnowledgeEntry.id)
        .limit(1)
    )
    remaining = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.status.in_(REVIEW_STATUSES)
        )
    )
    drafts = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.status == KnowledgeStatus.draft.value
        )
    )
    return {
        "entry": _entry_view(entry) if entry else None,
        "remaining": remaining or 0,
        "processing": drafts or 0,
    }


@router.post("/decide")
async def decide(payload: DecidePayload, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _require_manager(db, payload.telegram_id)
    entry = await db.get(KnowledgeEntry, payload.entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")

    before_status = entry.status
    if payload.action == "approve":
        if not entry.answer.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Javob bo'sh — avval ✏️ bilan javob yozing, keyin tasdiqlang.",
            )
        entry.status = KnowledgeStatus.verified.value
        entry.needs_recheck = False
        entry.recheck_notified_at = None
        entry.verified_by = actor.id
        entry.verified_at = datetime.utcnow()
    elif payload.action == "edit":
        if not (payload.answer or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Yangi javob matni bo'sh")
        entry.answer = payload.answer.strip()
        entry.status = KnowledgeStatus.verified.value
        entry.needs_recheck = False
        entry.recheck_notified_at = None
        entry.verified_by = actor.id
        entry.verified_at = datetime.utcnow()
        entry.review_note = None
    elif payload.action == "toggle_date":
        entry.date_sensitive = not entry.date_sensitive
    elif payload.action == "delete":
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="knowledge_delete",
                after={"id": entry.id, "question": entry.question[:200]},
            )
        )
        await db.delete(entry)
        await db.commit()
        return {"deleted": True}
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum amal")

    db.add(
        AuditLog(
            actor_id=actor.id,
            action=f"knowledge_{payload.action}",
            after={"id": entry.id, "before_status": before_status, "status": entry.status},
        )
    )
    await db.commit()
    return {"entry": _entry_view(entry)}


@router.post("/add")
async def add_entry(payload: AddPayload, db: AsyncSession = Depends(get_db)) -> dict:
    """Qo'lda rasmiy fakt kiritish (narxnoma, aksiya...) — rahbar kiritgani uchun
    darhol verified bo'ladi."""
    actor = await _require_manager(db, payload.telegram_id)
    if not payload.question.strip() or not payload.answer.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Savol va javob bo'sh bo'lmasin")
    category = payload.category if payload.category in svc.CATEGORIES else "umumiy"
    entry = KnowledgeEntry(
        kind="single",
        category=category,
        question=payload.question.strip(),
        answer=payload.answer.strip(),
        status=KnowledgeStatus.verified.value,
        date_sensitive=payload.date_sensitive,
        source=f"Qo'lda: {actor.full_name.strip()}",
        source_user_id=actor.id,
        verified_by=actor.id,
        verified_at=datetime.utcnow(),
    )
    db.add(entry)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="knowledge_add",
            after={"question": payload.question[:200], "category": category},
        )
    )
    await db.commit()
    await db.refresh(entry)
    return {"entry": _entry_view(entry)}


@router.get("/export/{telegram_id}")
async def export(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Barcha yozuvlar (.txt fayl bot tomonda quriladi) — kategoriya bo'yicha."""
    await _require_manager(db, telegram_id)
    entries = list(
        await db.scalars(
            select(KnowledgeEntry).order_by(KnowledgeEntry.category, KnowledgeEntry.id)
        )
    )
    return {"entries": [_entry_view(e) for e in entries]}


@router.post("/stale-tick")
async def stale_tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Kunlik: eskirgan sana-sezgir verified yozuvlarni belgilab rahbarga eslatadi."""
    return await svc.stale_check(db)


async def build_dataset(db: AsyncSession) -> dict:
    """Tashqi chatbot uchun tayyor dataset — FAQAT tasdiqlangan savol-javoblar
    va playbook. Bot (.json tugmasi) va /dataset endpointi bir xil shakl beradi."""
    entries = list(
        await db.scalars(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.status == KnowledgeStatus.verified.value)
            .order_by(KnowledgeEntry.category, KnowledgeEntry.id)
        )
    )
    playbook = list(
        await db.scalars(
            select(PlaybookEntry)
            .where(PlaybookEntry.status == "verified")
            .order_by(PlaybookEntry.kind, PlaybookEntry.id)
        )
    )
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(entries),
        "entries": [
            {
                "savol": e.question,
                "javob": e.answer,
                "kategoriya": e.category,
                "sana_sezgir": e.date_sensitive,
                "qayta_tekshirish_kerak": e.needs_recheck,
                "yangilangan": e.updated_at.strftime("%Y-%m-%d") if e.updated_at else None,
            }
            for e in entries
        ],
        "playbook": [
            {
                "turi": p.kind,
                "vaziyat": p.situation,
                "texnika": p.technique,
                "iboralar": p.phrases or [],
            }
            for p in playbook
        ],
    }


@router.get("/dataset-for-bot/{telegram_id}")
async def dataset_for_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Bot uchun xuddi shu dataset (rahbar .json faylini yuklab oladi)."""
    await _require_manager(db, telegram_id)
    return await build_dataset(db)


@public_router.get("/dataset")
async def dataset(key: str = "", db: AsyncSession = Depends(get_db)) -> dict:
    """Tashqi chatbot bilim bazasini shu yerdan tortib oladi. KNOWLEDGE_DATASET_KEY
    .env'da bo'sh bo'lsa endpoint umuman yo'qdek (404) — tasodifan ochilib qolmaydi."""
    if not settings.knowledge_dataset_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if not key or not hmac.compare_digest(key, settings.knowledge_dataset_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kalit noto'g'ri")
    return await build_dataset(db)
