"""CRM lid-ma'lumot rejimi: webhook (asosiy) yoki polling (eski usul/zaxira).

2026-08-01: Uysot webhook ochdi (hozircha faqat lid eventlari) va foydalanuvchi
qarori bilan lid POLLING butunlay o'chirildi — lid o'zgarishlari endi faqat
webhook orqali keladi (`api/routers/uysot_webhook.py`). Bu modul — yagona kalit:

  - `CRM_LEAD_POLLING_ENABLED=true` → eski polling rejimi (webhook'siz muhit
    yoki favqulodda zaxira uchun qoldirilgan; kod o'chirilmagan).
  - default (false) → webhook-only; LEKIN `CRM_WEBHOOK_SECRET` sozlanmagan
    bo'lsa (webhook endpointi 403-yopiq — voqealar UMUMAN kelmaydi) polling
    MAJBURAN yoqiq qoladi, aks holda lid oqimi butunlay ko'r bo'lib qolardi
    (masalan kod yangi serverga sekret'siz deploy qilinsa).

QAMROV: faqat LID skanlari — diff-tick/reconcile (`lead_diff.py`), issiq-lid
detect skani (`hot_lead.py`) va LeadStageDaily lid skani (`stats.py`).
Qo'ng'iroq tarixi (call-history) skanlari BUNGA KIRMAYDI — webhook qo'ng'iroq
ma'lumotini bermaydi, ular avvalgidek scheduler bilan ishlaydi."""
import logging

from api.config import settings

logger = logging.getLogger(__name__)

_warned_no_secret = False  # ogohlantirish har 5 daqiqada log to'ldirmasin


def lead_polling_active() -> bool:
    """True — lid skanlari (polling) ishlashi kerak; False — webhook-only."""
    global _warned_no_secret
    if settings.crm_lead_polling_enabled:
        return True
    if not settings.crm_webhook_secret:
        if not _warned_no_secret:
            logger.warning(
                "CRM_WEBHOOK_SECRET sozlanmagan — webhook yopiq, shuning uchun lid "
                "polling MAJBURAN davom etmoqda. Webhook-only rejim uchun sekretni "
                ".env'ga qo'yib, Uysot kabinetida URL'ni sozlang."
            )
            _warned_no_secret = True
        return True
    return False
