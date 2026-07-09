"""Operator AI — Claude qatlami (3-bosqich).

Claude RAQAMLARNI HISOBLAMAYDI — hisobni kod qiladi ([[auto_plan]], [[hourly_plan]]).
Claude faqat tayyor AGREGAT profil (PII yo'q: mijoz ismi/telefoni/audio hech qachon
yuborilmaydi) dan odam tilida qisqa matn yozadi. AI o'chiq bo'lsa yoki API xato bersa
har funksiya deterministik (kod) shablonga qaytadi — tizim hech qachon jim qolmaydi.

Uch funksiya: `coach_nudge` (operatorga yo'naltiruvchi), `daily_group_summary`
(guruhga kun yakuni), `weekly_trend` (haftalik). Har chaqiruv `ai_message_log`ga
yoziladi (audit + xotira)."""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from db.models import AiMessageLog

logger = logging.getLogger(__name__)

# Claude'ga beriladigan umumiy qoidalar. Ohang tuzatilgan qaror (dizayn): qo'llab-
# quvvatlovchi, lekin real oqibatli. Maxfiylik: faqat berilgan agregat raqamlar.
_SYSTEM_BASE = (
    "Sen sotuv operatorlariga yordam beradigan qisqa, aniq murabbiysan. O'zbek tilida "
    "yozasan. Senga FAQAT agregat raqamlar beriladi (mijoz ismi/telefoni/audio yo'q) — "
    "berilgan raqamlardan boshqa raqam O'YLAB TOPMA, hisob-kitob qilma. Ohang tartibi "
    "qat'iy: (1) holatni xotirjam ayt, (2) yordam taklif qil ('keling birga tuzataylik' "
    "ruhida, aniq keyingi qadam bilan), (3) faqat oxirida, orqada bo'lsa, kun oxirida "
    "guruhda statistika e'lon qilinishini bir jumlada ayt (do'q emas, real oqibat). "
    "Ayblovchi/kamsituvchi so'zlardan ('atigi', 'qoniqarsiz', 'yomon') qoch. "
    "Faqat matn qaytar, izohsiz. Emoji kam ishlat."
)

_MAX_TOKENS = 350


def _anthropic_client():
    """AsyncAnthropic klienti — kalit bor bo'lsa; aks holda None."""
    if not settings.anthropic_api_key:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic kutubxonasi o'rnatilmagan — fallback ishlatiladi")
        return None
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _generate_anthropic(system: str, user: str) -> str | None:
    client = _anthropic_client()
    if client is None:
        return None
    try:
        resp = await client.messages.create(
            model=settings.ai_model,
            max_tokens=_MAX_TOKENS,
            output_config={"effort": "low"},  # qisqa matn — arzon, tez
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


_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


async def _generate_gemini(system: str, user: str) -> str | None:
    """Gemini REST (generateContent) — SDK'siz, httpx orqali. `thinkingBudget: 0`
    flash modellarda o'ylashni o'chiradi (aks holda output tokenni o'ylashga sarflab
    bo'sh matn qaytarishi mumkin). Bepul tier RPM limiti tor (daqiqasiga ~10 so'rov),
    shuning uchun 429'da bir marta kutib qayta uriniladi — nudge/xulosa interaktiv
    emas (scheduler yuboradi), 20-30s kutish zarar qilmaydi."""
    if not settings.gemini_api_key:
        return None
    import asyncio

    import httpx

    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": 800, "thinkingConfig": {"thinkingBudget": 0}},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(2):
            resp = await client.post(
                f"{_GEMINI_BASE}/models/{settings.gemini_model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key},
                json=body,
            )
            if resp.status_code == 429 and attempt == 0:
                wait = min(float(resp.headers.get("retry-after", 25)), 60)
                logger.warning("Gemini rate limit (429) — %ss kutib qayta urinish", wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            candidates = resp.json().get("candidates") or []
            if not candidates:
                return None
            parts = (candidates[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts).strip() or None
    return None


async def _generate(system: str, payload: dict, instruction: str) -> tuple[str, str] | None:
    """Tanlangan provayderga (system + JSON payload + ko'rsatma) yuborib matn oladi.
    (text, "ai") qaytaradi; AI o'chiq/xato bo'lsa None (chaqiruvchi fallback qiladi)."""
    if not settings.ai_enabled:
        return None
    user = f"{instruction}\n\nMa'lumot (JSON):\n{json.dumps(payload, ensure_ascii=False)}"
    try:
        if settings.ai_provider == "gemini":
            text = await _generate_gemini(system, user)
        else:
            text = await _generate_anthropic(system, user)
        if not text:
            return None
        return text, "ai"
    except Exception:  # noqa: BLE001 — har qanday API/tarmoq xatosida fallback
        logger.exception("AI (%s) chaqiruvida xatolik — fallback ishlatiladi", settings.ai_provider)
        return None


async def _log(db: AsyncSession, user_id: int | None, kind: str, source: str, text: str, context: dict) -> None:
    db.add(AiMessageLog(user_id=user_id, kind=kind, source=source, text=text, context=context))
    await db.commit()


# ─── 1) Operatorga yo'naltiruvchi (soatlik/erta signal) ─────────────────────────
def _fallback_nudge(p: dict) -> str:
    name = p.get("name", "")
    hour = p.get("hour")
    done = p.get("done_so_far", 0)
    need = p.get("planned_so_far", 0)
    delta = done - need
    avg = p.get("avg_talk_sec")
    parts = [f"{name}, soat {hour:02d} da reja {need} edi, {done} ta bo'ldi"] if hour is not None else [
        f"{name}, hozirgacha reja {need}, bajarilgan {done}"]
    if avg is not None and avg > 0:
        parts.append(f"o'rtacha suhbat {avg}s")
    line = ", ".join(parts) + "."
    if delta < 0:
        line += (" Keling birga tuzataylik — keyingi soatda tezlashtiring. "
                 "Aks holda kun oxirida guruhda statistikang e'lon qilinadi.")
    else:
        line += " Yaxshi ketyapsiz, shu tempda davom eting."
    return line


async def coach_nudge(db: AsyncSession, user_id: int | None, payload: dict) -> dict:
    """Operatorga qisqa yo'naltiruvchi. `payload` (PII yo'q): name, hour, planned_so_far,
    done_so_far, avg_talk_sec, short_calls, day_target, day_done."""
    instruction = ("Operatorga bitta qisqa (1-2 jumla) yo'naltiruvchi yoz. Orqada bo'lsa "
                   "('done_so_far' < 'planned_so_far') qo'llab-quvvatlab tuzatishga chaqir va "
                   "guruhda e'lon oqibatini esga ol; oldinda bo'lsa qisqa maqta.")
    result = await _generate(_SYSTEM_BASE, payload, instruction)
    text, source = result if result else (_fallback_nudge(payload), "fallback")
    await _log(db, user_id, "nudge", source, text, payload)
    return {"text": text, "source": source}


# ─── 2) Guruhga kun yakuni xulosasi ─────────────────────────────────────────────
def _fallback_group_summary(p: dict) -> str:
    pct = p.get("team_completion_pct", 0)
    lines = [f"📊 Bugun jamoa rejaning {pct}%ini bajardi."]
    ops = p.get("operators") or []
    top = next((o for o in ops if o.get("top")), None)
    if top:
        lines.append(f"Eng yaxshi: {top.get('name')} ({top.get('done')} ta).")
    behind = [o.get("name") for o in ops if o.get("done", 0) < o.get("target", 0)]
    if behind:
        lines.append("Orqada qolganlar: " + ", ".join(behind) + ".")
    # Kun ichidagi pasayish epizodlari — kod hisoblagan faktlar (soat oralig'i bilan)
    for o in ops:
        for dip in o.get("dips") or []:
            outcome = "keyin to'g'irladi" if dip.get("recovered") else "kun oxirigacha to'g'irlanmadi"
            lines.append(
                f"{o.get('name')} {dip.get('from')}–{dip.get('to')} oralig'ida orqada qoldi, {outcome}."
            )
    reasons = p.get("reasons") or []
    if reasons:
        r = reasons[0]
        lines.append(f"Ko'p uchragan sabab: '{r.get('reason')}' ({r.get('count')} operator).")
    return " ".join(lines)


async def daily_group_summary(db: AsyncSession, payload: dict) -> dict:
    """Guruhga kun yakuni xulosasi. `payload`: date, team_completion_pct,
    operators[{name,done,target,avg_talk,dips,top}], reasons[{reason,count}].
    `dips` — kod hisoblagan kun ichidagi pasayish epizodlari (from/to soat,
    recovered, max_gap_calls): AI shulardan ANIQ faktli xulosa yozadi."""
    instruction = (
        "Guruhga kun yakuni xulosasini yoz (3-5 jumla): jamoa foizi, eng kuchli operator, "
        "orqada qolganlar va (bo'lsa) jamlangan sabab. Har operatordagi 'dips' ro'yxati — kun "
        "ichidagi pasayish epizodlari (from/to soat oralig'i, recovered, max_gap_calls). Dips "
        "bo'lgan operatorni ANIQ VAQTI bilan ayt: recovered=true bo'lsa \"14:00–16:00 oralig'ida "
        "orqada qoldi, keyin to'g'irladi\" ruhida (bu yaxshi holat — ta'kidla), recovered=false "
        "bo'lsa pasayish kun oxirigacha to'g'irlanmaganini ayt. Dips bo'sh bo'lsa u operator "
        "haqida pasayish yozma. FAQAT berilgan raqam, soat va ismlarni ishlat — taxmin qilma, "
        "yangi raqam hisoblama. Ayblovsiz, faktlarga asoslangan."
    )
    result = await _generate(_SYSTEM_BASE, payload, instruction)
    text, source = result if result else (_fallback_group_summary(payload), "fallback")
    await _log(db, None, "group_summary", source, text, payload)
    return {"text": text, "source": source}


# ─── Sabab tahlili (erkin matn) ────────────────────────────────────────────────
# Operator orqada qolganda sababini tugma emas, O'Z SO'ZLARI bilan yozadi; AI matnni
# quyidagi toifalardan biriga tasniflaydi. Tekshiruv (CRM/raqamlar) AI emas — KOD
# qiladi (ai_watch router): AI faqat "nima deyilgan"ni tushunadi, hukmni faktlar chiqaradi.
REASON_CATEGORIES: dict[str, str] = {
    "no_answer": "Mijozlar ko'tarmadi",
    "no_base": "Lid/baza tugadi",
    "tech": "Texnik muammo",
    "meeting": "Yig'ilish/boshqa vazifa",
    "other": "Boshqa",
}

_CLASSIFY_SYSTEM = (
    "Sen sotuv operatorining 'nega rejadan orqadaman' degan izohini tasniflaydigan "
    "yordamchisan. Matn o'zbek (lotin/kirill), rus yoki aralash tilda bo'lishi mumkin. "
    "FAQAT quyidagi JSON'ni qaytar, boshqa hech narsa yozma:\n"
    '{"category": "no_answer|no_base|tech|meeting|other", "summary": "<izohning 60 belgigacha qisqa mazmuni, o\'zbekcha>"}\n'
    "Toifalar: no_answer — mijozlar telefonni ko'tarmayapti/javob bermayapti; "
    "no_base — qo'ng'iroq qiladigan lid/baza/kontakt qolmagan yoki tugagan; "
    "tech — texnik muammo (telefon, internet, CRM, SIM...); "
    "meeting — yig'ilish, o'qitish yoki boshqa topshiriq bilan band bo'lgan; "
    "other — yuqoridagilarga tushmaydi (shaxsiy sabab, tushuntirishsiz va h.k.)."
)

# AI ishlamasa (o'chiq/xato) — sodda kalit so'z tasniflagichi, tizim jim qolmaydi.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("no_base", ("lid", "baza", "kontakt", "raqam qolma", "база", "лид")),
    ("no_answer", ("ko'tarma", "kotarma", "olmayap", "javob berm", "не берут", "не отвеча", "kutarma")),
    ("tech", ("texnik", "internet", "telefon", "sim", "crm", "tizim", "ishlamay", "не работает")),
    ("meeting", ("yig'ilish", "yigilish", "majlis", "planyorka", "uchrashuv", "o'qitish", "собрание")),
]


def _keyword_category(text: str) -> str:
    low = text.lower()
    for category, keys in _KEYWORD_RULES:
        if any(k in low for k in keys):
            return category
    return "other"


async def classify_reason_text(text: str) -> dict:
    """Operator yozgan erkin matnni toifalaydi. Qaytaradi:
    {"category": str, "label": str, "summary": str, "source": "ai"|"fallback"}."""
    result = await _generate(_CLASSIFY_SYSTEM, {"izoh": text[:500]}, "Izohni tasnifla.")
    if result:
        raw = result[0].strip()
        # Model ba'zan ```json ... ``` o'rab qaytaradi — qavslar orasini olamiz
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                category = parsed.get("category")
                if category in REASON_CATEGORIES:
                    return {
                        "category": category,
                        "label": REASON_CATEGORIES[category],
                        "summary": str(parsed.get("summary") or "")[:80],
                        "source": "ai",
                    }
            except (json.JSONDecodeError, TypeError):
                logger.warning("Sabab tasnifi JSON emas — kalit so'z fallback: %r", raw[:200])
    category = _keyword_category(text)
    return {"category": category, "label": REASON_CATEGORIES[category], "summary": text[:80], "source": "fallback"}


def _fallback_reason_reply(p: dict) -> str:
    label = p.get("label", "")
    note = p.get("verify_note") or ""
    verified = p.get("verified")
    if verified is False:
        return (
            f"Sababingiz qayd etildi ({label}), lekin tekshiruv boshqacha ko'rsatyapti: {note}. "
            "Iltimos, ishni davom ettiring — bu holat rahbarga ham yuborildi."
        )
    if verified is True:
        return f"Rahmat, sabab tasdiqlandi: {label} ({note}). Rahbar xabardor qilinadi — bu sizning aybingiz emas."
    if p.get("pending_manager"):
        return (
            f"Rahmat, sabab qayd etildi: {label}. Uni avtomatik tekshirib bo'lmadi, shuning uchun "
            "tasdiqlash uchun rahbarga yuborildi — natijasi haqida xabar beramiz."
        )
    return f"Rahmat, sabab qayd etildi: {label}. Rahbar kun yakunida ko'rib chiqadi."


async def reason_reply(db: AsyncSession, user_id: int | None, payload: dict) -> dict:
    """Tekshiruv yakunidan keyin operatorga yuboriladigan javob matni. `payload`:
    label, raw_text, verified (true/false/null), verify_note, planned_so_far,
    done_so_far, calls_dialed. Hukm allaqachon KODda chiqarilgan — AI faqat shu
    faktlarni odam tilida yetkazadi (yangi fakt/raqam o'ylab topmaydi)."""
    instruction = (
        "Operator orqada qolish sababini yozdi, tizim uni tekshirdi. Natijaga qarab 1-3 jumla javob yoz. "
        "verified=false bo'lsa: xushmuomala lekin qat'iy ohangda tekshiruv fakti ('verify_note') izoh bilan "
        "mos kelmasligini ayt, ishni davom ettirishga chaqir va bu holat rahbarga yuborilganini ayt — ayblovchi "
        "so'z ishlatma, faqat faktni ko'rsat. verified=true bo'lsa: sababi tasdiqlanganini, aybi yo'qligini va "
        "rahbar xabardor qilinishini ayt. verified=null bo'lsa: sabab qayd etilganini va rahbar ko'rishini ayt."
    )
    result = await _generate(_SYSTEM_BASE, payload, instruction)
    text, source = result if result else (_fallback_reason_reply(payload), "fallback")
    await _log(db, user_id, "reason_reply", source, text, payload)
    return {"text": text, "source": source}


# ─── 3) Haftalik trend ──────────────────────────────────────────────────────────
def _fallback_weekly(p: dict) -> str:
    name = p.get("name", "")
    t0 = p.get("talk_start_sec")
    t1 = p.get("talk_end_sec")
    line = f"{name}, haftalik xulosa: "
    if t0 is not None and t1 is not None:
        trend = "o'sdi" if t1 > t0 else ("pasaydi" if t1 < t0 else "barqaror")
        line += f"o'rtacha suhbat {t0}s → {t1}s ({trend})."
    else:
        line += "ma'lumot yig'ilmoqda."
    weak = p.get("weak_slot")
    if weak:
        line += f" Zaif nuqta: {weak}."
    return line


async def weekly_trend(db: AsyncSession, user_id: int | None, payload: dict) -> dict:
    """Operatorga haftalik trend xulosasi. `payload`: name, talk_start_sec,
    talk_end_sec, calls_avg, weak_slot."""
    instruction = ("Operatorga haftalik qisqa xulosa yoz (1-2 jumla): o'sish/pasayishni "
                   "ta'kidla, zaif nuqta bo'lsa ayt. Ruhlantiruvchi ohang.")
    result = await _generate(_SYSTEM_BASE, payload, instruction)
    text, source = result if result else (_fallback_weekly(payload), "fallback")
    await _log(db, user_id, "weekly", source, text, payload)
    return {"text": text, "source": source}
