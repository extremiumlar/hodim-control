"""Texnika xavfsizligi instruktaji — xodim tomoni, bot (TZ 3.6 / S-48).

⚠️ BU QOG'OZ JURNAL O'RNINI BOSMAYDI. Xodimga ham shu ochiq
aytiladi: tugma bosilishi qo'l qo'yish o'rniga o'tmaydi. Aks holda
xodim «men botda bosdim-ku» deb jurnalga imzo qo'ymay ketardi va
tekshiruvda kompaniya javobgar bo'lardi.

⚠️ MATERIAL O'QUV PANELIDAN keladi (3.1) — bu yerda alohida fayl
mexanizmi YO'Q. Kursi bor instruktaj uchun xodim «📚 Darsliklarim»
ga yo'naltiriladi.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_BRIEFINGS

router = Router(name="briefings")
logger = logging.getLogger(__name__)

_MAX_TUGMA = 8


def _matn(bandlar: list) -> str:
    kutayotgan = [b for b in bandlar if not b["acknowledged"]]
    q = ["🦺 <b>Texnika xavfsizligi instruktajlari</b>", ""]
    for b in bandlar[:20]:
        belgi = "✅" if b["acknowledged"] else "⏳"
        q.append(f"{belgi} {b['kind_label']} — {b['title']} ({b['held_on']})")
    if kutayotgan:
        q.append("\n⬇️ Tanishmagan instruktajingiz bor.")
    q.append(
        "\n⚠️ <i>Bu qayd QOG'OZ JURNAL o'rnini bosmaydi — jurnalga "
        "imzo qo'yish baribir shart.</i>"
    )
    return "\n".join(q)[:3500]


def _klaviatura(bandlar: list) -> InlineKeyboardMarkup | None:
    qatorlar = [
        [InlineKeyboardButton(text=f"✅ {b['title'][:40]}",
                              callback_data=f"brf:ack:{b['id']}")]
        for b in bandlar if not b["acknowledged"]
    ][:_MAX_TUGMA]
    return InlineKeyboardMarkup(inline_keyboard=qatorlar) if qatorlar else None


@router.message(F.text == BTN_BRIEFINGS)
async def my_briefings(message: Message) -> None:
    try:
        bandlar = await api_client.my_briefings(message.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Instruktajlarni olishda xato")
        await message.answer("Hozir ochib bo'lmadi — keyinroq urinib ko'ring.")
        return
    if not bandlar:
        await message.answer("🦺 Sizga instruktaj tayinlanmagan.")
        return
    await message.answer(_matn(bandlar), reply_markup=_klaviatura(bandlar))


@router.callback_query(F.data.startswith("brf:ack:"))
async def acknowledge(callback: CallbackQuery) -> None:
    briefing_id = int(callback.data.split(":")[2])
    try:
        await api_client.briefing_ack(callback.from_user.id, briefing_id)
        bandlar = await api_client.my_briefings(callback.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Instruktaj tanishuvini qayd etishda xato")
        await callback.answer("Qayd etib bo'lmadi", show_alert=True)
        return
    await callback.answer("✅ Tanishdingiz")
    try:
        await callback.message.edit_text(_matn(bandlar),
                                         reply_markup=_klaviatura(bandlar))
    except Exception:  # noqa: BLE001
        logger.debug("Ro'yxatni yangilab bo'lmadi", exc_info=True)
