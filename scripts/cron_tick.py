"""Scheduler o'rnini bosuvchi YAGONA cron skripti (cPanel deploy).

Shared hostingda doimiy scheduler jarayoni yo'q. Buning o'rniga cPanel cron shu
skriptni HAR DAQIQADA bir marta chaqiradi:

    * * * * *  cd ~/hodimlar && venv/bin/python scripts/cron_tick.py >> ~/hodimlar/logs/cron.log 2>&1

Skript joriy vaqtni (Asia/Tashkent) tekshirib, o'sha daqiqada bajarilishi kerak
bo'lgan API endpointlarini chaqiradi — scheduler/main.py'dagi JOBS jadvali bilan
bir xil, lekin apscheduler o'rniga cron tik'iga bog'langan. Endpointlar
X-Bot-Secret bilan himoyalangan (scheduler.client.call_api'dan foydalanadi).

MUHIM ISTISNO — lid snapshoti (og'ir skaner) HTTP orqali EMAS, shu jarayonning
O'ZIDA (in-process) bajariladi: butun CRM bazasini sahifalash ~5-7 daqiqa davom
etadi, shared hosting gateway'i esa HTTP so'rovni ~180 soniyada o'ldiradi (jonli
sinovda 182s da HTTP 500). Cron jarayoniga bunday limit yo'q. Parallel yozuvlar
uchun db/base.py'da SQLite busy timeout 30s qilingan; ketma-ket ikki skan
ustma-tushmasligi uchun lock fayl ishlatiladi.

Eslatma: crm_sync ilgari 30 soniyada edi — cron minimal granularligi 1 daqiqa,
shuning uchun daqiqada bir marta (8 xodimlik jamoa uchun yetarli)."""
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

# Lid skaneri lock fayli — skan ~5-7 daqiqa, interval 30 daqiqa; CRM sekinlashib
# (429 backoff) cho'zilib ketsa keyingi skan boshlanmasin. Eskirgan (25 daq+)
# lock e'tiborga olinmaydi (jarayon o'lib qolgan bo'lishi mumkin).
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

    # ── Har daqiqalik tick'lar BU RO'YXATDA EMAS (2026-07-31) ─────────────────
    # group-tick, digest-tick, daily-results/sync, anketa/tick — barchasi
    # in-process bajariladi (main() pastda). Sabab: jonli o'lchovda har
    # daqiqadagi HTTP to'plami Passenger'ning YAGONA ishchisini 2-4s band qilib,
    # o'sha oynaga tushgan foydalanuvchi so'rovlari 3s+ kutar yoki timeout
    # bo'lardi. Endi ishchiga cron'dan deyarli HTTP kelmaydi.

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
    if m % 5 == 3:
        add("/knowledge/tick", timeout=120)          # bilim bazasi AI ishlovi (draft yo'q — no-op)
        add("/playbook/tick", timeout=120)           # playbook qurish bosqichlari (build yo'q — no-op)

    # ── Interval ──
    if m % 15 == 0:
        add("/tasks/mark-overdue")
        add("/auto-plan/snapshot", timeout=120)      # AI actual (o'chiqda no-op)
    # DIQQAT: lid snapshoti (/stats/lead-stages/sync) bu ro'yxatda YO'Q — u og'ir
    # (~5-7 daqiqa) va gateway HTTP limitiga sig'maydi; _lead_sync_due + in-process
    # yo'l bilan bajariladi (pastda).
    # DIQQAT: /hot-lead/tick va /idle-watch/tick bu ro'yxatda YO'Q — jonli
    # o'lchovda 4.7s va 2.0s chiqqani uchun lid skaneri kabi in-process
    # bajariladi (main() pastda) — Passenger'ning yagona ishchisi band bo'lmasin.

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
    """Lid snapshoti vaqti: har LEAD_SNAPSHOT_INTERVAL_MINUTES (default 15 daqiqa —
    :00/:15/:30/:45) va HAR KUNI 23:57 "muzlatish" (scheduler/main.py bilan bir
    xil — avvalgi versiyada muzlatish xato ravishda faqat oyning oxirgi kuniga
    bog'langan edi)."""
    if now.minute % cfg.LEAD_SNAPSHOT_INTERVAL_MINUTES == 0:
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


async def _run_minute_ticks_inprocess(now: datetime) -> None:
    """Har daqiqalik yengil tick'lar — HTTP o'rniga shu jarayonda.

    Har biri alohida sessiya va alohida try ichida: bittasining xatosi
    qolganlarini to'xtatmasin. Router funksiyalari faqat `db` qabul qiladi,
    shuning uchun to'g'ridan-to'g'ri chaqirsa bo'ladi."""
    from db.base import async_session

    async def one(label: str, fn) -> None:
        try:
            async with async_session() as db:
                await fn(db)
        except Exception as exc:  # noqa: BLE001 — bittasi qolganini to'xtatmasin
            print(f"{now:%Y-%m-%d %H:%M} {label} XATO: {type(exc).__name__}: {exc}")

    from api.routers.attendance import attendance_digest_tick
    from api.routers.stats import group_post_tick

    await one("kunlik digest tick", group_post_tick)
    await one("davomat digest tick", attendance_digest_tick)

    if now.minute % 2 == 1:
        from api.routers import anketa as anketa_router
        from api.routers.daily_results import sync_daily_results

        await one("CRM sync", sync_daily_results)
        await one("anketa tick", anketa_router.tick)


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
        results = await asyncio.gather(
            *(call_api(path, **kw) for path, kw in jobs), return_exceptions=True
        )
        fired = [p for (p, _), r in zip(jobs, results) if r is not None and not isinstance(r, Exception)]
        if fired:
            print(f"{now:%Y-%m-%d %H:%M} tik: {', '.join(fired)}")

    # Har daqiqalik yengil tick'lar (digest'lar; toq daqiqada CRM sync + anketa)
    await _run_minute_ticks_inprocess(now)

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
