from datetime import date, timedelta

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_EXCUSED, BTN_MARK_EXCUSED, cancel_menu, menu_for_user

router = Router(name="excused")

# decide_excused_day bilan bir xil qamrov — ROP bu yerda ham yo'q (faqat
# hr/boss/dasturchi xodim nomidan sababli kun belgilay oladi).
MARK_EXCUSED_ROLES = {"hr", "boss", "dasturchi"}


class ExcusedDayFSM(StatesGroup):
    waiting_for_date = State()
    waiting_for_reason = State()


class MarkExcusedFSM(StatesGroup):
    choosing_employee = State()
    choosing_date = State()
    entering_reason = State()


class ExplanationFSM(StatesGroup):
    """Tushuntirish xati — xodim sababsiz kelmagan kun uchun izoh yozadi."""

    waiting_text = State()


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
@router.message(StateFilter(MarkExcusedFSM.choosing_employee), F.text == BTN_CANCEL)
@router.message(StateFilter(MarkExcusedFSM.choosing_date), F.text == BTN_CANCEL)
@router.message(StateFilter(MarkExcusedFSM.entering_reason), F.text == BTN_CANCEL)
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


def _mark_excused_date_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Bugun", callback_data="mark_excused_date:today"),
                InlineKeyboardButton(text="Ertaga", callback_data="mark_excused_date:tomorrow"),
            ]
        ]
    )


@router.message(F.text == BTN_MARK_EXCUSED)
async def start_mark_excused(message: Message, state: FSMContext) -> None:
    # Menyu tugmasi keyboards.py'da hr/boss/dasturchi'ga ko'rinadi, lekin
    # eski klaviatura keshi qolgan bo'lishi mumkin — norms.py'dagi
    # BTN_CHANGE_NORM bilan bir xil ikkinchi tekshiruv.
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MARK_EXCUSED_ROLES:
        await message.answer("Bu buyruq faqat HR/Boshliq/Dasturchi uchun mavjud.")
        return

    employees = await api_client.excused_day_targets(message.from_user.id)
    if not employees:
        await message.answer("Faol xodimlar topilmadi.")
        return

    names_by_id = {str(emp["id"]): emp["full_name"] for emp in employees}
    await state.update_data(names_by_id=names_by_id)

    buttons = [
        [InlineKeyboardButton(text=emp["full_name"], callback_data=f"markexcusedtarget:{emp['id']}")]
        for emp in employees
    ]
    await state.set_state(MarkExcusedFSM.choosing_employee)
    await message.answer(
        "Kim uchun sababli kun belgilaymiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(StateFilter(MarkExcusedFSM.choosing_employee), F.data.startswith("markexcusedtarget:"))
async def choose_mark_excused_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = callback.data.split(":")[1]
    data = await state.get_data()
    name = (data.get("names_by_id") or {}).get(target_id, "?")

    await state.update_data(target_user_id=int(target_id))
    await state.set_state(MarkExcusedFSM.choosing_date)
    await callback.message.edit_text(f"Tanlandi: {name}.")
    await callback.message.answer(
        "Qaysi sana uchun? Tugmalardan tanlang yoki aniq sanani "
        "<code>YYYY-MM-DD</code> ko'rinishida yozing.",
        reply_markup=_mark_excused_date_kb(),
    )
    await callback.answer()


@router.callback_query(StateFilter(MarkExcusedFSM.choosing_date), F.data.startswith("mark_excused_date:"))
async def pick_mark_excused_date(callback: CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.split(":", 1)[1]
    day = date.today() if choice == "today" else date.today() + timedelta(days=1)
    await state.update_data(excused_date=day.isoformat())
    await state.set_state(MarkExcusedFSM.entering_reason)
    await callback.message.edit_text(f"Tanlandi: {day.isoformat()}.")
    await callback.message.answer("Endi sababni yozib yuboring:", reply_markup=cancel_menu())
    await callback.answer()


@router.message(StateFilter(MarkExcusedFSM.choosing_date))
async def receive_mark_excused_date_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        day = date.fromisoformat(text)
    except ValueError:
        await message.answer(
            "Sana formati noto'g'ri. <code>YYYY-MM-DD</code> ko'rinishida yozing "
            "yoki yuqoridagi tugmalardan tanlang.",
            reply_markup=_mark_excused_date_kb(),
        )
        return
    await state.update_data(excused_date=day.isoformat())
    await state.set_state(MarkExcusedFSM.entering_reason)
    await message.answer("Endi sababni yozib yuboring:", reply_markup=cancel_menu())


@router.message(StateFilter(MarkExcusedFSM.entering_reason), F.text)
async def receive_mark_excused_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    excused_date = data.get("excused_date")
    name = (data.get("names_by_id") or {}).get(str(target_user_id), "?")
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        await api_client.record_excused_day_for_user(
            message.from_user.id, target_user_id, reason, date_str=excused_date
        )
    except httpx.HTTPStatusError as exc:
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
        f"✅ {name} uchun {excused_date or 'bugungi kun'} sababli kun sifatida belgilandi.",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(MarkExcusedFSM.entering_reason))
async def non_text_mark_excused_reason(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


@router.callback_query(F.data.startswith("explain:"))
async def start_explanation(callback: CallbackQuery, state: FSMContext) -> None:
    """«✍️ Tushuntirish yozish» tugmasi — kechqurungi job yuborgan xabarda."""
    req_id = int(callback.data.split(":")[1])
    await state.clear()
    await state.set_state(ExplanationFSM.waiting_text)
    await state.update_data(explanation_id=req_id)
    await callback.message.answer(
        "Sababingizni yozib yuboring (kamida 3 belgi). HR ko'rib chiqadi.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(ExplanationFSM.waiting_text), F.text == BTN_CANCEL)
async def cancel_explanation(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer(
        "Bekor qilindi. Tushuntirishni keyinroq ham yozishingiz mumkin — "
        "yuqoridagi xabardagi tugmani qayta bosing.",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(ExplanationFSM.waiting_text), F.text)
async def receive_explanation(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    req_id = data.get("explanation_id")
    if not req_id:
        await state.clear()
        await message.answer("Sessiya topilmadi. Xabardagi tugmani qayta bosing.")
        return
    if len(text) < 3:
        # Holat SAQLANADI — xodim qayta yozsin (matn juda qisqa).
        await message.answer("Juda qisqa — sababni to'liqroq yozing.", reply_markup=cancel_menu())
        return

    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        await api_client.answer_explanation(req_id, message.from_user.id, text)
    except httpx.HTTPStatusError as exc:
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
        "✅ Tushuntirishingiz HR'ga yuborildi. Qaror chiqqach shu yerda xabar beramiz.",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(ExplanationFSM.waiting_text))
async def non_text_explanation(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


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
