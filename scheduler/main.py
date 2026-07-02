import asyncio
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.config import API_BASE_URL, BOT_SHARED_SECRET, TIMEZONE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {"X-Bot-Secret": BOT_SHARED_SECRET}

# "Kun davomida, oraliq kamayib boradi" (6.3-bo'lim): kunduzi bitta, kechga yaqin har soatda.
REMINDER_HOURS = [13, 16, 17, 18]
DAILY_SUMMARY_HOUR = 19

# CRM webhook mavjud bo'lmagan holat uchun zaxira: ish soatlarida har soatda so'raladi.
CRM_SYNC_HOURS = list(range(9, 20))

# "Har oy oxirida, 1 marta" (8-bo'lim).
MONTHLY_BONUS_DAY = "last"
MONTHLY_BONUS_HOUR = 23
MONTHLY_BONUS_MINUTE = 30


async def send_reminders() -> None:
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=30) as client:
        try:
            resp = await client.post("/tasks/send-reminders")
            resp.raise_for_status()
            logger.info("Eslatmalar yuborildi: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("Eslatmalarni yuborishda xatolik")


async def send_daily_summary() -> None:
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=30) as client:
        try:
            resp = await client.post("/reports/daily-summary")
            resp.raise_for_status()
            logger.info("Kunlik xulosa yuborildi: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("Kunlik xulosani yuborishda xatolik")


async def sync_daily_results() -> None:
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=30) as client:
        try:
            resp = await client.post("/daily-results/sync")
            resp.raise_for_status()
            logger.info("CRM sinxronizatsiyasi: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("CRM sinxronizatsiyasida xatolik")


async def calculate_monthly_bonus() -> None:
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=60) as client:
        try:
            resp = await client.post("/bonuses/calculate-monthly", json={})
            resp.raise_for_status()
            logger.info("Oylik bonus hisoblandi: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("Oylik bonus hisoblashda xatolik")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    for hour in REMINDER_HOURS:
        scheduler.add_job(send_reminders, CronTrigger(hour=hour, minute=0, timezone=TIMEZONE))

    scheduler.add_job(send_daily_summary, CronTrigger(hour=DAILY_SUMMARY_HOUR, minute=0, timezone=TIMEZONE))

    for hour in CRM_SYNC_HOURS:
        scheduler.add_job(sync_daily_results, CronTrigger(hour=hour, minute=15, timezone=TIMEZONE))

    scheduler.add_job(
        calculate_monthly_bonus,
        CronTrigger(
            day=MONTHLY_BONUS_DAY, hour=MONTHLY_BONUS_HOUR, minute=MONTHLY_BONUS_MINUTE, timezone=TIMEZONE
        ),
    )

    scheduler.start()
    logger.info(
        "Scheduler ishga tushdi (%s). Eslatma soatlari: %s, kunlik xulosa: %02d:00, "
        "CRM sync: har soatda (%s), oylik bonus: oyning oxirgi kuni %02d:%02d",
        TIMEZONE,
        REMINDER_HOURS,
        DAILY_SUMMARY_HOUR,
        CRM_SYNC_HOURS,
        MONTHLY_BONUS_HOUR,
        MONTHLY_BONUS_MINUTE,
    )

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
