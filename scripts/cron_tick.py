"""Scheduler o'rnini bosuvchi YAGONA cron skripti (cPanel deploy).

Shared hostingda doimiy scheduler jarayoni yo'q. Buning o'rniga cPanel cron shu
skriptni HAR DAQIQADA bir marta chaqiradi:

    * * * * *  cd ~/hodimlar && venv/bin/python scripts/cron_tick.py >> ~/hodimlar/logs/cron.log 2>&1

Skript joriy vaqtni (Asia/Tashkent) tekshirib, o'sha daqiqada bajarilishi kerak
bo'lgan API endpointlarini chaqiradi — scheduler/main.py'dagi JOBS jadvali bilan
bir xil, lekin apscheduler o'rniga cron tik'iga bog'langan. Endpointlar
X-Bot-Secret bilan himoyalangan (scheduler.client.call_api'dan foydalanadi).

MUHIM ISTISNO — lid snapshoti va boshqa uzun ishlaydigan skanlar HTTP orqali
EMAS, shu jarayonning O'ZIDA (in-process) bajariladi: shared hosting gateway'i
HTTP so'rovni ~180 soniyada o'ldiradi (jonli sinovda 182s da HTTP 500), cron
jarayoniga esa bunday limit yo'q. (Lid snapshoti 2026-08-03 dan lokal
LeadEvent hisobiga o'tib ancha yengillashdi — CRM'ga faqat qo'ng'iroqlar skani
qoldi — lekin Passenger'ning yagona ishchisini band qilmaslik uchun in-process
yo'lda qoladi.) Parallel yozuvlar uchun db/base.py'da SQLite busy timeout 30s
qilingan; ketma-ket ikki skan ustma-tushmasligi uchun lock fayl ishlatiladi.

Eslatma: crm_sync cron granularligi tufayli bu rejimda har 2 daqiqada (m%2==1)
— scheduler rejimidagi CRM_SYNC_INTERVAL_SECONDS=120 bilan mos."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scheduler import config as cfg  # noqa: E402
from scheduler.client import call_api  # noqa: E402

TZ = ZoneInfo(cfg.TIMEZONE)

# Lid skaneri lock fayli — snapshot endi yengil (lidlar lokal hisobdan, CRM'ga
# faqat qo'ng'iroqlar skani, odatda <1 daqiqa), lekin 429 cooldown'da cho'zilishi
# mumkin — keyingi skan boshlanmasin. Eskirgan (25 daq+) lock e'tiborga
# olinmaydi (jarayon o'lib qolgan bo'lishi mumkin).
LEAD_SYNC_LOCK = ROOT / "logs" / "lead_sync.lock"
LEAD_SYNC_LOCK_STALE_MINUTES = 25

# Diff-engine (lead_diff.py) — chegaralangan skan ham (200 sahifagacha, 429
# backoff'da) gateway'ning 180s limitiga sig'maslik xavfi bor, shuning uchun
# lid skaneri bilan bir xil in-process+lock naqshi ishlatiladi. Interval qisqa
# (3 daqiqa) bo'lgani uchun stale chegara ham qisqaroq.
LEAD_DIFF_LOCK = ROOT / "logs" / "lead_diff.lock"
LEAD_DIFF_LOCK_STALE_MINUTES = 8
LEAD_DIFF_RECONCILE_LOCK = ROOT / "logs" / "lead_diff_reconcile.lock"
LEAD_DIFF_RECONCILE_LOCK_STALE_MINUTES = 25

# Issiq lid va harakatsizlik nazorati — jonli o'lchovda (2026-07-31) HTTP orqali
# 4.7s va 2.0s chiqdi. cPanel'da Passenger'ning YAGONA ishchisi bor — bu ikkovi
# HTTP orqali chaqirilsa ishchi shu vaqt band bo'lib, sayt so'rovlari navbatda
# kutadi. Shuning uchun lid skaneri bilan bir xil in-process+lock naqshiga
# ko'chirildi (HTTP endpointlar Docker/scheduler rejimi uchun saqlanadi).
HOT_LEAD_LOCK = ROOT / "logs" / "hot_lead.lock"
HOT_LEAD_LOCK_STALE_MINUTES = 8
IDLE_WATCH_LOCK = ROOT / "logs" / "idle_watch.lock"
IDLE_WATCH_LOCK_STALE_MINUTES = 8


def _is_last_day(d: datetime) -> bool:
    return (d + timedelta(days=1)).month != d.month


def _due(now: datetime) -> list:
    """Shu daqiqada bajarilishi kerak bo'lgan (path, kwargs) chaqiruvlar ro'yxati."""
    m, h = now.minute, now.hour
    dow_sun = now.isoweekday() == 7
    last_day = _is_last_day(now)
    jobs: list[tuple[str, dict]] = []

    def add(path: str, **kw) -> None:
        jobs.append((path, kw))

    # ── Har daqiqa — FAQAT aniq vaqtga bog'liqlari ────────────────────────────
    # Bu ikkisi foydalanuvchi sozlagan ANIQ daqiqada ishlashi kerak (vaqt bazadan
    # o'qiladi, ">=" semantikasi + kuniga-bir-marta qo'riqchisi bilan), shuning
    # uchun siyraklashtirilmaydi.
    add("/stats/lead-stages/group-tick", timeout=120)  # kunlik digest (API vaqtni tekshiradi)
    add("/attendance/digest-tick", timeout=60)       # davomat digesti (API vaqtni bazadan tekshiradi)

    # ── Siyraklashtirilgan (2026-07-27) ───────────────────────────────────────
    # SABAB: bu hostda Passenger'da ATIGI 1 ta ishchi jarayon bor. Har daqiqada
    # 6 ta ketma-ket HTTP chaqiruv (eng sekini /daily-results/sync — jonli
    # o'lchovda 1-4.4s) yagona ishchini to'ldirib qo'yardi va shu paytda kelgan
    # sayt/bot so'rovlari navbatda qotib, 25s+ timeout berardi. Quyidagilarning
    # hech biri aniq daqiqaga bog'liq emas (kechikish zararsiz), shuning uchun
    # siyraklashtirildi — egasi ongli qarori: "sekinroq bo'lsa ham ishlasin".
    # DIQQAT: toq/siljitilgan qoldiq ATAYIN — mavjud job'lar (m%15, m%5, m%2,
    # m==0) hammasi JUFT daqiqalarda, ayniqsa :00 da to'planadi (o'lchandi: bitta
    # daqiqada 11 ta chaqiruv). Bu guruhlar toq daqiqalarga surildi — cho'qqi
    # tekislanadi, yagona ishchi bir zumda to'lib qolmaydi.
    if m % 2 == 1:
        # CRM sync: so'rov byudjeti pacing'i bilan kun oxirida (10-15 sahifa
        # call-history + tashrif lidlari) 30s'dan oshishi mumkin — default 30s
        # timeout'da cron.log'ga ReadTimeout traceback tushardi (jonli, 2026-08-04).
        add("/daily-results/sync", timeout=120)
        add("/anketa/tick", timeout=120)             # anketa max 2 daq kechikib boshlanadi
    if m % 5 == 3:
        add("/knowledge/tick", timeout=120)          # bilim bazasi AI ishlovi (draft yo'q — no-op)
        add("/playbook/tick", timeout=120)           # playbook qurish bosqichlari (build yo'q — no-op)

    # ── Interval ──
    if m % 15 == 0:
        add("/tasks/mark-overdue")
        add("/auto-plan/snapshot", timeout=120)      # AI actual (o'chiqda no-op)
    # CRM aloqasi qo'riqchisi — 17-daqiqa qoldig'i ATAYIN (yuqoridagi m%15
    # guruhiga qo'shilmasin, yagona Passenger ishchisi bir zumda to'lmasin).
    # Chegara 2 soat bo'lgani uchun yarim soatlik tekshiruv yetarli.
    if m % 30 == 17:
        add("/crm-health/tick", json={}, timeout=60)
    # DIQQAT: lid snapshoti (/stats/lead-stages/sync) bu ro'yxatda YO'Q — u og'ir
    # (~5-7 daqiqa) va gateway HTTP limitiga sig'maydi; _lead_sync_due + in-process
    # yo'l bilan bajariladi (pastda).
    # DIQQAT: /hot-lead/tick va /idle-watch/tick bu ro'yxatda YO'Q — jonli
    # o'lchovda 4.7s va 2.0s chiqqani uchun lid skaneri kabi in-process
    # bajariladi (main() pastda) — Passenger'ning yagona ishchisi band bo'lmasin.

    # «Keldim/Ketdim bosishni unutmang» — API dam kuni/sababli kun/allaqachon
    # bosganlarni o'zi filtrlaydi va kuniga bir marta yuboradi (UNIQUE iz).
    # Toq qoldiq (==1) ATAYLAB: yuqoridagi guruhlar juft daqiqalarda
    # to'planadi, yagona Passenger ishchisi bir zumda to'lib qolmasin.
    if m % cfg.ATTENDANCE_REMINDER_INTERVAL_MINUTES == 1:
        add("/attendance/reminder-tick", json={}, timeout=120)

    # ── Soatlik ──
    if m == 0:
        add("/hourly-plan/send", timeout=60)         # soatlik reja (API ish oynasini tekshiradi)
        # Telegram login xavfsizligi: replay-himoya hash'lari + rate-limit
        # urinish yozuvlarini tozalash (scheduler/main.py'dagi
        # login_security_cleanup bilan bir xil — cron_tick shared hostingda
        # o'sha APScheduler job'ining o'rnini bosadi).
        add("/auth/login-security-cleanup", json={}, timeout=30)
    if m == cfg.AI_WATCH_MINUTE:
        add("/ai-watch/tick", timeout=180)           # AI kuzatuv (o'chiqda no-op)

    # ── Kunlik ──
    if m == 0 and h in cfg.REMINDER_HOURS:
        add("/tasks/send-reminders")
    if h == cfg.YESTERDAY_CORRECTION_HOUR and m == cfg.YESTERDAY_CORRECTION_MINUTE:
        add("/reports/yesterday-correction", timeout=60)
    if h == cfg.AI_BUILD_TARGETS_HOUR and m == 0:
        add("/auto-plan/build-targets", timeout=120)
    if h == 9 and m == 35:
        add("/knowledge/stale-tick", timeout=60)     # eskirgan sana-sezgir yozuvlar eslatmasi
    # Payroll (OYLIK_JARIMA_REJASI.md, Bosqich 6) — scheduler/main.py'dagi
    # payroll_late_warnings / payroll_overtime_auto_detect job'lari bilan bir xil
    if h == cfg.LATE_WARNING_HOUR and m == cfg.LATE_WARNING_MINUTE:
        add("/payroll/late-warnings-tick", json={}, timeout=60)   # kechikish limiti ogohlantirishi (1.5-band)
    if h == cfg.OVERTIME_AUTO_DETECT_HOUR and m == cfg.OVERTIME_AUTO_DETECT_MINUTE:
        add("/payroll/overtime/auto-detect", json={}, timeout=60)  # qo'shimcha ish nomzodlari (1.3-band)
    # DIQQAT: davomat digesti bu yerda EMAS — vaqti bazadan (botdan /davomat_vaqt
    # bilan) sozlanadi, shuning uchun har daqiqa chaqiriladigan
    # /attendance/digest-tick o'zi tekshiradi (yuqorida).

    # ── Haftalik (yakshanba) ──
    if dow_sun and h == cfg.AI_COMPUTE_PROFILES_HOUR and m == 0:
        add("/auto-plan/compute-profiles", timeout=120)
    if dow_sun and h == cfg.WEEKLY_DIGEST_HOUR and m == cfg.WEEKLY_DIGEST_MINUTE:
        add("/reports/weekly-digest", timeout=120)
    if dow_sun and h == cfg.AI_WEEKLY_HOUR and m == cfg.AI_WEEKLY_MINUTE:
        add("/ai-watch/weekly-run", timeout=300)

    # ── Oylik (oyning oxirgi kuni) ──
    if last_day and h == cfg.MONTHLY_DIGEST_HOUR and m == cfg.MONTHLY_DIGEST_MINUTE:
        add("/reports/monthly-digest", timeout=120)
    if last_day and h == cfg.MONTHLY_BONUS_HOUR and m == cfg.MONTHLY_BONUS_MINUTE:
        add("/bonuses/calculate-monthly", json={}, timeout=60)

    # ── Oylik (KEYINGI oyning 1-kuni) ──
    # Payroll bonus (oxirgi kun 23:30) va davomat yopilishidan (22:00) KEYIN
    # ishlaydi — shuning uchun oxirgi kun emas, keyingi oyning 1-kuni ertalab
    # (9-bo'lim savol 10 QAROR; scheduler/main.py monthly_payroll bilan bir xil).
    if (now.day == cfg.MONTHLY_PAYROLL_DAY and h == cfg.MONTHLY_PAYROLL_HOUR
            and m == cfg.MONTHLY_PAYROLL_MINUTE):
        add("/payroll/calculate-monthly", json={}, timeout=120)

    return jobs


def _lead_sync_due(now: datetime) -> bool:
    """Lid snapshoti vaqti: har LEAD_SNAPSHOT_INTERVAL_MINUTES da bir, va HAR KUNI
    23:57 "muzlatish" (scheduler/main.py bilan bir xil — avvalgi versiyada
    muzlatish xato ravishda faqat oyning oxirgi kuniga bog'langan edi).

    Qoldiq 8 ATAYIN (2026-08-03): ==0 bo'lsa diff skani (m%5==0) bilan bir
    daqiqaga to'planardi. Cron jarayoni ICHIDAGI to'qnashuvlar (issiq-lid m%2==0)
    endi xavfsiz — hammasi bitta so'rov byudjeti orqali o'tadi (crm/uysot.py);
    asosiy xavf BOSHQA jarayondagi (Passenger, toq daqiqalardagi
    /daily-results/sync) CRM chaqiruvlari bilan ustma-ust tushish edi. 8 juft
    (toq guruhga tegmaydi) va 5 ga bo'linmaydi (diff bilan kesishmaydi) —
    :08/:38."""
    if now.minute % cfg.LEAD_SNAPSHOT_INTERVAL_MINUTES == 8:
        return True
    return now.hour == cfg.LEAD_SNAPSHOT_FREEZE_HOUR and now.minute == cfg.LEAD_SNAPSHOT_FREEZE_MINUTE


def _lock_fresh(lock_path: Path, stale_minutes: int, now: datetime) -> bool:
    """Boshqa skan hali tugamagan bo'lsa True (lock fayl yosh)."""
    try:
        started = datetime.fromisoformat(lock_path.read_text().strip())
        return (now - started) < timedelta(minutes=stale_minutes)
    except (OSError, ValueError):
        return False


def _lead_lock_fresh(now: datetime) -> bool:
    return _lock_fresh(LEAD_SYNC_LOCK, LEAD_SYNC_LOCK_STALE_MINUTES, now)


async def _run_lead_sync_inprocess(now: datetime) -> None:
    """Og'ir lid skanerini HTTP'siz, shu cron jarayonining o'zida bajaradi —
    gateway timeout'iga bog'liq emas. Xato bo'lsa log'ga yozadi, lock har doim
    tozalanadi (keyingi skan bloklanib qolmasin)."""
    if _lead_lock_fresh(now):
        print(f"{now:%Y-%m-%d %H:%M} lid snapshot: oldingi skan hali tugamagan — o'tkazib yuborildi")
        return

    LEAD_SYNC_LOCK.parent.mkdir(parents=True, exist_ok=True)
    LEAD_SYNC_LOCK.write_text(now.isoformat())
    try:
        # Importlar shu yerda — oddiy (yengil) daqiqalarda FastAPI/DB yuklanmasin
        from api.routers.stats import _snapshot_lead_breakdown
        from db.base import async_session

        async with async_session() as db:
            result = await _snapshot_lead_breakdown(db)
        print(f"{now:%Y-%m-%d %H:%M} lid snapshot (in-process): {result}")
    except Exception as exc:  # noqa: BLE001 — cron jim o'lmasin, log qoldirsin
        print(f"{now:%Y-%m-%d %H:%M} lid snapshot XATO: {type(exc).__name__}: {exc}")
    finally:
        try:
            LEAD_SYNC_LOCK.unlink()
        except OSError:
            pass


async def _run_lead_diff_inprocess(now: datetime, full: bool) -> None:
    """Diff-engine skanerini HTTP'siz, shu cron jarayonining o'zida bajaradi —
    gateway timeout'iga bog'liq emas (`_run_lead_sync_inprocess` bilan bir xil
    naqsh, alohida lock fayl bilan)."""
    lock = LEAD_DIFF_RECONCILE_LOCK if full else LEAD_DIFF_LOCK
    stale = LEAD_DIFF_RECONCILE_LOCK_STALE_MINUTES if full else LEAD_DIFF_LOCK_STALE_MINUTES
    label = "lid diff (to'liq)" if full else "lid diff"

    if _lock_fresh(lock, stale, now):
        print(f"{now:%Y-%m-%d %H:%M} {label}: oldingi skan hali tugamagan — o'tkazib yuborildi")
        return

    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(now.isoformat())
    try:
        from api.services.lead_diff import diff_tick
        from db.base import async_session

        async with async_session() as db:
            result = await diff_tick(db, full=full)
        print(f"{now:%Y-%m-%d %H:%M} {label} (in-process): {result}")
    except Exception as exc:  # noqa: BLE001 — cron jim o'lmasin, log qoldirsin
        print(f"{now:%Y-%m-%d %H:%M} {label} XATO: {type(exc).__name__}: {exc}")
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


async def _run_service_inprocess(now: datetime, label: str, lock: Path, stale_min: int, runner) -> None:
    """Umumiy in-process yurituvchi: lock oladi, servisni shu jarayonda bajaradi,
    natija/xatoni log'ga yozadi (lead sync/diff bilan bir xil naqsh)."""
    if _lock_fresh(lock, stale_min, now):
        print(f"{now:%Y-%m-%d %H:%M} {label}: oldingisi hali tugamagan — o'tkazib yuborildi")
        return

    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(now.isoformat())
    try:
        from db.base import async_session

        async with async_session() as db:
            result = await runner(db)
        print(f"{now:%Y-%m-%d %H:%M} {label} (in-process): {result}")
    except Exception as exc:  # noqa: BLE001 — cron jim o'lmasin, log qoldirsin
        print(f"{now:%Y-%m-%d %H:%M} {label} XATO: {type(exc).__name__}: {exc}")
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


async def _run_hot_lead_inprocess(now: datetime) -> None:
    async def runner(db):
        from api.services.hot_lead import tick
        return await tick(db)

    await _run_service_inprocess(now, "issiq lid", HOT_LEAD_LOCK, HOT_LEAD_LOCK_STALE_MINUTES, runner)


async def _run_idle_watch_inprocess(now: datetime) -> None:
    async def runner(db):
        from api.services.idle_watch import evaluate_and_alert
        return await evaluate_and_alert(db)

    await _run_service_inprocess(now, "harakatsizlik", IDLE_WATCH_LOCK, IDLE_WATCH_LOCK_STALE_MINUTES, runner)


def _lead_diff_due(now: datetime) -> bool:
    return now.minute % cfg.LEAD_DIFF_INTERVAL_MINUTES == 0


def _lead_diff_reconcile_due(now: datetime) -> bool:
    return now.hour == cfg.LEAD_DIFF_RECONCILE_HOUR and now.minute == cfg.LEAD_DIFF_RECONCILE_MINUTE


async def main() -> None:
    now = datetime.now(TZ)

    # Qo'lda darhol skan: venv/bin/python scripts/cron_tick.py --lead-sync-now
    # (deploy'dan keyin birinchi to'ldirish yoki diagnostika uchun — :00/:30 kutilmaydi)
    if "--lead-sync-now" in sys.argv:
        await _run_lead_sync_inprocess(now)
        return
    # Diff-engine'ni qo'lda sinash: --lead-diff-now (chegaralangan) yoki
    # --lead-diff-reconcile-now (to'liq, baseline birinchi marta shu bilan seed qilinadi)
    if "--lead-diff-now" in sys.argv:
        await _run_lead_diff_inprocess(now, full=False)
        return
    if "--lead-diff-reconcile-now" in sys.argv:
        await _run_lead_diff_inprocess(now, full=True)
        return

    jobs = _due(now)
    if jobs:
        # Passenger'da BITTA ishchi bor — hamma so'rov unda navbatga tushadi.
        # Vaqt-sezgir daqiqalik ticklar (digest'lar) AVVAL, tez tugaydi (~1-2s);
        # keyin qolganlari. Aks holda (jonli, 2026-08-04 15:23) toq daqiqada
        # /daily-results/sync (Uysot pacing bilan ~30-40s) ishchini band qilib,
        # /attendance/digest-tick 60s timeout'iga yetmay ReadTimeout berardi.
        URGENT_PATHS = {"/stats/lead-stages/group-tick", "/attendance/digest-tick"}
        urgent = [(p, kw) for p, kw in jobs if p in URGENT_PATHS]
        rest = [(p, kw) for p, kw in jobs if p not in URGENT_PATHS]
        results = []
        for batch in (urgent, rest):
            if batch:
                results += await asyncio.gather(
                    *(call_api(path, **kw) for path, kw in batch), return_exceptions=True
                )
        ordered = urgent + rest
        fired = [p for (p, _), r in zip(ordered, results) if r is not None and not isinstance(r, Exception)]
        if fired:
            print(f"{now:%Y-%m-%d %H:%M} tik: {', '.join(fired)}")

    # Issiq lid va harakatsizlik nazorati — in-process (4.7s/2.0s HTTP o'rniga),
    # avvalgi bilan bir xil chastota: har 2 daqiqa / IDLE_WATCH_INTERVAL_MINUTES
    if now.minute % 2 == 0:
        await _run_hot_lead_inprocess(now)
    if now.minute % cfg.IDLE_WATCH_INTERVAL_MINUTES == 0:
        await _run_idle_watch_inprocess(now)

    # Og'ir lid skaneri — HTTP jobs'dan KEYIN (yengil ticklar kechikmasin)
    if _lead_sync_due(now):
        await _run_lead_sync_inprocess(now)

    # Diff-engine (haqiqiy lid voqealari) — xuddi shu sabab bilan in-process
    if _lead_diff_due(now):
        await _run_lead_diff_inprocess(now, full=False)
    if _lead_diff_reconcile_due(now):
        await _run_lead_diff_inprocess(now, full=True)


if __name__ == "__main__":
    asyncio.run(main())
