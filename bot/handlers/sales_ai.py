"""Sotuvchi AI — bot rejimi.

«🤖 Sotuv AI» tugmasi (sotuv xodimlari + rop/boss/dasturchi) FSM rejimini ochadi:
foydalanuvchi mijoz savolini yozadi → AI tasdiqlangan bilim bazasi + playbook
asosida RASMIY javob variantini qaytaradi → rejim ochiq qoladi (yana savol
yozish mumkin), «❌ Bekor qilish» yoki istalgan menyu tugmasi chiqaradi.

Bu YORDAMCHI rejim: javobni xodimning o'zi mijozga yuboradi. AI javob topa
olmagan savollar bilim bazasiga «bilim bo'shlig'i» sifatida tushadi — Boss
to'ldirgach AI keyingi safar javob bera oladi."""
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_SALES_AI, cancel_menu, menu_for_user

logger = logging.getLogger(__name__)
router = Router(name="sales_ai")


class SalesAi(StatesGroup):
    asking = State()


@router.message(F.text == BTN_SALES_AI)
async def enter_mode(message: Message, state: FSMContext) -> None:
    await state.clear()
    data = await api_client.sales_ai_overview(message.from_user.id)
    if data is None:
        return  # ro'yxatdan o'tmagan
    if not data.get("ai_enabled"):
        await message.answer("⚠️ AI hozircha o'chiq — administratorga murojaat qiling.")
        return
    if not data.get("kb_verified"):
        await message.answer(
            "Bilim bazasida hali tasdiqlangan ma'lumot yo'q — avval rahbar «📚 Bilim "
            "bazasi» bo'limida anketa javoblarini tasdiqlashi kerak."
        )
        return
    await state.set_state(SalesAi.asking)
    await message.answer(
        "🤖 <b>Sotuv AI</b> — mijoz savolini yozing, men kompaniyaning tasdiqlangan "
        "ma'lumotlari asosida RASMIY javob variantini beraman.\n\n"
        f"(Bazada: {data['kb_verified']} ta tasdiqlangan javob, "
        f"{data['pb_verified']} ta playbook yozuvi)\n\n"
        "Javobni o'zingiz mijozga moslab yuborasiz. Chiqish — «❌ Bekor qilish».",
        reply_markup=cancel_menu(),
    )


@router.message(Command("sotuv_ai"))
async def enter_mode_cmd(message: Message, state: FSMContext) -> None:
    await enter_mode(message, state)


@router.message(SalesAi.asking, F.text)
async def on_question(message: Message, state: FSMContext) -> None:
    if message.text == BTN_CANCEL:
        await state.clear()
        user = await api_client.get_user_by_telegram(message.from_user.id)
        await message.answer("Sotuv AI rejimidan chiqildi.", reply_markup=menu_for_user(user))
        return

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:  # noqa: BLE001 — bezak, oqimni to'xtatmasin
        pass

    try:
        result = await api_client.sales_ai_ask(message.from_user.id, message.text)
    except httpx.HTTPError:
        logger.exception("Sotuv AI so'rovida xatolik")
        await message.answer(
            "⚠️ Javob olishda xatolik — birozdan keyin qayta urinib ko'ring.",
            reply_markup=cancel_menu(),
        )
        return

    reply = result.get("answer") or "⚠️ Javob olinmadi."
    if result.get("escalate"):
        reply += (
            "\n\n📌 <i>Bu savolga bazada aniq javob yo'q — savol rahbarga «bilim "
            "bo'shlig'i» sifatida yuborildi. Mijozga taxminiy ma'lumot bermang.</i>"
        )
    await message.answer(reply, reply_markup=cancel_menu())
