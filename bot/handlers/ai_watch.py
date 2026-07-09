"""Operator AI sabab so'rovi tugmalari (4-bosqich).

API (ai-watch/tick) orqada qolgan operatorga nudge + sabab tugmalarini yuboradi;
operator tugmani bosganda callback shu yerga keladi: sabab API'ga yoziladi,
tugmalar olib tashlanadi va tasdiq ko'rsatiladi. Yorliq matnlari API'da
(bitta manba) — bot faqat kodni uzatadi."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import api_client

logger = logging.getLogger(__name__)
router = Router()


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
