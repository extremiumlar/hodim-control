"""Sotuv bilim bazasi servisi — anketa javoblarini tartibli bazaga aylantirish.

Uch qadam (og'ir AI ishi cron tick'ka bo'lingan — cPanel gateway ~180s HTTP
limiti sababli bitta so'rovda hammasini qilib bo'lmaydi, ecb9413 naqshi):

1. `create_drafts` (tez, AI'siz) — yakunlangan anketa sessiyalari javoblaridan
   draft yozuvlar: A qism (hammada bir xil savol) `common` guruhlar, C qism
   (ochiq savollar) `open`, qolganlari `single`.
2. `process_batch` (har daqiqa /knowledge/tick, chegaralangan AI chaqiruvlar) —
   common guruhlarni birlashtiradi (yoki conflict), open javoblarni alohida
   savol-javob juftlarga ajratadi, single'larni tasniflaydi (unknown/sana-sezgir).
   AI FAKT QO'SHMAYDI — faqat tozalaydi/guruhlaydi. AI 3 urinishda ham javob
   bermasa deterministik fallback (yozuvlar aslicha unverified bo'ladi) — tizim
   hech qachon tiqilib qolmaydi (ai_coach konventsiyasi).
3. Hammasi tayyor bo'lgach boss/dasturchi'ga bot xabari — ular botda ko'rib
   tasdiqlaydi; sotuv AI'ga (2-3 bosqich) faqat verified yozuvlar beriladi.
"""
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services.ai_coach import _generate_gemini
from api.services.anketa_data import toplam_questions
from api.telegram_notify import send_message
from db.models import (
    AnketaAnswer,
    AnketaAssignment,
    AnketaSession,
    AnketaSessionStatus,
    AnketaTemplate,
    KnowledgeEntry,
    KnowledgeStatus,
    Role,
    User,
)

logger = logging.getLogger(__name__)

# Rahbar rollari — bilim bazasini boshqaradi va bildirishnoma oladi
MANAGER_ROLES = {Role.boss.value, Role.dasturchi.value}

CATEGORIES = [
    "asosiy", "kompaniya", "qurilish", "xonadon", "narx",
    "topshirish", "hudud", "jarayon", "etiroz", "ochiq", "umumiy",
]

_CATEGORY_BY_SECTION = {
    "Kompaniya va ishonch": "kompaniya",
    "Qurilish va texnik": "qurilish",
    "Xonadon va ta'mir": "xonadon",
    "Narx va to'lov": "narx",
    "Topshirish va muddat": "topshirish",
    "Hudud va infratuzilma": "hudud",
    "Jarayon va aloqa": "jarayon",
    "Qiyin savollar va e'tirozlar": "etiroz",
}

# AI ishlovi sozlamalari
MAX_AI_ATTEMPTS = 3  # shundan keyin deterministik fallback
CLASSIFY_BATCH = 8  # bitta AI chaqiruvida tasniflanadigan single yozuvlar
STALE_DAYS = 30  # sana-sezgir yozuv shu muddatdan keyin qayta tekshirishga chiqadi

# Yuklangan to'plamlarda "ochiq" savolni taxminlash: bitta javobda bir nechta
# savol-javob juftini so'raydigan matnlar ("3-5 ta savolni yozing" kabi)
_OPEN_HINT_RE = re.compile(r"\d\s*[-–]\s*\d\s*ta|sanab\s+yozing|ro'?yxat", re.I)

_UNKNOWN_MARKERS = (
    "bilmayman", "bilmadim", "aniq emas", "ma'lumotim yo'q", "malumotim yo'q",
    "javob yo'q", "bilmiman",
)


def heuristic_unknown(text: str) -> bool:
    """Kod darajasidagi 'javob yo'q' aniqlagichi (AI'siz ham ishlaydi)."""
    t = (text or "").strip().lower()
    if len(t) < 8:
        return True
    return any(m in t for m in _UNKNOWN_MARKERS)


def _category_for_section(section: str) -> str:
    if section.startswith("A qism"):
        return "asosiy"
    if section.startswith("C qism"):
        return "ochiq"
    tail = section.split("·", 1)[-1].strip()
    return _CATEGORY_BY_SECTION.get(tail, "umumiy")


# ─── AI chaqiruv qatlami ─────────────────────────────────────────────────────

_JSON_SYSTEM = (
    "Sen NURLI DIYOR turar-joy majmuasi sotuv bo'limining ma'lumot tahrirchisisan. "
    "Xodimlar anketada yozgan javoblarni tartibga solasan. QAT'IY QOIDALAR: "
    "(1) hech qanday yangi FAKT (narx, raqam, muddat, shart) qo'shma va mavjudini "
    "o'zgartirma — faqat tozalash, birlashtirish, guruhlash mumkin; "
    "(2) javob faqat so'ralgan JSON formatida bo'lsin, boshqa matn/izoh yozma; "
    "(3) o'zbek tilida."
)


async def _generate_anthropic_json(system: str, user: str, max_tokens: int) -> str | None:
    """ai_coach._generate_anthropic bilan bir xil naqsh, lekin kengroq max_tokens —
    birlashtirilgan javob/ajratilgan juftlar 350 tokenga sig'maydi."""
    if not settings.anthropic_api_key:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic kutubxonasi o'rnatilmagan")
        return None
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        resp = await client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip() or None
    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001
                pass


def _parse_json(text: str):
    """AI javobidan JSON ajratadi (```json ... ``` o'ramlarini ham ko'taradi)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    if start == -1:
        return None
    try:
        return json.loads(t[start:])
    except json.JSONDecodeError:
        return None


def ai_available() -> bool:
    return settings.ai_enabled


async def _generate_json(instruction: str, payload, max_tokens: int = 1200):
    """Tanlangan provayderdan JSON javob oladi; xato/o'chiq bo'lsa None
    (chaqiruvchi ai_attempts hisoblab fallback'ga o'tadi)."""
    if not ai_available():
        return None
    user = f"{instruction}\n\nMa'lumot (JSON):\n{json.dumps(payload, ensure_ascii=False)}"
    try:
        if settings.ai_provider == "gemini":
            text = await _generate_gemini(_JSON_SYSTEM, user)
        else:
            text = await _generate_anthropic_json(_JSON_SYSTEM, user, max_tokens)
    except Exception:  # noqa: BLE001 — har qanday API/tarmoq xatosida retry/fallback
        logger.exception("Bilim bazasi AI chaqiruvida xatolik")
        return None
    if not text:
        return None
    parsed = _parse_json(text)
    if parsed is None:
        logger.warning("Bilim bazasi AI JSON'ini o'qib bo'lmadi: %.200s", text)
    return parsed


# ─── 1-qadam: draft yaratish (AI'siz, tez) ───────────────────────────────────

async def create_drafts(db: AsyncSession) -> dict:
    """Anketa javoblaridan draft yozuvlar yaratadi. Javob darajasida idempotent
    (AnketaAnswer.ingested_at) — shuning uchun TUGALLANMAGAN (in_progress)
    sessiyani ham qisman yuklash mumkin: hozirgacha yozilgan javoblar olinadi,
    keyin xodimlar davom etsa keyingi yuklash faqat yangi javoblarni qo'shadi."""
    sessions = list(
        await db.scalars(
            select(AnketaSession).where(
                AnketaSession.status.in_(
                    [AnketaSessionStatus.done.value, AnketaSessionStatus.in_progress.value]
                )
            )
        )
    )
    if not sessions:
        return {"created": 0, "sessions": []}

    created = 0
    touched_sessions: list[int] = []
    for session in sessions:
        session_created = 0
        assignments = list(
            await db.scalars(
                select(AnketaAssignment).where(AnketaAssignment.session_id == session.id)
            )
        )
        # Nechta xodim AYNAN bir xil savol to'plamini olgan — shu holda bir xil
        # indeksdagi savol hammada bir xil bo'ladi va javoblar birlashtiriladi
        set_counts: dict[tuple, int] = {}
        for a in assignments:
            key = ("t", a.template_id) if a.template_id else ("n", a.toplam)
            set_counts[key] = set_counts.get(key, 0) + 1

        for a in assignments:
            user = await db.get(User, a.user_id)
            name = user.full_name.strip() if user else "?"
            if a.template_id:
                template = await db.get(AnketaTemplate, a.template_id)
                questions = list(template.questions or []) if template else []
                set_label = template.name if template else "To'plam"
            else:
                questions = toplam_questions(a.toplam)
                set_label = f"№{a.toplam}"
            shared = set_counts.get(
                ("t", a.template_id) if a.template_id else ("n", a.toplam), 1
            ) > 1
            answers = list(
                await db.scalars(
                    select(AnketaAnswer)
                    .where(
                        AnketaAnswer.assignment_id == a.id,
                        AnketaAnswer.ingested_at.is_(None),
                    )
                    .order_by(AnketaAnswer.question_index)
                )
            )
            for ans in answers:
                q = questions[ans.question_index] if ans.question_index < len(questions) else None
                section = q["section"] if q else ""
                if a.template_id:
                    # Yuklangan to'plam: bir xil to'plamni bir necha xodim olgan
                    # bo'lsa, bir xil indeksdagi savol ham bir xil — birlashtiramiz
                    if shared:
                        kind = "common"
                        group_key = f"common:{session.id}:t{a.template_id}:{ans.question_index}"
                    elif _OPEN_HINT_RE.search(ans.question_text):
                        kind, group_key = "open", None
                    else:
                        kind, group_key = "single", None
                elif ans.question_index < 3:
                    # Ichki 5 to'plamning A qismi hamma to'plamda bir xil
                    kind, group_key = "common", f"common:{session.id}:{ans.question_index}"
                elif shared:
                    kind = "common"
                    group_key = f"common:{session.id}:n{a.toplam}:{ans.question_index}"
                elif section.startswith("C qism"):
                    kind, group_key = "open", None
                else:
                    kind, group_key = "single", None
                db.add(
                    KnowledgeEntry(
                        kind=kind,
                        group_key=group_key,
                        category=_category_for_section(section),
                        question=ans.question_text,
                        answer=ans.answer_text,
                        status=KnowledgeStatus.draft.value,
                        source=f"Anketa {set_label}, savol {ans.question_index + 1}: {name}",
                        source_user_id=a.user_id,
                        session_id=session.id,
                        anketa_answer_id=ans.id,
                    )
                )
                ans.ingested_at = datetime.utcnow()
                created += 1
                session_created += 1
        if session_created:
            touched_sessions.append(session.id)
    await db.commit()
    return {"created": created, "sessions": touched_sessions}


# ─── 2-qadam: AI ishlovi (cron tick, chegaralangan) ──────────────────────────

async def _finish_common_group(db: AsyncSession, members: list[KnowledgeEntry]) -> bool:
    """Bitta common guruhni AI bilan birlashtiradi. True — birlik bajarildi
    (muvaffaqiyat yoki yakuniy fallback), False — AI xatosi, keyin qayta uriniladi."""
    payload = {
        "savol": members[0].question,
        "javoblar": [
            {"xodim": m.source.split(": ", 1)[-1], "javob": m.answer} for m in members
        ],
    }
    result = await _generate_json(
        "Bir xil savolga bir nechta xodim javob bergan. Solishtir: agar javoblar mazmunan "
        "MOS bo'lsa ularni BITTA rasmiy kanonik javobga birlashtir (faqat berilgan "
        "ma'lumotdan, hech narsa qo'shmasdan; 'aniq bilmayman' deganlarni e'tiborsiz "
        "qoldir). Agar javoblar bir-biriga ZID bo'lsa (har xil faktlar) — 'conflict'. "
        "Hamma javob bo'sh/bilmayman bo'lsa — 'unknown'. JSON qaytar: "
        '{"result": "merged"|"conflict"|"unknown", "answer": "birlashtirilgan javob '
        '(merged bo\'lsa)", "note": "qisqa izoh (qaysi javoblar farq qildi)", '
        '"date_sensitive": true|false}',
        payload,
    )

    if result is None or not isinstance(result, dict) or "result" not in result:
        for m in members:
            m.ai_attempts += 1
        if members[0].ai_attempts < MAX_AI_ATTEMPTS:
            await db.commit()
            return False
        # Yakuniy fallback: birlashtirmasdan har birini alohida ko'rib chiqishga
        for m in members:
            m.status = (
                KnowledgeStatus.unknown.value
                if heuristic_unknown(m.answer)
                else KnowledgeStatus.unverified.value
            )
            m.review_note = "AI birlashtira olmadi — qo'lda solishtiring (bir xil savol)."
        await db.commit()
        return True

    verdict = result.get("result")
    note = str(result.get("note") or "")[:1000]
    if verdict == "merged" and (result.get("answer") or "").strip():
        first = members[0]
        db.add(
            KnowledgeEntry(
                kind="common",
                group_key=None,
                category=first.category,
                question=first.question,
                answer=str(result["answer"]).strip(),
                status=KnowledgeStatus.unverified.value,
                date_sensitive=bool(result.get("date_sensitive")),
                source="Anketa (A qism, 5 xodim javobi birlashtirilgan)",
                session_id=first.session_id,
                review_note=note or None,
            )
        )
        for m in members:
            await db.delete(m)
    elif verdict == "unknown":
        first = members[0]
        db.add(
            KnowledgeEntry(
                kind="common",
                category=first.category,
                question=first.question,
                answer="",
                status=KnowledgeStatus.unknown.value,
                source="Anketa (A qism — hech kim aniq javob bermagan)",
                session_id=first.session_id,
                review_note=note or None,
            )
        )
        for m in members:
            await db.delete(m)
    else:  # conflict
        for m in members:
            m.status = KnowledgeStatus.conflict.value
            m.review_note = note or "Xodimlar javoblari zid — to'g'risini tanlang/yozing."
    await db.commit()
    return True


async def _finish_open_entry(db: AsyncSession, entry: KnowledgeEntry) -> bool:
    """C qism ochiq javobini alohida savol-javob juftlarga ajratadi."""
    payload = {"savol": entry.question, "xodim_javobi": entry.answer}
    result = await _generate_json(
        "Xodim ochiq savolga mijozlardan keladigan savallar va (bo'lsa) javoblarini "
        "yozgan. Matndan alohida SAVOL-JAVOB juftlarini ajrat. Javobi yozilmagan savol "
        "uchun javobni bo'sh qoldir. Hech narsa o'ylab topma — faqat matndagi ma'lumot. "
        f"Kategoriyani shu ro'yxatdan tanla: {', '.join(CATEGORIES)}. JSON qaytar: "
        '{"pairs": [{"question": "...", "answer": "...", "category": "...", '
        '"date_sensitive": true|false}], "note": "izoh"} — matnda hech qanday '
        'foydali savol bo\'lmasa pairs bo\'sh bo\'lsin.',
        payload,
    )

    if result is None or not isinstance(result, dict) or "pairs" not in result:
        entry.ai_attempts += 1
        if entry.ai_attempts < MAX_AI_ATTEMPTS:
            await db.commit()
            return False
        entry.kind = "single"
        entry.status = (
            KnowledgeStatus.unknown.value
            if heuristic_unknown(entry.answer)
            else KnowledgeStatus.unverified.value
        )
        entry.review_note = "AI ajrata olmadi — xom ko'rinishda (ochiq javob)."
        await db.commit()
        return True

    pairs = [
        p for p in (result.get("pairs") or [])
        if isinstance(p, dict) and (p.get("question") or "").strip()
    ]
    for p in pairs:
        answer_text = str(p.get("answer") or "").strip()
        category = p.get("category") if p.get("category") in CATEGORIES else "umumiy"
        db.add(
            KnowledgeEntry(
                kind="single",
                category=category,
                question=str(p["question"]).strip(),
                answer=answer_text,
                status=(
                    KnowledgeStatus.unknown.value
                    if not answer_text or heuristic_unknown(answer_text)
                    else KnowledgeStatus.unverified.value
                ),
                date_sensitive=bool(p.get("date_sensitive")),
                source=f"{entry.source} (ochiq javobdan ajratilgan)",
                source_user_id=entry.source_user_id,
                session_id=entry.session_id,
                anketa_answer_id=entry.anketa_answer_id,
            )
        )
    await db.delete(entry)  # xom open yozuv o'rnini juftlar egalladi
    await db.commit()
    return True


async def _finish_single_batch(db: AsyncSession, entries: list[KnowledgeEntry]) -> bool:
    """Single draft'lar to'plamini tasniflaydi: unknown va sana-sezgirlik."""
    payload = [
        {"id": e.id, "savol": e.question, "javob": e.answer} for e in entries
    ]
    result = await _generate_json(
        "Har bir yozuv uchun ayt: (a) unknown — javob aslida yo'q/taxminiy/'bilmayman' "
        "bo'lsa true; (b) date_sensitive — javobda vaqt o'tishi bilan eskiradigan "
        "ma'lumot (narx, muddat, qurilish bosqichi, aksiya) bo'lsa true. JSON massiv "
        'qaytar: [{"id": 1, "unknown": false, "date_sensitive": true}, ...]',
        payload,
        max_tokens=800,
    )

    by_id = {}
    if isinstance(result, list):
        by_id = {r.get("id"): r for r in result if isinstance(r, dict)}

    if not by_id:
        for e in entries:
            e.ai_attempts += 1
        if entries[0].ai_attempts < MAX_AI_ATTEMPTS:
            await db.commit()
            return False
        for e in entries:  # yakuniy fallback: faqat evristika
            e.status = (
                KnowledgeStatus.unknown.value
                if heuristic_unknown(e.answer)
                else KnowledgeStatus.unverified.value
            )
        await db.commit()
        return True

    for e in entries:
        r = by_id.get(e.id, {})
        unknown = bool(r.get("unknown")) or heuristic_unknown(e.answer)
        e.status = KnowledgeStatus.unknown.value if unknown else KnowledgeStatus.unverified.value
        e.date_sensitive = bool(r.get("date_sensitive"))
    await db.commit()
    return True


async def _notify_managers(db: AsyncSession, text: str) -> None:
    managers = list(
        await db.scalars(
            select(User).where(
                User.role.in_(MANAGER_ROLES), User.telegram_id.isnot(None), User.is_active.is_(True)
            )
        )
    )
    for m in managers:
        await send_message(m.telegram_id, text)


async def status_counts(db: AsyncSession) -> dict:
    rows = list(
        await db.execute(
            select(KnowledgeEntry.status, func.count()).group_by(KnowledgeEntry.status)
        )
    )
    return {status: count for status, count in rows}


async def process_batch(db: AsyncSession, max_ai_calls: int = 3) -> dict:
    """Chegaralangan AI ishlovi — har chaqiruvda ko'pi bilan `max_ai_calls` AI
    so'rovi (har biri ~≤20s, HTTP tick timeout'iga bemalol sig'adi). Draft
    qolmagach rahbarlarga bir marta xabar yuboradi."""
    processed = 0
    calls = 0

    while calls < max_ai_calls:
        # 1) common guruhlar
        group_key = await db.scalar(
            select(KnowledgeEntry.group_key)
            .where(
                KnowledgeEntry.status == KnowledgeStatus.draft.value,
                KnowledgeEntry.group_key.isnot(None),
            )
            .order_by(KnowledgeEntry.group_key)
            .limit(1)
        )
        if group_key:
            members = list(
                await db.scalars(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.group_key == group_key,
                        KnowledgeEntry.status == KnowledgeStatus.draft.value,
                    )
                )
            )
            calls += 1
            if await _finish_common_group(db, members):
                processed += 1
            continue

        # 2) open yozuvlar
        open_entry = await db.scalar(
            select(KnowledgeEntry)
            .where(
                KnowledgeEntry.status == KnowledgeStatus.draft.value,
                KnowledgeEntry.kind == "open",
            )
            .order_by(KnowledgeEntry.id)
            .limit(1)
        )
        if open_entry:
            calls += 1
            if await _finish_open_entry(db, open_entry):
                processed += 1
            continue

        # 3) single to'plami
        singles = list(
            await db.scalars(
                select(KnowledgeEntry)
                .where(
                    KnowledgeEntry.status == KnowledgeStatus.draft.value,
                    KnowledgeEntry.kind == "single",
                )
                .order_by(KnowledgeEntry.id)
                .limit(CLASSIFY_BATCH)
            )
        )
        if singles:
            calls += 1
            if await _finish_single_batch(db, singles):
                processed += 1
            continue

        break  # draft qolmadi

    remaining = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.status == KnowledgeStatus.draft.value
        )
    )
    notified = False
    if processed and not remaining:
        counts = await status_counts(db)
        await _notify_managers(
            db,
            "📚 <b>Bilim bazasi tayyor</b> — anketa javoblari qayta ishlandi.\n"
            f"Ko'rib chiqish kutmoqda: {counts.get('unverified', 0)} ta · "
            f"bilim bo'shlig'i: {counts.get('unknown', 0)} ta · "
            f"ziddiyat: {counts.get('conflict', 0)} ta.\n"
            "Botda «📚 Bilim bazasi» → «🔍 Ko'rib chiqish» bo'limiga kiring.",
        )
        notified = True

    return {"processed": processed, "remaining": remaining or 0, "notified": notified}


# ─── 3-qadam: eskirgan sana-sezgir yozuvlar (kunlik) ─────────────────────────

async def stale_check(db: AsyncSession) -> dict:
    """Verified + sana-sezgir yozuvlar STALE_DAYS'dan eskirsa needs_recheck
    belgilaydi va rahbarlarga BIR MARTA eslatma yuboradi."""
    threshold = datetime.utcnow() - timedelta(days=STALE_DAYS)
    stale = list(
        await db.scalars(
            select(KnowledgeEntry).where(
                KnowledgeEntry.status == KnowledgeStatus.verified.value,
                KnowledgeEntry.date_sensitive.is_(True),
                KnowledgeEntry.updated_at < threshold,
                KnowledgeEntry.recheck_notified_at.is_(None),
            )
        )
    )
    if not stale:
        return {"flagged": 0}
    for e in stale:
        e.needs_recheck = True
        e.recheck_notified_at = datetime.utcnow()
    await db.commit()

    lines = [f"• {e.question[:80]}" for e in stale[:10]]
    if len(stale) > 10:
        lines.append(f"... va yana {len(stale) - 10} ta")
    await _notify_managers(
        db,
        f"⏰ <b>Bilim bazasi: {len(stale)} ta sana-sezgir yozuv {STALE_DAYS} kundan "
        "eskirdi</b> — narx/muddat o'zgargan bo'lishi mumkin, tekshirib yangilang:\n"
        + "\n".join(lines),
    )
    return {"flagged": len(stale)}
