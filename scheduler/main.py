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
        # Muddati o'tgan pending vazifalarni overdue ga o'tkazish — har 15 daqiqada
        JobSpec(
            "mark_overdue", jobs.mark_overdue_tasks, IntervalTrigger(minutes=15),
            max_instances=1, coalesce=True,
        ),
        # Kunlik yagona digest (vazifa + qo'ng'iroq/lid/tashrif + AI xulosa, bitta
        # xabar) — vaqt bazadan (/statistika_vaqt) sozlangani uchun har daqiqa
        # tekshiriladi (API vaqt kelganini va shu kuni yuborilmaganini o'zi hal qiladi).
        JobSpec(
            "group_post_tick", jobs.group_post_tick, IntervalTrigger(minutes=1),
            max_instances=1, coalesce=True,
        ),
        # Haftalik raqamli yakun — yakshanba kechqurun, AI'siz ham ishlaydi
        JobSpec(
            "weekly_digest", jobs.send_weekly_digest,
            _cron(day_of_week=cfg.WEEKLY_DIGEST_DOW, hour=cfg.WEEKLY_DIGEST_HOUR, minute=cfg.WEEKLY_DIGEST_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Davomat digesti — vaqti bazadan (botdan /davomat_vaqt) sozlanadi,
        # shuning uchun har daqiqa tekshiriladi (lid group_post_tick naqshi).
        JobSpec(
            "attendance_digest_tick", jobs.attendance_digest_tick, IntervalTrigger(minutes=1),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Oylik yakun — oyning oxirgi kuni kechqurun (bonus hisobidan oldin)
        JobSpec(
            "monthly_digest", jobs.send_monthly_digest,
            _cron(day=cfg.MONTHLY_DIGEST_DAY, hour=cfg.MONTHLY_DIGEST_HOUR, minute=cfg.MONTHLY_DIGEST_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Ertalabki "kecha yakuni" tuzatishi — faqat farq sezilarli bo'lsa yuboriladi
        JobSpec(
            "yesterday_correction", jobs.send_yesterday_correction,
            _cron(hour=cfg.YESTERDAY_CORRECTION_HOUR, minute=cfg.YESTERDAY_CORRECTION_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
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
        # Tizim sog'ligi qo'riqchisi — CRM, zaxira nusxa, davomat oqimi
        # (chegara 2 soat, shuning uchun yarim soatlik tekshiruv yetarli)
        JobSpec(
            "system_health_tick", jobs.system_health_tick, IntervalTrigger(minutes=30),
            max_instances=1, coalesce=True,
        ),
        # Diff-engine — lidlarning HAQIQIY o'zgarishini kuzatuvchi tez skan
        # (chegaralangan, guruh digesti shundan o'qiydi — deyarli real-vaqtli)
        JobSpec(
            "lead_diff_tick", jobs.lead_diff_tick,
            IntervalTrigger(minutes=cfg.LEAD_DIFF_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # Diff-engine tungi to'liq solishtiruvi (xavfsizlik to'ri) — kam trafik vaqtida
        JobSpec(
            "lead_diff_reconcile", jobs.lead_diff_reconcile,
            _cron(hour=cfg.LEAD_DIFF_RECONCILE_HOUR, minute=cfg.LEAD_DIFF_RECONCILE_MINUTE),
            max_instances=1, misfire_grace_time=cfg.MISFIRE_GRACE_SHORT, coalesce=True,
        ),
        # Oylik bonus — oyning oxirgi kuni
        JobSpec(
            "monthly_bonus", jobs.calculate_monthly_bonus,
            _cron(day=cfg.MONTHLY_BONUS_DAY, hour=cfg.MONTHLY_BONUS_HOUR, minute=cfg.MONTHLY_BONUS_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # «Keldim/Ketdim bosishni unutmang» — ish oynasi chegarasiga yaqin
        # qolganda. API o'zi filtrlaydi va kuniga bir marta yuboradi.
        JobSpec(
            "attendance_reminder", jobs.attendance_reminder_tick,
            IntervalTrigger(minutes=cfg.ATTENDANCE_REMINDER_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # Ish kundaligi eslatmasi — ish tugashiga yaqin, bugun yozmaganlarga
        # (KUNDALIK_ETIROZ_REJASI.md, Bosqich 1). API o'zi filtrlaydi.
        JobSpec(
            "work_log_reminder", jobs.work_log_reminder_tick,
            IntervalTrigger(minutes=cfg.WORK_LOG_REMINDER_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # E'tiroz/shikoyat SLA — kuniga bir marta (chegaralar 3 va 5 KUN).
        JobSpec(
            "appeals_sla", jobs.appeals_sla_tick,
            _cron(hour=cfg.APPEALS_SLA_HOUR, minute=cfg.APPEALS_SLA_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # ─── Telegram login xavfsizligi (replay himoyasi + rate-limit) ───────────
        # Eskirgan hash/urinish yozuvlarini tozalash — vaqtinchalik jadvallar
        JobSpec(
            "login_security_cleanup", jobs.login_security_cleanup_tick,
            IntervalTrigger(minutes=cfg.LOGIN_SECURITY_CLEANUP_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # ─── Payroll avtomatikasi (OYLIK_JARIMA_REJASI.md, Bosqich 6) ────────────
        # Oylik ish haqi — keyingi oyning 1-kuni ertalab (bonus va davomat
        # yopilishidan keyin, 9-bo'lim savol 10 QAROR)
        JobSpec(
            "monthly_payroll", jobs.calculate_monthly_payroll,
            _cron(day=cfg.MONTHLY_PAYROLL_DAY, hour=cfg.MONTHLY_PAYROLL_HOUR, minute=cfg.MONTHLY_PAYROLL_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Kechikish limiti ogohlantirishi — ish kuni boshlanishidan oldin (1.5-band)
        JobSpec(
            "payroll_late_warnings", jobs.payroll_late_warnings_tick,
            _cron(hour=cfg.LATE_WARNING_HOUR, minute=cfg.LATE_WARNING_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Qo'shimcha ish avtomatik aniqlash — tungi, kam trafik vaqtida (1.3-band)
        JobSpec(
            "payroll_overtime_auto_detect", jobs.payroll_overtime_auto_detect,
            _cron(hour=cfg.OVERTIME_AUTO_DETECT_HOUR, minute=cfg.OVERTIME_AUTO_DETECT_MINUTE),
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
        # Issiq lid (speed-to-lead) — yangi lidni tez ilg'ash uchun qisqa interval
        # (API HOT_LEAD_ENABLED o'chiq bo'lsa no-op, CRM/DB yuk yo'q)
        JobSpec(
            "hot_lead_tick", jobs.hot_lead_tick,
            IntervalTrigger(minutes=cfg.HOT_LEAD_POLL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # Real-vaqtli harakatsizlik nazorati — 20 daqiqalik chegarani o'z vaqtida
        # ilg'ash uchun soatlik ai_watch'dan tezroq
        JobSpec(
            "idle_watch_tick", jobs.idle_watch_tick,
            IntervalTrigger(minutes=cfg.IDLE_WATCH_INTERVAL_MINUTES),
            max_instances=1, coalesce=True,
        ),
        # Bilim bazasi anketasi — tasdiqlangan vaqti kelgan sessiyani boshlash
        JobSpec(
            "anketa_tick", jobs.anketa_tick, IntervalTrigger(minutes=1),
            max_instances=1, coalesce=True,
        ),
        # Bilim bazasi — draft'larni AI bilan bo'lib-bo'lib qayta ishlash
        JobSpec(
            "knowledge_tick", jobs.knowledge_tick, IntervalTrigger(minutes=1),
            max_instances=1, coalesce=True,
        ),
        # Sotuv playbook — qurish bosqichlarini davom ettirish
        JobSpec(
            "playbook_tick", jobs.playbook_tick, IntervalTrigger(minutes=1),
            max_instances=1, coalesce=True,
        ),
        # Bilim bazasi — eskirgan sana-sezgir yozuvlar eslatmasi (kunlik)
        JobSpec(
            "knowledge_stale", jobs.knowledge_stale, _cron(hour=9, minute=35),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
        ),
        # Haftalik AI trend (shaxsiy xabarlar) — haftalik digestdan keyinroq,
        # operator avval guruhdagi raqamlarni, keyin shaxsiy xulosasini ko'radi
        JobSpec(
            "ai_weekly", jobs.ai_weekly_run,
            _cron(day_of_week=cfg.AI_WEEKLY_DOW, hour=cfg.AI_WEEKLY_HOUR, minute=cfg.AI_WEEKLY_MINUTE),
            misfire_grace_time=cfg.MISFIRE_GRACE_DEFAULT, coalesce=True,
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
