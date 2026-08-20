"""Avans kuni oqimi — tugmalar va summa kiritish (Avans TZ C-01…C-03).

Ikki router:
- `router` — callback tugmalari (`adv:need:…` / `adv:no:…`). Ular boshqa
  hech narsaga xalaqit bermaydi, shuning uchun oddiy tartibda ulanadi.
- `amount_router` — «erkin matn» ushlagichi. Dispatcher'da
  `anketa.answer_router` dan OLDIN ulanadi va API'da summa
  kutilmayotgan bo'lsa `SkipHandler` bilan xabarni keyingi handlerga
  o'tkazadi.

  ⚠️ TARTIB NOZIK (anketa modulida uchragan tuzoq): agar bu handler
  `SkipHandler` qilmasa, u anketa javoblarini va AI sabab matnlarini
  YUTIB YUBORARDI. Shuning uchun qaror API tomonda qabul qilinadi va
  bot faqat `handled` bayrog'iga qaraydi.

BUTUN MANTIQ API DA (`api/services/advance_bot.py`) — chegara, tekshiruv
va yozuv. Bu yerda faqat uzatish va ko'rsatish.
"""
import logging

import httpx
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from bot import api_client

logger = logging.getLogger(__name__)

router = Router(name="advance")
amount_router = Router(name="advance_amount")


@router.callback_query(F.data.startswith("adv:"))
async def on_advance_button(callback: CallbackQuery) -> None:
    """«Summa kiritish» / «Kerak emas».

    `callback_data` — `adv:<amal>:<davr>`. Davr SHART: o'tgan oyning
    xabari bosilsa API «bu xabar eskirgan» deb javob beradi va jimgina
    joriy oyga yozib qo'ymaydi."""
    await callback.answer()
    qismlar = (callback.data or "").split(":")
    if len(qismlar) != 3:
        await callback.message.answer("Tugma ma'lumoti tushunarsiz.")
        return
    _, action, period = qismlar

    try:
        res = await api_client.advance_bot_callback(callback.from_user.id, action, period)
    except httpx.HTTPError:
        logger.exception("Avans tugmasini qayta ishlashda xatolik")
        await callback.message.answer(
            "Hozir javob bera olmadim — birozdan keyin qayta urinib ko'ring."
        )
        return

    if res.get("clear_keyboard"):
        # Tugmalarni olib tashlaymiz — bir marta bosilgan tanlov
        # ikkinchi marta bosilmasin.
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 — xabar eski bo'lsa Telegram rad etadi
            pass
    if res.get("text"):
        await callback.message.answer(res["text"])


@amount_router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/"),
    StateFilter(None),
)
async def on_possible_amount(message: Message) -> None:
    """Menyu/FSM/buyruqlardan o'tgan oddiy matn — avans summasi bo'lishi
    mumkin. API tekshiradi: kutilmayotgan bo'lsa `SkipHandler` — xabar
    keyingi handlerga (anketa javobi, AI sabab) o'tadi."""
    try:
        res = await api_client.advance_bot_text(message.from_user.id, message.text)
    except httpx.HTTPError:
        # Avans oqimini aniqlab bo'lmadi — xabarni boshqa oqimlarga
        # o'tkazamiz, aks holda API qisqa uzilishida anketa javoblari
        # ham, AI sabablari ham yo'qolardi.
        logger.exception("Avans summasini tekshirishda xatolik")
        raise SkipHandler

    if not res.get("handled"):
        raise SkipHandler

    if res.get("text"):
        await message.answer(res["text"])
