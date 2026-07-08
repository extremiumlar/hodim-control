"""Scheduler job korutinlari — har biri ingichka: `call_api` chaqiradi va natijaga
qarab muvaffaqiyat log'ini yozadi. Xatolar `call_api` ichida log qilinadi.

Yangi job qo'shish: shu yerga korutin yozing, so'ng `scheduler/main.py`dagi `JOBS`
reyestriga trigger bilan qo'shing."""
import logging

from scheduler.client import call_api

logger = logging.getLogger(__name__)


# ─── Mavjud jadval (vazifa/hisobot/CRM) ─────────────────────────────────────────
async def send_reminders() -> None:
    body = await call_api("/tasks/send-reminders", label="Eslatmalar")
    if body is not None:
        logger.info("Eslatmalar yuborildi: %s", body)


async def send_daily_summary() -> None:
    body = await call_api("/reports/daily-summary", label="Kunlik xulosa")
    if body is not None:
        logger.info("Kunlik xulosa yuborildi: %s", body)


async def sync_daily_results() -> None:
    body = await call_api("/daily-results/sync", label="CRM sync")
    if body is not None:
        logger.info("CRM sinxronizatsiyasi: %s", body)


async def snapshot_lead_stages() -> None:
    """Bugungi operator×bosqich lid kesimini CRM'dan skanerlab bazaga yozadi (sekin —
    butun bazani sahifalaydi, shuning uchun timeout katta)."""
    body = await call_api("/stats/lead-stages/sync", timeout=600, label="Lid snapshot")
    if body is not None:
        logger.info("Lid statistikasi snapshot'i: %s", body)


async def group_post_tick() -> None:
    """Har daqiqa: boss belgilagan vaqt kelganda kunlik lid statistikasini guruhga
    yuboradi (API vaqtni va "bugun yuborilganmi"ni o'zi tekshiradi)."""
    body = await call_api("/stats/lead-stages/group-tick", timeout=60, label="Guruh tick")
    if body and body.get("fired"):
        logger.info("Lid statistikasi guruhga yuborildi: %s", body)


async def send_hourly_plan() -> None:
    """Har soat boshida ish vaqtidagi xodimlarga soatlik reja + progressni yuboradi
    (API ish oynasidan tashqarida/dam kunida hech kimga yubormaydi)."""
    body = await call_api("/hourly-plan/send", timeout=60, label="Soatlik reja")
    if body is not None:
        logger.info("Soatlik reja yuborildi: %s", body)


async def calculate_monthly_bonus() -> None:
    """Muvaffaqiyatsiz bo'lsa xodimlarga bonus umuman hisoblanmaydi — natija har doim
    aniq (OK/FAILED) log'ga yoziladi (grep uchun)."""
    body = await call_api("/bonuses/calculate-monthly", json={}, timeout=60, label="[BONUS FAILED] Oylik bonus")
    if body is not None:
        logger.info("[BONUS OK] Oylik bonus muvaffaqiyatli hisoblandi: %s", body)
