"""CRM lid-ma'lumot rejimi: webhook (asosiy) yoki polling (eski usul/zaxira).

2026-08-01: Uysot webhook ochdi (hozircha faqat lid eventlari) va foydalanuvchi
qarori bilan lid POLLING webhook'ka bo'shatildi. LEKIN jonli tekshiruv (o'sha kun
kechqurun) ko'rsatdi: sekret sozlangani bilanoq polling o'chirilgan, Uysot esa
webhook'ka HALI BITTA ham lid yubormagan (access-log'da faqat o'z curl-testimiz) —
tizim jimgina ko'r bo'lib qoldi, tashrif/lid statistikasi muzlab qoldi. Shuning
uchun rejim endi DALILGA asoslangan:

  - `CRM_LEAD_POLLING_ENABLED=true` → polling har doim yoqiq (majburiy rejim).
  - `CRM_WEBHOOK_SECRET` sozlanmagan → webhook endpointi 403-yopiq, polling
    MAJBURAN yoqiq (aks holda lid oqimi butunlay ko'r bo'lardi).
  - Sekret sozlangan → polling FAQAT webhook o'zini isbotlaganda o'chadi:
    so'nggi `WEBHOOK_LIVENESS_HOURS` soat ichida kamida bitta lid AJRATILGAN
    (`parsed_events > 0`) webhook so'rovi kelgan bo'lishi shart. Webhook jim
    bo'lsa (hali sozlanmagan, Uysot yubormayapti, format o'zgarib parse
    buzilgan) — polling o'z-o'zidan davom etadi va webhook tirilganda
    o'z-o'zidan to'xtaydi (qo'lda aralashuvsiz, ikkala yo'nalishda).

QAMROV: faqat LID skanlari — diff-tick/reconcile (`lead_diff.py`), issiq-lid
detect skani (`hot_lead.py`) va LeadStageDaily lid skani (`stats.py`).
Qo'ng'iroq tarixi (call-history) skanlari BUNGA KIRMAYDI — webhook qo'ng'iroq
ma'lumotini bermaydi, ular avvalgidek scheduler bilan ishlaydi."""
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from db.models import CrmWebhookLog

logger = logging.getLogger(__name__)

# Webhook "jonli" hisoblanadigan oyna. 24 soat — tungi/dam olish kunlaridagi
# tabiiy jimlik webhook o'lgan deb baholanmasin; webhook chindan o'lsa esa
# ko'pi bilan bir kunlik teshikdan keyin polling o'zi qoplab ketadi.
WEBHOOK_LIVENESS_HOURS = 24

_WARN_INTERVAL_SECONDS = 1800  # ogohlantirish har tikda emas, 30 daqiqada bir
_last_warn = {"no_secret": 0.0, "webhook_silent": 0.0}


def _warn_throttled(key: str, message: str) -> None:
    now = time.monotonic()
    if now - _last_warn[key] < _WARN_INTERVAL_SECONDS:
        return
    _last_warn[key] = now
    logger.warning(message)


async def lead_polling_active(db: AsyncSession) -> bool:
    """True — lid skanlari (polling) ishlashi kerak; False — webhook-only.
    Webhook-only faqat webhook JONLI ekani (yaqinda lid ajratilgan so'rov
    kelgani) bazadan tasdiqlanganda — aks holda polling xavfsizlik to'ri
    sifatida davom etadi."""
    if settings.crm_lead_polling_enabled:
        return True
    if not settings.crm_webhook_secret:
        _warn_throttled(
            "no_secret",
            "CRM_WEBHOOK_SECRET sozlanmagan — webhook yopiq, shuning uchun lid "
            "polling MAJBURAN davom etmoqda. Webhook-only rejim uchun sekretni "
            ".env'ga qo'yib, Uysot kabinetida URL'ni sozlang.",
        )
        return True

    cutoff = datetime.utcnow() - timedelta(hours=WEBHOOK_LIVENESS_HOURS)
    last_alive = await db.scalar(
        select(func.max(CrmWebhookLog.received_at)).where(CrmWebhookLog.parsed_events > 0)
    )
    if last_alive is None or last_alive < cutoff:
        _warn_throttled(
            "webhook_silent",
            "CRM webhook jonsiz (so'nggi %s soatda lid ajratilgan so'rov kelmagan"
            "%s) — lid polling xavfsizlik to'ri sifatida davom etmoqda. Uysot "
            "kabinetida webhook URL sozlanganini tekshiring."
            % (
                WEBHOOK_LIVENESS_HOURS,
                "" if last_alive is None else f", oxirgisi: {last_alive:%Y-%m-%d %H:%M} UTC",
            ),
        )
        return True
    return False
