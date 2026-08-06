"""Tizim sog'ligi qo'riqchisi — jimgina ishlamay qolgan qismlarni aniqlab
guruhga ogohlantiradi.

NEGA QURILDI (2026-08-05, egasining talabi): 2026-08-04 soat 16:45 da Uysot
Open API tokeni bekor qilindi va tizim **27 SOAT jimgina ko'r** bo'lib qoldi —
yangi lid xabari operatorga bormadi, tashrif statistikasi muzladi,
harakatsizlik nazorati o'chdi. Xato faqat `logs/cron.log` da ko'rinardi, hech
kimga xabar bermasdi; muammo tasodifan topildi.

UMUMIY NAQSH: har bir tekshiruv bitta savolga javob beradi — «bu signal
oxirgi marta qachon yangilangan?» Kutilganidan uzoq jim bo'lsa — odamga
xabar. Yangi tekshiruv qo'shish uchun `_CHECKS` ro'yxatiga bitta funksiya
yozish kifoya (holat, shovqin nazorati va tiklanish xabari umumiy).

HOZIRGI TEKSHIRUVLAR:
  • `crm`        — CRM'dan ma'lumot kelyaptimi (polling yoki webhook)
  • `backup`     — kunlik avtomatik zaxira nusxa olinyaptimi
  • `attendance` — ish kunida xodimlar check-in qilyaptimi (Face ID sog'mi)

SHOVQIN NAZORATI: bir marta ogohlantirilgach `realert_hours` o'tmaguncha
takrorlanmaydi; tiklanganda «tiklandi» xabari BIR MARTA yuboriladi va holat
tozalanadi (qayta buzilsa yana ogohlantiradi). Har tekshiruvning holati
ALOHIDA — biri ogohlantirsa boshqasi susmaydi.

DIQQAT — holat NEGA bazada: production cPanel CRON rejimida ishlaydi, ya'ni
har daqiqa YANGI python jarayoni ko'tariladi; modul darajasidagi o'zgaruvchi
saqlanmaydi."""
import logging
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ
from db.models import (
    Attendance,
    CrmLeadState,
    CrmWebhookLog,
    MonitoredGroup,
    Role,
    SystemHealthState,
    User,
)

logger = logging.getLogger(__name__)

# Loyiha ildizi (api/services/system_health.py -> ../..)
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Umumiy yordamchilar
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Bitta tekshiruv natijasi.

    `healthy` — hammasi joyida. `skipped` — hozir tekshirish o'rinli emas
    (masalan yakshanba, yoki tizim hali ishga tushmagan) — bu XATO EMAS va
    holatga tegilmaydi. `detail` — javobga qo'shiladigan diagnostika."""

    healthy: bool
    alert_text: str = ""
    recovery_text: str = ""
    stale_since: datetime | None = None
    skipped: bool = False
    detail: dict | None = None


async def _state(db: AsyncSession, check: str) -> SystemHealthState:
    row = await db.get(SystemHealthState, check)
    if row is None:
        row = SystemHealthState(check=check, alerting=False)
        db.add(row)
        await db.flush()
    return row


async def _alert_recipients(db: AsyncSession) -> list[int]:
    """Ogohlantirish kimga boradi.

    EGASINING QARORI (2026-08-05): bu xabarlar TEXNIK — «token o'lgan»,
    «zaxira olinmayapti» kabi. Ular sotuv guruhiga kerak emas va shovqin
    qiladi, shuning uchun FAQAT DASTURCHIGA shaxsiy xabar sifatida boradi.

    ZAXIRA YO'L: dasturchi topilmasa (roli o'zgargan, telegram_id yo'q,
    hisob o'chirilgan) xabar guruhga tushadi. Sabab: qo'riqchining o'zi
    jimgina ko'r bo'lib qolishi — aynan biz kurashayotgan nosozlik turi;
    noto'g'ri manzilga borgan ogohlantirish umuman bormaganidan yaxshi.
    Bu holat log'ga ANIQ yoziladi. Guruhga ham NUSXA kerak bo'lsa:
    `WATCHDOG_ALSO_NOTIFY_GROUP=true`."""
    rows = await db.scalars(
        select(User.telegram_id).where(
            User.role == Role.dasturchi.value,
            User.is_active == True,  # noqa: E712
            User.telegram_id.isnot(None),
        )
    )
    recipients = [tid for tid in rows if tid]

    group_id = await db.scalar(
        select(MonitoredGroup.chat_id).where(
            MonitoredGroup.purpose == "main", MonitoredGroup.is_active == True  # noqa: E712
        )
    ) or (settings.telegram_group_chat_id or None)

    if not recipients:
        logger.error(
            "Qo'riqchi: DASTURCHI topilmadi (rol/telegram_id/is_active) — "
            "ogohlantirish zaxira yo'l bilan guruhga yuborilmoqda."
        )
        return [group_id] if group_id else []

    if settings.watchdog_also_notify_group and group_id:
        recipients.append(group_id)
    return recipients


async def _send_all(recipients: list[int], text: str) -> None:
    """Har manzilga alohida yuboradi — biri xato bersa (bot bloklangan,
    chat topilmadi) qolganlari baribir oladi."""
    for chat_id in recipients:
        try:
            await send_message(chat_id, text)
        except Exception:  # noqa: BLE001 — bitta manzil qo'riqchini yiqitmasin
            logger.exception("Qo'riqchi xabarini yuborishda xato (chat_id=%s)", chat_id)


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
    return ts.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ).strftime("%d.%m.%Y %H:%M")


# ---------------------------------------------------------------------------
# 1. CRM aloqasi
# ---------------------------------------------------------------------------


async def crm_last_data_at(db: AsyncSession) -> datetime | None:
    """CRM ma'lumoti oxirgi marta qachon kelgan (polling yoki webhook — qaysi
    yangiroq bo'lsa).

    Polling signali: muvaffaqiyatli skan har KO'RILGAN lidning
    `CrmLeadState.last_seen_at`ini yangilaydi (o'zgarish bo'lmasa ham), ya'ni
    bu maydonning eng kattasi = CRM'dan oxirgi muvaffaqiyatli o'qish payti.
    Webhook signali: `parsed_events > 0` bo'lgan so'rov (haqiqatan lid
    ajratilgan). `None` — hech qachon (tizim hali ishga tushmagan)."""
    last_poll = await db.scalar(select(func.max(CrmLeadState.last_seen_at)))
    last_webhook = await db.scalar(
        select(func.max(CrmWebhookLog.received_at)).where(CrmWebhookLog.parsed_events > 0)
    )
    candidates = [t for t in (last_poll, last_webhook) if t is not None]
    return max(candidates) if candidates else None


async def check_crm(db: AsyncSession, now: datetime) -> CheckResult:
    if not settings.crm_health_watchdog_enabled:
        return CheckResult(healthy=True, skipped=True)

    last_at = await crm_last_data_at(db)
    # Hech qachon ma'lumot olinmagan — bu "uzilish" emas, "hali boshlanmagan"
    # (yangi o'rnatma/bo'sh baza). Aks holda birinchi deploydayoq yolg'on signal.
    if last_at is None:
        return CheckResult(healthy=True, skipped=True, detail={"last_data_at": None})

    gap = now - last_at
    detail = {"last_data_at": last_at.isoformat(), "gap_minutes": int(gap.total_seconds() // 60)}
    if gap <= timedelta(hours=settings.crm_health_stale_hours):
        # DIQQAT: `recovery_text` SOG' natijada beriladi — tiklanish xabari
        # aynan shu paytda yuboriladi (nosoz natijadagi matn hech qachon
        # ishlatilmasdi; 2026-08-05 sinovida topilgan xato).
        return CheckResult(
            healthy=True,
            recovery_text=(
                "🟢 <b>CRM aloqasi tiklandi</b>\n\n"
                f"Ma'lumot yangilandi: {_local(last_at)}\n"
                "Lid saralash, statistika va nazorat qayta ishlayapti."
            ),
            detail=detail,
        )

    alert = "\n".join([
        "🔴 <b>CRM aloqasi uzildi</b>",
        "",
        f"Oxirgi ma'lumot: <b>{_local(last_at)}</b>",
        f"Ya'ni <b>{_human_gap(gap)}</b> dan beri yangilanmayapti.",
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
    ])
    recovery = "\n".join([
        "🟢 <b>CRM aloqasi tiklandi</b>",
        "",
        f"Ma'lumot yangilandi: {_local(last_at)}",
        "Lid saralash, statistika va nazorat qayta ishlayapti.",
    ])
    return CheckResult(False, alert, recovery, stale_since=last_at, detail=detail)


# ---------------------------------------------------------------------------
# 2. Zaxira nusxa
# ---------------------------------------------------------------------------


def latest_backup() -> tuple[Path, datetime] | None:
    """Eng yangi AVTOMATIK zaxira nusxa (`backups/pg_*.sql.gz`) va uning vaqti.

    Faqat tugallangan fayllar: `backup_db.sh` avval `.part` ga yozib, tugagach
    yakuniy nomga ko'chiradi — shuning uchun yarim yozilgan fayl bu yerga
    tushmaydi. Qo'lda olingan `pg_before_*.sql` lar ham hisobga olinmaydi
    (ular tasodifiy, kunlik jadval dalili emas)."""
    backup_dir = ROOT / "backups"
    if not backup_dir.is_dir():
        return None
    newest: tuple[Path, float] | None = None
    for path in backup_dir.glob("pg_*.sql.gz"):
        if path.name.startswith("pg_before_"):
            continue
        mtime = path.stat().st_mtime
        if newest is None or mtime > newest[1]:
            newest = (path, mtime)
    if newest is None:
        return None
    return newest[0], datetime.utcfromtimestamp(newest[1])


async def check_backup(db: AsyncSession, now: datetime) -> CheckResult:
    if not settings.backup_watchdog_enabled:
        return CheckResult(healthy=True, skipped=True)

    latest = latest_backup()
    if latest is None:
        # Hech qanday avtomatik nusxa yo'q — bu HAQIQIY muammo (cron sozlanmagan),
        # lekin "eskirish" emas. Ogohlantiramiz, chunki aynan shu holat
        # 2026-08-05 gacha davom etgan va hech kim bilmagan.
        alert = "\n".join([
            "🔴 <b>Zaxira nusxa olinmayapti</b>",
            "",
            "`backups/` papkada birorta ham avtomatik zaxira nusxa topilmadi.",
            "",
            "Ya'ni baza buzilsa <b>ma'lumotlarni tiklab bo'lmaydi</b>: davomat, "
            "oylik, lid tarixi — hammasi yo'qoladi.",
            "",
            "Tekshirish kerak: crontab'da <code>backup_db.sh</code> jobi bormi "
            "va <code>logs/backup.log</code> da xato bormi.",
        ])
        return CheckResult(False, alert, "🟢 <b>Zaxira nusxa tiklandi</b>\n\nAvtomatik nusxa olindi.",
                           detail={"latest": None})

    path, made_at = latest
    gap = now - made_at
    detail = {"latest": path.name, "made_at": made_at.isoformat(),
              "age_hours": round(gap.total_seconds() / 3600, 1)}
    if gap <= timedelta(hours=settings.backup_stale_hours):
        return CheckResult(
            healthy=True,
            recovery_text=(
                "🟢 <b>Zaxira nusxa tiklandi</b>\n\n"
                f"Yangi nusxa olindi: {_local(made_at)}"
            ),
            detail=detail,
        )

    alert = "\n".join([
        "🔴 <b>Zaxira nusxa eskirdi</b>",
        "",
        f"Oxirgi nusxa: <b>{_local(made_at)}</b> ({_human_gap(gap)} oldin)",
        "",
        "Kunlik avtomatik zaxira ishlamayapti. Baza buzilsa shu sanadan "
        "keyingi hamma ma'lumot yo'qoladi.",
        "",
        "Tekshirish kerak: <code>logs/backup.log</code>.",
    ])
    recovery = "\n".join([
        "🟢 <b>Zaxira nusxa tiklandi</b>",
        "",
        f"Yangi nusxa olindi: {_local(made_at)}",
    ])
    return CheckResult(False, alert, recovery, stale_since=made_at, detail=detail)


# ---------------------------------------------------------------------------
# 3. Davomat (Face ID sog'ligi)
# ---------------------------------------------------------------------------


async def check_attendance(db: AsyncSession, now: datetime) -> CheckResult:
    """Ish kunida soat `attendance_check_hour` dan keyin BIRORTA ham check-in
    bo'lmasa — Face ID/davomat oqimi buzilgan degan signal.

    Yolg'on signaldan himoya: (a) yakshanba tekshirilmaydi (dam kuni — jonli
    ma'lumotda yakshanba check-in'lari kam), (b) faqat belgilangan soatdan
    keyin (ertalab hali hamma kelmagan bo'lishi mumkin), (c) chegara ATIGI
    NOL — ya'ni "kam keldi" emas, "umuman ishlamadi" holatigina ushlanadi.
    Jonli ma'lumot (2026-08): ish kunlarida barqaror 13 ta check-in."""
    if not settings.attendance_watchdog_enabled:
        return CheckResult(healthy=True, skipped=True)

    local_now = now.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    if local_now.isoweekday() == 7:  # yakshanba
        return CheckResult(healthy=True, skipped=True, detail={"reason": "yakshanba"})
    if local_now.hour < settings.attendance_check_hour:
        return CheckResult(healthy=True, skipped=True, detail={"reason": "hali erta"})

    today: date_type = local_now.date()
    count = await db.scalar(
        select(func.count())
        .select_from(Attendance)
        .where(Attendance.date == today, Attendance.check_in_time.isnot(None))
    )
    detail = {"date": today.isoformat(), "checkins": count or 0}
    if (count or 0) > 0:
        return CheckResult(
            healthy=True,
            recovery_text=(
                "🟢 <b>Davomat tiklandi</b>\n\n"
                f"Bugun {count} ta check-in qayd etildi."
            ),
            detail=detail,
        )

    alert = "\n".join([
        "🔴 <b>Davomat ishlamayapti</b>",
        "",
        f"Bugun ({local_now.strftime('%d.%m.%Y')}) soat "
        f"{settings.attendance_check_hour}:00 gacha <b>birorta ham xodim</b> "
        "check-in qilmadi.",
        "",
        "Odatda ish kunida 13 ga yaqin check-in bo'ladi — demak Face ID yoki "
        "davomat sahifasi ishlamayotgan bo'lishi mumkin.",
        "",
        "Tekshirish kerak: sayt ochilyaptimi, kamera ruxsati va yuz modeli "
        "fayllari joyidami.",
    ])
    recovery = "🟢 <b>Davomat tiklandi</b>\n\nCheck-in yozuvlari qayta kelmoqda."
    return CheckResult(False, alert, recovery, detail=detail)


# ---------------------------------------------------------------------------
# Yurituvchi
# ---------------------------------------------------------------------------

_CHECKS = {
    "crm": check_crm,
    "backup": check_backup,
    "attendance": check_attendance,
}

# Tiklanish xabari uchun zaxira nom — tekshiruv SOG' natijada `recovery_text`
# bermasa ishlatiladi (yangi tekshiruv qo'shganda esdan chiqsa, tiklanish
# xabari JIMGINA yo'qolib qolmasin — aynan shu xato 2026-08-05 sinovida
# topilgan edi).
_LABELS = {"crm": "CRM aloqasi", "backup": "Zaxira nusxa", "attendance": "Davomat"}


async def tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Barcha tekshiruvlarni yurgizadi. Qaytaradi: har tekshiruv uchun holat +
    yuborilgan ogohlantirishlar. `dry_run` — hech narsa yubormaydi/yozmaydi.

    Bitta tekshiruv xato bersa (kutilmagan istisno) qolganlari baribir
    ishlaydi — qo'riqchining o'zi bitta nosozlikdan yiqilmasin."""
    now = datetime.utcnow()
    recipients = await _alert_recipients(db)
    realert_after = timedelta(hours=settings.crm_health_realert_hours)

    out: dict = {"ok": True, "dry_run": dry_run, "checks": {}, "alerted": [], "recovered": []}

    for name, fn in _CHECKS.items():
        try:
            res = await fn(db, now)
        except Exception:  # noqa: BLE001 — qo'riqchi bitta tekshiruv sababli o'lmasin
            logger.exception("Qo'riqchi tekshiruvi xato berdi: %s", name)
            out["checks"][name] = {"error": True}
            continue

        entry = {"healthy": res.healthy, "skipped": res.skipped, **(res.detail or {})}
        out["checks"][name] = entry
        if res.skipped:
            continue

        state = await _state(db, name)

        # ── Tiklandi ──
        if res.healthy and state.alerting:
            out["recovered"].append(name)
            if not dry_run:
                text = res.recovery_text or (
                    f"🟢 <b>{_LABELS.get(name, name)} tiklandi</b>"
                )
                await _send_all(recipients, text)
                state.alerting = False
                state.last_alert_at = None
                state.stale_since = None
            logger.info("Qo'riqchi: '%s' tiklandi", name)
            continue

        if res.healthy:
            continue

        # ── Nosoz: ogohlantirish kerakmi? ──
        if state.alerting and state.last_alert_at is not None:
            if now - state.last_alert_at < realert_after:
                continue  # yaqinda ogohlantirilgan — shovqin qilmaymiz

        out["alerted"].append(name)
        if not dry_run:
            if recipients and res.alert_text:
                await _send_all(recipients, res.alert_text)
            elif not recipients:
                logger.error(
                    "Qo'riqchi '%s' ogohlantirmoqchi, lekin MANZIL YO'Q — "
                    "dasturchi ham, guruh ham topilmadi.", name
                )
            if not state.alerting:
                state.stale_since = res.stale_since
            state.alerting = True
            state.last_alert_at = now
        logger.warning("Qo'riqchi: '%s' nosoz — ogohlantirish yuborildi (%s)", name, res.detail)

    if not dry_run:
        await db.commit()
    return out
