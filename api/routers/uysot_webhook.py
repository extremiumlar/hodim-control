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
import os

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
# ─────────────────────────────────────────────────────────────────────────
# UYSOT IMZO SXEMASI — VAQTINCHALIK ISHONCH (2026-08-11)
#
# Uysot sekretni YUBORMAYDI. U kalit + tanadan hisoblangan IMZO yuboradi:
#     x-webhook-signature: sha256=<64 hex>
#     x-webhook-timestamp: <unix>
#     x-webhook-id:        <uuid>
# Ya'ni yuqoridagi `_SECRET_HEADERS` yondashuvi (qiymatni sekret bilan
# TENGLASHTIRISH) printsipial ravishda ishlamaydi — imzo har so'rovda boshqa.
#
# To'g'ri yo'l — imzoni qayta hisoblab solishtirish. LEKIN Uysot imzo QAYSI
# qatordan hisoblanishini hujjatlashtirmagan va u aniqlanmadi: to'g'ri kalit
# bilan 1536 kombinatsiya sinaldi (HMAC-SHA256/SHA1/SHA512/MD5 × 8 xabar
# tuzilishi × 8 ajratuvchi × kalitning matn/hex ko'rinishi × hex/base64)
# — birortasi mos kelmadi.
#
# Shu sababli VAQTINCHALIK ishonch mezoni: so'rov Uysot'ning ma'lum chiquvchi
# IP'sidan kelgan VA imzo sarlavhasi mavjud bo'lsa qabul qilinadi.
# Nega bu yetarli darajada xavfsiz: ulanish HTTPS, manba IP'ni soxtalashtirib
# javob olib bo'lmaydi, URL maxfiy, imzo sarlavhasi majburiy. Ideal emas —
# shuning uchun imzo `headers` bilan birga SAQLANADI: Uysot spetsifikatsiyani
# bergach eski yozuvlarda algoritmni tekshirib, shu blokni haqiqiy HMAC
# tekshiruviga almashtiramiz (o'shanda IP mezonini olib tashlash mumkin).
_TRUSTED_WEBHOOK_IPS = tuple(
    ip.strip()
    for ip in os.getenv("CRM_WEBHOOK_TRUSTED_IPS", "158.179.201.167").split(",")
    if ip.strip()
)
# Imzo mavjudligi tekshiriladigan sarlavhalar (qiymat TEKSHIRILMAYDI — yuqoriga qarang)
_SIGNATURE_HEADERS = ("x-webhook-signature", "x-hub-signature-256", "x-signature")

# Jurnalga yozilMAYdigan standart headerlar — qolganlari (maxsus/notanish)
# Uysot sekret kanalini aniqlashga yordam beradi
# DIQQAT: `x-forwarded-for` va `x-real-ip` ATAYLAB saqlanadi (2026-08-12).
# Ular ishonch qarorining KIRISHI (`_proxy_verified_ip`) — saqlanmasa, so'rov
# nega rad etilganini aniqlab bo'lmaydi. Maxfiy ma'lumot emas.
_BORING_HEADERS = {
    "host", "content-length", "content-type", "accept", "accept-encoding",
    "connection", "x-forwarded-proto", "x-forwarded-host",
    "cf-connecting-ip", "cf-ray", "cf-visitor", "cdn-loop",
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

    # ── Vaqtinchalik ishonch: Uysot imzo sxemasi (yuqoridagi uzun izohga qarang) ──
    ip = _proxy_verified_ip(request)
    signature = next(
        (request.headers[name] for name in _SIGNATURE_HEADERS if name in request.headers),
        None,
    )
    if ip in _TRUSTED_WEBHOOK_IPS and signature:
        # Qabul qilinadi, LEKIN aniq iz qoldiramiz: bu HMAC tekshiruvi EMAS.
        # Imzo `headers`da saqlanadi — spetsifikatsiya kelgach shu yozuvlarda
        # algoritmni aniqlab, bu yo'lni haqiqiy tekshiruvga almashtiramiz.
        logger.info(
            "CRM webhook ISHONCHLI IP orqali qabul qilindi (imzo TEKSHIRILMADI) — "
            "IP: %s, imzo: %s",
            ip,
            signature[:24] + "...",
        )
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
    # Ishonch qarorining KIRISHLARI ham yoziladi: `proksi_ip` aynan
    # `_proxy_verified_ip` ko'rgan qiymat — nega ishonchli IP mezoni
    # ishlamaganini shu ko'rsatadi (imzo bor/yo'qligi bilan birga).
    return (
        "rad: sekret mos emas | proksi_ip=%s | imzo=%s | UA: %s"
        % (ip, "bor" if signature else "yo'q", request.headers.get("user-agent", "-")[:40])
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
    """Jurnal uchun mijoz IP'si — `x-forwarded-for`ning BIRINCHI qiymati
    (odatiy amaliyot: eng chekka mijoz). DIQQAT: bu qiymatni mijozning O'ZI
    yuborishi mumkin, ya'ni u FAQAT diagnostika uchun — ishonch qarorida
    ishlatilmaydi (buning uchun `_proxy_verified_ip`)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def _proxy_verified_ip(request: Request) -> str | None:
    """IShONCH qarorlari uchun IP — soxtalashtirib bo'lmaydigan qiymat.

    NEGA `_remote_ip` YARAMAYDI: u `x-forwarded-for`ning BIRINCHI elementini
    oladi, mijoz esa o'z so'roviga istalgan `X-Forwarded-For` qo'shishi mumkin.
    Oldimizdagi proksi (LiteSpeed/Apache) haqiqiy IP'ni ro'yxat OXIRIGA
    qo'shadi, ya'ni `spoofed, ..., HAQIQIY`. Shuning uchun ishonch uchun
    OXIRGI element olinadi. `x-real-ip` ham proksi tomonidan qo'yiladi va
    mijoznikini bosib ketadi — u birinchi navbatda ishlatiladi."""
    real = request.headers.get("x-real-ip")
    if real:
        return _normalize_ip(real)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return _normalize_ip(forwarded.split(",")[-1])
    return _normalize_ip(request.client.host) if request.client else None


def _normalize_ip(value: str) -> str:
    """`::ffff:1.2.3.4` → `1.2.3.4`.

    NEGA KERAK (2026-08-12, jonli o'lchov): bu hostdagi proksi `x-real-ip`ni
    IPv4-mapped IPv6 ko'rinishida beradi (`::ffff:213.230.93.114`). Normallash-
    tirilmasa ishonchli IP ro'yxati bilan solishtirish HECH QACHON mos kelmaydi
    — Uysot webhooklari aynan shu sababdan rad etilgan edi."""
    ip = value.strip()[:64]
    low = ip.lower()
    if low.startswith("::ffff:"):
        ip = ip[7:]
    return ip


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
