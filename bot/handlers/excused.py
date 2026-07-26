from datetime import date, timedelta

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_EXCUSED, cancel_menu, menu_for_user

router = Router(name="excused")


class ExcusedDayFSM(StatesGroup):
    waiting_for_date = State()
    waiting_for_reason = State()


def _date_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Bugun", callback_data="excused_date:today"),
                InlineKeyboardButton(text="Ertaga", callback_data="excused_date:tomorrow"),
            ]
        ]
    )


@router.message(F.text == BTN_EXCUSED)
async def start_excused_request(message: Message, state: FSMContext) -> None:
    # 5.6-band: ilgari faqat "bugun" uchun so'rov yuborish mumkin edi — xodim
    # shifokorga ertaga borishini oldindan bilsa ham, aynan o'sha kuni ertalab
    # (yoki undan keyin) so'rashga majbur edi. Endi bugun/ertaga/aniq sana.
    await state.set_state(ExcusedDayFSM.waiting_for_date)
    await message.answer(
        "Sababli kun QAYSI SANA uchun? Tugmalardan tanlang yoki aniq sanani "
        "<code>YYYY-MM-DD</code> ko'rinishida yozib yuboring (masalan 2026-08-01).",
        reply_markup=_date_kb(),
    )


@router.message(StateFilter(ExcusedDayFSM.waiting_for_date), F.text == BTN_CANCEL)
@router.message(StateFilter(ExcusedDayFSM.waiting_for_reason), F.text == BTN_CANCEL)
async def cancel_excused_request(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.callback_query(StateFilter(ExcusedDayFSM.waiting_for_date), F.data.startswith("excused_date:"))
async def pick_excused_date(callback: CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.split(":", 1)[1]
    day = date.today() if choice == "today" else date.today() + timedelta(days=1)
    await state.update_data(excused_date=day.isoformat())
    await state.set_state(ExcusedDayFSM.waiting_for_reason)
    await callback.message.edit_text(f"Tanlandi: {day.isoformat()}.")
    await callback.message.answer(
        "Endi sababni yozib yuboring (masalan: kasallik, oilaviy holat).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(ExcusedDayFSM.waiting_for_date))
async def receive_excused_date_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        day = date.fromisoformat(text)
    except ValueError:
        await message.answer(
            "Sana formati noto'g'ri. <code>YYYY-MM-DD</code> ko'rinishida yozing "
            "(masalan 2026-08-01) yoki yuqoridagi tugmalardan tanlang.",
            reply_markup=_date_kb(),
        )
        return
    await state.update_data(excused_date=day.isoformat())
    await state.set_state(ExcusedDayFSM.waiting_for_reason)
    await message.answer(
        "Endi sababni yozib yuboring (masalan: kasallik, oilaviy holat).",
        reply_markup=cancel_menu(),
    )


@router.message(StateFilter(ExcusedDayFSM.waiting_for_reason))
async def receive_excused_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    data = await state.get_data()
    excused_date = data.get("excused_date")
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        await api_client.create_excused_day(message.from_user.id, reason, date_str=excused_date)
    except httpx.HTTPStatusError as exc:
        # 5.7-band: backend endi dublikat (bir kunga ikkinchi PENDING/APPROVED
        # so'rov) va boshqa xatolarni 400 bilan rad etadi — bu yerda ushlanmasa
        # xodim hech qanday javob olmay qolardi (4.3-band bilan bir xil xavf).
        detail = "Xatolik yuz berdi."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        await message.answer(f"⚠️ {detail}", reply_markup=menu_for_user(user))
        return
    except Exception:
        await message.answer(
            "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    await message.answer(
        "So'rovingiz HR'ga yuborildi, javobini shu yerda kutib turing.",
        reply_markup=menu_for_user(user),
    )


@router.callback_query(F.data.startswith("excused_decide:"))
async def on_excused_decide(callback: CallbackQuery) -> None:
    _, item_id_str, decision = callback.data.split(":")
    try:
        item = await api_client.decide_excused_day(int(item_id_str), callback.from_user.id, decision)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            await callback.answer("Bu amal uchun ruxsatingiz yo'q.", show_alert=True)
        elif exc.response.status_code == 400:
            await callback.answer("Bu so'rov allaqachon hal qilingan.", show_alert=True)
        else:
            await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return

    verdict = "✅ tasdiqlandi" if item["status"] == "approved" else "❌ rad etildi"
    await callback.message.edit_text(
        f"{item['user_full_name']} — {item['date']} sababli kuni {verdict}."
    )
    await callback.answer("Qaror saqlandi.")


@router.callback_query(F.data.startswith("face_rereg_decide:"))
async def on_face_rereg_decide(callback: CallbackQuery) -> None:
    """Savol A (yumshoq choralar): xodim yuzini QAYTA ro'yxatdan o'tkazishga
    HR/rahbarning tasdig'i — excused_decide bilan bir xil naqsh."""
    _, item_id_str, decision = callback.data.split(":")
    try:
        item = await api_client.decide_face_rereg(int(item_id_str), callback.from_user.id, decision)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            await callback.answer("Bu amal uchun ruxsatingiz yo'q.", show_alert=True)
        elif exc.response.status_code == 400:
            await callback.answer("Bu so'rov allaqachon hal qilingan.", show_alert=True)
        else:
            await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return

    verdict = "✅ tasdiqlandi" if item["status"] == "approved" else "❌ rad etildi"
    await callback.message.edit_text(
        f"{item['user_full_name']} — yuzni qayta ro'yxatdan o'tkazish {verdict}."
    )
    await callback.answer("Qaror saqlandi.")
