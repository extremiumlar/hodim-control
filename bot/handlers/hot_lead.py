"""Issiq lid (speed-to-lead) bot tomoni: operator "✅ Qabul qildim" tugmasini
bosganda qabul vaqti API'ga yoziladi va xabar tasdiq bilan yangilanadi. Lid
ma'lumoti va tugma API tomonidan yuboriladi (hot_lead servisi) — bu yerda faqat
callback ushlanadi."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import api_client

logger = logging.getLogger(__name__)
router = Router()


def _fmt_reaction(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} soniya"
    return f"{seconds // 60} daqiqa"


@router.callback_query(F.data.startswith("hl:"))
async def on_claim(callback: CallbackQuery) -> None:
    # callback_data: "hl:<hot_lead_id>"
    try:
        hot_lead_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Xato ma'lumot")
        return

    try:
        result = await api_client.claim_hot_lead(callback.from_user.id, hot_lead_id)
    except Exception:  # noqa: BLE001 — API xatosida operatorni jim qoldirmaymiz
        logger.exception("Issiq lidni qabul qilishda xatolik")
        await callback.answer("Saqlashda xatolik — birozdan keyin urinib ko'ring", show_alert=True)
        return

    if result is None:
        await callback.answer("Bu lid boshqa operatorga tayinlangan", show_alert=True)
        return

    # Tugmani olib tashlab, tasdiqni xabar ostiga qo'shamiz
    try:
        if callback.message:
            await callback.message.edit_text(
                f"{callback.message.html_text}\n\n✅ Qabul qilindi ({_fmt_reaction(result.get('reaction_sec', 0))}da)",
                reply_markup=None,
            )
    except Exception:  # noqa: BLE001 — edit ishlamasa (eski xabar) toast yetadi
        logger.debug("Issiq lid xabarini tahrirlab bo'lmadi", exc_info=True)
    await callback.answer("Qabul qilindi — omad! 🚀")
