"""Sotuv AI markazi — yagona dashboard (Anketa/Bilim bazasi/Playbook/Sotuv AI).

Ilgari bu to'rt bo'lim alohida-alohida joyda yashardi (ba'zisi asosiy
reply-klaviaturada, Playbook esa Bilim bazasi ichiga ko'milgan) — endi
hammasi «🧠 Sotuv AI markazi» tugmasidan boshlanadi va holat + ANIQ keyingi
qadam (tavsiya) bitta ekranda ko'rinadi. Har bo'limning o'z ichki ekranidagi
"⬅️" (bo'lim darajasida, ichki bosqichlarda emas) endi shu dashboardga
qaytadi — bot/handlers/anketa.py, knowledge.py, playbook.py'dagi tegishli
tugmalarga qarang."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_AI_CENTER

logger = logging.getLogger(__name__)
router = Router(name="ai_center")


def _anketa_line(a: dict) -> str:
    if not a.get("exists"):
        return "2️⃣ Anketa: hali boshlanmagan"
    label = {
        "scheduled": "🗓 rejalashtirilgan",
        "in_progress": "⏳ davom etmoqda",
        "done": "✅ yakunlangan",
        "cancelled": "🚫 bekor qilingan",
    }.get(a["status"], a["status"])
    return f"2️⃣ Anketa: {label} — {a['done']}/{a['total']} xodim javob berdi"


def _knowledge_line(kb: dict) -> str:
    c = kb["counts"]
    parts = [f"{c.get('verified', 0)} tasdiqlangan", f"{kb['review_pending']} kutmoqda"]
    if c.get("unknown"):
        parts.append(f"{c['unknown']} bo'shliq")
    if c.get("draft"):
        parts.append(f"{c['draft']} AI ishlovida")
    return "3️⃣ Bilim bazasi: " + ", ".join(parts)


def _playbook_line(pb: dict) -> str:
    if pb.get("building"):
        return f"4️⃣ Sotuv playbook: ⏳ qurilmoqda ({pb['building']['label']})"
    c = pb["counts"]
    if not c:
        return "4️⃣ Sotuv playbook: hali qurilmagan"
    return f"4️⃣ Sotuv playbook: {c.get('verified', 0)} tasdiqlangan, {c.get('unverified', 0)} kutmoqda"


def _dashboard_view(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        "🧠 <b>Sotuv AI markazi</b>",
        "",
        f"1️⃣ Savol to'plamlari: {data['templates']} ta yuklangan",
        _anketa_line(data["anketa"]),
        _knowledge_line(data["knowledge"]),
        _playbook_line(data["playbook"]),
    ]
    if not data.get("ai_enabled"):
        lines.append("\n⚠️ AI o'chiq (.env: AI_ENABLED) — ba'zi bosqichlar ishlamaydi.")
    lines.append(f"\n💡 <b>Tavsiya:</b> {data['recommendation']}")

    rows = [
        [
            InlineKeyboardButton(text="1️⃣ Savol to'plamlari", callback_data="anketa:tpls"),
            InlineKeyboardButton(text="2️⃣ Anketa", callback_data="anketa:back"),
        ],
        [
            InlineKeyboardButton(text="3️⃣ Bilim bazasi", callback_data="kb:menu"),
            InlineKeyboardButton(text="4️⃣ Sotuv playbook", callback_data="pb:menu"),
        ],
        [InlineKeyboardButton(text="🤖 Sotuv AI'ni sinash", callback_data="aic:sales_ai")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_dashboard(telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    data = await api_client.ai_center_overview(telegram_id)
    if data is None:
        return None
    return _dashboard_view(data)


@router.message(F.text == BTN_AI_CENTER)
async def on_menu_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    view = await _show_dashboard(message.from_user.id)
    if view is None:
        await message.answer("Bu bo'lim faqat Boshliq/Dasturchi uchun.")
        return
    text, markup = view
    await message.answer(text, reply_markup=markup)


@router.message(Command("ai_markazi"))
async def on_command(message: Message, state: FSMContext) -> None:
    await on_menu_button(message, state)


@router.callback_query(F.data == "aic:menu")
async def on_back_to_dashboard(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    view = await _show_dashboard(callback.from_user.id)
    if view is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = view
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "aic:sales_ai")
async def on_sales_ai_shortcut(callback: CallbackQuery, state: FSMContext) -> None:
    """Dashboarddan «🤖 Sotuv AI'ni sinash» — sales_ai.py'dagi bir xil FSM
    rejimini ochadi (callback orqali, matn-tugma bosilgandek)."""
    from bot.handlers.sales_ai import enter_mode_from_chat

    await enter_mode_from_chat(callback.message, callback.from_user.id, state)
    await callback.answer()
