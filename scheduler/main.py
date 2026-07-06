import asyncio
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scheduler.config import API_BASE_URL, BOT_SHARED_SECRET, TIMEZONE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {"X-Bot-Secret": BOT_SHARED_SECRET}

# "Kun davomida, oraliq kamayib boradi" (6.3-bo'lim): kunduzi bitta, kechga yaqin har soatda.
REMINDER_HOURS = [13, 16, 17, 18]
DAILY_SUMMARY_HOUR = 19

# CRM webhook mavjud bo'lmagan holat uchun zaxira. Deyarli real-vaqtli bo'lishi uchun
# har 30 soniyada so'raladi — amoCRM ulanganda API so'rov chegarasiga (rate limit)
# e'tibor bering, xodimlar soni ko'p bo'lsa oraliqni kattalashtirish kerak bo'lishi mumkin.
CRM_SYNC_INTERVAL_SECONDS = 30

# Lid statistikasi snapshoti oralig'i (daqiqa). Skaner butun bazani sahifalab o'qiydi
# va sekin — juda tez-tez yugurtirsa rate-limitni band qiladi, shuning uchun 30 daqiqa.
LEAD_SNAPSHOT_INTERVAL_MINUTES = 30

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


async def snapshot_lead_stages() -> None:
    """Bugungi operator×bosqich lid kesimini CRM'dan to'liq skanerlab bazaga yozadi.
    Skaner sekin (Uysot rate-limitiga rioya qilib butun bazani sahifalab o'qiydi, bir
    necha daqiqa) — shuning uchun timeout katta. Bot bazadan tez o'qiydi."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=600) as client:
        try:
            resp = await client.post("/stats/lead-stages/sync")
            resp.raise_for_status()
            logger.info("Lid statistikasi snapshot'i: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("Lid statistikasi snapshot'ida xatolik")


async def calculate_monthly_bonus() -> None:
    """Bu job muvaffaqiyatsiz bo'lsa, xodimlarga bonus umuman hisoblanmay qoladi —
    shuning uchun natija har doim (muvaffaqiyatli/muvaffaqiyatsiz) aniq log'ga yoziladi.
    Kelajakda: muvaffaqiyatsizlikda bossga Telegram orqali darhol xabar yuborish tavsiya
    qilinadi (masalan alohida "/scheduler/notify-boss" API endpointi orqali) — hozircha
    faqat log orqali kuzatiladi."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=60) as client:
        try:
            resp = await client.post("/bonuses/calculate-monthly", json={})
            resp.raise_for_status()
            logger.info("[BONUS OK] Oylik bonus muvaffaqiyatli hisoblandi: %s", resp.json())
        except httpx.HTTPError:
            logger.exception("[BONUS FAILED] Oylik bonus hisoblashda xatolik yuz berdi")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # misfire_grace_time + coalesce: agar scheduler band/o'chiq bo'lgani sabab job o'z
    # vaqtida ishga tushmasa, uni butunlay o'tkazib yubormasdan (default xatti-harakat),
    # imkon bo'lganda (grace davri ichida) kechroq bitta marta ishga tushiradi.
    MISFIRE_GRACE_TIME = 3600

    for hour in REMINDER_HOURS:
        scheduler.add_job(
            send_reminders,
            CronTrigger(hour=hour, minute=0, timezone=TIMEZONE),
            misfire_grace_time=MISFIRE_GRACE_TIME,
            coalesce=True,
        )

    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=DAILY_SUMMARY_HOUR, minute=0, timezone=TIMEZONE),
        misfire_grace_time=MISFIRE_GRACE_TIME,
        coalesce=True,
    )

    scheduler.add_job(sync_daily_results, IntervalTrigger(seconds=CRM_SYNC_INTERVAL_SECONDS))

    # Lid statistikasi snapshoti: butun bazani skanerlagani uchun sekin va og'ir
    # (rate-limit), shuning uchun tez-tez emas — har LEAD_SNAPSHOT_INTERVAL_MINUTES
    # daqiqada + kun yakunida (23:57) oxirgi holatni muzlatish uchun. max_instances=1:
    # oldingi skaner tugamasdan yangisi boshlanmaydi.
    scheduler.add_job(
        snapshot_lead_stages,
        IntervalTrigger(minutes=LEAD_SNAPSHOT_INTERVAL_MINUTES),
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        snapshot_lead_stages,
        CronTrigger(hour=23, minute=57, timezone=TIMEZONE),
        max_instances=1,
        misfire_grace_time=600,
        coalesce=True,
    )

    scheduler.add_job(
        calculate_monthly_bonus,
        CronTrigger(
            day=MONTHLY_BONUS_DAY, hour=MONTHLY_BONUS_HOUR, minute=MONTHLY_BONUS_MINUTE, timezone=TIMEZONE
        ),
        misfire_grace_time=MISFIRE_GRACE_TIME,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler ishga tushdi (%s). Eslatma soatlari: %s, kunlik xulosa: %02d:00, "
        "CRM sync: har %d soniyada, oylik bonus: oyning oxirgi kuni %02d:%02d",
        TIMEZONE,
        REMINDER_HOURS,
        DAILY_SUMMARY_HOUR,
        CRM_SYNC_INTERVAL_SECONDS,
        MONTHLY_BONUS_HOUR,
        MONTHLY_BONUS_MINUTE,
    )

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
