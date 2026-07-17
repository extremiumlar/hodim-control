"""Sotuv playbook — sotuvchilar uslubini o'rganish (2-bosqich).

Qurish jarayoni og'ir AI ishi bo'lgani uchun cron tick'da bosqichma-bosqich
boradi (knowledge.py bilan bir xil naqsh, cPanel gateway ~180s limiti):

1. `profiles` — har sotuvchining anketa javoblaridan uslub profili (AI): e'tirozga
   yondashuv, ishontirish argumentlari, xarakterli iboralar. Har tick 2 ta profil.
2. `objections` — shortfall_reason erkin matnlaridan REAL mijoz e'tirozlari (AI,
   PII'siz — matnlarda mijoz ismi/telefoni bo'lmaydi, operator o'z so'zlari).
3. `synthesis` — yakuniy playbook: vaziyat → texnika → namunaviy iboralar. ENG
   NATIJALI sotuvchiga og'irlik: oxirgi 60 kun daily_results (suhbat/tashrif) va
   issiq lid tezligi (hot_lead.first_call_sec) deterministik hisoblanadi va AI'ga
   "shu xodim uslubini asos qilib ol" deb beriladi. AI FAKT O'YLAB TOPMAYDI —
   faqat berilgan material (profillar, e'tirozlar, bilim bazasining tasdiqlangan
   e'tiroz javoblari) asosida.

AI 3 urinishda javob bermasa bosqich deterministik fallback bilan o'tib ketadi
(profil bo'sh, e'tirozlar ro'yxati bo'sh) — synthesis ham ishlamasa build failed
bo'lib rahbarga xabar boradi. Tayyor yozuvlar `unverified` — Boss botda tasdiqlaydi;
sotuv AI (3-bosqich) faqat verified yozuvlardan foydalanadi."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services.knowledge import (
    MANAGER_ROLES,
    _generate_anthropic_json,
    _notify_managers,
    _parse_json,
    ai_available,
)
from db.models import (
    AnketaAnswer,
    AnketaAssignment,
    AnketaSession,
    AnketaSessionStatus,
    DailyResult,
    HotLead,
    KnowledgeEntry,
    KnowledgeStatus,
    PlaybookBuild,
    PlaybookEntry,
    ShortfallReason,
    User,
)

logger = logging.getLogger(__name__)

MAX_AI_ATTEMPTS = 3
STATS_DAYS = 60  # natijalar oynasi (suhbat/tashrif)
OBJECTION_DAYS = 90  # operator sabablari oynasi
ACTIVE_STATUSES = ("profiles", "objections", "synthesis")

_SYSTEM = (
    "Sen NURLI DIYOR turar-joy majmuasi sotuv bo'limining metodisti (murabbiy)san. "
    "Vazifang — sotuvchilarning yozganlaridan sotuv uslubini o'rganib chiqarish. "
    "QAT'IY QOIDALAR: (1) faqat berilgan materialdan foydalan — yangi fakt (narx, "
    "muddat, shart) va berilmagan iborani O'YLAB TOPMA; (2) javob faqat so'ralgan "
    "JSON formatida, boshqa matnsiz; (3) o'zbek tilida."
)


async def _generate_gemini_json(system: str, user: str, max_tokens: int) -> str | None:
    """ai_coach._generate_gemini bilan bir xil, lekin maxOutputTokens sozlanadi —
    playbook sinteziga 800 token yetmaydi."""
    if not settings.gemini_api_key:
        return None
    import httpx

    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}},
    }
    timeout = httpx.Timeout(30.0, connect=6.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json=body,
        )
        resp.raise_for_status()
        candidates = resp.json().get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip() or None


async def _generate_json(instruction: str, payload, max_tokens: int = 2500):
    if not ai_available():
        return None
    import json as _json

    user = f"{instruction}\n\nMaterial (JSON):\n{_json.dumps(payload, ensure_ascii=False)}"
    try:
        if settings.ai_provider == "gemini":
            text = await _generate_gemini_json(_SYSTEM, user, max_tokens)
        else:
            text = await _generate_anthropic_json(_SYSTEM, user, max_tokens)
    except Exception:  # noqa: BLE001
        logger.exception("Playbook AI chaqiruvida xatolik")
        return None
    if not text:
        return None
    parsed = _parse_json(text)
    if parsed is None:
        logger.warning("Playbook AI JSON'ini o'qib bo'lmadi: %.200s", text)
    return parsed


# ─── Deterministik statlar (kod hisoblaydi, AI emas) ─────────────────────────

async def _seller_stats(db: AsyncSession, user_ids: list[int]) -> dict[int, dict]:
    """Oxirgi STATS_DAYS kun: suhbat/tashrif yig'indisi + issiq lidga o'rtacha
    birinchi qo'ng'iroq tezligi. Og'irlik uchun asosiy signal — tashrif."""
    since = datetime.utcnow().date() - timedelta(days=STATS_DAYS)
    stats: dict[int, dict] = {uid: {"suhbat": 0, "tashrif": 0, "hot_lead_avg_sec": None} for uid in user_ids}

    rows = await db.execute(
        select(
            DailyResult.user_id,
            func.sum(DailyResult.conversations_count),
            func.sum(DailyResult.visits_count),
        )
        .where(DailyResult.user_id.in_(user_ids), DailyResult.date >= since)
        .group_by(DailyResult.user_id)
    )
    for uid, conv, visits in rows:
        stats[uid]["suhbat"] = int(conv or 0)
        stats[uid]["tashrif"] = int(visits or 0)

    hl_since = datetime.utcnow() - timedelta(days=OBJECTION_DAYS)
    rows = await db.execute(
        select(HotLead.user_id, func.avg(HotLead.first_call_sec), func.count())
        .where(
            HotLead.user_id.in_(user_ids),
            HotLead.first_call_sec.isnot(None),
            HotLead.detected_at >= hl_since,
        )
        .group_by(HotLead.user_id)
    )
    for uid, avg_sec, cnt in rows:
        if cnt:
            stats[uid]["hot_lead_avg_sec"] = int(avg_sec)
    return stats


async def _anketa_answers_for(db: AsyncSession, user_id: int) -> list[dict]:
    """Xodimning anketa javoblari (savol bilan). Tugallanmagan sessiyalar ham
    olinadi — yozilgan javob bor bo'lsa uslubni o'rganish mumkin (bekor
    qilinganlarning javoblari bazadan o'chirilgan, o'zi kirmaydi)."""
    rows = list(
        await db.scalars(
            select(AnketaAnswer)
            .join(AnketaAssignment, AnketaAssignment.id == AnketaAnswer.assignment_id)
            .join(AnketaSession, AnketaSession.id == AnketaAssignment.session_id)
            .where(
                AnketaAssignment.user_id == user_id,
                AnketaSession.status.in_(
                    [AnketaSessionStatus.done.value, AnketaSessionStatus.in_progress.value]
                ),
            )
            .order_by(AnketaAnswer.question_index)
        )
    )
    return [{"savol": r.question_text, "javob": r.answer_text} for r in rows]


# ─── Build boshlash ──────────────────────────────────────────────────────────

async def active_build(db: AsyncSession) -> PlaybookBuild | None:
    return await db.scalar(
        select(PlaybookBuild)
        .where(PlaybookBuild.status.in_(ACTIVE_STATUSES))
        .order_by(PlaybookBuild.id.desc())
    )


async def start_build(db: AsyncSession, actor: User) -> PlaybookBuild:
    """Yangi qurishni boshlaydi: maqsad sotuvchilar (yakunlangan anketa javobi
    borlar) + deterministik natija statlari yig'iladi. Oldingi buildlarning
    TASDIQLANMAGAN yozuvlari o'chiriladi (verified'lar qoladi)."""
    seller_ids = [
        row
        for row in (
            await db.scalars(
                select(AnketaAssignment.user_id)
                .join(AnketaSession, AnketaSession.id == AnketaAssignment.session_id)
                .join(AnketaAnswer, AnketaAnswer.assignment_id == AnketaAssignment.id)
                .where(
                    AnketaSession.status.in_(
                        [AnketaSessionStatus.done.value, AnketaSessionStatus.in_progress.value]
                    )
                )
                .distinct()
            )
        ).all()
    ]
    if not seller_ids:
        raise ValueError("Anketa javoblari yo'q — avval anketa o'tkazilishi kerak.")

    stats = await _seller_stats(db, seller_ids)
    targets = []
    for uid in seller_ids:
        user = await db.get(User, uid)
        if user is None:
            continue
        targets.append({"user_id": uid, "name": user.full_name.strip(), **stats[uid]})
    # Eng natijali sotuvchi — tashrif, teng bo'lsa suhbat bo'yicha
    top = max(targets, key=lambda t: (t["tashrif"], t["suhbat"]), default=None)

    # Eski tasdiqlanmagan yozuvlarni tozalaymiz (yangi build ularni almashtiradi)
    old_unverified = list(
        await db.scalars(select(PlaybookEntry).where(PlaybookEntry.status == "unverified"))
    )
    for e in old_unverified:
        await db.delete(e)

    build = PlaybookBuild(
        created_by=actor.id,
        status="profiles",
        data={"targets": targets, "top_user_id": top["user_id"] if top else None, "profiles": {}, "objections": []},
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)
    return build


# ─── Tick bosqichlari ────────────────────────────────────────────────────────

async def _step_profiles(db: AsyncSession, build: PlaybookBuild, budget: int) -> int:
    """Profili yo'q sotuvchilarni ishlaydi; sarflangan AI chaqiruvlar sonini qaytaradi."""
    used = 0
    data = dict(build.data)
    profiles = dict(data.get("profiles") or {})
    for target in data["targets"]:
        if used >= budget:
            break
        key = str(target["user_id"])
        if key in profiles:
            continue
        answers = await _anketa_answers_for(db, target["user_id"])
        result = await _generate_json(
            f"{target['name']} ismli sotuvchining anketa javoblari berilgan. Uning SOTUV "
            "USLUBINI o'rganib chiq: e'tirozlarga qanday javob beradi, qanday ishontirish "
            "argumentlari va xarakterli iboralari bor, ohangi qanday. Faqat javoblarida "
            "haqiqatan bor narsani yoz. JSON qaytar: "
            '{"summary": "2-3 jumla uslub tavsifi", "objection_style": "e\'tirozga '
            'yondashuvi 1-2 jumla", "phrases": ["javoblaridan olingan 2-5 ta xarakterli '
            'ibora"]}',
            {"sotuvchi": target["name"], "javoblar": answers},
            max_tokens=1200,
        )
        used += 1
        if result is None or not isinstance(result, dict) or "summary" not in result:
            build.ai_attempts += 1
            if build.ai_attempts >= MAX_AI_ATTEMPTS:
                profiles[key] = {"summary": "", "objection_style": "", "phrases": []}
                build.ai_attempts = 0
            break  # shu tickda qayta urinmaymiz (keyingi daqiqada davom etadi)
        profiles[key] = {
            "summary": str(result.get("summary") or ""),
            "objection_style": str(result.get("objection_style") or ""),
            "phrases": [str(p) for p in (result.get("phrases") or [])][:6],
        }
        build.ai_attempts = 0

    data["profiles"] = profiles
    build.data = data
    if all(str(t["user_id"]) in profiles for t in data["targets"]):
        build.status = "objections"
    await db.commit()
    return used


async def _step_objections(db: AsyncSession, build: PlaybookBuild) -> int:
    """Operator sabablaridan real mijoz e'tirozlarini ajratadi (1 AI chaqiruv)."""
    since = datetime.utcnow().date() - timedelta(days=OBJECTION_DAYS)
    texts = [
        t
        for t in (
            await db.scalars(
                select(ShortfallReason.raw_text)
                .where(ShortfallReason.raw_text.isnot(None), ShortfallReason.date >= since)
                .order_by(ShortfallReason.id.desc())
                .limit(120)
            )
        ).all()
        if t and t.strip()
    ]
    data = dict(build.data)
    if not texts:
        data["objections"] = []
        build.data = data
        build.status = "synthesis"
        await db.commit()
        return 0

    result = await _generate_json(
        "Operatorlar reja ortda qolganda yozgan izohlar berilgan. Ulardan faqat MIJOZ "
        "tomonidan aytilgan e'tiroz/to'siqlarni ajrat (masalan: narx qimmat, o'ylab "
        "ko'raman, ishonch yo'q, uzoq, keyin olaman). Operatorning ichki/texnik "
        "sabablarini (baza tugadi, telefon buzildi, yig'ilish) OLMA. JSON qaytar: "
        '{"objections": [{"situation": "mijoz nima deydi", "chastota": "tez-tez"|"ba\'zan"}]}'
        " — ko'pi bilan 10 ta, takrorlarni birlashtir.",
        {"izohlar": texts},
        max_tokens=1200,
    )
    if result is None or not isinstance(result, dict) or "objections" not in result:
        build.ai_attempts += 1
        if build.ai_attempts >= MAX_AI_ATTEMPTS:
            data["objections"] = []
            build.data = data
            build.status = "synthesis"
            build.ai_attempts = 0
        await db.commit()
        return 1

    data["objections"] = [
        {"situation": str(o.get("situation") or ""), "chastota": str(o.get("chastota") or "")}
        for o in (result.get("objections") or [])
        if isinstance(o, dict) and o.get("situation")
    ][:10]
    build.data = data
    build.status = "synthesis"
    build.ai_attempts = 0
    await db.commit()
    return 1


async def _step_synthesis(db: AsyncSession, build: PlaybookBuild) -> int:
    """Yakuniy playbook yozuvlarini quradi (1 AI chaqiruv)."""
    data = build.data
    top_id = data.get("top_user_id")
    top_name = next(
        (t["name"] for t in data["targets"] if t["user_id"] == top_id), None
    )

    # Bilim bazasining tasdiqlangan e'tiroz javoblari — texnikalar faktlarga
    # tayanishi uchun (AI yangi fakt o'ylab topmasin)
    etiroz_entries = list(
        await db.scalars(
            select(KnowledgeEntry)
            .where(
                KnowledgeEntry.status == KnowledgeStatus.verified.value,
                KnowledgeEntry.category.in_(["etiroz", "asosiy"]),
            )
            .limit(20)
        )
    )
    payload = {
        "sotuvchilar": [
            {
                **{k: t[k] for k in ("name", "suhbat", "tashrif", "hot_lead_avg_sec")},
                "profil": data["profiles"].get(str(t["user_id"]), {}),
            }
            for t in data["targets"]
        ],
        "eng_natijali_sotuvchi": top_name,
        "mijoz_etirozlari": data.get("objections") or [],
        "tasdiqlangan_etiroz_javoblari": [
            {"savol": e.question, "javob": e.answer} for e in etiroz_entries
        ],
    }
    weight_rule = (
        f"eng natijali sotuvchi {top_name} uslubini ASOS qilib ol, "
        "boshqalarnikini to'ldiruvchi sifatida ishlat"
        if top_name
        else "profillar asosida tuz"
    )
    result = await _generate_json(
        "Sotuv playbook tuz: har yozuv — vaziyat, texnika (qanday yondashish) va "
        "sotuvchilarning berilgan iboralaridan namunalar. 8-15 ta yozuv. Qoidalar: "
        f"(1) {weight_rule}; "
        "(2) texnika faqat berilgan profil/iboralar/tasdiqlangan javoblarga tayansin — "
        "yangi fakt va yo'q iborani o'ylab topma; (3) mijoz e'tirozlari ro'yxatidagi har "
        "tez-tez uchraydigan e'tirozga kamida bitta yozuv; (4) kind: 'etiroz' (e'tiroz "
        "bilan ishlash), 'uslub' (ohang/muloqot uslubi), 'qoida' (umumiy qoida, masalan "
        "yangi lidga tez qo'ng'iroq — hot_lead_avg_sec berilgan bo'lsa). JSON qaytar: "
        '{"entries": [{"kind": "etiroz", "situation": "...", "technique": "...", '
        '"phrases": [{"text": "...", "source": "sotuvchi ismi"}]}]}',
        payload,
        max_tokens=3000,
    )
    if result is None or not isinstance(result, dict) or not result.get("entries"):
        build.ai_attempts += 1
        if build.ai_attempts >= MAX_AI_ATTEMPTS:
            build.status = "failed"
            build.finished_at = datetime.utcnow()
            await db.commit()
            await _notify_managers(
                db,
                "⚠️ Sotuv playbook qurish muvaffaqiyatsiz — AI javob bermadi. "
                "Keyinroq «🔨 Qurish»ni qayta bosing.",
            )
            return 1
        await db.commit()
        return 1

    created = 0
    for e in result["entries"]:
        if not isinstance(e, dict) or not (e.get("situation") and e.get("technique")):
            continue
        kind = e.get("kind") if e.get("kind") in ("etiroz", "uslub", "qoida") else "etiroz"
        phrases = [
            {"text": str(p.get("text") or ""), "source": str(p.get("source") or "")}
            for p in (e.get("phrases") or [])
            if isinstance(p, dict) and p.get("text")
        ][:5]
        db.add(
            PlaybookEntry(
                build_id=build.id,
                kind=kind,
                situation=str(e["situation"]).strip(),
                technique=str(e["technique"]).strip(),
                phrases=phrases,
            )
        )
        created += 1

    build.status = "done"
    build.finished_at = datetime.utcnow()
    build.ai_attempts = 0
    await db.commit()
    await _notify_managers(
        db,
        f"🧭 <b>Sotuv playbook tayyor</b> — {created} ta yozuv tuzildi"
        + (f" (asos: {top_name} uslubi)" if top_name else "")
        + ".\nBotda «📚 Bilim bazasi» → «🧭 Sotuv playbook» → «🔍 Ko'rib chiqish»da tasdiqlang.",
    )
    return 1


async def process_build(db: AsyncSession, max_ai_calls: int = 2) -> dict:
    build = await active_build(db)
    if build is None:
        return {"active": False}
    used = 0
    if build.status == "profiles":
        used = await _step_profiles(db, build, max_ai_calls)
    elif build.status == "objections":
        used = await _step_objections(db, build)
    elif build.status == "synthesis":
        used = await _step_synthesis(db, build)
    return {"active": True, "status": build.status, "ai_calls": used}
