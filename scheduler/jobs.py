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


async def mark_overdue_tasks() -> None:
    """Muddati o'tgan pending vazifalarni overdue statusiga o'tkazadi."""
    body = await call_api("/tasks/mark-overdue", label="Muddati o'tganlar")
    if body is not None and body.get("marked_overdue"):
        logger.info("Muddati o'tgan vazifalar belgilandi: %s", body)


async def send_weekly_digest() -> None:
    """Haftalik raqamli yakun (shu hafta vs o'tgan hafta, operator kesimida) — guruhga
    bitta xabar. Sof kod hisobi — AI o'chiq bo'lsa ham ishlaydi."""
    body = await call_api("/reports/weekly-digest", timeout=120, label="Haftalik digest")
    if body is not None:
        logger.info("Haftalik digest: %s", body)


async def attendance_digest_tick() -> None:
    """Davomat digesti tekshiruvi (har daqiqa) — vaqt bazadan sozlanadi
    (botdan /davomat_vaqt), API o'zi yetganini tekshirib yuboradi."""
    body = await call_api(
        "/attendance/digest-tick", timeout=60, label="Davomat digesti tick"
    )
    if body is not None and body.get("fired"):
        logger.info("Davomat digesti yuborildi: %s", body)


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


async def system_health_tick() -> None:
    """Tizim sog'ligi qo'riqchisi: jimgina ishlamay qolgan qismlarni (CRM
    aloqasi, kunlik zaxira nusxa, davomat oqimi) aniqlab guruhga ogohlantiradi.
    Tiklanganda «tiklandi» xabari."""
    body = await call_api("/system-health/tick", json={}, timeout=60, label="Tizim qo'riqchisi")
    if body is None:
        return
    if body.get("alerted"):
        logger.warning("Qo'riqchi ogohlantirdi: %s", body["alerted"])
    if body.get("recovered"):
        logger.info("Qo'riqchi: tiklandi — %s", body["recovered"])


async def lead_diff_tick() -> None:
    """Diff-engine: chegaralangan (so'nggi N kun yaratilgan) tez skan — CRM
    lidlarining HAQIQIY bosqich/mas'ul o'zgarishini aniqlab `LeadEvent`ga yozadi.
    Guruh digesti shundan o'qiydi (deyarli real-vaqtli, taxminiy emas)."""
    body = await call_api("/lead-events/diff-tick", timeout=180, label="Lid diff tick")
    if body is not None and body.get("skipped"):
        return  # webhook-only rejim (crm_mode) — skan API tomonda ataylab o'chiq
    if body is not None and body.get("ok"):
        logger.info(
            "Lid diff: skanerlandi=%s yangi=%s bosqich=%s mas'ul=%s",
            body.get("scanned"), body.get("new_leads"), body.get("stage_events"), body.get("responsible_events"),
        )


async def lead_diff_reconcile() -> None:
    """Diff-engine tungi to'liq solishtiruvi: BUTUN bazani skanerlaydi (sekin) —
    chegaralangan skan oynasidan tashqarida qolgan eski-lekin-qayta-faollashgan
    lidlarni ushlab qoladigan xavfsizlik to'ri."""
    body = await call_api("/lead-events/reconcile", timeout=900, label="Lid diff reconcile")
    if body is not None and body.get("skipped"):
        return  # webhook-only rejim (crm_mode) — skan API tomonda ataylab o'chiq
    if body is not None and body.get("ok"):
        logger.info(
            "Lid diff (to'liq): skanerlandi=%s yangi=%s bosqich=%s mas'ul=%s",
            body.get("scanned"), body.get("new_leads"), body.get("stage_events"), body.get("responsible_events"),
        )


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


async def attendance_reminder_tick() -> None:
    """«Keldim/Ketdim bosishni unutmang» — ish oynasi boshlanishiga/tugashiga
    yaqin qolganda bosmaganlarga eslatma. API dam kuni/sababli kun/allaqachon
    bosgan holatlarni o'zi filtrlaydi va bir kunda bir marta yuboradi."""
    body = await call_api(
        "/attendance/reminder-tick", json={}, timeout=120, label="Davomat eslatmasi"
    )
    if body is not None and body.get("sent"):
        logger.info("Davomat eslatmasi: %s ta yuborildi (nomzod %s)", body["sent"], body.get("candidates"))


async def appeals_sla_tick() -> None:
    """E'tiroz/shikoyat SLA: 3 kundan beri javobsiz murojaat uchun qabul
    qiluvchiga eslatma, 5 kundan beri javobsizi uchun Boshliqqa eskalatsiya.
    API iz ustunlari bilan har birini bir marta yuboradi."""
    body = await call_api("/appeals/sla-tick", json={}, timeout=60, label="Murojaat SLA")
    if body is not None and (body.get("reminded") or body.get("escalated")):
        logger.info(
            "Murojaat SLA: %s eslatma, %s eskalatsiya (ochiq %s)",
            body.get("reminded"), body.get("escalated"), body.get("open"),
        )


async def requests_sla_tick() -> None:
    """Ariza SLA: 3 kundan javobsizga HR eslatmasi, 5 kundan Boshliqqa
    eskalatsiya (murojaat SLA'si bilan bir xil naqsh, iz ustunlari bilan)."""
    body = await call_api("/requests/sla-tick", json={}, timeout=60, label="Ariza SLA")
    if body is not None and (body.get("reminded") or body.get("escalated")):
        logger.info(
            "Ariza SLA: %s eslatma, %s eskalatsiya (ochiq %s)",
            body.get("reminded"), body.get("escalated"), body.get("open"),
        )


async def work_log_reminder_tick() -> None:
    """Ish kundaligi eslatmasi — ish tugashiga yaqin, bugun ishlagan-u hali
    hech narsa yozmaganlarga. API dam kuni/sababli kun/kelmagan/yozgan
    holatlarni o'zi filtrlaydi va kuniga bir marta yuboradi (UNIQUE iz)."""
    body = await call_api(
        "/work-log/reminder-tick", json={}, timeout=120, label="Kundalik eslatmasi"
    )
    if body is not None and body.get("sent"):
        logger.info(
            "Kundalik eslatmasi: %s ta yuborildi (nomzod %s)", body["sent"], body.get("candidates")
        )


# ─── Telegram login xavfsizligi (replay himoyasi + rate-limit) ─────────────────
async def login_security_cleanup_tick() -> None:
    """Replay-himoya hash'lari (UsedTelegramLoginHash) va rate-limit urinish
    yozuvlarini (LoginAttempt) eskirganini tozalaydi — jadvallar cheksiz o'sib
    ketmasin."""
    body = await call_api("/auth/login-security-cleanup", json={}, timeout=30, label="Login xavfsizlik tozalash")
    if body is not None:
        logger.info("Login xavfsizlik tozalash: %s", body)


# ─── Payroll (oylik ish haqi + jarima) — OYLIK_JARIMA_REJASI.md, Bosqich 6 ──────
async def calculate_monthly_payroll() -> None:
    """Oylik ish haqi — keyingi oyning 1-kuni ertalab (9-bo'lim, savol 10, QAROR).
    Muvaffaqiyatsiz bo'lsa xodimlarga payroll umuman hisoblanmaydi — bonus jobi
    bilan bir xil [OK]/[FAILED] log naqshi (grep uchun)."""
    body = await call_api(
        "/payroll/calculate-monthly", json={}, timeout=120, label="[PAYROLL FAILED] Oylik ish haqi"
    )
    if body is not None:
        logger.info("[PAYROLL OK] Oylik ish haqi muvaffaqiyatli hisoblandi: %s", body)


async def payroll_late_warnings_tick() -> None:
    """Kechikish limiti ogohlantirishi (1.5-band): kecha limitni birinchi marta
    oshirgan/unga yaqinlashtirgan xodimlarga botga darhol shaxsiy xabar."""
    body = await call_api(
        "/payroll/late-warnings-tick", json={}, timeout=60, label="Kechikish limiti ogohlantirish"
    )
    if body is not None and body.get("warned"):
        logger.info("Kechikish limiti ogohlantirish: %s", body)


async def payroll_overtime_auto_detect() -> None:
    """Qo'shimcha ish avtomatik aniqlash (1.3-band): kechagi check-out'lardan
    nomzod (`pending`) yaratadi — HR/rahbar hali tasdiqlashi kerak."""
    body = await call_api(
        "/payroll/overtime/auto-detect", json={}, timeout=60, label="Overtime avtomatik aniqlash"
    )
    if body is not None and body.get("created"):
        logger.info("Overtime nomzodlari avtomatik yaratildi: %s", body)


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


async def idle_watch_tick() -> None:
    """Real-vaqtli harakatsizlik nazorati: so'nggi qo'ng'iroqdan beri 20+ daqiqa
    o'tgan, ochiq lidi bor operatorlarni guruhga chiqaradi (adolat filtrlari va
    shovqin nazorati bilan). API AI_ENABLED va runtime idle_alerts_enabled'ni
    o'zi tekshiradi (o'chiqda no-op)."""
    body = await call_api("/idle-watch/tick", timeout=60, label="Harakatsizlik nazorati tick")
    if body is None or body.get("disabled") or body.get("idle_alerts_disabled"):
        return
    if body.get("alerted"):
        logger.info("Harakatsizlik: %s ta operatorga ogohlantirish", body["alerted"])


async def anketa_tick() -> None:
    """Bilim bazasi anketasi: Dasturchi tasdiqlagan vaqti kelgan sessiyalarni
    boshlaydi (xodimlarga birinchi savollarni yuboradi). Faol sessiya bo'lmasa no-op."""
    body = await call_api("/anketa/tick", timeout=120, label="Anketa tick")
    if body is not None and body.get("started"):
        logger.info("Anketa: %s ta sessiya boshlandi", body["started"])


async def knowledge_tick() -> None:
    """Bilim bazasi: draft yozuvlarni chegaralangan AI to'plamida qayta ishlaydi
    (draft bo'lmasa no-op)."""
    body = await call_api("/knowledge/tick", timeout=120, label="Bilim bazasi tick")
    if body is not None and body.get("processed"):
        logger.info(
            "Bilim bazasi: %s birlik ishlandi, %s draft qoldi",
            body["processed"], body.get("remaining"),
        )


async def playbook_tick() -> None:
    """Sotuv playbook: faol qurish bosqichini davom ettiradi (build yo'q — no-op)."""
    body = await call_api("/playbook/tick", timeout=120, label="Playbook tick")
    if body is not None and body.get("active"):
        logger.info("Playbook qurilmoqda: bosqich=%s", body.get("status"))


async def knowledge_stale() -> None:
    """Bilim bazasi: eskirgan sana-sezgir yozuvlarni belgilab rahbarga eslatadi."""
    body = await call_api("/knowledge/stale-tick", timeout=60, label="Bilim bazasi eskirish")
    if body is not None and body.get("flagged"):
        logger.info("Bilim bazasi: %s ta eskirgan yozuv belgilandi", body["flagged"])


async def ai_weekly_run() -> None:
    """Haftalik AI trend: har operatorga SHAXSIY xulosa (guruhga jamoa ko'rinishini
    endi raqamli haftalik digest beradi — send_weekly_digest)."""
    body = await call_api("/ai-watch/weekly-run", timeout=300, label="AI haftalik")
    if body is not None and not body.get("disabled") and not body.get("weekly_disabled"):
        logger.info("AI haftalik: operators=%s sent=%s", body.get("operators"), body.get("sent"))
