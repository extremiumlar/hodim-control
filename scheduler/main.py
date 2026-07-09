"""Scheduler bootstrap — deklarativ job reyestri.

Barcha rejalashtirilgan ishlar `JOBS` ro'yxatida bitta joyda e'lon qilinadi
(korutin + trigger + parametrlar). `main()` shu ro'yxatni aylanib scheduler'ga
qo'shadi — yangi job qo'shish uchun `scheduler/jobs.py`ga korutin yozib, shu
ro'yxatga bitta `JobSpec` qatorini qo'shish kifoya (main() o'zgarmaydi)."""
import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scheduler import config as cfg
from scheduler import jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobSpec:
    """Bitta rejalashtirilgan ish. `None` parametrlar `add_job`ga uzatilmaydi
    (apscheduler default'i qo'llanadi) — bu har job'ning aniq xatti-harakatini
    saqlaydi."""

    name: str
    func: Callable[[], Awaitable[None]]
    trigger: BaseTrigger
    max_instances: int | None = None
    misfire_grace_time: int | None = None
    coalesce: bool | None = None


def _cron(**kwargs) -> CronTrigger:
    return CronTrigger(timezone=cfg.TIMEZONE, **kwargs)


def _build_jobs() -> list[JobSpec]:
    specs: list[JobSpec] = []

    # Vazifa eslatmalari — belgilangan soatlarda
    for hour in cfg.REMINDER_HOURS:
        specs.append(
            JobSpec(
                f"reminders@{hour:02d}", jobs.send_reminders, _cron(hour=hour, minute=0),
                misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
            )
        )

    specs += [
        # Kunlik xulosa
        JobSpec(
            "daily_summary", jobs.send_daily_summary,
            _cron(hour=cfg.DAILY_SUMMARY_HOUR, minute=0),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Guruhga kunlik lid statistikasi — vaqt bazadan sozlangani uchun har daqiqa
        # tekshiriladi (API vaqt kelganini va shu kuni yuborilmaganini o'zi hal qiladi).
        JobSpec(
            "group_post_tick", jobs.group_post_tick, IntervalTrigger(minutes=1),
            max_instances=1, coalesce=True,
        ),
        # CRM natijalarini deyarli real-vaqtli sinxronlash
        JobSpec(
            "crm_sync", jobs.sync_daily_results,
            IntervalTrigger(seconds=cfg.CRM_SYNC_INTERVAL_SECONDS),
        ),
        # Soatlik reja eslatmasi — har soat boshida (API ish oynasini o'zi filtrlaydi)
        JobSpec(
            "hourly_plan", jobs.send_hourly_plan, _cron(minute=0),
            misfire_grace_time=cfg.MISFIRE_GRACE_SHORT, coalesce=True,
        ),
        # Lid statistikasi snapshoti — davriy + kun yakunida "muzlatish"
        JobSpec(
            "lead_snapshot", jobs.snapshot_lead_stages,
            IntervalTrigger(minutes=cfg.LEAD_SNAPSHOT_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        JobSpec(
            "lead_snapshot_freeze", jobs.snapshot_lead_stages,
            _cron(hour=cfg.LEAD_SNAPSHOT_FREEZE_HOUR, minute=cfg.LEAD_SNAPSHOT_FREEZE_MINUTE),
            max_instances=1, misfire_grace_time=cfg.MISFIRE_GRACE_SHORT, coalesce=True,
        ),
        # Oylik bonus — oyning oxirgi kuni
        JobSpec(
            "monthly_bonus", jobs.calculate_monthly_bonus,
            _cron(day=cfg.MONTHLY_BONUS_DAY, hour=cfg.MONTHLY_BONUS_HOUR, minute=cfg.MONTHLY_BONUS_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # ─── Operator AI (avto-reja) — API o'chiq bo'lsa no-op ───────────────────
        # Bugungi actual snapshoti — davomiy (reja vs haqiqiy + ertangi tarix)
        JobSpec(
            "ai_snapshot", jobs.ai_snapshot_actuals,
            IntervalTrigger(minutes=cfg.AI_SNAPSHOT_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # Kunlik reja — har kuni ertalab, ish boshlanishidan oldin
        JobSpec(
            "ai_build_targets", jobs.ai_build_targets,
            _cron(hour=cfg.AI_BUILD_TARGETS_HOUR, minute=0),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Profillarni haftada qayta hisoblash (build-targets'dan oldin ishlaydi)
        JobSpec(
            "ai_compute_profiles", jobs.ai_compute_profiles,
            _cron(day_of_week=cfg.AI_COMPUTE_PROFILES_DOW, hour=cfg.AI_COMPUTE_PROFILES_HOUR, minute=0),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Soatlik kuzatuv — orqada qolganlarga nudge + sabab so'rovi (API bayroqlarni
        # o'zi tekshiradi; AI_NUDGE_ENABLED o'chiq bo'lsa hech kimga yubormaydi)
        JobSpec(
            "ai_watch_tick", jobs.ai_watch_tick,
            _cron(minute=cfg.AI_WATCH_MINUTE),
            max_instances=1, misfire_grace_time=cfg.MISFIRE_GRACE_SHORT, coalesce=True,
        ),
    ]
    return specs


JOBS = _build_jobs()


def _register(scheduler: AsyncIOScheduler, spec: JobSpec) -> None:
    kwargs: dict = {}
    if spec.max_instances is not None:
        kwargs["max_instances"] = spec.max_instances
    if spec.misfire_grace_time is not None:
        kwargs["misfire_grace_time"] = spec.misfire_grace_time
    if spec.coalesce is not None:
        kwargs["coalesce"] = spec.coalesce
    scheduler.add_job(spec.func, spec.trigger, id=spec.name, name=spec.name, **kwargs)


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone=cfg.TIMEZONE)
    for spec in JOBS:
        _register(scheduler, spec)

    scheduler.start()
    logger.info("Scheduler ishga tushdi (%s). Ro'yxatga olingan ishlar: %s",
                cfg.TIMEZONE, ", ".join(s.name for s in JOBS))

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
