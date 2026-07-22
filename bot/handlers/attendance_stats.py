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


async def _kb(days: int) -> InlineKeyboardMarkup:
    period_row = [
        InlineKeyboardButton(
            text=("✅ " if d == days else "") + label, callback_data=f"attstat:show:{d}"
        )
        for d, label in PERIODS
    ]
    rows = [period_row]
    if await group_registry.get_group_ids("main"):
        rows.append(
            [InlineKeyboardButton(text="📤 Guruhga yuborish", callback_data=f"attstat:send:{days}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_ATTENDANCE_STATS)
async def show_attendance_stats(message: Message, state: FSMContext) -> None:
    await state.clear()  # boshqa menyu tugmalari kabi chala FSM oqimini tozalaydi
    days = 7
    rows = await api_client.attendance_late_stats(message.from_user.id, days)
    if rows is None:
        await message.answer("Bu bo'lim faqat rahbarlar (HR/ROP/Boshliq) uchun.")
        return
    await message.answer(format_late_stats(rows, days), reply_markup=await _kb(days))


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

    rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return
    try:
        await callback.message.edit_text(format_late_stats(rows, days), reply_markup=await _kb(days))
    except Exception:
        # "message is not modified" (bir xil matn) — e'tiborsiz qoldiramiz
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("attstat:send:"))
async def send_to_group(callback: CallbackQuery) -> None:
    try:
        days = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return
    main_chat_ids = await group_registry.get_group_ids("main")
    if not main_chat_ids:
        await callback.answer("Guruh sozlanmagan (/guruh_biriktir main).", show_alert=True)
        return

    try:
        for chat_id in main_chat_ids:
            await callback.bot.send_message(chat_id, format_late_stats(rows, days))
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


@router.message(Command("davomat_vaqt"))
async def cmd_davomat_vaqt(message: Message, command: CommandObject) -> None:
    """Davomat digesti vaqtini ko'rish/o'zgartirish. Argumentsiz — joriy holat."""
    cfg = await api_client.get_attendance_digest_time(message.from_user.id)
    if cfg is None:
        await message.reply("Bu buyruq faqat rahbarlar uchun.")
        return

    args = (command.args or "").split()
    if not args:
        await message.reply(_fmt_cfg(cfg))
        return

    kind = _KIND_WORDS.get(args[0].lower())
    if kind is None or len(args) < 2:
        await message.reply("Format: <code>/davomat_vaqt ertalab 09:30</code>\n\n" + _fmt_cfg(cfg))
        return

    value = args[1].lower()
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

    if updated is None:
        await message.reply("Vaqtni faqat Boshliq o'zgartira oladi.")
        return
    await message.reply("✅ Saqlandi.\n\n" + _fmt_cfg(updated))
