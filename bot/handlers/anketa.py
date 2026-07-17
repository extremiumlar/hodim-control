"""Bilim bazasi anketasi — bot tomonlari.

Ikki router:
- `router` — Dasturchi boshqaruvi: «📝 Anketa» tugmasi / /anketa buyrug'i,
  holat ko'rinishi, «hozir boshlash» yoki kun/vaqt kiritish (FSM) + tasdiqlash,
  bekor qilish, javoblarni .txt fayl qilib yuklab olish.
- `answer_router` — xodim javoblarini ushlovchi matn handleri. Dispatcher'da
  ai_watch.reason_text_router'dan OLDIN ulanadi: API'da faol savol kutilmayotgan
  bo'lsa ({"handled": false}) SkipHandler bilan xabar keyingi (AI sabab)
  handlerga o'tadi — mavjud oqimlar buzilmaydi.

Boshlanish vaqti kelganda savollarni API o'zi yuboradi (/anketa/tick — cron yoki
scheduler), shuning uchun bot bu yerda faqat boshqaruv va javob qabul qiladi."""
import html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import api_client
from bot.keyboards import BTN_ANKETA, BTN_CANCEL, cancel_menu, menu_for_user

logger = logging.getLogger(__name__)
router = Router(name="anketa")
answer_router = Router(name="anketa_answers")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

_STATUS_LABELS = {
    "scheduled": "🗓 rejalashtirilgan",
    "in_progress": "⏳ davom etmoqda",
    "done": "✅ yakunlangan",
    "cancelled": "🚫 bekor qilingan",
}
_ASSIGN_EMOJI = {"pending": "🕓", "in_progress": "⏳", "done": "✅", "stopped": "⏹"}


class AnketaSchedule(StatesGroup):
    waiting_datetime = State()


def _overview_text(data: dict) -> str:
    lines = ["📝 <b>Bilim bazasi anketasi</b>", ""]
    if data.get("targets_error"):
        lines.append(f"⚠️ Standart taqsimot xatosi: {html.escape(data['targets_error'])}")
    else:
        lines.append("<b>Standart taqsimot</b> (boshlashda boshqa guruhni ham tanlash mumkin):")
        for t in data.get("targets", []):
            warn = "" if t.get("bot_started") else " ⚠️ botga /start bosmagan"
            lines.append(f"• {html.escape(t['full_name'])} — To'plam №{t['toplam']}{warn}")

    session = data.get("session")
    if session:
        lines.append("")
        lines.append(
            f"<b>Oxirgi sessiya:</b> {_STATUS_LABELS.get(session['status'], session['status'])}"
        )
        if session.get("scheduled_at_local"):
            lines.append(f"Boshlanish vaqti: {session['scheduled_at_local']} (Toshkent)")
        for a in session.get("assignments", []):
            emoji = _ASSIGN_EMOJI.get(a["status"], "•")
            lines.append(
                f"{emoji} {html.escape(a['full_name'])} (№{a['toplam']}): {a['answered']}/{a['total']} javob"
            )
    else:
        lines.append("")
        lines.append("Hali sessiya boshlanmagan.")
    return "\n".join(lines)


def _overview_keyboard(data: dict) -> InlineKeyboardMarkup:
    session = data.get("session")
    active = session and session["status"] in {"scheduled", "in_progress"}
    rows: list[list[InlineKeyboardButton]] = []
    if active:
        if session["status"] == "in_progress":
            # Yakunlash — javoblar saqlanadi (to'ldirmaganlarni kutmasdan yopish);
            # bekor qilish — javoblar ham o'chadi (sinovni tozalash uchun)
            rows.append([
                InlineKeyboardButton(
                    text="🏁 Yakunlash (javoblar saqlanadi)", callback_data="anketa:finish"
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text="❌ Bekor qilish (javoblar o'chadi)", callback_data="anketa:cancel"
            )
        ])
    else:
        # Standart taqsimot xato bo'lsa ham boshqa guruhlar (all/lavozim/rol)
        # bilan boshlash mumkin — tugmalar har doim chiqadi
        rows.append([
            InlineKeyboardButton(text="▶️ Hozir boshlash", callback_data="anketa:now"),
            InlineKeyboardButton(text="🗓 Kun/vaqt belgilash", callback_data="anketa:settime"),
        ])
    if session:
        rows.append([InlineKeyboardButton(text="📥 Javoblar (.txt)", callback_data="anketa:results")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_overview(message: Message, telegram_id: int) -> None:
    data = await api_client.anketa_overview(telegram_id)
    if data is None:
        await message.answer("Bu bo'lim faqat Dasturchi uchun.")
        return
    await message.answer(_overview_text(data), reply_markup=_overview_keyboard(data))


@router.message(F.text == BTN_ANKETA)
async def anketa_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_overview(message, message.from_user.id)


@router.message(Command("anketa"))
async def anketa_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_overview(message, message.from_user.id)


# Qatnashchi tanlash spetsifikatsiyasi (callback'da yuriydi, ichida ':' yo'q):
# std | all | role_boss | role_rop | role_hr | role_employee | pos_<id>
def _parse_spec(spec: str) -> dict:
    if spec == "std":
        return {"target_type": "standart", "position_id": None, "role": None}
    if spec == "all":
        return {"target_type": "all", "position_id": None, "role": None}
    if spec.startswith("role_"):
        return {"target_type": "role", "position_id": None, "role": spec[len("role_"):]}
    if spec.startswith("pos_"):
        return {"target_type": "position", "position_id": int(spec[len("pos_"):]), "role": None}
    return {"target_type": "standart", "position_id": None, "role": None}


async def _targets_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Qatnashchilar tanlovi — vazifa berishdagi kabi: hamma / rol / lavozim.
    mode: now | time (keyingi qadamni belgilaydi)."""
    rows = [
        [InlineKeyboardButton(text="🎯 Standart (5 sotuvchi)", callback_data=f"anketa:tg:{mode}:std")],
        [InlineKeyboardButton(text="👥 Barcha xodimlar", callback_data=f"anketa:tg:{mode}:all")],
        [
            InlineKeyboardButton(text="👑 Boshliq", callback_data=f"anketa:tg:{mode}:role_boss"),
            InlineKeyboardButton(text="🧭 ROPlar", callback_data=f"anketa:tg:{mode}:role_rop"),
            InlineKeyboardButton(text="🗂 HRlar", callback_data=f"anketa:tg:{mode}:role_hr"),
        ],
    ]
    try:
        positions = await api_client.list_positions()
    except Exception:  # noqa: BLE001 — lavozimlar kelmasa ham asosiy tanlovlar qolsin
        positions = []
    pos_buttons = [
        InlineKeyboardButton(text=f"Lavozim: {p['name']}", callback_data=f"anketa:tg:{mode}:pos_{p['id']}")
        for p in positions
    ]
    for i in range(0, len(pos_buttons), 2):
        rows.append(pos_buttons[i : i + 2])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "anketa:now")
async def on_start_now(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "▶️ Anketa KIMLARGA yuborilsin? Guruhni tanlang:",
        reply_markup=await _targets_keyboard("now"),
    )
    await callback.answer()


@router.callback_query(F.data == "anketa:settime")
async def on_set_time(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🗓 Avval anketa KIMLARGA yuborilishini tanlang:",
        reply_markup=await _targets_keyboard("time"),
    )
    await callback.answer()


def _preview_text(targets: list[dict]) -> str:
    lines = [f"Qatnashchilar ({len(targets)} kishi):"]
    for t in targets:
        warn = "" if t.get("bot_started") else " ⚠️ botga /start bosmagan"
        lines.append(f"• {html.escape(t['full_name'])} — To'plam №{t['toplam']}{warn}")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("anketa:tg:"))
async def on_target_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, mode, spec = callback.data.split(":", 3)
    try:
        preview = await api_client.anketa_preview_targets(callback.from_user.id, **_parse_spec(spec))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    targets = preview.get("targets", [])

    if mode == "now":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha, hozir boshlansin", callback_data=f"anketa:confirm:{spec}:now"),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back"),
            ]]
        )
        await callback.message.edit_text(
            f"▶️ Anketa HOZIR boshlansinmi?\n\n{_preview_text(targets)}\n\n"
            "Har biriga o'z to'plamining birinchi savoli darhol yuboriladi.",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    # mode == "time": spec'ni FSM'da saqlab, sana-vaqt so'raymiz
    await state.set_state(AnketaSchedule.waiting_datetime)
    await state.update_data(target_spec=spec)
    await callback.message.edit_text(_preview_text(targets))
    await callback.message.answer(
        "🗓 Boshlanish kun va vaqtini yozing (Toshkent vaqti).\n\n"
        "Qabul qilinadigan ko'rinishlar:\n"
        "• <code>15:30</code> — bugun\n"
        "• <code>bugun 15:30</code> / <code>ertaga 09:00</code>\n"
        "• <code>17.07.2026 09:00</code>",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


def _parse_local_datetime(raw: str) -> datetime | None:
    """Foydalanuvchi kiritgan matnni Toshkent vaqtidagi datetime'ga o'giradi.
    Tushunarsiz format — None (bot qayta so'raydi)."""
    text = " ".join(raw.strip().lower().split())
    now = datetime.now(TASHKENT_TZ).replace(tzinfo=None)

    day_offset = 0
    if text.startswith("bugun"):
        text = text[len("bugun"):].strip()
    elif text.startswith("ertaga"):
        day_offset = 1
        text = text[len("ertaga"):].strip()

    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        t = datetime.strptime(text, "%H:%M")
    except ValueError:
        return None
    base = now.date() + timedelta(days=day_offset)
    return datetime.combine(base, t.time())


@router.message(AnketaSchedule.waiting_datetime, F.text)
async def on_datetime_input(message: Message, state: FSMContext) -> None:
    if message.text == BTN_CANCEL:
        await state.clear()
        user = await api_client.get_user_by_telegram(message.from_user.id)
        await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
        return

    parsed = _parse_local_datetime(message.text)
    if parsed is None:
        await message.answer(
            "Tushunarsiz format. Masalan: <code>ertaga 09:00</code> yoki <code>17.07.2026 09:00</code>"
        )
        return
    now_local = datetime.now(TASHKENT_TZ).replace(tzinfo=None)
    if parsed <= now_local:
        await message.answer("Bu vaqt o'tib bo'lgan — kelajakdagi vaqtni kiriting.")
        return

    data = await state.get_data()
    spec = data.get("target_spec", "std")
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    iso = parsed.strftime("%Y-%m-%dT%H:%M")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlayman", callback_data=f"anketa:confirm:{spec}:{iso}"),
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back"),
        ]]
    )
    await message.answer(
        f"🗓 Anketa <b>{parsed.strftime('%d.%m.%Y %H:%M')}</b> (Toshkent) da boshlansinmi?\n"
        "Tasdiqlansa, vaqt kelganda bot xodimlarga savollarni o'zi yuboradi.",
        reply_markup=keyboard,
    )
    await message.answer("Asosiy menyu:", reply_markup=menu_for_user(user))


@router.callback_query(F.data.startswith("anketa:confirm:"))
async def on_confirm(callback: CallbackQuery) -> None:
    # Format: anketa:confirm:<spec>:<now|YYYY-MM-DDTHH:MM> (spec ichida ':' yo'q).
    # Eski xabarlardagi tugmalar (spec'siz format: "now" yoki iso) ham ishlaydi.
    rest = callback.data.split(":", 2)[2]
    if ":" in rest and not rest[0].isdigit() and rest != "now":
        spec, value = rest.split(":", 1)
    else:
        spec, value = "std", rest
    scheduled_at = None if value == "now" else value
    try:
        result = await api_client.anketa_schedule(
            callback.from_user.id, scheduled_at, **_parse_spec(spec)
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise

    session = result.get("session") or {}
    if session.get("status") == "in_progress":
        text = "🚀 Anketa boshlandi — xodimlarga birinchi savollar yuborildi."
    else:
        text = (
            f"✅ Tasdiqlandi. Anketa <b>{session.get('scheduled_at_local')}</b> (Toshkent) da "
            "avtomatik boshlanadi."
        )
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()


@router.callback_query(F.data == "anketa:finish")
async def on_finish_session(callback: CallbackQuery) -> None:
    try:
        result = await api_client.anketa_finish(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text(
        f"🏁 Sessiya yakunlandi: {result['done']} xodim to'liq tugatgan, "
        f"{result['stopped']} xodimniki to'xtatildi (yozgan javoblari saqlandi).\n\n"
        "Endi «📚 Bilim bazasi» → «🔄 Anketadan yuklash» bilan javoblarni bazaga "
        "olishingiz mumkin.",
        reply_markup=None,
    )
    await callback.answer("Yakunlandi")


@router.callback_query(F.data == "anketa:cancel")
async def on_cancel_session(callback: CallbackQuery) -> None:
    try:
        await api_client.anketa_cancel(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text("🚫 Sessiya bekor qilindi.", reply_markup=None)
    await callback.answer("Bekor qilindi")


@router.callback_query(F.data == "anketa:back")
async def on_back(callback: CallbackQuery) -> None:
    data = await api_client.anketa_overview(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    await callback.message.edit_text(_overview_text(data), reply_markup=_overview_keyboard(data))
    await callback.answer()


@router.callback_query(F.data == "anketa:results")
async def on_results(callback: CallbackQuery) -> None:
    try:
        data = await api_client.anketa_results(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await callback.answer("Hali sessiya yo'q", show_alert=True)
            return
        raise
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    session = data.get("session") or {}
    lines = [
        "NURLI DIYOR — BILIM BAZASI ANKETASI (javoblar)",
        f"Sessiya #{session.get('id')} · holat: {session.get('status')}",
        f"Boshlangan: {session.get('started_at_local') or '-'} · Yakunlangan: {session.get('finished_at_local') or '-'}",
        "=" * 60,
    ]
    for u in data.get("users", []):
        lines.append("")
        lines.append(f"XODIM: {u['full_name']} — To'plam №{u['toplam']} ({u['status']})")
        lines.append("-" * 60)
        if not u["answers"]:
            lines.append("(hali javob yo'q)")
        for ans in u["answers"]:
            lines.append(f"{ans['n']}. {ans['question']}")
            lines.append(f"JAVOB ({ans['answered_at_local']}): {ans['answer']}")
            lines.append("")
    content = "\n".join(lines).encode("utf-8")
    filename = f"anketa_javoblar_sessiya_{session.get('id', 0)}.txt"
    await callback.message.answer_document(BufferedInputFile(content, filename=filename))
    await callback.answer()


@answer_router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/"),
    StateFilter(None),
)
async def on_possible_answer(message: Message) -> None:
    """Menyu/FSM/buyruqlardan o'tgan oddiy matn — faol anketa savoli kutilayotgan
    xodimniki bo'lishi mumkin. API tekshiradi: kutilmayotgan bo'lsa SkipHandler —
    xabar keyingi handlerga (AI sabab oqimi) o'tadi."""
    try:
        result = await api_client.anketa_answer(message.from_user.id, message.text)
    except httpx.HTTPError:
        # Anketa oqimini aniqlab bo'lmadi — xabarni boshqa oqimlarga o'tkazamiz,
        # aks holda API qisqa uzilishida xodim javoblari ham, AI sabablari ham yo'qoladi.
        logger.exception("Anketa javobini tekshirishda xatolik")
        raise SkipHandler

    if not result.get("handled"):
        raise SkipHandler

    for text in result.get("messages", []):
        await message.answer(text)
