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

    # ── Har daqiqa (yengil, o'zini vaqt/bayroq bo'yicha tekshiradi) ──
    add("/daily-results/sync")                       # CRM sync (ilgari 30s)
    add("/stats/lead-stages/group-tick", timeout=120)  # kunlik digest (API vaqtni tekshiradi)
    add("/anketa/tick", timeout=120)                 # rejalashtirilgan anketani boshlash
    add("/knowledge/tick", timeout=120)              # bilim bazasi AI ishlovi (draft yo'q — no-op)
    add("/playbook/tick", timeout=120)               # playbook qurish bosqichlari (build yo'q — no-op)
    add("/attendance/digest-tick", timeout=60)       # davomat digesti (API vaqtni bazadan tekshiradi)

    # ── Interval ──
    if m % 15 == 0:
        add("/tasks/mark-overdue")
        add("/auto-plan/snapshot", timeout=120)      # AI actual (o'chiqda no-op)
    # DIQQAT: lid snapshoti (/stats/lead-stages/sync) bu ro'yxatda YO'Q — u og'ir
    # (~5-7 daqiqa) va gateway HTTP limitiga sig'maydi; _lead_sync_due + in-process
    # yo'l bilan bajariladi (pastda).
    if m % 2 == 0:
        add("/hot-lead/tick", timeout=120)           # issiq lid (o'chiqda no-op)

    # ── Soatlik ──
    if m == 0:
        add("/hourly-plan/send", timeout=60)         # soatlik reja (API ish oynasini tekshiradi)
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

    return jobs


def _lead_sync_due(now: datetime) -> bool:
    """Lid snapshoti vaqti: har LEAD_SNAPSHOT_INTERVAL_MINUTES (default :00/:30)
    va HAR KUNI 23:57 "muzlatish" (scheduler/main.py bilan bir xil — avvalgi
    versiyada muzlatish xato ravishda faqat oyning oxirgi kuniga bog'langan edi)."""
    if now.minute % cfg.LEAD_SNAPSHOT_INTERVAL_MINUTES == 0:
        return True
    return now.hour == cfg.LEAD_SNAPSHOT_FREEZE_HOUR and now.minute == cfg.LEAD_SNAPSHOT_FREEZE_MINUTE


def _lead_lock_fresh(now: datetime) -> bool:
    """Boshqa skan hali tugamagan bo'lsa True (lock fayl yosh)."""
    try:
        started = datetime.fromisoformat(LEAD_SYNC_LOCK.read_text().strip())
        return (now - started) < timedelta(minutes=LEAD_SYNC_LOCK_STALE_MINUTES)
    except (OSError, ValueError):
        return False


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


async def main() -> None:
    now = datetime.now(TZ)

    # Qo'lda darhol skan: venv/bin/python scripts/cron_tick.py --lead-sync-now
    # (deploy'dan keyin birinchi to'ldirish yoki diagnostika uchun — :00/:30 kutilmaydi)
    if "--lead-sync-now" in sys.argv:
        await _run_lead_sync_inprocess(now)
        return

    jobs = _due(now)
    if jobs:
        results = await asyncio.gather(
            *(call_api(path, **kw) for path, kw in jobs), return_exceptions=True
        )
        fired = [p for (p, _), r in zip(jobs, results) if r is not None and not isinstance(r, Exception)]
        if fired:
            print(f"{now:%Y-%m-%d %H:%M} tik: {', '.join(fired)}")

    # Og'ir lid skaneri — HTTP jobs'dan KEYIN (yengil ticklar kechikmasin)
    if _lead_sync_due(now):
        await _run_lead_sync_inprocess(now)


if __name__ == "__main__":
    asyncio.run(main())
