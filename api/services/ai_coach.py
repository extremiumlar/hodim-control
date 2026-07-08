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
    "berilgan raqamlardan boshqa raqam O'YLAB TOPMA, hisob-kitob qilma. Ohang: avval "
    "qo'llab-quvvatlovchi ('keling birga tuzataylik'), lekin natija bo'lmasa kun oxirida "
    "guruhda statistika e'lon qilinishini ochiq, xotirjam ayt (do'q emas, real oqibat). "
    "Faqat matn qaytar, izohsiz. Emoji kam ishlat."
)

_MAX_TOKENS = 350


def _client():
    """AsyncAnthropic klienti — AI yoqilgan va kalit bor bo'lsa; aks holda None."""
    if not settings.ai_enabled or not settings.anthropic_api_key:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic kutubxonasi o'rnatilmagan — fallback ishlatiladi")
        return None
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _generate(system: str, payload: dict, instruction: str) -> tuple[str, str] | None:
    """Claude'ga (system + JSON payload + ko'rsatma) yuborib matn oladi.
    (text, "ai") qaytaradi; AI o'chiq/xato bo'lsa None (chaqiruvchi fallback qiladi)."""
    client = _client()
    if client is None:
        return None
    user = f"{instruction}\n\nMa'lumot (JSON):\n{json.dumps(payload, ensure_ascii=False)}"
    try:
        resp = await client.messages.create(
            model=settings.ai_model,
            max_tokens=_MAX_TOKENS,
            output_config={"effort": "low"},  # qisqa matn — arzon, tez
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        if not text:
            return None
        return text, "ai"
    except Exception:  # noqa: BLE001 — har qanday API/tarmoq xatosida fallback
        logger.exception("Claude chaqiruvida xatolik — fallback ishlatiladi")
        return None
    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001
                pass


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
    reasons = p.get("reasons") or []
    if reasons:
        r = reasons[0]
        lines.append(f"Ko'p uchragan sabab: '{r.get('reason')}' ({r.get('count')} operator).")
    return " ".join(lines)


async def daily_group_summary(db: AsyncSession, payload: dict) -> dict:
    """Guruhga kun yakuni xulosasi. `payload`: date, team_completion_pct,
    operators[{name,done,target,avg_talk,top}], reasons[{reason,count}]."""
    instruction = ("Guruhga kun yakuni xulosasini yoz (2-4 jumla): jamoa foizi, eng kuchli "
                   "operator, orqada qolganlar va (bo'lsa) jamlangan sabab. Ayblovsiz, "
                   "faktlarga asoslangan.")
    result = await _generate(_SYSTEM_BASE, payload, instruction)
    text, source = result if result else (_fallback_group_summary(payload), "fallback")
    await _log(db, None, "group_summary", source, text, payload)
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
