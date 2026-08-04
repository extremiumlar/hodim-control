"""Scheduler → API o'rtasidagi yagona HTTP yordamchisi.

Har job ilgari o'z httpx klientini, try/except va log'ini takrorlardi — endi hammasi
shu yerda. Job'lar `call_api(...)` chaqirib, natijaga qarab o'z muvaffaqiyat log'ini
yozadi (masalan group-tick faqat "fired" bo'lsa, bonus [OK]/[FAILED] prefiksi bilan)."""
import logging

import httpx

from scheduler.config import API_BASE_URL, BOT_SHARED_SECRET

logger = logging.getLogger(__name__)

HEADERS = {"X-Bot-Secret": BOT_SHARED_SECRET}


async def call_api(
    path: str,
    *,
    method: str = "POST",
    json: dict | None = None,
    timeout: float = 30,
    label: str | None = None,
) -> dict | None:
    """API endpointini chaqiradi. Muvaffaqiyatda javob JSON'ini (dict) qaytaradi,
    xatolikda `None` (xatoni o'zi log'ga yozadi). Chaqiruvchi muvaffaqiyat log'ini
    o'zi hal qiladi (turli job'lar turlicha log qiladi)."""
    label = label or path
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=timeout) as client:
        try:
            resp = await client.request(method, path, json=json)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            # Timeout — kutilgan turdagi vaqtinchalik holat (masalan Passenger'ning
            # yagona ishchisi boshqa so'rov bilan band): to'liq traceback log'ni
            # to'ldirardi (cron.log'da minglab qator) — bir qator kifoya.
            logger.warning("%s timeout (%.0fs) — keyingi tick'da qayta uriniladi", label, timeout)
            return None
        except httpx.HTTPError:
            logger.exception("%s xatosi", label)
            return None
