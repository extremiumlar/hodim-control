"""Sotuvchi AI (3-bosqich) — mijoz savollariga bilim bazasi + playbook asosida javob.

Qat'iy chegara: mahsulot FAKTLARI faqat VERIFIED bilim bazasidan, muloqot uslubi
VERIFIED playbook'dan. AI yangi fakt o'ylab topmaydi; javob bazada bo'lmasa ochiq
tan oladi (escalate) va savol bilim bazasiga `unknown` yozuv sifatida tushadi —
Boss uni mavjud «🔍 Ko'rib chiqish» oqimida to'ldirsa, keyingi safar AI javob
bera oladi (baza shu tarzda uzluksiz o'sadi).

Rejimlar (bot tomonda): SINOV (rahbarlar o'zi sinaydi) va YORDAMCHI (operator
mijoz savolini yozadi, AI rasmiy javob variantini beradi — operator o'zi mijozga
yuboradi). Mijoz bilan to'g'ridan-to'g'ri muloqot rejimi ATAYLAB yo'q.

Har javob ai_message_log'ga yoziladi (kind='sales_ai') — audit."""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services.knowledge import _generate_anthropic_json, _parse_json, ai_available
from api.services.sales_playbook import _generate_gemini_json
from db.models import AiMessageLog, KnowledgeEntry, KnowledgeStatus, PlaybookEntry, User

logger = logging.getLogger(__name__)

MAX_QUESTION_LEN = 1000

_KIND_TITLES = {"etiroz": "E'tiroz bilan ishlash", "uslub": "Uslub", "qoida": "Qoidalar"}


def _system_prompt(kb_text: str, pb_text: str) -> str:
    return (
        "Sen NURLI DIYOR turar-joy majmuasining sotuv bo'yicha yordamchisisan. Quyida "
        "kompaniyaning TASDIQLANGAN bilim bazasi va eng yaxshi sotuvchilardan o'rganilgan "
        "sotuv qo'llanmasi (playbook) berilgan.\n\n"
        "QAT'IY QOIDALAR:\n"
        "1. Mahsulot faktlari (narx, muddat, raqam, shartlar, manzil) uchun FAQAT bilim "
        "bazasidan foydalan — HECH QACHON o'ylab topma, taxmin qilma.\n"
        "2. Javob bazada yo'q bo'lsa ochiq ayt: «bu savolni aniqlashtirib qaytaman» va "
        "escalate=true qaytar.\n"
        "3. Sana ko'rsatilgan (eskirishi mumkin) ma'lumotni aytganda ehtiyot bo'l — "
        "«hozirgi holat bo'yicha» deb qo'shib ayt.\n"
        "4. Mijoz e'tiroz bildirsa playbook'dagi texnikani qo'lla — sotuvchilarimizning "
        "iboralari uslubida, lekin tabiiy qilib.\n"
        "5. Samimiy, hurmatli o'zbek tilida, qisqa yoz (2-6 jumla). «Siz»lab gapir.\n"
        "6. Har javob oxirida bitta keyingi qadam taklif qil (obyektga tashrif, bron, "
        "qo'ng'iroq) — playbook'dagi qoidalarga mos.\n"
        "7. Sotishga intil, lekin yolg'on va'da berma; kompaniya haqida faqat ijobiy, "
        "lekin halol gapir.\n\n"
        f"=== BILIM BAZASI (tasdiqlangan) ===\n{kb_text}\n\n"
        f"=== SOTUV PLAYBOOK (tasdiqlangan) ===\n{pb_text}\n\n"
        "JAVOB FORMATI: faqat JSON qaytar, boshqa matnsiz: "
        '{"javob": "mijozga aytiladigan matn", "escalate": true|false} '
        "(escalate=true — javob bazada topilmadi yoki aniq emas)."
    )


async def build_context(db: AsyncSession) -> tuple[str, str, int, int]:
    """Verified bilim bazasi va playbook'ni prompt matniga yig'adi."""
    entries = list(
        await db.scalars(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.status == KnowledgeStatus.verified.value)
            .order_by(KnowledgeEntry.category, KnowledgeEntry.id)
        )
    )
    kb_lines: list[str] = []
    current_cat = None
    for e in entries:
        if e.category != current_cat:
            current_cat = e.category
            kb_lines.append(f"\n[{current_cat.upper()}]")
        flags = ""
        if e.date_sensitive:
            updated = e.updated_at.strftime("%d.%m.%Y") if e.updated_at else "?"
            flags = f" (sana-sezgir, yangilangan: {updated})"
        kb_lines.append(f"S: {e.question}\nJ: {e.answer}{flags}")

    playbook = list(
        await db.scalars(
            select(PlaybookEntry)
            .where(PlaybookEntry.status == "verified")
            .order_by(PlaybookEntry.kind, PlaybookEntry.id)
        )
    )
    pb_lines: list[str] = []
    current_kind = None
    for p in playbook:
        if p.kind != current_kind:
            current_kind = p.kind
            pb_lines.append(f"\n[{_KIND_TITLES.get(current_kind, current_kind)}]")
        pb_lines.append(f"Vaziyat: {p.situation}\nTexnika: {p.technique}")
        for ph in p.phrases or []:
            src = f" ({ph.get('source')})" if ph.get("source") else ""
            pb_lines.append(f"  Ibora: «{ph.get('text')}»{src}")

    return (
        "\n".join(kb_lines).strip() or "(bo'sh)",
        "\n".join(pb_lines).strip() or "(bo'sh)",
        len(entries),
        len(playbook),
    )


async def _escalate_to_knowledge(db: AsyncSession, question: str, asker: User) -> None:
    """Javobsiz savolni bilim bazasiga unknown yozuv qilib qo'shadi (takror emas).
    Boss uni «🔍 Ko'rib chiqish»da to'ldirgach AI javob bera boshlaydi."""
    norm = " ".join(question.lower().split())[:300]
    existing = list(
        await db.scalars(
            select(KnowledgeEntry.question).where(
                KnowledgeEntry.status == KnowledgeStatus.unknown.value
            )
        )
    )
    if any(" ".join(q.lower().split())[:300] == norm for q in existing):
        return
    db.add(
        KnowledgeEntry(
            kind="single",
            category="umumiy",
            question=question.strip()[:1000],
            answer="",
            status=KnowledgeStatus.unknown.value,
            source=f"Sotuv AI eskalatsiya (so'ragan: {asker.full_name.strip()})",
            source_user_id=asker.id,
        )
    )
    await db.commit()


async def ask(db: AsyncSession, asker: User, question: str) -> dict:
    """Savolga javob. Qaytaradi: {answer, escalate, kb_count, pb_count, ai_ok}."""
    question = (question or "").strip()[:MAX_QUESTION_LEN]
    kb_text, pb_text, kb_count, pb_count = await build_context(db)

    if kb_count == 0:
        return {
            "answer": (
                "Bilim bazasida hali tasdiqlangan ma'lumot yo'q — avval «📚 Bilim bazasi» "
                "bo'limida anketa javoblarini tasdiqlang."
            ),
            "escalate": False,
            "kb_count": 0,
            "pb_count": pb_count,
            "ai_ok": False,
        }

    system = _system_prompt(kb_text, pb_text)
    user_msg = f"Mijoz savoli: {question}"
    text = None
    if ai_available():
        try:
            if settings.ai_provider == "gemini":
                text = await _generate_gemini_json(system, user_msg, 800)
            else:
                text = await _generate_anthropic_json(system, user_msg, 800)
        except Exception:  # noqa: BLE001
            logger.exception("Sotuv AI chaqiruvida xatolik")

    if not text:
        return {
            "answer": "⚠️ AI hozircha javob bera olmadi — birozdan keyin qayta urinib ko'ring.",
            "escalate": False,
            "kb_count": kb_count,
            "pb_count": pb_count,
            "ai_ok": False,
        }

    parsed = _parse_json(text)
    if isinstance(parsed, dict) and parsed.get("javob"):
        answer = str(parsed["javob"]).strip()
        escalate = bool(parsed.get("escalate"))
    else:
        # JSON buzilgan bo'lsa ham matnni yo'qotmaymiz — xom ko'rinishda beramiz
        answer = text.strip()
        escalate = False

    if escalate:
        await _escalate_to_knowledge(db, question, asker)

    db.add(
        AiMessageLog(
            user_id=asker.id,
            kind="sales_ai",
            source="ai",
            text=answer,
            context={
                "savol": question,
                "escalate": escalate,
                "kb_count": kb_count,
                "pb_count": pb_count,
            },
        )
    )
    await db.commit()

    return {
        "answer": answer,
        "escalate": escalate,
        "kb_count": kb_count,
        "pb_count": pb_count,
        "ai_ok": True,
    }
