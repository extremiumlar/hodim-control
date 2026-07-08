"""Soatma-soat reja: xodimning kunlik normasini ish jadvalidagi soatlarga bo'lib,
har soatda nima qilish kerakligini (reja) va haqiqiy natija (CRM) bilan solishtirib
ko'rsatadi. Xodim botda ochib ko'radi; scheduler har soatda avtomatik eslatadi."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.schemas import HourlyMetricStatus, HourlyPlanOut
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ, today_local
from db.models import Role, User, WorkScheduleOverride, WorkScheduleWeekly

router = APIRouter(prefix="/hourly-plan", tags=["hourly-plan"])

WEEKDAYS_UZ = ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"]
DEFAULT_START = "09:00"
DEFAULT_END = "18:00"
# Tushlik tanaffusi — reja hisobidan chiqariladi (ish soatiga kirmaydi).
LUNCH_START = 13 * 60  # 13:00
LUNCH_END = 14 * 60  # 14:00


def _work_minutes(a: int, b: int) -> int:
    """[a, b) oralig'idagi ish daqiqalari — tushlik (13:00–14:00) ayirilgan holda."""
    if b <= a:
        return 0
    lunch_overlap = max(0, min(b, LUNCH_END) - max(a, LUNCH_START))
    return (b - a) - lunch_overlap


def _to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


# To'liq (standart) ish kuni uzunligi — qisqa/yarim kunlarda normani shunga
# nisbatan proporsional kamaytirish uchun (09:00-18:00, tushliksiz = 8 soat).
FULL_DAY_MINUTES = _work_minutes(_to_min(DEFAULT_START), _to_min(DEFAULT_END))


async def _effective_today(db: AsyncSession, user: User, day: date) -> tuple[bool, str, str]:
    """Bugungi amaldagi ish oynasi: (is_working, start, end). Override > haftalik >
    default. Jadval umuman belgilanmagan bo'lsa — dushanba-jumada default 09:00-18:00,
    shanba-yakshanbada dam olish kuni deb hisoblanadi."""
    ov = await db.scalar(
        select(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user.id, WorkScheduleOverride.date == day
        )
    )
    if ov is not None:
        if not ov.is_working:
            return False, "", ""
        return True, ov.start_time or DEFAULT_START, ov.end_time or DEFAULT_END

    w = await db.scalar(
        select(WorkScheduleWeekly).where(
            WorkScheduleWeekly.user_id == user.id, WorkScheduleWeekly.weekday == day.weekday()
        )
    )
    if w is not None:
        if not w.is_working:
            return False, "", ""
        return True, w.start_time or DEFAULT_START, w.end_time or DEFAULT_END

    # Jadval belgilanmagan — dam olish kunlari (shanba/yakshanba) ishlanmaydi deb
    # hisoblanadi, ish kunlarida default ish oynasi qo'llanadi.
    if day.weekday() >= 5:
        return False, "", ""
    return True, DEFAULT_START, DEFAULT_END


async def build_ai_plan(db: AsyncSession, user: User, now: datetime) -> HourlyPlanOut | None:
    """Operator AI rejimi (2-bosqich): rejani qo'lda normadan emas, avto-hisoblangan
    `hourly_target`dan (profil+benchmark+stretch) o'qiydi, haqiqiy natijani
    `hourly_actual`dan (CRM soatlik qo'ng'iroq) oladi. Bugunga target yo'q bo'lsa
    `None` qaytaradi — chaqiruvchi eski (norma) oqimga qaytadi."""
    from db.models import HourlyActual, HourlyTarget  # circular importdan qochish

    day = now.date()
    targets = list(
        await db.scalars(
            select(HourlyTarget).where(HourlyTarget.user_id == user.id, HourlyTarget.date == day)
        )
    )
    header = f"📋 <b>Bugungi rejam — {day:%d.%m} ({WEEKDAYS_UZ[day.weekday()]})</b>"
    if not targets:
        return None

    is_working, start, end = await _effective_today(db, user, day)
    if not is_working:
        return HourlyPlanOut(
            date=day, is_working=False,
            text=f"{header}\n\n🌙 Bugun dam olish kuni (ish jadvali bo'yicha).",
        )

    targets_by_hour = {t.hour: t for t in targets}
    actual_rows = list(
        await db.scalars(
            select(HourlyActual).where(HourlyActual.user_id == user.id, HourlyActual.date == day)
        )
    )
    actual_by_hour = {a.hour: a for a in actual_rows}

    start_min, end_min = _to_min(start), _to_min(end)
    now_min = now.hour * 60 + now.minute
    cur_hour = now.hour
    frac = now.minute / 60
    in_lunch = start_min <= now_min < end_min and LUNCH_START <= now_min < LUNCH_END

    daily_target = sum(t.target_calls for t in targets)
    cumulative_target = 0
    for t in targets:
        if t.hour < cur_hour:
            cumulative_target += t.target_calls
        elif t.hour == cur_hour:
            cumulative_target += round(t.target_calls * frac)
    actual_total = sum(a.calls for a in actual_rows)
    this_hour_target = targets_by_hour[cur_hour].target_calls if cur_hour in targets_by_hour else 0

    total_hours = max(len(targets), 1)
    status = HourlyMetricStatus(
        key="suhbat", label="Qo'ng'iroqlar", norm=daily_target, effective_norm=daily_target,
        per_hour=round(daily_target / total_hours, 1), this_hour_target=this_hour_target,
        cumulative_target=cumulative_target, actual=actual_total,
        delta=actual_total - cumulative_target, tracked=True,
    )

    now_hm = f"{now.hour:02d}:{now.minute:02d}"
    lines = [header, f"🕘 Ish vaqti: {start}–{end} (tushlik 13:00–14:00) | Hozir: {now_hm}",
             "🤖 Reja avto-hisoblangan (30 kunlik tempingiz + jamoa + o'sish)", ""]
    lines.append(f"<b>Qo'ng'iroqlar</b> — bugungi reja: {daily_target}")
    before_start = now_min < start_min
    after_end = now_min >= end_min
    if status.delta >= 0:
        mark = f"✅ +{status.delta}" if status.delta else "✅ rejada"
    else:
        mark = f"⚠️ {status.delta}"
    lines.append(f"  Shu paytgacha: kerak {cumulative_target} / bajarildi {actual_total}  {mark}")
    if before_start:
        lines.append(f"  Ish {start} da boshlanadi")
    elif after_end:
        lines.append("  Ish vaqti tugadi")
    elif in_lunch:
        lines.append("  🍽 Hozir tushlik vaqti (13:00–14:00)")
    else:
        lines.append(f"  ⏱ Bu soatda reja: ~{this_hour_target} ta")

    # Sifat holati (javob + o'rtacha suhbat) — bugungi actual asosida
    ans = sum(a.answered for a in actual_rows)
    talk = sum(a.talk_sec for a in actual_rows)
    if actual_total:
        avg_talk = round(talk / ans) if ans else 0
        lines.append(f"  Sifat: {ans} javob berildi, o'rtacha suhbat {avg_talk}s")

    # Soatlik reja jadvali
    lines.append("")
    lines.append("📊 Soatlik reja (qo'ng'iroq):")
    blocks = []
    h = start_min // 60
    end_h = (end_min + 59) // 60
    while h < end_h:
        label = f"{h:02d}:00–{h + 1:02d}:00"
        if h == LUNCH_START // 60:
            blocks.append(f"{label} 🍽")
        else:
            t = targets_by_hour.get(h)
            a = actual_by_hour.get(h)
            cell = f"{label}: {t.target_calls if t else 0}"
            if a is not None:
                cell += f" (⟶{a.calls})"
            blocks.append(cell)
        h += 1
    lines.append(" · ".join(blocks))

    return HourlyPlanOut(
        date=day, is_working=True, in_lunch=in_lunch, start_time=start, end_time=end, now=now_hm,
        metrics=[status], text="\n".join(lines).strip(),
    )


async def build_plan(db: AsyncSession, user: User, now: datetime) -> HourlyPlanOut:
    from api.routers.stats import today_metric_rows  # circular importdan qochish

    # Operator AI yoqilgan bo'lsa avval avto-reja (hourly_target)ni sinaymiz; bugunga
    # target tuzilmagan bo'lsa (None) eski qo'lda-norma oqimiga tushamiz.
    if settings.ai_enabled:
        ai_plan = await build_ai_plan(db, user, now)
        if ai_plan is not None:
            return ai_plan

    day = now.date()
    is_working, start, end = await _effective_today(db, user, day)
    header = f"📋 <b>Bugungi rejam — {day:%d.%m} ({WEEKDAYS_UZ[day.weekday()]})</b>"

    if not is_working:
        return HourlyPlanOut(
            date=day, is_working=False,
            text=f"{header}\n\n🌙 Bugun dam olish kuni (ish jadvali bo'yicha).",
        )

    start_min, end_min = _to_min(start), _to_min(end)
    total = max(_work_minutes(start_min, end_min), 1)  # tushliksiz ish daqiqalari
    total_hours = total / 60
    now_min = now.hour * 60 + now.minute
    elapsed = _work_minutes(start_min, min(max(now_min, start_min), end_min))
    in_lunch = start_min <= now_min < end_min and LUNCH_START <= now_min < LUNCH_END

    def cum_target(effective_norm: int, up_to_min: int) -> int:
        """[start, up_to_min) oralig'ida (tushliksiz) kumulyativ qilinishi kerak
        bo'lgan miqdor — soatlik bloklar va joriy soat maqsadi shundan farq
        sifatida hisoblanadi, shuning uchun ular yig'indisi har doim aniq
        effective_norm'ga teng chiqadi (yaxlitlash qoldig'i yo'qolmaydi)."""
        clipped = min(max(up_to_min, start_min), end_min)
        return round(effective_norm * _work_minutes(start_min, clipped) / total)

    metric_rows = await today_metric_rows(db, user)
    statuses: list[HourlyMetricStatus] = []
    for r in metric_rows:
        if not r.norm or r.norm <= 0:
            continue
        # Qisqa/yarim ish kunida normani to'liq kunga (8 soat) nisbatan
        # proporsional kamaytiramiz — aks holda soatlik maqsad sun'iy shishadi.
        proration = min(total, FULL_DAY_MINUTES) / FULL_DAY_MINUTES
        effective_norm = max(round(r.norm * proration), 0) if proration < 1 else r.norm

        cumulative_target = cum_target(effective_norm, now_min)
        hour_start_clock = (now_min // 60) * 60
        this_hour_target = cumulative_target - cum_target(effective_norm, hour_start_clock)

        statuses.append(
            HourlyMetricStatus(
                key=r.key, label=r.label, norm=r.norm, effective_norm=effective_norm,
                per_hour=round(effective_norm / total_hours, 1),
                this_hour_target=max(this_hour_target, 0),
                cumulative_target=cumulative_target,
                actual=r.value,
                delta=r.value - cumulative_target,
                tracked=r.tracked,
            )
        )

    now_hm = f"{now.hour:02d}:{now.minute:02d}"
    lines = [header, f"🕘 Ish vaqti: {start}–{end} (tushlik 13:00–14:00) | Hozir: {now_hm}", ""]

    if not statuses:
        lines.append("Sizga hali kunlik norma belgilanmagan — rahbaringizga murojaat qiling.")
    else:
        before_start = now_min < start_min
        after_end = now_min >= end_min
        for s in statuses:
            norm_line = f"<b>{s.label}</b> — kunlik reja: {s.norm}"
            if s.effective_norm != s.norm:
                norm_line += f" (bugun qisqa kun uchun: {s.effective_norm})"
            lines.append(norm_line)

            if not s.tracked:
                lines.append("  ❔ Bu ko'rsatkich hozircha kuzatilmayapti (CRM bog'lanmagan)")
            else:
                if s.delta >= 0:
                    mark = f"✅ +{s.delta}" if s.delta else "✅ rejada"
                else:
                    mark = f"⚠️ {s.delta}"
                lines.append(f"  Shu paytgacha: kerak {s.cumulative_target} / bajarildi {s.actual}  {mark}")

            if before_start:
                first_hour_target = cum_target(s.effective_norm, start_min + 60)
                lines.append(f"  Ish {start} da boshlanadi (birinchi soatda ~{first_hour_target} ta)")
            elif after_end:
                lines.append("  Ish vaqti tugadi")
            elif in_lunch:
                lines.append("  🍽 Hozir tushlik vaqti (13:00–14:00)")
            else:
                lines.append(f"  ⏱ Bu soatda: ~{s.this_hour_target} ta")
            lines.append("")
        # Soatlik reja jadvali (birinchi ko'rsatkich bo'yicha) — har blok kumulyativ
        # qoldiqdan hisoblanadi, shuning uchun yig'indisi aniq normaga teng chiqadi.
        first = statuses[0]
        blocks = []
        b = start_min
        while b < end_min:
            b2 = min(b + 60, end_min)
            label = f"{b // 60:02d}:{b % 60:02d}–{b2 // 60:02d}:{b2 % 60:02d}"
            if _work_minutes(b, b2) == 0:  # to'liq tushlik blogi
                blocks.append(f"{label} 🍽")
            else:
                block_target = cum_target(first.effective_norm, b2) - cum_target(first.effective_norm, b)
                blocks.append(f"{label}: {block_target}")
            b += 60
        lines.append(f"📊 Soatlik reja ({first.label.lower()}):")
        lines.append(" · ".join(blocks))

    return HourlyPlanOut(
        date=day, is_working=True, in_lunch=in_lunch, start_time=start, end_time=end, now=now_hm,
        metrics=statuses, text="\n".join(lines).strip(),
    )


@router.get("/{telegram_id}/me", response_model=HourlyPlanOut, dependencies=[Depends(verify_bot_secret)])
async def my_hourly_plan(telegram_id: int, db: AsyncSession = Depends(get_db)) -> HourlyPlanOut:
    """Xodim botda ochganda: hozirgi holatga qarab bugungi soatma-soat reja + progress."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await build_plan(db, user, datetime.now(TASHKENT_TZ))


@router.get(
    "/{telegram_id}/employee/{user_id}", response_model=HourlyPlanOut, dependencies=[Depends(verify_bot_secret)]
)
async def employee_hourly_plan(telegram_id: int, user_id: int, db: AsyncSession = Depends(get_db)) -> HourlyPlanOut:
    """Rahbar (ROP/HR/Boshliq/Dasturchi) uchun: bitta xodimning bugungi soatma-soat
    rejasi — norma boshqaruvi bilan bir xil doira (norma o'rnata oladigan rahbar
    reja ham ko'radi)."""
    from api.routers.norms import can_manage_norms  # circular importdan qochish

    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")

    target = await db.get(User, user_id)
    if not target or target.role != Role.employee.value or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    is_privileged = actor.role in (Role.boss.value, Role.dasturchi.value)
    if not is_privileged and not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning nazoratingizda emas")

    return await build_plan(db, target, datetime.now(TASHKENT_TZ))


@router.post("/send", dependencies=[Depends(verify_bot_secret)])
async def send_hourly_plan(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler har soat boshida chaqiradi: ayni damда ish vaqtida bo'lgan va normasi
    bor xodimlarga shu soat rejasini + progressni yuboradi. Ish vaqtidan tashqarida
    (yoki dam olish kunida) hech kimga yuborilmaydi. Xavfsizlik uchun default o'chiq
    (settings.hourly_plan_enabled) — haqiqiy xodimlarga xabar ketgani sabab."""
    if not settings.hourly_plan_enabled:
        return {"sent": 0, "disabled": True}
    now = datetime.now(TASHKENT_TZ)
    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )
    sent = 0
    for user in users:
        plan = await build_plan(db, user, now)
        if not plan.is_working or not plan.metrics or plan.in_lunch:
            continue
        # Faqat ish oynasi ichida (rejada boshlanmagan/tugagan bo'lsa yubormaymiz)
        if plan.start_time and plan.end_time:
            now_min = now.hour * 60 + now.minute
            if now_min < _to_min(plan.start_time) or now_min >= _to_min(plan.end_time):
                continue
        result = await send_message(user.telegram_id, plan.text)
        if result is not None:
            sent += 1
    return {"sent": sent, "at": f"{now.hour:02d}:{now.minute:02d}", "date": today_local().isoformat()}
