"""Kunlik davomat (kelib-ketish) digesti — guruhga avtomatik yuboriladi.

Ikki xil digest:
  • ertalabki (default 09:30) — kim keldi, kim kechikdi, kim hali kelmadi;
  • kechki (default 22:00) — kun yakuni: ish vaqti, kechikishlar, chiqmaganlar,
    umuman kelmaganlar.

Ma'lumot manbai: `attendance` jadvali + xodimning o'sha kungi ish jadvali
(WorkScheduleOverride > WorkScheduleWeekly > default) + tasdiqlangan sababli
kunlar. `ATTENDANCE_TRACKED_ROLES` — Boshliqdan tashqari HAMMA (xodim, HR, ROP,
dasturchi) — rahbarlar (Boshliqdan boshqa) ham davomat ro'yxatida ko'rinadi
(late-stats/employee-summary bilan bir xil qoida; 4.9-band — bu izoh ilgari
eskirgan edi, faqat "employee" deb yozilgan).

Dam olish kuni (hech kim ishlamaydi) — digest yuborilmaydi (guruhda shovqin
bo'lmasligi uchun)."""
import html
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.hourly_plan import _effective_today
from api.services.attendance import ATTENDANCE_TRACKED_ROLES, AUTO_CLOSED_MARK
from api.services.daily_digest import digest_group_targets
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ, today_local, work_minutes
from db.models import (
    Attendance,
    AttendanceDigestConfig,
    ExcusedDay,
    ExcusedStatus,
    Role,
    User,
    WorkScheduleOverride,
    WorkScheduleWeekly,
)

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS_UZ = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


def _fmt_local(dt: datetime | None) -> str:
    """Bazadagi naive-UTC vaqtni Toshkent soatiga o'giradi: '08:52'."""
    if dt is None:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ).strftime("%H:%M")


def _fmt_date(d) -> str:
    return f"{d.day}-{MONTHS_UZ[d.month - 1]}, {WEEKDAYS_UZ[d.weekday()]}"


def _name(u: User) -> str:
    return html.escape(u.full_name)


def _minute_of_day(dt: datetime) -> int:
    """naive-UTC vaqtdan Toshkent kunidagi daqiqa (0-1439)."""
    local = dt.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    return local.hour * 60 + local.minute


def _hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


async def collect_day(db: AsyncSession, day=None) -> dict:
    """Kunning davomat manzarasi — ikkala digest uchun YAGONA yig'uvchi.

    Qaytaradi: {day, expected, present, late, early_in, absent, excused,
    no_checkout, early_out, late_out}. Har bir "vaqt" ro'yxati (user, att, daqiqa)
    uchligi: `early_in` — jadvaldan necha daqiqa erta kelgan; `early_out` — erta
    ketgan; `late_out` — ish oynasi tugagach necha daqiqa ortiqcha qolgan.
    Kechikish (`late`) Attendance.late_minutes'dan (grace bilan hisoblangan),
    qolganlari shu yerda ish jadvali oynasidan hisoblanadi."""
    day = day or today_local()

    employees = list(
        await db.scalars(
            select(User).where(
                User.is_active.is_(True), User.role.in_(ATTENDANCE_TRACKED_ROLES)
            )
        )
    )
    att_rows = {
        a.user_id: a
        for a in await db.scalars(select(Attendance).where(Attendance.date == day))
    }
    excused_ids = {
        e.user_id
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.date == day, ExcusedDay.status == ExcusedStatus.approved.value
            )
        )
    }

    # 3.5-band: ilgari har xodim uchun `_effective_today` alohida chaqirilardi —
    # 2 ta so'rov (override + weekly) xodimlar soniga ko'paytirilardi. `digest_tick`
    # har daqiqa ishlagani uchun bu sezilarli yuk edi (`dashboard()`dagi bilan
    # bir xil naqsh: hamma xodim uchun BITTA so'rovda olib, lug'atga solish).
    overrides_by_user = {
        o.user_id: (o.is_working, o.start_time, o.end_time)
        for o in await db.scalars(select(WorkScheduleOverride).where(WorkScheduleOverride.date == day))
    }
    weekly_by_user = {
        w.user_id: (w.is_working, w.start_time, w.end_time)
        for w in await db.scalars(select(WorkScheduleWeekly).where(WorkScheduleWeekly.weekday == day.weekday()))
    }
    default_schedule = (day.weekday() < 5, None, None)

    expected: list[User] = []  # bugun ishlashi kerak bo'lganlar
    present: list[tuple[User, Attendance]] = []
    late: list[tuple[User, Attendance]] = []
    early_in: list[tuple[User, Attendance, int]] = []
    absent: list[User] = []
    excused: list[User] = []
    no_checkout: list[tuple[User, Attendance]] = []
    early_out: list[tuple[User, Attendance, int]] = []
    late_out: list[tuple[User, Attendance, int]] = []

    for u in employees:
        is_working, start, end = overrides_by_user.get(u.id, weekly_by_user.get(u.id, default_schedule))
        if not is_working:
            continue  # dam olish kuni — ro'yxatga kirmaydi
        expected.append(u)

        att = att_rows.get(u.id)
        if att is not None and att.check_in_time is not None:
            present.append((u, att))
            if att.late_minutes > 0:
                late.append((u, att))
            elif start:
                # Kechikmagan bo'lsa — jadvaldan qancha erta kelgani
                early = _hm_to_min(start) - _minute_of_day(att.check_in_time)
                if early > 0:
                    early_in.append((u, att, early))

            if att.check_out_time is None:
                no_checkout.append((u, att))
            elif end:
                diff = _minute_of_day(att.check_out_time) - _hm_to_min(end)
                if diff > 0:
                    late_out.append((u, att, diff))
                elif att.early_leave_minutes > 0:
                    early_out.append((u, att, att.early_leave_minutes))
        elif u.id in excused_ids:
            excused.append(u)
        else:
            absent.append(u)

    late.sort(key=lambda p: p[1].late_minutes, reverse=True)
    early_in.sort(key=lambda p: p[2], reverse=True)
    early_out.sort(key=lambda p: p[2], reverse=True)
    late_out.sort(key=lambda p: p[2], reverse=True)
    present.sort(key=lambda p: p[1].check_in_time or datetime.max)

    return {
        "day": day,
        "expected": expected,
        "present": present,
        "late": late,
        "early_in": early_in,
        "absent": absent,
        "excused": excused,
        "no_checkout": no_checkout,
        "early_out": early_out,
        "late_out": late_out,
    }


def build_morning_text(data: dict) -> str:
    """Ertalabki digest — hozirgi holat: keldi / kelmadi / kech keldi.

    Egasining 2026-08-04 talabi: «o'z vaqtida keldi» kerak emas. Ilgari ro'yxat
    to'rtga bo'lingan edi (erta keldi / o'z vaqtida / kechikdi / hali kelmadi)
    va uzun chiqardi. Endi UCH toifa: erta kelgan ham, aniq vaqtida kelgan ham
    bitta «Keldi» ro'yxatida — rahbarga muhimi kim keldi, kim kechikdi, kim yo'q.
    """
    now_hm = datetime.now(TASHKENT_TZ).strftime("%H:%M")
    present, late = data["present"], data["late"]
    late_ids = {u.id for u, _ in late}
    on_time = [(u, a) for u, a in present if u.id not in late_ids]

    lines = [
        f"🌅 <b>Ertalabki davomat</b> — {_fmt_date(data['day'])} ({now_hm})",
        "",
        f"👥 Bugun ishlashi kerak: <b>{len(data['expected'])}</b> · "
        f"keldi: <b>{len(present)}</b> · kelmadi: <b>{len(data['absent'])}</b>",
    ]

    if on_time:
        lines += ["", f"✅ <b>Keldi ({len(on_time)}):</b>"]
        lines += [f"  • {_name(u)} — {_fmt_local(a.check_in_time)}" for u, a in on_time]

    if late:
        total = sum(a.late_minutes for _, a in late)
        lines += ["", f"⏰ <b>Kech keldi ({len(late)}) — jami {total} daq:</b>"]
        lines += [
            f"  • {_name(u)} — {_fmt_local(a.check_in_time)} (+{a.late_minutes} daq)"
            for u, a in late
        ]

    if data["absent"]:
        lines += ["", f"❌ <b>Kelmadi ({len(data['absent'])}):</b>"]
        lines += [f"  • {_name(u)}" for u in data["absent"]]

    if data["excused"]:
        lines += ["", f"🏖 <b>Sababli ({len(data['excused'])}):</b> " +
                  ", ".join(_name(u) for u in data["excused"])]

    return "\n".join(lines)


# Dasturchi ish joyida bo'lsa ham check-in qilmasligi mumkin (u serverxonada
# yoki texnik ish bilan band). Egasining talabi: kechqurun uni "kelmadi" deb
# emas, "ofisda" deb ko'rsatish. ROLGA bog'langan, ISMGA emas — ism o'zgarsa
# qoida jim buzilmasin (egasi 2026-08-04 da shu variantni tanladi).
OFFICE_ASSUMED_ROLE = Role.dasturchi.value
OFFICE_ASSUMED_AFTER_HM = "18:00"


def build_evening_text(data: dict) -> str:
    """Kechki digest — kun yakuni.

    Egasining 2026-08-04 talabi bo'yicha ketish qismi kelish qismi bilan bir
    xil uch toifaga keltirildi: <b>ketdi / ketmadi / erta ketdi</b>. «Kech
    ketganlar» (ortiqcha ishlaganlar) va «erta kelganlar» ro'yxatlari olib
    tashlandi — ular saytda baribir ko'rinadi, guruhdagi xabar esa qisqa
    bo'lishi kerak.
    """
    present, late = data["present"], data["late"]
    lines = [
        f"🌙 <b>Kunlik davomat yakuni</b> — {_fmt_date(data['day'])}",
        "",
        f"👥 Ishlashi kerak edi: <b>{len(data['expected'])}</b> · "
        f"keldi: <b>{len(present)}</b> · kelmadi: <b>{len(data['absent'])}</b>",
    ]

    if late:
        total = sum(a.late_minutes for _, a in late)
        lines += ["", f"⏰ <b>Kech keldi ({len(late)}) — jami {total} daq:</b>"]
        lines += [f"  • {_name(u)} +{a.late_minutes} daq ({_fmt_local(a.check_in_time)})"
                  for u, a in late]

    # ── Ketish: ketdi / erta ketdi / ketmadi ──
    early_out_ids = {u.id for u, _, _ in data["early_out"]}
    no_checkout_ids = {u.id for u, _ in data["no_checkout"]}
    left_ok = [
        (u, a) for u, a in present
        if a.check_out_time is not None and u.id not in early_out_ids
    ]

    if left_ok:
        lines += ["", f"✅ <b>Ketdi ({len(left_ok)}):</b>"]
        for u, a in left_ok:
            worked = f"{round(a.worked_minutes / 60, 1)} soat" if a.worked_minutes else "—"
            lines.append(f"  • {_name(u)} — {_fmt_local(a.check_out_time)} ({worked})")

    if data["early_out"]:
        lines += ["", f"🏃 <b>Erta ketdi ({len(data['early_out'])}):</b>"]
        lines += [f"  • {_name(u)} {mins} daq erta ({_fmt_local(a.check_out_time)})"
                  for u, a, mins in data["early_out"]]

    if data["no_checkout"]:
        lines += ["", f"🚪 <b>Ketmadi — «Ketdim» bosilmagan ({len(no_checkout_ids)}):</b> " +
                  ", ".join(_name(u) for u, _ in data["no_checkout"])]

    if data["absent"]:
        lines += ["", f"❌ <b>Kelmadi ({len(data['absent'])}):</b> " +
                  ", ".join(_name(u) for u in data["absent"])]

    if data["excused"]:
        lines += ["", f"🏖 <b>Sababli ({len(data['excused'])}):</b> " +
                  ", ".join(_name(u) for u in data["excused"])]

    # ── Dasturchi: check-in yo'q bo'lsa "ofisda" deb izohlanadi ──
    # `expected` ichidan qidiramiz: dam kunida yoki sababli kunda bu satr
    # chiqmasligi kerak (u paytda u haqiqatan yo'q).
    checked_in_ids = {u.id for u, _ in present}
    office = [
        u for u in data["expected"]
        if u.role == OFFICE_ASSUMED_ROLE and u.id not in checked_in_ids
    ]
    if office:
        lines += [""]
        # UX2-C12: guruhga har kuni chiqadigan satr — to'g'ri o'zbekcha bo'lsin
        lines += [
            f"🖥 {_name(u)} — «Keldim» bosmagan, {OFFICE_ASSUMED_AFTER_HM} dan keyin "
            "ofisda deb hisoblanadi."
            for u in office
        ]

    return "\n".join(lines)


async def write_absent_records(db: AsyncSession, day=None) -> int:
    """Kun tugagach, kelmagan (check-in qilmagan, sababli ham bo'lmagan) xodimlarga
    `status='absent'` yozuvi yaratadi. Buni yozmasa: (1) `GET /attendance
    ?status_filter=absent` doim bo'sh qaytardi, (2) `employee-summary`/`late-stats`
    kabi OUTER JOIN hisobotlar kelmagan kunni "0 kun" deb hisoblay olardi, lekin
    "necha kun kelmadi" degan raqamning o'zi hech qayerda saqlanmas edi.

    Idempotent: `uq_attendance_user_date` bor yozuv uchun qayta yozmaydi — bir necha
    marta chaqirilsa ham xavfsiz. `AttendanceDigestConfig.absent_marked_date`
    bildirishnoma sozlamasidan (evening_enabled) MUSTAQIL — xodim kelmagani
    haqiqati guruhga xabar yuborish yoqiq-o'chiqligiga bog'liq bo'lmasligi kerak."""
    data = await collect_day(db, day)
    if not data["expected"]:
        return 0  # dam olish kuni — hech kim ishlamaydi

    already = {
        a.user_id
        for a in await db.scalars(select(Attendance).where(Attendance.date == data["day"]))
    }
    written = 0
    for u in data["absent"]:
        if u.id in already:
            continue  # ehtiyot chorasi — collect_day ham shu mantiqni hisoblaydi
        db.add(
            Attendance(
                user_id=u.id,
                date=data["day"],
                status="absent",
                is_weekend=False,
                late_minutes=0,
                early_leave_minutes=0,
                worked_minutes=0,
            )
        )
        written += 1
    if written:
        await db.commit()
    return written


async def ask_explanations(db: AsyncSession, day=None) -> int:
    """Sababsiz kelmagan xodimlardan TUSHUNTIRISH XATI so'raydi.

    `write_absent_records` dan KEYIN chaqiriladi — o'sha payt `absent`
    yozuvlari allaqachon bor. Dam kuni va sababli kun bu yerga UMUMAN
    yetib kelmaydi: `collect_day` ularni `absent` ro'yxatiga qo'shmaydi.

    ⚠️ JARIMAGA TEGMAYDI — kun `absent` bo'lib qolaveradi va jarima o'z
    kuchida turadi. Faqat HR "sababli" deb qabul qilsa, MAVJUD `ExcusedDay`
    orqali kun sababliga aylanadi (`decide_explanation`).

    Idempotent: UNIQUE(user_id, date) — bir kunga bitta so'rov."""
    from api.notify import notify_user
    from api.services.push import Category
    from api.telegram_notify import inline_keyboard
    from db.models import ExplanationRequest

    day = day or today_local()
    absent_rows = list(
        await db.scalars(
            select(Attendance).where(Attendance.date == day, Attendance.status == "absent")
        )
    )
    if not absent_rows:
        return 0

    existing = {
        r.user_id
        for r in await db.scalars(select(ExplanationRequest).where(ExplanationRequest.date == day))
    }

    asked = 0
    for att in absent_rows:
        if att.user_id in existing:
            continue
        user = await db.get(User, att.user_id)
        if user is None or not user.is_active or user.telegram_id is None:
            continue

        req = ExplanationRequest(user_id=user.id, date=day)
        db.add(req)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue  # boshqa chaqiruv ulgurdi
        await db.refresh(req)

        text = (
            f"📄 <b>Tushuntirish xati</b>\n\n"
            f"{day} kuni sizda kelish qayd etilmagan va sababli kun ham belgilanmagan.\n"
            f"Iltimos, sababini yozib yuboring — HR ko'rib chiqadi.\n\n"
            f"<i>Agar sabab uzrli deb topilsa, o'sha kun sababli kunga o'tkaziladi.</i>"
        )
        keyboard = inline_keyboard([[("✍️ Tushuntirish yozish", f"explain:{req.id}")]])
        # Telegram MAJBURIY: javob yozish faqat botda mumkin (ilovada bu
        # ekran yo'q), shuning uchun push bilan almashtirib bo'lmaydi.
        await notify_user(
            db, user, Category.DECISIONS, text, reply_markup=keyboard, force_telegram=True
        )
        asked += 1
    return asked


async def auto_close_unclosed_checkouts(db: AsyncSession, today=None) -> int:
    """2.2-band (Savol C javobi: FAQAT avtomatik) — kelib-u «Ketdim» bosmagan
    xodimlarning O'TGAN kunlari (bugundan oldingi) avtomatik yopiladi. Bosmasa
    `worked_minutes` abadiy 0 bo'lib qolar, `month_worked_hours` doimo kam
    ko'rsatardi va Dasturchidan boshqa hech kim (u ham faqat O'CHIRISH orqali)
    tuzata olmasdi.

    Faqat `date < today` — bugungi ochiq yozuvga tegilmaydi (xodim hali ishda
    bo'lishi yoki 2.1-band bo'yicha yarim tundan keyin o'zi yopishi mumkin; bu
    funksiya kuni tugagach — kechki digest vaqtida — chaqiriladi, o'sha payt
    2.1'ning 6 soatlik oynasi allaqachon yopilgan bo'ladi, ikkalasi to'qnashmaydi).
    Yopilish vaqti — o'sha kunning ish jadvali TUGASH vaqti; topilmasa (jadval
    yo'q) standart 9 soatlik ish kuni taxmin qilinadi."""
    today = today or today_local()
    rows = list(
        await db.scalars(
            select(Attendance).where(
                Attendance.date < today,
                Attendance.check_in_time.isnot(None),
                Attendance.check_out_time.is_(None),
            )
        )
    )
    closed = 0
    for att in rows:
        user = await db.get(User, att.user_id)
        if user is None:
            continue
        is_working, start, end = await _effective_today(db, user, att.date)
        if end:
            h, m = map(int, end.split(":"))
            local_end = datetime(att.date.year, att.date.month, att.date.day, h, m, tzinfo=TASHKENT_TZ)
            check_out_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            check_out_utc = att.check_in_time + timedelta(hours=9)
        # Chiqish "kelishdan oldin" chiqib qolmasin (masalan juda kech check-in
        # qilib, o'sha kunning ish oynasi allaqachon tugagan bo'lsa).
        if check_out_utc <= att.check_in_time:
            check_out_utc = att.check_in_time + timedelta(hours=1)

        att.check_out_time = check_out_utc
        if is_working and start and end:
            in_local = att.check_in_time.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
            in_min = in_local.hour * 60 + in_local.minute
            worked = work_minutes(max(in_min, _hm_to_min(start)), _hm_to_min(end))
        else:
            worked = 0
        att.worked_minutes = max(0, worked)
        att.early_leave_minutes = 0
        # Belgi matni `AUTO_CLOSED_MARK` dan olinadi — tayyorlik hisoboti
        # (`collect_readiness`) aynan shu bo'yicha "ishlangan vaqt taxminiy"
        # kunlarni topadi, ikki joyda matn ajralib ketmasin.
        note = f"⚠️ {AUTO_CLOSED_MARK} — xodim «Ketdim» bosmagan."
        att.note = f"{att.note} {note}" if att.note else note
        closed += 1
    if closed:
        await db.commit()
    return closed


async def _lead_digest_fires_at(db: AsyncSession, now: datetime) -> bool:
    """5.10-band: lid/statistika digesti (`GroupPostConfig`, `daily_digest.py`)
    davomat digesti bilan BIR XIL guruhlarga yuboriladi (`digest_group_targets`),
    lekin ikkalasi mutlaqo mustaqil jadvaldan ishlaydi. Vaqtlar yaqinlashsa
    (masalan rahbar davomat kechki vaqtini 19:10 ga o'zgartirsa) guruhga bir
    daqiqada ikkita uzun xabar tushib qolishi mumkin edi."""
    from db.models import GroupPostConfig

    cfg = await db.get(GroupPostConfig, 1)
    if cfg is None:
        return False
    return (now.hour, now.minute) == (cfg.post_hour, cfg.post_minute)


async def get_digest_config(db: AsyncSession) -> AttendanceDigestConfig:
    """Sozlama qatorini (id=1) oladi, bo'lmasa defaultlar bilan yaratadi."""
    cfg = await db.get(AttendanceDigestConfig, 1)
    if cfg is None:
        cfg = AttendanceDigestConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def digest_tick(db: AsyncSession) -> dict:
    """Cron har daqiqa chaqiradi. Sozlangan vaqt YETGAN yoki O'TGAN va bugun hali
    yuborilmagan bo'lsa — tegishli digestni yuboradi. `>=` semantikasi ataylab:
    cron aynan o'sha daqiqani o'tkazib yuborsa ham (restart, kechikish) keyingi
    tick'da baribir yuboriladi; `*_last_posted` bir kunda ikki marta yuborilishdan
    saqlaydi (lid digesti group-tick bilan bir xil naqsh)."""
    cfg = await get_digest_config(db)
    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    fired: list[dict] = []

    # 5.2/5.3-band: qo'riqchi (`*_last_posted`) ilgari faqat yuborish TUGAGANDAN
    # keyin yozilardi — yuborishning o'zi esa Telegram tarmoq chaqiruvi
    # (timeout=60s). Cron har daqiqa ishlaydi VA `scripts/cron_tick.py` bilan
    # `scheduler/main.py` ikkalasi ham shu funksiyani chaqiradi (5.3) — demak
    # ikkita chaqiruv bir vaqtda ishlab, ikkalasi ham eski qo'riqchini ko'rib,
    # digest bir kunda IKKI marta yuborilishi mumkin edi. Endi ATOMIK
    # UPDATE ... WHERE bilan avval "band qilinadi" — faqat BITTASI muvaffaqiyatli
    # bo'ladi (rowcount>0), yuborish shundan KEYIN boshlanadi.
    if cfg.absent_marked_date != today and (now.hour, now.minute) >= (cfg.evening_hour, cfg.evening_minute):
        absent_claim = await db.execute(
            update(AttendanceDigestConfig)
            .where(
                AttendanceDigestConfig.id == 1,
                or_(AttendanceDigestConfig.absent_marked_date.is_(None), AttendanceDigestConfig.absent_marked_date != today),
            )
            .values(absent_marked_date=today)
        )
        await db.commit()
        if absent_claim.rowcount:
            written = await write_absent_records(db, today)
            # 2.2-band (Savol C: FAQAT avtomatik) — kelib-u "Ketdim" bosmagan
            # o'tgan kunlar shu bir xil "kun tugadi" nuqtasida yopiladi.
            closed = await auto_close_unclosed_checkouts(db, today)
            # Tushuntirish xati — `write_absent_records` dan KEYIN, chunki u
            # `absent` yozuvlarini endi yaratdi. Bir xil atomik "band qilish"
            # ichida, ya'ni kuniga bir marta so'raladi.
            asked = await ask_explanations(db, today)
            if written:
                fired.append({"kind": "absent_marking", "written": written})
            if closed:
                fired.append({"kind": "auto_checkout_close", "closed": closed})
            if asked:
                fired.append({"kind": "explanation_asked", "asked": asked})

    for kind, enabled, hour, minute, last in (
        ("morning", cfg.morning_enabled, cfg.morning_hour, cfg.morning_minute, cfg.morning_last_posted),
        ("evening", cfg.evening_enabled, cfg.evening_hour, cfg.evening_minute, cfg.evening_last_posted),
    ):
        if not enabled or last == today:
            continue
        if (now.hour, now.minute) < (hour, minute):
            continue
        if await _lead_digest_fires_at(db, now):
            # 5.10-band: lid/statistika digesti (GroupPostConfig, odatda 19:10)
            # BIR XIL guruhlarga yuboriladi. Aynan shu daqiqaga to'g'ri kelsa,
            # guruhga bir vaqtda ikkita uzun xabar tushmasin uchun 1 daqiqaga
            # kechiktiramiz — `>=` semantikasi tufayli keyingi tick'da xavfsiz
            # yuboriladi (yo'qolib ketmaydi).
            continue

        field = f"{kind}_last_posted"
        claim = await db.execute(
            update(AttendanceDigestConfig)
            .where(
                AttendanceDigestConfig.id == 1,
                or_(getattr(AttendanceDigestConfig, field).is_(None), getattr(AttendanceDigestConfig, field) != today),
            )
            .values(**{field: today})
        )
        await db.commit()
        if claim.rowcount == 0:
            continue  # boshqa jarayon (yoki tick) allaqachon band qilgan/yuborgan

        result = await send_attendance_digest(db, kind=kind)
        # 3.3-band bilan bir xil sabab: HAQIQATAN yuborilmasa (masalan guruh
        # sozlanmagan) — bandni BEKOR qilamiz, keyingi tick qayta urinishi uchun.
        if not (result.get("sent") or result.get("final")):
            await db.execute(
                update(AttendanceDigestConfig).where(AttendanceDigestConfig.id == 1).values(**{field: last})
            )
            await db.commit()
        fired.append({"kind": kind, **result})

    if fired:
        return {"fired": True, "results": fired}
    return {
        "fired": False,
        "morning": f"{cfg.morning_hour:02d}:{cfg.morning_minute:02d}",
        "evening": f"{cfg.evening_hour:02d}:{cfg.evening_minute:02d}",
    }


async def send_attendance_digest(
    db: AsyncSession, kind: str, chat_id: int | None = None, dry_run: bool = False
) -> dict:
    """Davomat digestini guruh(lar)ga yuboradi. kind: 'morning' | 'evening'.
    Bugun hech kim ishlamasa (dam olish kuni) — yuborilmaydi."""
    if kind not in ("morning", "evening"):
        return {"sent": False, "reason": f"noma'lum digest turi: {kind}"}

    data = await collect_day(db)
    if not data["expected"]:
        # 3.3-band: bu TO'G'RI xatti-harakat (dam olish kuni) — qayta urinishning
        # hojati yo'q, shuning uchun "final" (bugun bo'yicha yakunlangan holat).
        return {"sent": False, "final": True, "reason": "bugun hech kim ishlamaydi (dam olish kuni)"}

    text = build_morning_text(data) if kind == "morning" else build_evening_text(data)
    if dry_run:
        return {"sent": False, "dry_run": True, "text": text}

    targets = await digest_group_targets(db, chat_id)
    if not targets:
        # 3.3-band: guruh hali sozlanmagan — bu VAQTINCHA holat, `final` EMAS.
        # `digest_tick` shuning uchun `*_last_posted`ni BELGILAMAYDI, guruh
        # sozlangach keyingi tick'da digest baribir yuboriladi. Ilgari har doim
        # belgilanardi — ya'ni sozlanmagan kunning digesti butunlay yo'qolardi.
        return {"sent": False, "reason": "guruh sozlanmagan (monitored_groups: main/stats)"}

    delivered = 0
    for cid in targets:
        if await send_message(cid, text):
            delivered += 1
    return {"sent": delivered > 0, "kind": kind, "chats": delivered, "text": text}
