"""CRM aloqasi qo'riqchisi — ma'lumot kelmay qolsa guruhga ogohlantirish.

NEGA QURILDI (2026-08-05, egasining talabi): 2026-08-04 soat 16:45 da Uysot
Open API tokeni bekor qilindi. Tizim 27 SOAT davomida jimgina ko'r bo'lib
qoldi — yangi lid xabari operatorga bormadi, bosqich/tashrif statistikasi
muzladi, harakatsizlik nazorati o'chdi. Xato faqat cron log'ida ko'rinardi,
hech kimga xabar bermasdi. Muammo tasodifan (boshqa mavzudagi tekshiruvda)
topildi.

MANTIQ. Ikkita mustaqil kanal bor va IKKALASI ham ma'lumot keltirishi mumkin:
  1. Polling — muvaffaqiyatli skan har ko'rilgan lidning `CrmLeadState.
     last_seen_at`ini yangilaydi (o'zgarish bo'lmasa ham). Ya'ni bu maydonning
     eng katta qiymati = CRM'dan oxirgi marta MUVAFFAQIYATLI o'qigan payt.
  2. Webhook — `CrmWebhookLog` da `parsed_events > 0` bo'lgan yozuv, ya'ni
     haqiqatan lid ajratib olingan so'rov.

Qo'riqchi ikkalasining ENG YANGISIGA qaraydi: shu vaqtdan beri
`stale_hours`dan ko'p o'tgan bo'lsa — aloqa uzilgan deb hisoblanadi. Bu
"biznes faolligi" emas, "tizim sog'ligi" o'lchovi: tunda yangi lid bo'lmasa
ham skan ishlaydi va `last_seen_at` yangilanadi, shuning uchun jimlik
YOLG'ON signal bermaydi.

SHOVQIN NAZORATI: bir marta ogohlantirilgach `realert_hours` o'tmaguncha
takrorlanmaydi; aloqa tiklanganda esa "tiklandi" xabari BIR MARTA yuboriladi
va holat tozalanadi (qayta uzilsa yana ogohlantiradi)."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ
from db.models import CrmHealthState, CrmLeadState, CrmWebhookLog, MonitoredGroup

logger = logging.getLogger(__name__)


async def _state(db: AsyncSession) -> CrmHealthState:
    row = await db.get(CrmHealthState, 1)
    if row is None:
        row = CrmHealthState(id=1, alerting=False)
        db.add(row)
        await db.flush()
    return row


async def _main_group_chat_id(db: AsyncSession) -> int | None:
    """Ogohlantirish manzili: dasturchi botdan biriktirgan "main" guruh
    (issiq-lid eskalatsiyasi va kunlik digest bilan bir xil kanal). Guruh
    biriktirilmagan bo'lsa .env dagi asosiy guruhga tushadi."""
    chat_id = await db.scalar(
        select(MonitoredGroup.chat_id).where(
            MonitoredGroup.purpose == "main", MonitoredGroup.is_active == True  # noqa: E712
        )
    )
    return chat_id or (settings.telegram_group_chat_id or None)


async def last_data_at(db: AsyncSession) -> datetime | None:
    """CRM ma'lumoti oxirgi marta qachon kelgan (polling yoki webhook — qaysi
    yangiroq bo'lsa). `None` — hech qachon (tizim hali ishga tushmagan)."""
    last_poll = await db.scalar(select(func.max(CrmLeadState.last_seen_at)))
    last_webhook = await db.scalar(
        select(func.max(CrmWebhookLog.received_at)).where(CrmWebhookLog.parsed_events > 0)
    )
    candidates = [t for t in (last_poll, last_webhook) if t is not None]
    return max(candidates) if candidates else None


def _human_gap(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days} kun {hours} soat"
    if hours:
        return f"{hours} soat {minutes} daqiqa"
    return f"{minutes} daqiqa"


def _local(ts: datetime) -> str:
    """Bazadagi UTC-naive vaqtni Toshkent vaqtiga o'giradi — xabar xodimlarga
    boradi, ular UTC bilan ishlamaydi."""
    return (
        ts.replace(tzinfo=timezone.utc)
        .astimezone(TASHKENT_TZ)
        .strftime("%d.%m.%Y %H:%M")
    )


def _alert_text(last_at: datetime | None, gap: timedelta | None) -> str:
    lines = ["🔴 <b>CRM aloqasi uzildi</b>", ""]
    if last_at is None:
        lines.append("CRM'dan hali hech qanday ma'lumot olinmagan.")
    else:
        lines.append(f"Oxirgi ma'lumot: <b>{_local(last_at)}</b>")
        if gap is not None:
            lines.append(f"Ya'ni <b>{_human_gap(gap)}</b> dan beri yangilanmayapti.")
    lines += [
        "",
        "<b>Hozir ishlamayapti:</b>",
        "• yangi lid tushganda operatorga xabar",
        "• bosqich/tashrif statistikasi",
        "• qo'ng'iroq hisobi va harakatsizlik nazorati",
        "",
        "<b>Ehtimoliy sabab:</b> Uysot API tokeni bekor qilingan yoki muddati "
        "tugagan, yoxud Uysot serveri javob bermayapti.",
        "",
        "Tekshirish kerak: Uysot kabinetidagi Open API tokeni amal qiladimi.",
    ]
    return "\n".join(lines)


def _recovery_text(last_at: datetime | None, outage: timedelta | None) -> str:
    lines = ["🟢 <b>CRM aloqasi tiklandi</b>", ""]
    if outage is not None:
        lines.append(f"Uzilish davomiyligi: <b>{_human_gap(outage)}</b>.")
    if last_at is not None:
        lines.append(f"Ma'lumot yangilandi: {_local(last_at)}")
    lines += [
        "",
        "Lid saralash, statistika va nazorat qayta ishlayapti.",
        "Uzilish davridagi voqealar keyingi to'liq skanerlashda qoplanadi.",
    ]
    return "\n".join(lines)


async def tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Bitta tekshiruv. Qaytaradi: {ok, last_data_at, stale, gap_minutes,
    alerted, recovered, dry_run}.

    `dry_run` — hech narsa yubormaydi/yozmaydi, faqat holatni qaytaradi."""
    if not settings.crm_health_watchdog_enabled:
        return {"disabled": True}

    now = datetime.utcnow()
    last_at = await last_data_at(db)
    gap = (now - last_at) if last_at is not None else None
    stale_after = timedelta(hours=settings.crm_health_stale_hours)

    # `last_at is None` — tizim hali hech qachon ma'lumot olmagan (yangi o'rnatma
    # yoki bo'sh baza). Bunday holatda ogohlantirmaymiz: bu "uzilish" emas,
    # "hali boshlanmagan" — aks holda birinchi deploydayoq yolg'on signal bo'lardi.
    stale = last_at is not None and gap is not None and gap > stale_after

    state = await _state(db)
    result = {
        "ok": True,
        "last_data_at": last_at.isoformat() if last_at else None,
        "stale": stale,
        "gap_minutes": int(gap.total_seconds() // 60) if gap else None,
        "alerted": False,
        "recovered": False,
        "dry_run": dry_run,
    }

    chat_id = await _main_group_chat_id(db)

    # ── Tiklandi ──
    if not stale and state.alerting:
        outage = None
        if state.stale_since is not None and last_at is not None:
            outage = last_at - state.stale_since
        result["recovered"] = True
        if not dry_run:
            if chat_id:
                await send_message(chat_id, _recovery_text(last_at, outage))
            state.alerting = False
            state.last_alert_at = None
            state.stale_since = None
            await db.commit()
        logger.info("CRM aloqasi tiklandi (oxirgi ma'lumot: %s)", last_at)
        return result

    if not stale:
        return result

    # ── Uzilgan: ogohlantirish kerakmi? ──
    realert_after = timedelta(hours=settings.crm_health_realert_hours)
    if state.alerting and state.last_alert_at is not None:
        if now - state.last_alert_at < realert_after:
            return result  # yaqinda ogohlantirilgan — shovqin qilmaymiz

    result["alerted"] = True
    if not dry_run:
        if chat_id:
            await send_message(chat_id, _alert_text(last_at, gap))
        else:
            logger.error(
                "CRM aloqasi uzilgan, lekin ogohlantirish yuborish uchun guruh "
                "topilmadi (MonitoredGroup 'main' yoki TELEGRAM_GROUP_CHAT_ID)."
            )
        if not state.alerting:
            state.stale_since = last_at  # birinchi ogohlantirishda uzilish nuqtasi
        state.alerting = True
        state.last_alert_at = now
        await db.commit()
    logger.warning(
        "CRM aloqasi uzilgan — ogohlantirish yuborildi (oxirgi ma'lumot: %s, tanaffus: %s)",
        last_at, gap,
    )
    return result
