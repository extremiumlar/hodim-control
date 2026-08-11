"""Uysot CRM webhook qabul qiluvchisi — Uysot kabinetida sozlanadigan endpoint.

Uysot 2026-08-01 da webhook'ni ochdi: kabinetda URL (+ maxfiy kalit) ko'rsatiladi,
hozircha faqat LID eventlari yuboriladi. Kabinetga yoziladigan URL:

    https://<domen>/api/crm-webhook/uysot?secret=<CRM_WEBHOOK_SECRET>

Sekret tekshiruvi ATAYIN bir nechta kanalni qabul qiladi (`?secret=` query,
`X-Crm-Webhook-Secret` va boshqa keng tarqalgan headerlar, `Authorization:
Bearer`) — Uysot kalitni QAYSI usulda yuborishi hujjatlashtirilmagan; query
varianti esa har qanday holatda ishlaydi (URL'ning o'ziga yoziladi). Qaysi
headerlar kelgani jurnalga (sekret qiymati maskalanib) yozib boriladi — keyin
aniq kanalga toraytirsa bo'ladi.

Tezlik sharti (chatbot loyihasidagi "webhook so'rov ichida og'ir ish" saboqidan):
handler faqat sekretni tekshiradi, xom so'rovni jurnalga yozadi va DARHOL 200
qaytaradi — parse/diff/DM hammasi fon vazifada (`services/uysot_webhook.py`).
Aks holda CRM javob kutib qolar yoki timeout'da qayta yuborib navbat o'stirar edi."""
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db
from api.services import uysot_webhook as service
from db.models import CrmWebhookLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm-webhook", tags=["crm-webhook"])

# So'rov tanasi chegarasi — lid eventi kichik JSON; katta tana jurnal jadvalini
# shishirmasin (himoya, Uysot bunday yubormaydi)
MAX_BODY_BYTES = 256 * 1024

# Sekret izlanadigan headerlar (kichik harfda) — birinchi mos kelgani yetarli
_SECRET_HEADERS = (
    "x-crm-webhook-secret",
    "x-webhook-secret",
    "x-secret-key",
    "x-secret",
    "x-api-key",
    "x-auth-token",
    "x-token",
)
# Jurnalga yozilMAYdigan standart headerlar — qolganlari (maxsus/notanish)
# Uysot sekret kanalini aniqlashga yordam beradi
_BORING_HEADERS = {
    "host", "content-length", "content-type", "accept", "accept-encoding",
    "connection", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host",
    "x-real-ip", "cf-connecting-ip", "cf-ray", "cf-visitor", "cdn-loop",
}


def _candidate_secrets(request: Request) -> list[str]:
    out: list[str] = []
    for name in ("secret", "token", "key"):
        value = request.query_params.get(name)
        if value:
            out.append(value)
    for name in _SECRET_HEADERS:
        value = request.headers.get(name)
        if value:
            out.append(value)
    auth = request.headers.get("authorization", "")
    if auth:
        out.append(auth.removeprefix("Bearer ").strip())
    return out


def _secret_rejection_reason(request: Request) -> str | None:
    """Sekret tekshiruvi. Qabul qilinsa `None`, aks holda RAD SABABI (qisqa matn).
    Chaqiruvchi bu sababni DB jurnaliga `note` sifatida yozadi va SO'NG 401/403
    qaytaradi.

    NEGA ISTISNO OTMAYDI (2026-08-11): ilgari bu funksiya to'g'ridan-to'g'ri
    HTTPException otardi va rad etilgan so'rov DB'ga UMUMAN tushmasdi. Yagona
    iz `logger.warning` edi — LEKIN `api/main.py`da logging sozlanmagan, ya'ni
    u stderr'ga ketib Passenger ostida yo'qolardi. Natijada: agar CRM sekretni
    biz kutmagan kanalda yuborsa, so'rov 401 olardi va bizda O'QIY OLADIGAN
    HECH QANDAY IZ QOLMASDI — «webhook kelmayapti»mi yoki «kelyapti-yu rad
    etilyapti»mi, ajratib bo'lmasdi (access log esa kechikadi va ishonchsiz).
    Endi HAR BIR so'rov avval yoziladi, keyin rad etiladi."""
    if not settings.crm_webhook_secret:
        return "rad: CRM_WEBHOOK_SECRET .env'da sozlanmagan"
    for candidate in _candidate_secrets(request):
        if hmac.compare_digest(candidate, settings.crm_webhook_secret):
            return None
    # Sekret QAYSI kanalda kelayotganini aniqlash uchun header NOMLARI va query
    # KALITLARI (qiymatlarsiz — sekret jurnalga tushmasin) saqlanadi. Mos kanal
    # topilsa `_SECRET_HEADERS`ga o'sha nom qo'shiladi.
    logger.warning(
        "CRM webhook so'rovi rad etildi (sekret mos emas yoki yo'q) — IP: %s, UA: %s, "
        "header nomlari: [%s], query kalitlari: [%s]",
        _remote_ip(request),
        request.headers.get("user-agent", "-")[:100],
        ", ".join(sorted(request.headers.keys()))[:300],
        ", ".join(sorted(request.query_params.keys()))[:100],
    )
    return (
        "rad: sekret mos emas | query kalitlari: ["
        + ", ".join(sorted(request.query_params.keys()))[:80]
        + "] | UA: "
        + request.headers.get("user-agent", "-")[:60]
    )[:255]


def _interesting_headers(request: Request) -> dict:
    """Maxsus headerlar jurnal uchun — sekret qiymati qayerda bo'lsa ham maskalanadi."""
    secret = settings.crm_webhook_secret
    out = {}
    for name, value in request.headers.items():
        if name.lower() in _BORING_HEADERS:
            continue
        if secret and secret in value:
            value = "***"
        out[name] = value[:200]
    return out


def _remote_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


@router.get("/uysot")
async def uysot_webhook_ping() -> dict:
    """Kabinet URL'ni tekshirishda GET yuborishi mumkin — 405 o'rniga ok."""
    return {"ok": True}


@router.post("/uysot")
async def uysot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "So'rov tanasi juda katta")

    # DIQQAT — TARTIB MUHIM: avval JURNALGA yozamiz, keyin sekretni tekshiramiz.
    # Sababi `_secret_rejection_reason` izohida: aks holda rad etilgan so'rov
    # hech qanday o'qiy oladigan iz qoldirmaydi va "CRM yubormayaptimi yoki
    # yuboryapti-yu rad etilyaptimi" degan savolga javob topib bo'lmaydi.
    # Xavfsizlikka ta'siri YO'Q: 401 baribir qaytadi, sekret qiymati
    # `_interesting_headers` va `note`da maskalanadi/yozilmaydi. Jadval
    # shishmasligi uchun tana `MAX_BODY_BYTES` bilan cheklangan va eski
    # qatorlar `RETENTION_DAYS` bo'yicha tozalanadi.
    reason = _secret_rejection_reason(request)

    text = body.decode("utf-8", errors="replace")
    entry = CrmWebhookLog(
        remote_ip=_remote_ip(request),
        headers=_interesting_headers(request),
        payload=text,
        note=reason,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    if reason is not None:
        if "sozlanmagan" in reason:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "CRM_WEBHOOK_SECRET .env'da sozlanmagan — endpoint o'chiq",
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Webhook sekreti noto'g'ri")

    # Og'ir ish (parse, diff, issiq-lid DM) — javobdan KEYIN, fon vazifada
    background_tasks.add_task(service.process_log_entry, entry.id)

    # Diagnostika qulayligi: nechta lid ko'ringanini javobda ham qaytaramiz
    # (Uysot buni o'qimaydi, lekin qo'lda curl-test qilganda darhol ko'rinadi)
    try:
        preview = len(service.parse_lead_events(json.loads(text)))
    except ValueError:
        preview = 0
    return {"ok": True, "log_id": entry.id, "leads_detected": preview}
