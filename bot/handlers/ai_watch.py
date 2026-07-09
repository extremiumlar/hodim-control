"""Operator AI bot tomonlari: sabab so'rovi tugmalari (4-bosqich) va rahbar
boshqaruvi /ai_sozlama + /ai_vaqt (6-bosqich).

Sabab oqimi: API (ai-watch/tick) orqada qolgan operatorga nudge + sabab
tugmalarini yuboradi; operator tugmani bosganda sabab API'ga yoziladi, tugmalar
olib tashlanadi va tasdiq ko'rsatiladi. Yorliq matnlari API'da (bitta manba).

Boshqaruv: rahbar AI qismlarini (nudge/kun yakuni/haftalik) yoqib-o'chiradi va
xulosa vaqtini o'zgartiradi — odam-qaror tamoyili."""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client

logger = logging.getLogger(__name__)
router = Router()

_TOGGLE_LABELS = {
    "nudges_enabled": "🔔 Soatlik nudge",
    "group_summary_enabled": "📊 Kun yakuni (guruh)",
    "weekly_enabled": "📈 Haftalik xulosa",
}


def _config_view(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    master = "yoqiq ✅" if cfg.get("ai_enabled") and cfg.get("push_enabled") else "O'CHIQ ❌ (.env: AI_ENABLED/AI_NUDGE_ENABLED)"
    lines = [
        "🤖 <b>Operator AI sozlamalari</b>",
        f"Bosh kalit (server): {master}",
        f"Provayder: {cfg.get('provider')}",
        f"Kun yakuni vaqti: {cfg.get('summary_hour', 0):02d}:{cfg.get('summary_minute', 0):02d}"
        " (o'zgartirish: /ai_vaqt 19:30)",
        "",
        "Qismlarni tugma bilan yoqing/o'chiring:",
    ]
    rows = [
        [InlineKeyboardButton(
            text=f"{label}: {'✅' if cfg.get(field) else '❌'}",
            callback_data=f"aicfg:{field}",
        )]
        for field, label in _TOGGLE_LABELS.items()
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("ai_sozlama"))
async def cmd_ai_config(message: Message) -> None:
    cfg = await api_client.get_ai_config(message.from_user.id)
    if cfg is None:
        await message.reply("Bu buyruq faqat rahbarlar uchun.")
        return
    text, markup = _config_view(cfg)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("aicfg:"))
async def on_toggle(callback: CallbackQuery) -> None:
    field = callback.data.split(":", 1)[1]
    if field not in _TOGGLE_LABELS:
        await callback.answer("Noma'lum sozlama")
        return
    cfg = await api_client.get_ai_config(callback.from_user.id)
    if cfg is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    updated = await api_client.set_ai_config(callback.from_user.id, **{field: not cfg.get(field)})
    if updated is None:
        await callback.answer("O'zgartirish faqat Boshliq uchun", show_alert=True)
        return
    text, markup = _config_view(updated)
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 — matn o'zgarmagan bo'lsa ham toast beramiz
        logger.debug("Sozlama xabarini tahrirlab bo'lmadi", exc_info=True)
    state = "yoqildi ✅" if updated.get(field) else "o'chirildi ❌"
    await callback.answer(f"{_TOGGLE_LABELS[field]} {state}")


@router.message(Command("ai_vaqt"))
async def cmd_ai_time(message: Message, command: CommandObject) -> None:
    """Kun yakuni xulosasi vaqtini o'zgartirish: /ai_vaqt 19:30 (faqat Boshliq)."""
    if not command.args:
        cfg = await api_client.get_ai_config(message.from_user.id)
        if cfg is None:
            await message.reply("Bu buyruq faqat rahbarlar uchun.")
            return
        await message.reply(
            f"Kun yakuni vaqti: {cfg['summary_hour']:02d}:{cfg['summary_minute']:02d}\n"
            "O'zgartirish: /ai_vaqt 19:30"
        )
        return
    try:
        hour_s, minute_s = command.args.strip().split(":")
        hour, minute = int(hour_s), int(minute_s)
    except ValueError:
        await message.reply("Format noto'g'ri. Masalan: /ai_vaqt 19:30")
        return
    updated = await api_client.set_ai_config(message.from_user.id, summary_hour=hour, summary_minute=minute)
    if updated is None:
        await message.reply("Vaqtni faqat Boshliq o'zgartira oladi.")
        return
    await message.reply(f"✅ Kun yakuni vaqti: {updated['summary_hour']:02d}:{updated['summary_minute']:02d}")


@router.callback_query(F.data.startswith("sfr:"))
async def on_shortfall_reason(callback: CallbackQuery) -> None:
    # callback_data: "sfr:<YYYY-MM-DD>:<soat>:<kod>"
    try:
        _, day, hour_s, code = callback.data.split(":", 3)
        hour = int(hour_s)
    except ValueError:
        await callback.answer("Xato ma'lumot", show_alert=False)
        return

    try:
        result = await api_client.post_shortfall_reason(callback.from_user.id, day, hour, code)
    except Exception:  # noqa: BLE001 — API xatosida operatorni jim qoldirmaymiz
        logger.exception("Sababni saqlashda xatolik")
        await callback.answer("Saqlashda xatolik — birozdan keyin urinib ko'ring", show_alert=True)
        return

    label = result.get("label", "")
    # Tugmalarni olib tashlaymiz (qayta-qayta bosilmasin) va tasdiqni matn ostiga qo'shamiz
    try:
        if callback.message:
            await callback.message.edit_text(
                f"{callback.message.html_text}\n\n✅ Sabab qayd etildi: <b>{label}</b>",
                reply_markup=None,
            )
    except Exception:  # noqa: BLE001 — edit ishlamasa (eski xabar) toast yetadi
        logger.debug("Nudge xabarini tahrirlab bo'lmadi", exc_info=True)
    await callback.answer("Qayd etildi")
