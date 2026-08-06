"""«🕐 Davomat statistikasi» — rahbarlar uchun kechikish statistikasi.

Tugma bosilganda shaxsiy chatда statistika chiqadi (default: oxirgi 7 kun);
inline tugmalar bilan davrni almashtirish (Bugun / 7 kun / 30 kun) va
«📤 Guruhga yuborish» — sozlangan umumiy guruhga xuddi shu matnni yuboradi.

Ma'lumot manbai: /attendance/late-stats-bot/{telegram_id} (yagona backend,
kunma-kun late_minutes)."""
import html

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot import group_registry
from bot.keyboards import BTN_ATTENDANCE_STATS

router = Router(name="attendance_stats")

PERIODS = [(0, "Bugun"), (7, "7 kun"), (30, "30 kun")]
VALID_DAYS = {d for d, _ in PERIODS}

# 4.3-band: Telegramning o'zi 4096 belgigacha xabarni qabul qiladi — 30 kunlik
# statistikada ko'p xodim kechiksa (har biri kunma-kun ro'yxati bilan) bu
# chegaradan oshib, xabar UMUMAN yuborilmay qolishi mumkin edi. Xavfsizlik
# marzhasi bilan 4000 belgida bo'lamiz.
TELEGRAM_MSG_LIMIT = 4000


def _split_for_telegram(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Matnni Telegram xabar chegarasidan oshib ketmaydigan bo'laklarga ajratadi —
    bitta xodim yozuvi o'rtasidan emas, QATOR chegarasidan bo'linadi."""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += add_len
    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


def _period_title(days: int) -> str:
    return "bugun" if days == 0 else f"oxirgi {days} kun"


def format_late_stats(rows: list[dict], days: int) -> str:
    """Statistika matni (HTML) — DM va guruh uchun bir xil ko'rinish."""
    title = f"🕐 <b>Kechikish statistikasi</b> ({_period_title(days)})"
    if not rows:
        return f"{title}\n\n✅ Hech kim kechikmagan."

    lines = [title, ""]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. <b>{html.escape(r['full_name'])}</b> — jami <b>{r['total_late_minutes']} daq</b>"
            f" ({r['late_days']} kun, o'rtacha {r['avg_late_minutes']}, eng ko'p {r['max_late_minutes']})"
        )
        # Kunma-kun: "16.07 +20 · 17.07 +15" (sana ISO: YYYY-MM-DD)
        day_bits = " · ".join(
            f"{d['date'][8:10]}.{d['date'][5:7]} +{d['late_minutes']}" for d in r["days"]
        )
        lines.append(f"    {day_bits}")
    lines.append("")
    lines.append(f"Jami kechikkanlar: {len(rows)} xodim")
    return "\n".join(lines)


async def _kb(days: int, *, status_view: bool = False) -> InlineKeyboardMarkup:
    period_row = [
        InlineKeyboardButton(
            text=("✅ " if d == days and not status_view else "") + label,
            callback_data=f"attstat:show:{d}",
        )
        for d, label in PERIODS
    ]
    rows = [period_row]
    # UX2-C5: «Bugungi holat» — kim keldi/kelmadi/kechikdi ISMLAR bilan;
    # ilgari bu ma'lumot botda umuman yo'q edi (faqat saytda).
    rows.append(
        [
            InlineKeyboardButton(
                text=("✅ " if status_view else "") + "👥 Bugungi holat",
                callback_data="attstat:status",
            ),
            # UX2-qoldiq #4/#5: xabari yo'qolgan kutilayotgan so'rovlar
            # (sababli kun + yuz qayta-ro'yxat) endi botdan topiladi.
            InlineKeyboardButton(text="📥 So'rovlar", callback_data="attstat:pending"),
        ]
    )
    if await group_registry.get_group_ids("main"):
        rows.append(
            [InlineKeyboardButton(text="📤 Guruhga yuborish", callback_data=f"attstat:send:{days}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_today_status(dash: dict) -> str:
    """«Bugungi holat» matni — web «Bugun» tabining bot ko'rinishi."""
    s = dash.get("summary", {})
    lines = [
        f"👥 <b>Bugungi davomat</b> ({dash.get('today', '')})",
        "",
        f"Keldi: <b>{s.get('checked_in_today', 0)}/{s.get('working_today', 0)}</b>"
        f" · Hozir ofisda: {s.get('present_now', 0)}"
        f" · Ketdi: {s.get('left_today', 0)}",
    ]
    not_come = dash.get("not_come", [])
    if not_come:
        lines.append("")
        lines.append(f"❌ <b>Kelmagan ({len(not_come)}):</b>")
        for p in not_come:
            lines.append(
                f"  • {html.escape(p['full_name'].strip())} (jadval {p.get('schedule_start', '—')})"
            )
    late_list = dash.get("late_list", [])
    if late_list:
        lines.append("")
        lines.append(f"⏱ <b>Kechikdi ({len(late_list)}):</b>")
        for p in late_list:
            lines.append(f"  • {html.escape(p['user_name'].strip())} +{p['late_minutes']} daq")
    excused = dash.get("excused_today", [])
    if excused:
        lines.append("")
        lines.append(
            "🌿 Sababli: " + ", ".join(html.escape(p["full_name"].strip()) for p in excused)
        )
    day_off = dash.get("on_day_off", [])
    if day_off:
        lines.append(
            "🌙 Dam olishda: " + ", ".join(html.escape(p["full_name"].strip()) for p in day_off)
        )
    if not not_come and not late_list:
        lines.append("")
        lines.append("✅ Hamma o'z vaqtida keldi!")
    return "\n".join(lines)


@router.message(F.text == BTN_ATTENDANCE_STATS)
async def show_attendance_stats(message: Message, state: FSMContext) -> None:
    await state.clear()  # boshqa menyu tugmalari kabi chala FSM oqimini tozalaydi
    days = 7
    # 4.3-band: backend xato qaytarsa (500, tarmoq uzilishi) ilgari bu yerda
    # ushlanmagan istisno ko'tarilib, xodim HECH QANDAY javob olmasdi.
    try:
        rows = await api_client.attendance_late_stats(message.from_user.id, days)
    except Exception:
        await message.answer("⚠️ Statistikani olishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
        return
    if rows is None:
        await message.answer("Bu bo'lim faqat rahbarlar (HR/ROP/Boshliq/Dasturchi) uchun.")
        return
    chunks = _split_for_telegram(format_late_stats(rows, days))
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        await message.answer(chunk, reply_markup=await _kb(days) if is_last else None)


@router.callback_query(F.data == "attstat:pending")
async def show_pending_requests(callback: CallbackQuery) -> None:
    """UX2-qoldiq #4/#5: kutilayotgan sababli kun + yuz qayta-ro'yxat
    so'rovlari — har biri o'zining MAVJUD qaror tugmalari bilan
    (excused_decide / face_rereg_decide callbacklarini excused.py allaqachon
    ushlaydi — yangi qaror mantig'i yozilmadi)."""
    try:
        excused = await api_client.pending_excused_bot(callback.from_user.id)
        rereg = await api_client.pending_face_rereg_bot(callback.from_user.id)
    except Exception:
        await callback.answer("So'rovlarni olishda xatolik yuz berdi.", show_alert=True)
        return
    # excused None — DECIDE_ROLES emas (masalan ROP); rereg esa MANAGER_ROLES.
    if excused is None and rereg is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return

    total = len(excused or []) + len(rereg or [])
    if total == 0:
        await callback.answer("Kutilayotgan so'rov yo'q ✅", show_alert=True)
        return

    await callback.answer(f"{total} ta so'rov — pastga yuborildi.")
    for item in excused or []:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Tasdiqlayman", callback_data=f"excused_decide:{item['id']}:approved"
                    ),
                    InlineKeyboardButton(
                        text="❌ Rad etaman", callback_data=f"excused_decide:{item['id']}:rejected"
                    ),
                ]
            ]
        )
        await callback.message.answer(
            "🙋 <b>Sababli kun so'rovi</b>\n"
            f"Xodim: {html.escape(item['user_full_name'].strip())}\n"
            f"Sana: {item['date']}\n"
            f"Sabab: {html.escape(item['reason'])}",
            reply_markup=kb,
        )
    for item in rereg or []:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Tasdiqlayman",
                        callback_data=f"face_rereg_decide:{item['id']}:approved",
                    ),
                    InlineKeyboardButton(
                        text="❌ Rad etaman",
                        callback_data=f"face_rereg_decide:{item['id']}:rejected",
                    ),
                ]
            ]
        )
        await callback.message.answer(
            "📸 <b>Yuzni qayta ro'yxatdan o'tkazish so'rovi</b>\n"
            f"Xodim: {html.escape(item['user_full_name'].strip())}",
            reply_markup=kb,
        )


@router.callback_query(F.data == "attstat:status")
async def show_today_status(callback: CallbackQuery) -> None:
    """UX2-C5: «Bugungi holat» — kim keldi/kelmadi/kechikdi (ismlar bilan)."""
    try:
        dash = await api_client.attendance_dashboard_bot(callback.from_user.id)
    except Exception:
        await callback.answer("Holatni olishda xatolik yuz berdi.", show_alert=True)
        return
    if dash is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return

    chunks = _split_for_telegram(format_today_status(dash))
    try:
        if len(chunks) == 1:
            await callback.message.edit_text(chunks[0], reply_markup=await _kb(7, status_view=True))
        else:
            await callback.message.edit_text(chunks[0])
    except Exception:
        pass  # "message is not modified" — e'tiborsiz
    for i, extra in enumerate(chunks[1:]):
        is_last = i == len(chunks) - 2
        await callback.message.answer(
            extra, reply_markup=await _kb(7, status_view=True) if is_last else None
        )
    await callback.answer()


@router.callback_query(F.data.startswith("attstat:show:"))
async def switch_period(callback: CallbackQuery) -> None:
    try:
        days = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return
    if days not in VALID_DAYS:
        await callback.answer()
        return

    try:
        rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    except Exception:
        # 4.3-band: bu yerda ushlanmasa callback.answer() hech qachon chaqirilmay,
        # tugma spinneri Telegram'da abadiy "yuklanmoqda" holida qolib ketardi.
        await callback.answer("Statistikani olishda xatolik yuz berdi.", show_alert=True)
        return
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return

    chunks = _split_for_telegram(format_late_stats(rows, days))
    try:
        if len(chunks) == 1:
            await callback.message.edit_text(chunks[0], reply_markup=await _kb(days))
        else:
            # Bir nechta xabarga bo'lingan — birinchisi tahrirlanadi, qolgani
            # yangi xabar sifatida yuboriladi (tugmalar OXIRGISIDA).
            await callback.message.edit_text(chunks[0])
    except Exception:
        # "message is not modified" (bir xil matn) — e'tiborsiz qoldiramiz
        pass
    for i, extra in enumerate(chunks[1:]):
        is_last = i == len(chunks) - 2
        await callback.message.answer(extra, reply_markup=await _kb(days) if is_last else None)
    await callback.answer()


@router.callback_query(F.data.startswith("attstat:send:"))
async def send_to_group(callback: CallbackQuery) -> None:
    try:
        days = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    try:
        rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    except Exception:
        await callback.answer("Statistikani olishda xatolik yuz berdi.", show_alert=True)
        return
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return
    main_chat_ids = await group_registry.get_group_ids("main")
    if not main_chat_ids:
        await callback.answer(
            "Guruh sozlanmagan — GURUH ICHIDA /guruh_biriktir main deb yozing.", show_alert=True
        )
        return

    chunks = _split_for_telegram(format_late_stats(rows, days))
    try:
        for chat_id in main_chat_ids:
            for chunk in chunks:
                await callback.bot.send_message(chat_id, chunk)
        await callback.answer("✅ Guruhga yuborildi.")
    except Exception:
        await callback.answer("Guruhga yuborib bo'lmadi — bot guruhda bormi?", show_alert=True)


# ── Digest vaqtini sozlash (/davomat_vaqt) ────────────────────────────────

USAGE = (
    "🕐 <b>Davomat digesti vaqti</b>\n\n"
    "Hozirgi: ertalabki <b>{morning}</b>{m_off}, kechki <b>{evening}</b>{e_off}\n\n"
    "O'zgartirish (faqat Boshliq):\n"
    "<code>/davomat_vaqt ertalab 09:30</code>\n"
    "<code>/davomat_vaqt kechqurun 22:00</code>\n"
    "O'chirish/yoqish:\n"
    "<code>/davomat_vaqt ertalab off</code> · <code>/davomat_vaqt kechqurun on</code>"
)

_KIND_WORDS = {
    "ertalab": "morning", "ertalabki": "morning", "morning": "morning",
    "kechqurun": "evening", "kechki": "evening", "kech": "evening", "evening": "evening",
}


def _fmt_cfg(cfg: dict) -> str:
    return USAGE.format(
        morning=cfg["morning"],
        evening=cfg["evening"],
        m_off="" if cfg.get("morning_enabled", True) else " (o'chiq)",
        e_off="" if cfg.get("evening_enabled", True) else " (o'chiq)",
    )


def _digest_time_kb() -> InlineKeyboardMarkup:
    """UX2-qoldiq #7: tez-tez ishlatiladigan vaqtlar tugma bilan — Boshliq
    endi buyruq sintaksisini yodlab yozishi shart emas (matnli yo'l ham
    ishlashda davom etadi)."""
    def row(kind: str, values: list[str]) -> list[InlineKeyboardButton]:
        return [
            InlineKeyboardButton(text=v, callback_data=f"digesttime:{kind}:{v}") for v in values
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="— Ertalabki —", callback_data="digesttime:noop:-")],
            row("morning", ["08:30", "09:00", "09:30", "10:00"]),
            row("morning", ["on", "off"]),
            [InlineKeyboardButton(text="— Kechki —", callback_data="digesttime:noop:-")],
            row("evening", ["21:00", "21:30", "22:00", "22:30"]),
            row("evening", ["on", "off"]),
        ]
    )


@router.message(Command("davomat_vaqt"))
async def cmd_davomat_vaqt(message: Message, command: CommandObject) -> None:
    """Davomat digesti vaqtini ko'rish/o'zgartirish. Argumentsiz — joriy holat."""
    # 4.3-band: backend bilan bog'liq HAMMA chaqiruv shu bir xil xavfga ega —
    # ushlanmagan istisno bo'lsa foydalanuvchi hech qanday javob olmasdi.
    try:
        cfg = await api_client.get_attendance_digest_time(message.from_user.id)
    except Exception:
        await message.reply("⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
        return
    if cfg is None:
        await message.reply("Bu buyruq faqat rahbarlar uchun.")
        return

    args = (command.args or "").split()
    if not args:
        await message.reply(_fmt_cfg(cfg), reply_markup=_digest_time_kb())
        return

    kind = _KIND_WORDS.get(args[0].lower())
    if kind is None or len(args) < 2:
        await message.reply("Format: <code>/davomat_vaqt ertalab 09:30</code>\n\n" + _fmt_cfg(cfg))
        return

    value = args[1].lower()
    try:
        if value in ("off", "o'chir", "ochir"):
            updated = await api_client.set_attendance_digest_time(message.from_user.id, kind, enabled=False)
        elif value in ("on", "yoq"):
            updated = await api_client.set_attendance_digest_time(message.from_user.id, kind, enabled=True)
        else:
            try:
                hh, mm = value.split(":")
                hour, minute = int(hh), int(mm)
            except ValueError:
                await message.reply("Vaqt formati: <code>09:30</code>")
                return
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                await message.reply("Vaqt noto'g'ri: soat 0-23, daqiqa 0-59.")
                return
            updated = await api_client.set_attendance_digest_time(
                message.from_user.id, kind, hour=hour, minute=minute
            )
    except Exception:
        await message.reply("⚠️ Saqlashda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
        return

    if updated is None:
        await message.reply("Vaqtni faqat Boshliq o'zgartira oladi.")
        return
    await message.reply("✅ Saqlandi.\n\n" + _fmt_cfg(updated))


@router.callback_query(F.data.startswith("digesttime:"))
async def digest_time_button(callback: CallbackQuery) -> None:
    """UX2-qoldiq #7: /davomat_vaqt inline tugmalari."""
    _, kind, value = callback.data.split(":", 2)
    if kind == "noop":
        await callback.answer()
        return

    try:
        if value in ("on", "off"):
            updated = await api_client.set_attendance_digest_time(
                callback.from_user.id, kind, enabled=(value == "on")
            )
        else:
            hh, mm = value.split(":")
            updated = await api_client.set_attendance_digest_time(
                callback.from_user.id, kind, hour=int(hh), minute=int(mm)
            )
    except Exception:
        await callback.answer("Saqlashda xatolik yuz berdi.", show_alert=True)
        return

    if updated is None:
        await callback.answer("Vaqtni faqat Boshliq o'zgartira oladi.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            "✅ Saqlandi.\n\n" + _fmt_cfg(updated), reply_markup=_digest_time_kb()
        )
    except Exception:
        pass  # "message is not modified"
    await callback.answer("Saqlandi.")
