"""Scheduler o'rnini bosuvchi YAGONA cron skripti (cPanel deploy).

Shared hostingda doimiy scheduler jarayoni yo'q. Buning o'rniga cPanel cron shu
skriptni HAR DAQIQADA bir marta chaqiradi:

    * * * * *  cd ~/hodimlar && venv/bin/python scripts/cron_tick.py >> ~/hodimlar/logs/cron.log 2>&1

Skript joriy vaqtni (Asia/Tashkent) tekshirib, o'sha daqiqada bajarilishi kerak
bo'lgan API endpointlarini chaqiradi — scheduler/main.py'dagi JOBS jadvali bilan
bir xil, lekin apscheduler o'rniga cron tik'iga bog'langan. Endpointlar
X-Bot-Secret bilan himoyalangan (scheduler.client.call_api'dan foydalanadi).

Eslatma: crm_sync ilgari 30 soniyada edi — cron minimal granularligi 1 daqiqa,
shuning uchun daqiqada bir marta (8 xodimlik jamoa uchun yetarli)."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import config as cfg  # noqa: E402
from scheduler.client import call_api  # noqa: E402

TZ = ZoneInfo(cfg.TIMEZONE)


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

    # ── Interval ──
    if m % 15 == 0:
        add("/tasks/mark-overdue")
        add("/auto-plan/snapshot", timeout=120)      # AI actual (o'chiqda no-op)
    if m % 30 == 0:
        add("/stats/lead-stages/sync", timeout=600)  # lid snapshot
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
    if last_day and h == cfg.LEAD_SNAPSHOT_FREEZE_HOUR and m == cfg.LEAD_SNAPSHOT_FREEZE_MINUTE:
        add("/stats/lead-stages/sync", timeout=600)  # kun/oy yakunida "muzlatish"

    return jobs


async def main() -> None:
    now = datetime.now(TZ)
    jobs = _due(now)
    if not jobs:
        return
    results = await asyncio.gather(
        *(call_api(path, **kw) for path, kw in jobs), return_exceptions=True
    )
    fired = [p for (p, _), r in zip(jobs, results) if r is not None and not isinstance(r, Exception)]
    if fired:
        print(f"{now:%Y-%m-%d %H:%M} tik: {', '.join(fired)}")


if __name__ == "__main__":
    asyncio.run(main())
