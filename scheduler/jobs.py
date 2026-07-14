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


async def send_weekly_digest() -> None:
    """Haftalik raqamli yakun (shu hafta vs o'tgan hafta, operator kesimida) — guruhga
    bitta xabar. Sof kod hisobi — AI o'chiq bo'lsa ham ishlaydi."""
    body = await call_api("/reports/weekly-digest", timeout=120, label="Haftalik digest")
    if body is not None:
        logger.info("Haftalik digest: %s", body)


async def send_monthly_digest() -> None:
    """Oylik yakun (joriy oy vs o'tgan oy, operator kesimida, bonus bilan) — guruhga
    bitta xabar, oyning oxirgi kuni kechqurun. Sof kod hisobi."""
    body = await call_api("/reports/monthly-digest", timeout=120, label="Oylik digest")
    if body is not None:
        logger.info("Oylik digest: %s", body)


async def send_yesterday_correction() -> None:
    """Ertalab: kechagi yakuniy raqam kechqurungi digestdagidan sezilarli oshgan
    bo'lsa guruhga qisqa "kecha yakuni" tuzatishi (API taqqoslab o'zi hal qiladi)."""
    body = await call_api("/reports/yesterday-correction", timeout=60, label="Kecha yakuni tuzatish")
    if body is not None and body.get("sent"):
        logger.info("Kecha yakuni tuzatishi yuborildi: %s", body)


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
    """Har daqiqa: boss belgilagan vaqt kelganda kunlik yagona digestni (vazifa +
    qo'ng'iroq/lid/tashrif + AI xulosa, bitta xabar) guruhga yuboradi (API vaqtni
    va "bugun yuborilganmi"ni o'zi tekshiradi). Digest AI xulosani ham kutishi
    mumkin — timeout shunga yarasha."""
    body = await call_api("/stats/lead-stages/group-tick", timeout=120, label="Kunlik digest tick")
    if body and body.get("fired"):
        logger.info("Kunlik digest guruhga yuborildi: %s", body)


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


async def hot_lead_tick() -> None:
    """Issiq lid: yangi CRM lidini aniqlab mas'ul operatorga darhol DM, birinchi
    qo'ng'iroq (speed-to-lead) o'lchovi, kechikkanini guruhga eskalatsiya. API
    HOT_LEAD_ENABLED va runtime toggle'ni o'zi tekshiradi (o'chiqda no-op)."""
    body = await call_api("/hot-lead/tick", timeout=120, label="Issiq lid tick")
    if body is None or body.get("disabled") or body.get("off"):
        return
    detect = body.get("detect") or {}
    if detect.get("seeded"):
        logger.info("Issiq lid baseline: %s ta mavjud lid qayd etildi", detect["seeded"])
    if detect.get("new"):
        logger.info("Issiq lid: %s ta yangi lid yuborildi", detect["new"])
    escalation = body.get("escalation") or {}
    if escalation.get("escalated"):
        logger.info("Issiq lid eskalatsiya: %s ta", escalation["escalated"])


async def ai_weekly_run() -> None:
    """Haftalik AI trend: har operatorga SHAXSIY xulosa (guruhga jamoa ko'rinishini
    endi raqamli haftalik digest beradi — send_weekly_digest)."""
    body = await call_api("/ai-watch/weekly-run", timeout=300, label="AI haftalik")
    if body is not None and not body.get("disabled") and not body.get("weekly_disabled"):
        logger.info("AI haftalik: operators=%s sent=%s", body.get("operators"), body.get("sent"))
