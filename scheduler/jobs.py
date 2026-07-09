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


# ─── Operator AI (avto-reja dvigateli) — API tomonda AI o'chiq bo'lsa no-op ──────
async def ai_snapshot_actuals() -> None:
    """Bugungi soatlik actual'ni CRM'dan o'qib `hourly_actual`ga yozadi (reja vs
    haqiqiy va ertangi tarix uchun)."""
    body = await call_api("/auto-plan/snapshot", timeout=120, label="AI actual snapshot")
    if body is not None and not body.get("disabled"):
        logger.info("AI actual snapshot: %s", body)


async def ai_build_targets() -> None:
    """Bugungi kunlik rejani (profil+benchmark+stretch) tuzadi — ish boshlanishidan oldin."""
    body = await call_api("/auto-plan/build-targets", timeout=120, label="AI reja tuzish")
    if body is not None and not body.get("disabled"):
        logger.info("AI kunlik reja tuzildi: %s", body)


async def ai_compute_profiles() -> None:
    """Operatorlarning soatlik baseline profilini oxirgi ~30 kundan qayta hisoblaydi
    (haftada, operator o'ssa reja ham o'sadi)."""
    body = await call_api("/auto-plan/compute-profiles", timeout=120, label="AI profil hisob")
    if body is not None and not body.get("disabled"):
        logger.info("AI profillar yangilandi: %s", body)


async def ai_watch_tick() -> None:
    """Soatlik kuzatuv: reja vs haqiqiy — orqada qolgan/anomaliyali operatorlarga
    AI nudge + sabab tugmalari. Joyida bo'lganlarga jim. API AI_ENABLED va
    AI_NUDGE_ENABLED bayroqlarini o'zi tekshiradi (o'chiqda no-op)."""
    body = await call_api("/ai-watch/tick", timeout=180, label="AI kuzatuv tick")
    if body is not None and not body.get("disabled"):
        if body.get("nudge_disabled"):
            return  # push o'chiq — jimgina o'tamiz (log shovqin qilmasin)
        logger.info("AI kuzatuv: triggered=%s sent=%s", body.get("triggered"), body.get("sent"))


async def ai_summary_tick() -> None:
    """Har daqiqa: boss belgilagan vaqt kelganda kun yakuni AI xulosasini guruhga
    yuboradi (API vaqtni va "bugun yuborilganmi"ni o'zi tekshiradi)."""
    body = await call_api("/ai-watch/summary-tick", timeout=120, label="AI kun yakuni tick")
    if body and body.get("fired"):
        logger.info("AI kun yakuni guruhga yuborildi: %s", body)


async def ai_weekly_run() -> None:
    """Haftalik trend: har operatorga shaxsiy xulosa + guruhga jamoa ko'rinishi."""
    body = await call_api("/ai-watch/weekly-run", timeout=300, label="AI haftalik")
    if body is not None and not body.get("disabled") and not body.get("weekly_disabled"):
        logger.info("AI haftalik: operators=%s sent=%s", body.get("operators"), body.get("sent"))
