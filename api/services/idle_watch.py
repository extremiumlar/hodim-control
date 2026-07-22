"""Operator AI — real-vaqtli harakatsizlik nazorati (4-band). `watch_rules.py`dan
FARQLI: soatlik REJA-VS-FAKT nisbati emas, xom "so'nggi qo'ng'iroqdan beri necha
daqiqa o'tdi" signali — tezroq (5-10 daqiqada bir) ishlaydi va OMMAVIY (guruhga)
eskalatsiya qiladi (watch_rules'ning shaxsiy/DM soatlik nudge'idan farqli —
hot_lead.py'dagi "shaxsiy DM → jiddiy holatda ommaviy" ikki-bosqichli naqshning
davomi, faqat bu safar butun kun davomidagi umumiy harakatsizlik uchun).

Ataylab qo'yilgan cheklovlar (ko'r-ko'rona ayblamaslik uchun):
  - Faqat "suhbat" (qo'ng'iroq) kuzatiladigan lavozimlar (`metrics_for`) —
    tashrif-asosiy rollar uchun aniq real-vaqtli signal yo'q (CRM aniq
    tashrif-vaqti bermaydi), shuning uchun BU TEKSHIRUVDAN butunlay chiqarib
    qo'yilgan — noto'g'ri ayblashdan ko'ra tekshirmaslik afzal.
  - Operatorda ISHLANMAGAN OCHIQ LID borligi CRM'dan (`count_open_leads`)
    tasdiqlanmasa yoki 0 bo'lsa — signal berilmaydi ("lid yo'q" operatorning
    aybi emas — 3-band/ShortfallReason'dagi bir xil tamoyil).
  - Yaqinda (RECENT_PRIVATE_NUDGE_GRACE_MINUTES ichida) xuddi shu operatorga
    `watch_rules` orqali shaxsiy nudge yuborilgan bo'lsa — ustiga yana ommaviy
    eskalatsiya YO'Q (ikki tizim bir-biriga "pile-on" qilmasin).
  - `OperatorBusyPeriod` (boshliq/dasturchi belgilagan) davrida — signal yo'q.
  - Adolat filtrlari (ish oynasi/tushlik/GRACE/ExcusedDay) — watch_rules bilan
    bir xil qoidalar."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.routers.norms import metrics_for
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ, local_range_utc_naive
from crm import get_crm_adapter
from db.models import AiMessageLog, ExcusedDay, ExcusedStatus, OperatorBusyPeriod, Role, User

logger = logging.getLogger(__name__)

IDLE_THRESHOLD_MINUTES = 20
GRACE_MINUTES = 60  # watch_rules bilan bir xil — smena boshida baholanmaydi
LUNCH_HOUR = 13
COOLDOWN_MINUTES = 60  # bir xil "harakatsizlik seriyasi" uchun qayta ogohlantirmaslik
MAX_ALERTS_PER_DAY = 3
RECENT_PRIVATE_NUDGE_GRACE_MINUTES = 10  # watch_rules DM'idan keyin darhol ommaviy chiqarmaslik

ALERT_KIND = "idle_alert"


def _adapter():
    return get_crm_adapter(settings.crm_type)


async def _is_excused(db: AsyncSession, user_id: int, day) -> bool:
    row = await db.scalar(
        select(ExcusedDay).where(
            ExcusedDay.user_id == user_id,
            ExcusedDay.date == day,
            ExcusedDay.status == ExcusedStatus.approved.value,
        )
    )
    return row is not None


async def _is_busy(db: AsyncSession, user_id: int, now_utc: datetime) -> bool:
    """`OperatorBusyPeriod.start_at/end_at` naive-UTC saqlanadi (`busy_period.py`
    `datetime.utcnow()` bilan yozadi) — solishtiruv HAM naive-UTC bo'lishi shart."""
    row = await db.scalar(
        select(OperatorBusyPeriod).where(
            OperatorBusyPeriod.user_id == user_id,
            OperatorBusyPeriod.start_at <= now_utc,
            OperatorBusyPeriod.end_at > now_utc,
        )
    )
    return row is not None


async def _alerts_today(db: AsyncSession, user_id: int, day) -> list[AiMessageLog]:
    start_utc, end_utc = local_range_utc_naive(day, day)
    return list(
        await db.scalars(
            select(AiMessageLog)
            .where(
                AiMessageLog.user_id == user_id,
                AiMessageLog.kind == ALERT_KIND,
                AiMessageLog.created_at >= start_utc,
                AiMessageLog.created_at < end_utc,
            )
            .order_by(AiMessageLog.created_at.desc())
        )
    )


async def _recent_private_nudge(db: AsyncSession, user_id: int) -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=RECENT_PRIVATE_NUDGE_GRACE_MINUTES)
    row = await db.scalar(
        select(AiMessageLog).where(
            AiMessageLog.user_id == user_id,
            AiMessageLog.kind == "nudge",
            AiMessageLog.created_at >= cutoff,
        )
    )
    return row is not None


async def evaluate_and_alert(db: AsyncSession, dry_run: bool = False) -> dict:
    from api.routers.hourly_plan import _effective_today, _to_min
    from api.services.hot_lead import _main_group_chat_id  # bitta guruh-manzil manbai

    adapter = _adapter()
    if adapter is None:
        return {"ok": False, "reason": "CRM sozlanmagan"}

    now_local = datetime.now(TASHKENT_TZ)
    # OperatorBusyPeriod (va kod bazasidagi boshqa DateTime ustunlar) naive-UTC
    # saqlanadi — `now_local.replace(tzinfo=None)` mahalliy soat raqamlarini
    # UTC deb noto'g'ri solishtirar edi (Toshkent UTC+5 farqi bilan xato natija).
    now_utc = datetime.utcnow()
    day = now_local.date()
    now_min = now_local.hour * 60 + now_local.minute
    now_ts = int(now_local.timestamp())

    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
                User.crm_external_id.isnot(None),
            )
        )
    )
    # Faqat "suhbat" kuzatiladigan lavozimlar — tashrif-asosiy rollar bu
    # tekshiruvdan chiqarib qo'yilgan (modul docstring'iga qarang).
    candidates = [u for u in users if "suhbat" in metrics_for(u)]
    if not candidates:
        return {"ok": True, "checked": 0, "alerted": 0}

    # Adolat filtrlarini CRM so'rovidan OLDIN qo'llaymiz — faqat "hozir baholanishi
    # kerak" operatorlar uchun CRM'ga murojaat qilamiz. Har kimning smena
    # boshlanish vaqtini ham saqlaymiz (hali qo'ng'iroq topilmasa shundan hisoblash
    # uchun).
    active: list[User] = []
    shift_start_ts: dict[int, int] = {}
    for u in candidates:
        is_working, start, end = await _effective_today(db, u, day)
        if not is_working:
            continue
        start_min, end_min = _to_min(start), _to_min(end)
        if now_min < start_min + GRACE_MINUTES or now_min >= end_min:
            continue
        if now_local.hour == LUNCH_HOUR:
            continue
        if await _is_excused(db, u.id, day):
            continue
        if await _is_busy(db, u.id, now_utc):
            continue
        active.append(u)
        shift_start_ts[u.id] = now_ts - now_min * 60 + start_min * 60

    if not active:
        return {"ok": True, "checked": 0, "alerted": 0}

    emp_nums = {u.crm_external_id for u in active}
    since_ts = min(shift_start_ts.values())
    last_calls = await adapter.get_last_call_timestamps(emp_nums, since_ts)
    if last_calls is None:
        return {"ok": False, "reason": "CRM'dan so'nggi qo'ng'iroqlarni olib bo'lmadi"}

    main_chat_id = await _main_group_chat_id(db)
    alerted = []

    for u in active:
        last_ts = last_calls.get(u.crm_external_id)
        # Hali umuman qo'ng'iroq topilmagan bo'lsa — smena boshidan hisoblanadi
        # (since_ts hech bo'lmasa shu operatorning smena boshigacha qamraydi).
        reference_ts = last_ts if last_ts is not None else shift_start_ts[u.id]
        idle_minutes = (now_ts - reference_ts) // 60
        if idle_minutes < IDLE_THRESHOLD_MINUTES:
            continue

        alerts_today = await _alerts_today(db, u.id, day)
        if len(alerts_today) >= MAX_ALERTS_PER_DAY:
            continue
        if alerts_today and (datetime.utcnow() - alerts_today[0].created_at) < timedelta(minutes=COOLDOWN_MINUTES):
            continue
        if await _recent_private_nudge(db, u.id):
            continue

        if not u.crm_visit_external_id:
            continue
        open_count = await adapter.count_open_leads(u.crm_visit_external_id)
        if not open_count:  # 0 yoki None (tekshirib bo'lmadi) — operatorni ayblamaymiz
            continue

        text = (
            "⏸ <b>Harakatsizlik</b>\n"
            f"👤 {u.full_name} — so'nggi qo'ng'iroqdan beri {idle_minutes} daqiqa bo'ldi "
            f"({open_count} ta ishlanmagan lid bor). Muammo bormi?"
        )
        entry = {"user_id": u.id, "name": u.full_name, "idle_minutes": idle_minutes, "open_leads": open_count}
        if not dry_run:
            if main_chat_id:
                await send_message(main_chat_id, text)
            db.add(AiMessageLog(user_id=u.id, kind=ALERT_KIND, source="fallback", text=text))
        alerted.append(entry)

    if alerted and not dry_run:
        await db.commit()

    return {"ok": True, "checked": len(active), "alerted": len(alerted), "results": alerted}
