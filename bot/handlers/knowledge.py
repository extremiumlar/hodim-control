"""Sotuv bilim bazasi — bot boshqaruvi (faqat Boshliq/Dasturchi).

«📚 Bilim bazasi» tugmasi: holat + 4 amal:
- 🔄 Anketadan yuklash — yakunlangan anketa javoblaridan draft'lar (AI ishlovi
  keyingi daqiqalarda cron'da bo'lib-bo'lib boradi, tayyor bo'lgach xabar keladi);
- 🔍 Ko'rib chiqish — unverified/conflict/unknown yozuvlarni birma-bir:
  ✅ tasdiqlash / ✏️ javobni yozib tasdiqlash / 📅 sana-sezgirlikni almashtirish /
  ❌ o'chirish / ⏭ o'tkazib yuborish;
- ➕ Ma'lumot qo'shish — qo'lda rasmiy fakt (FSM: savol → javob → sana-sezgir →
  kategoriya), darhol verified;
- 📥 Baza (.txt) — barcha yozuvlar fayl ko'rinishida."""
import html
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command
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
from bot.keyboards import BTN_CANCEL, BTN_KNOWLEDGE, cancel_menu, menu_for_user

logger = logging.getLogger(__name__)
router = Router(name="knowledge")

_STATUS_BADGE = {
    "unverified": "🕓 tasdiq kutmoqda",
    "unknown": "❓ bilim bo'shlig'i (javob yo'q)",
    "conflict": "⚠️ ziddiyatli javoblar",
    "verified": "✅ tasdiqlangan",
    "draft": "⏳ AI ishlovida",
}

# Qo'lda qo'shishda tanlanadigan kategoriyalar (API svc.CATEGORIES bilan mos)
_ADD_CATEGORIES = [
    ("narx", "Narx va to'lov"),
    ("qurilish", "Qurilish"),
    ("xonadon", "Xonadon/ta'mir"),
    ("topshirish", "Topshirish/muddat"),
    ("kompaniya", "Kompaniya"),
    ("hudud", "Hudud"),
    ("jarayon", "Jarayon/aloqa"),
    ("etiroz", "E'tirozlar"),
    ("umumiy", "Boshqa"),
]


class KbEdit(StatesGroup):
    waiting_answer = State()


class KbAdd(StatesGroup):
    waiting_question = State()
    waiting_answer = State()


async def _overview_view(telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    data = await api_client.knowledge_overview(telegram_id)
    if data is None:
        return None
    counts = data.get("counts", {})
    lines = ["📚 <b>Sotuv bilim bazasi</b>", ""]
    lines.append(f"✅ Tasdiqlangan: {counts.get('verified', 0)}")
    lines.append(f"🕓 Tasdiq kutmoqda: {counts.get('unverified', 0)}")
    lines.append(f"❓ Bilim bo'shlig'i: {counts.get('unknown', 0)}")
    lines.append(f"⚠️ Ziddiyat: {counts.get('conflict', 0)}")
    if counts.get("draft"):
        lines.append(f"⏳ AI ishlovida: {counts['draft']} (har daqiqada bo'lib-bo'lib ishlanadi)")
    if data.get("needs_recheck"):
        lines.append(f"⏰ Eskirgan (tekshirish kerak): {data['needs_recheck']}")
    if not data.get("ai_enabled"):
        lines.append("\n⚠️ AI o'chiq (.env: AI_ENABLED) — yuklashda javoblar xom holda tushadi.")

    rows = [
        [InlineKeyboardButton(text="🔄 Anketadan yuklash", callback_data="kb:ingest")],
        [
            InlineKeyboardButton(
                text=f"🔍 Ko'rib chiqish ({data.get('review_pending', 0)})",
                callback_data="kb:review:0",
            )
        ],
        [
            InlineKeyboardButton(text="➕ Ma'lumot qo'shish", callback_data="kb:add"),
            InlineKeyboardButton(text="📥 Baza (.txt)", callback_data="kb:export"),
        ],
        [
            InlineKeyboardButton(text="🧭 Sotuv playbook", callback_data="pb:menu"),
            InlineKeyboardButton(text="📦 Dataset (.json)", callback_data="kb:dataset"),
        ],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_KNOWLEDGE)
async def kb_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    view = await _overview_view(message.from_user.id)
    if view is None:
        await message.answer("Bu bo'lim faqat Boshliq/Dasturchi uchun.")
        return
    text, markup = view
    await message.answer(text, reply_markup=markup)


@router.message(Command("bilim"))
async def kb_command(message: Message, state: FSMContext) -> None:
    await kb_menu(message, state)


@router.callback_query(F.data == "kb:menu")
async def on_kb_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    view = await _overview_view(callback.from_user.id)
    if view is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = view
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "kb:ingest")
async def on_ingest(callback: CallbackQuery) -> None:
    try:
        result = await api_client.knowledge_ingest(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text(
        f"🔄 {result['created']} ta javob yuklandi va AI ishloviga qo'yildi.\n"
        "Har daqiqada bo'lib-bo'lib ishlanadi (bir necha daqiqa) — tayyor bo'lgach "
        "sizga xabar keladi, keyin «🔍 Ko'rib chiqish» bilan tasdiqlaysiz.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu")]]
        ),
    )
    await callback.answer()


def _entry_card(entry: dict, remaining: int, processing: int) -> tuple[str, InlineKeyboardMarkup]:
    badge = _STATUS_BADGE.get(entry["status"], entry["status"])
    date_flag = "✅" if entry["date_sensitive"] else "❌"
    lines = [
        f"🔍 <b>Ko'rib chiqish</b> — qolgan: {remaining}"
        + (f" (+{processing} AI ishlovida)" if processing else ""),
        "",
        f"Holat: {badge} · Kategoriya: {entry['category']}",
        f"Manba: {html.escape(entry.get('source') or '-')}",
        f"📅 Sana-sezgir (narx/muddat): {date_flag}",
        "",
        f"<b>Savol:</b> {html.escape(entry['question'])}",
        "<b>Javob:</b> " + (html.escape(entry["answer"]) if entry["answer"] else "<i>(bo'sh)</i>"),
    ]
    if entry.get("review_note"):
        lines.append(f"\n💬 AI izohi: {html.escape(entry['review_note'])}")

    eid = entry["id"]
    rows = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"kb:ok:{eid}"),
            InlineKeyboardButton(text="✏️ Javob yozish", callback_data=f"kb:edit:{eid}"),
        ],
        [
            InlineKeyboardButton(text="📅 Sana-sezgir", callback_data=f"kb:date:{eid}"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"kb:del:{eid}"),
        ],
        [
            InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"kb:review:{eid}"),
            InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu"),
        ],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _source_name(source: str) -> str:
    """"Anketa №1, savol 2: Kamola" → "Kamola" (ko'rsatish uchun)."""
    return (source or "").rsplit(": ", 1)[-1].strip() or "?"


def _conflict_card(
    entry: dict, group: list[dict], remaining: int, processing: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Ziddiyatli savol kartasi: barcha xodimlar javoblari yonma-yon, rahbar
    birini qabul qiladi yoki birini tahrirlab o'tkazadi (qolganlari o'chadi)."""
    lines = [
        f"🔍 <b>Ko'rib chiqish</b> — qolgan: {remaining}"
        + (f" (+{processing} AI ishlovida)" if processing else ""),
        "",
        "⚠️ <b>Ziddiyatli javoblar</b> — bitta savolga xodimlar har xil javob bergan.",
        f"\n<b>Savol:</b> {html.escape(entry['question'])}",
    ]
    for i, m in enumerate(group, start=1):
        lines.append(
            f"\n<b>{i}) {html.escape(_source_name(m.get('source')))}:</b> "
            f"{html.escape(m['answer']) if m['answer'] else '<i>(bo`sh)</i>'}"
        )
    if entry.get("review_note"):
        lines.append(f"\n💬 AI izohi: {html.escape(entry['review_note'])}")
    lines.append("\nBirini qabul qiling yoki tahrirlab o'tkazing — qolganlari o'chiriladi.")

    rows = [
        [
            InlineKeyboardButton(text=f"✅ {i}-javobni qabul qilish", callback_data=f"kb:ok:{m['id']}"),
            InlineKeyboardButton(text=f"✏️ {i}-ni tahrirlash", callback_data=f"kb:edit:{m['id']}"),
        ]
        for i, m in enumerate(group, start=1)
    ]
    max_id = max(m["id"] for m in group)
    rows.append([
        InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"kb:review:{max_id}"),
        InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _review_view(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    """review-next javobidan karta quradi (oddiy / ziddiyatli guruh / tugadi)."""
    entry = data.get("entry")
    if entry is None:
        extra = (
            f"\n⏳ {data['processing']} ta yozuv hali AI ishlovida — birozdan keyin qaytib ko'ring."
            if data.get("processing")
            else ""
        )
        return (
            f"✅ Ko'rib chiqiladigan yozuv qolmadi.{extra}",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu")]]
            ),
        )
    group = data.get("conflict_group")
    if group and len(group) > 1:
        return _conflict_card(entry, group, data["remaining"], data.get("processing", 0))
    return _entry_card(entry, data["remaining"], data.get("processing", 0))


async def _show_next(callback: CallbackQuery, after_id: int) -> None:
    data = await api_client.knowledge_review_next(callback.from_user.id, after_id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = _review_view(data)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("kb:review:"))
async def on_review(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    after_id = int(callback.data.rsplit(":", 1)[1])
    await _show_next(callback, after_id)


async def _decide_and_next(callback: CallbackQuery, entry_id: int, action: str) -> None:
    try:
        await api_client.knowledge_decide(callback.from_user.id, entry_id, action)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403, 404):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    # Amaldan keyin navbatdagi yozuvga o'tamiz (toggle'da o'sha yozuv qayta ko'rsatiladi)
    if action == "toggle_date":
        await _show_next(callback, entry_id - 1)
    else:
        await _show_next(callback, 0)


@router.callback_query(F.data.startswith("kb:ok:"))
async def on_approve(callback: CallbackQuery) -> None:
    await _decide_and_next(callback, int(callback.data.rsplit(":", 1)[1]), "approve")


@router.callback_query(F.data.startswith("kb:del:"))
async def on_delete(callback: CallbackQuery) -> None:
    await _decide_and_next(callback, int(callback.data.rsplit(":", 1)[1]), "delete")


@router.callback_query(F.data.startswith("kb:date:"))
async def on_toggle_date(callback: CallbackQuery) -> None:
    await _decide_and_next(callback, int(callback.data.rsplit(":", 1)[1]), "toggle_date")


@router.callback_query(F.data.startswith("kb:edit:"))
async def on_edit(callback: CallbackQuery, state: FSMContext) -> None:
    entry_id = int(callback.data.rsplit(":", 1)[1])
    await state.set_state(KbEdit.waiting_answer)
    await state.update_data(entry_id=entry_id)
    await callback.message.answer(
        "✏️ Yangi RASMIY javob matnini yozing (saqlangach yozuv tasdiqlangan bo'ladi):",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(KbEdit.waiting_answer, F.text)
async def on_edit_text(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
        return
    data = await state.get_data()
    await state.clear()
    try:
        await api_client.knowledge_decide(
            message.from_user.id, data["entry_id"], "edit", answer=message.text
        )
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.json() or {}).get("detail", "Xatolik")
        await message.answer(f"⚠️ {detail}", reply_markup=menu_for_user(user))
        return
    await message.answer("✅ Javob saqlandi va tasdiqlandi.", reply_markup=menu_for_user(user))
    # Avtomatik davom: navbatdagi ko'rib chiqiladigan yozuvni darhol ko'rsatamiz
    next_data = await api_client.knowledge_review_next(message.from_user.id, 0)
    if next_data is not None:
        text, markup = _review_view(next_data)
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "kb:add")
async def on_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(KbAdd.waiting_question)
    await callback.message.answer(
        "➕ Yangi ma'lumot.\n1/2 — mijoz SAVOLINI yozing (masalan: «1 xonali kvartira narxi qancha?»):",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(KbAdd.waiting_question, F.text)
async def on_add_question(message: Message, state: FSMContext) -> None:
    if message.text == BTN_CANCEL:
        user = await api_client.get_user_by_telegram(message.from_user.id)
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
        return
    await state.update_data(question=message.text.strip())
    await state.set_state(KbAdd.waiting_answer)
    await message.answer("2/2 — RASMIY javobni yozing:", reply_markup=cancel_menu())


@router.message(KbAdd.waiting_answer, F.text)
async def on_add_answer(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
        return
    await state.update_data(answer=message.text.strip())
    data = await state.get_data()
    # State'ni tozalaymiz (matn kutish tugadi), lekin savol/javobni storage'da
    # qoldiramiz — kategoriya tugmasi bosilganda kbadd callback o'qib oladi
    # (matnlar callback_data'ning 64 baytiga sig'maydi).
    await state.clear()
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=f"kbadd:{value}:0")
            for value, label in _ADD_CATEGORIES[i : i + 3]
        ]
        for i in range(0, len(_ADD_CATEGORIES), 3)
    ]
    await message.answer("Kategoriya tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await message.answer("Asosiy menyu:", reply_markup=menu_for_user(user))
    await state.update_data(question=data["question"], answer=data["answer"])


@router.callback_query(F.data.startswith("kbadd:"))
async def on_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    category = parts[1]
    date_sensitive = parts[2] == "1"
    data = await state.get_data()
    if not data.get("question") or not data.get("answer"):
        await callback.answer("Ma'lumot topilmadi — «➕ Ma'lumot qo'shish»dan qayta boshlang", show_alert=True)
        return

    # Narx/topshirish kategoriyalari odatda sana-sezgir — avtomatik belgilaymiz
    if category in {"narx", "topshirish"} and not date_sensitive:
        date_sensitive = True

    try:
        await api_client.knowledge_add(
            callback.from_user.id, data["question"], data["answer"], category, date_sensitive
        )
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.json() or {}).get("detail", "Xatolik")
        await callback.answer(detail, show_alert=True)
        return
    await state.clear()
    flag = " (📅 sana-sezgir deb belgilandi)" if date_sensitive else ""
    await callback.message.edit_text(f"✅ Ma'lumot bazaga qo'shildi va tasdiqlandi{flag}.")
    await callback.answer("Saqlandi")


@router.callback_query(F.data == "kb:dataset")
async def on_dataset(callback: CallbackQuery) -> None:
    """Tashqi chatbot uchun tayyor dataset — FAQAT tasdiqlangan savol-javoblar
    (+ tasdiqlangan playbook) JSON faylda."""
    import json as _json

    data = await api_client.knowledge_dataset(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    if not data.get("count"):
        await callback.answer(
            "Tasdiqlangan yozuv hali yo'q — avval «🔍 Ko'rib chiqish»da tasdiqlang",
            show_alert=True,
        )
        return
    content = _json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(content, filename="bilim_dataset.json"),
        caption=(
            f"📦 Chatbot uchun dataset: {data['count']} ta tasdiqlangan savol-javob, "
            f"{len(data.get('playbook', []))} ta playbook yozuvi."
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "kb:export")
async def on_export(callback: CallbackQuery) -> None:
    data = await api_client.knowledge_export(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    entries = data.get("entries", [])
    if not entries:
        await callback.answer("Baza hali bo'sh", show_alert=True)
        return

    lines = ["NURLI DIYOR — SOTUV BILIM BAZASI", "=" * 60]
    current_cat = None
    for e in entries:
        if e["category"] != current_cat:
            current_cat = e["category"]
            lines.append("")
            lines.append(f"### {current_cat.upper()}")
            lines.append("-" * 60)
        badge = _STATUS_BADGE.get(e["status"], e["status"])
        flags = []
        if e["date_sensitive"]:
            flags.append("sana-sezgir")
        if e["needs_recheck"]:
            flags.append("ESKIRGAN — tekshiring")
        flag_s = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"S: {e['question']}")
        lines.append(f"J: {e['answer'] or '(javob yo`q)'}")
        lines.append(f"   ({badge}{flag_s} · manba: {e.get('source') or '-'})")
        lines.append("")
    content = "\n".join(lines).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(content, filename="bilim_bazasi.txt")
    )
    await callback.answer()
