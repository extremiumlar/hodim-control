"""«HR ga savol» — botda (yangi TZ 3.29 / S-28).

Ikki oqim bitta tugma ostida:
  • XODIM «❓ HR ga savol» → savolni yozadi → HR ga xabar ketadi;
    o'sha yerda o'z murojaatlari tarixi ham ko'rinadi.
  • HR o'ziga kelgan xabardagi «✍️ Javob berish» tugmasini bosadi →
    javobni yozadi → javob xodimga qaytadi.

⚠️ HR ham xodim: unda ham «HR ga savol» tugmasi bor (o'z oyligi
bo'yicha savoli bo'lishi mumkin). Shuning uchun javob berish AYRIM
tugma emas, murojaatga BOG'LANGAN inline tugma — aks holda HR ning
o'z savoli bilan javobi bir-biriga aralashardi.

⚠️ FSM bazada saqlanadi (`DbFsmStorage`) — cPanel webhook rejimida
jarayon har so'rovda yangidan ko'tariladi va xotiradagi holat yo'qolardi.
"""
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import ALL_MENU_BUTTONS, BTN_CANCEL, BTN_HR_ASK, cancel_menu, menu_for_user

router = Router(name="hr_inquiries")
logger = logging.getLogger(__name__)

#  Tarixda nechta murojaat ko'rsatiladi. Telegram xabari 4096 belgi —
#  uzun tarix xabarni umuman yubormaslikka olib keladi.
_HISTORY = 5


class AskFSM(StatesGroup):
    waiting_question = State()
    waiting_answer = State()


def _holat_belgisi(item: dict) -> str:
    return {"open": "🕓", "answered": "✅", "closed": "⚪"}.get(item.get("status"), "•")


def _tarix(items: list[dict]) -> list[str]:
    if not items:
        return []
    lines = ["", "<b>Oldingi murojaatlaringiz:</b>"]
    for it in items[:_HISTORY]:
        savol = (it.get("question") or "")[:80]
        lines.append(f"{_holat_belgisi(it)} {savol}")
        if it.get("answer"):
            lines.append(f"   ↳ <i>{it['answer'][:150]}</i>")
    return lines


@router.message(F.text == BTN_HR_ASK)
async def start_ask(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        oldingilar = await api_client.my_inquiries(message.from_user.id)
    except Exception:  # noqa: BLE001 — tarix ko'rsatilmasa ham savol berish ishlashi kerak
        logger.exception("Murojaatlar tarixini olishda xato")
        oldingilar = []

    lines = [
        "❓ <b>HR ga savol</b>",
        "",
        "Savolingizni yozing — HR ga yetkazamiz va javobi shu yerga keladi.",
    ]
    lines += _tarix(oldingilar)
    await state.set_state(AskFSM.waiting_question)
    await message.answer("\n".join(lines), reply_markup=cancel_menu())


@router.message(StateFilter(AskFSM.waiting_question), F.text == BTN_CANCEL)
async def cancel_ask(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(
    StateFilter(AskFSM.waiting_question), F.text, ~F.text.in_(ALL_MENU_BUTTONS)
)
async def receive_question(message: Message, state: FSMContext) -> None:
    matn = (message.text or "").strip()
    if len(matn) < 5:
        #  FSM buzilmaydi — qayta yozish mumkin.
        await message.answer("Savol juda qisqa — to'liqroq yozing.")
        return

    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        res = await api_client.ask_hr(message.from_user.id, matn)
    except Exception:  # noqa: BLE001
        logger.exception("Murojaat yuborishda xato")
        await state.clear()
        await message.answer(
            "Yuborib bo'lmadi — keyinroq urinib ko'ring.", reply_markup=menu_for_user(user)
        )
        return

    await state.clear()
    xabar = (
        "✅ Savolingiz HR ga yuborildi.\n"
        f"Toifa: <b>{res.get('category_label', '—')}</b>\n\n"
        "Javob kelishi bilan shu yerda xabar beramiz."
    )
    if not res.get("notified"):
        #  HR ham, Boshliq ham topilmadi — savol saqlandi, lekin hech
        #  kimga xabar ketmadi. Buni YASHIRMAYMIZ: xodim javob kutib
        #  o'tirgandan ko'ra bilgani yaxshi.
        xabar += "\n\n⚠️ Hozir HR xodimi tizimda ko'rinmadi — javob kechikishi mumkin."
    await message.answer(xabar, reply_markup=menu_for_user(user))


@router.message(StateFilter(AskFSM.waiting_question))
async def wrong_question(message: Message) -> None:
    """Matn kutilyapti, boshqa narsa keldi (rasm, stiker) — FSM ni
    buzmasdan eslatamiz."""
    await message.answer("Savolni matn ko'rinishida yozing (yoki «❌ Bekor qilish»).")


# ─────────────────────────────────────────────────────────────
# HR: javob berish
# ─────────────────────────────────────────────────────────────


def answer_button(inquiry_id: int) -> InlineKeyboardMarkup:
    """HR ga keladigan xabardagi «Javob berish» tugmasi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Javob berish", callback_data=f"hrq:ans:{inquiry_id}"
                )
            ]
        ]
    )


@router.callback_query(F.data.startswith("hrq:ans:"))
async def start_answer(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        inquiry_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user = await api_client.get_user_by_telegram(callback.from_user.id)
    if not user or user.get("role") not in {"hr", "boss", "dasturchi"}:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.set_state(AskFSM.waiting_answer)
    await state.update_data(inquiry_id=inquiry_id)
    await callback.message.answer(
        "Javobingizni yozing — xodimga o'sha zahoti yetadi.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(AskFSM.waiting_answer), F.text == BTN_CANCEL)
async def cancel_answer(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(StateFilter(AskFSM.waiting_answer), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def receive_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    inquiry_id = data.get("inquiry_id")
    if not inquiry_id:
        await state.clear()
        return
    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        res = await api_client.answer_inquiry(
            message.from_user.id, int(inquiry_id), (message.text or "").strip()
        )
    except Exception:  # noqa: BLE001
        logger.exception("Javob yuborishda xato")
        await state.clear()
        await message.answer(
            "Javobni saqlab bo'lmadi — keyinroq urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    await state.clear()
    xabar = "✅ Javob yuborildi."
    if not res.get("delivered"):
        xabar += "\n⚠️ Xodimga xabar yetkazilmadi, lekin javob jurnalda saqlandi."
    await message.answer(xabar, reply_markup=menu_for_user(user))


@router.message(StateFilter(AskFSM.waiting_answer))
async def wrong_answer(message: Message) -> None:
    await message.answer("Javobni matn ko'rinishida yozing (yoki «❌ Bekor qilish»).")
