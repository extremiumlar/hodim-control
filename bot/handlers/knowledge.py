"""Sotuv bilim bazasi — bot boshqaruvi (faqat Boshliq/Dasturchi).

Kirish: «🧠 Sotuv AI markazi» dashboardidagi «3️⃣ Bilim bazasi» tugmasi
(yoki /bilim). Holat + 4 amal:
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
    # Kategoriya tugmalari bosilguncha ham holat FAOL turadi (state.clear()
    # ATAYLAB chaqirilmaydi) — savol/javob matni shu FSM data'sida saqlanadi
    # (callback_data 64 baytga sig'maydi). Ilgari shu bosqichda state
    # tozalanib, lekin data qoldirilardi — bu boshqa FSM oqimiga (masalan
    # keyinroq ochilgan ✏️ tahrirlash) tasodifan aralashib ketishi mumkin
    # bo'lgan "osilib qolgan" ma'lumot edi. Endi state ONE PIECE sifatida
    # yuriydi: yakunlanganda yoki bekor qilinganda BIR JOYDA tozalanadi.
    waiting_category = State()


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

    total = data.get("review_pending", 0) + counts.get("verified", 0)
    rows = [
        [InlineKeyboardButton(text="🔄 Anketadan yuklash", callback_data="kb:ingest")],
        [InlineKeyboardButton(text=f"🔍 Ko'rib chiqish ({total})", callback_data="kb:review")],
        [
            InlineKeyboardButton(text="➕ Ma'lumot qo'shish", callback_data="kb:add"),
            InlineKeyboardButton(text="📥 Baza (.txt)", callback_data="kb:export"),
        ],
        [InlineKeyboardButton(text="📦 Dataset (.json)", callback_data="kb:dataset")],
        [InlineKeyboardButton(text="⬅️ Sotuv AI markazi", callback_data="aic:menu")],
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


def _source_name(source: str) -> str:
    """"Anketa №1, savol 2: Kamola" → "Kamola" (ko'rsatish uchun)."""
    return (source or "").rsplit(": ", 1)[-1].strip() or "?"


# ─── Yagona ko'rib chiqish oqimi (ilgari 3 xil "review" bo'lgan: pending/
# verified/all — endi bitta karta va bitta navigatsiya, holat FAQAT filtr) ───

_FILTER_LABELS = {"pending": "⏳ Kutayotganlar", "verified": "✅ Tasdiqlanganlar", "all": "📖 Hammasi"}
_FILTER_TITLES = {"pending": "🔍 Ko'rib chiqish", "verified": "🔍 Ko'rib chiqish", "all": "📖 To'liq ko'rib chiqish"}


def _filter_choice_view(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    counts = data.get("counts", {})
    pending = data.get("review_pending", 0)
    verified = counts.get("verified", 0)
    rows = [
        [InlineKeyboardButton(text=f"⏳ Kutayotganlar ({pending})", callback_data="kb:rev:pending:0")],
        [InlineKeyboardButton(text=f"✅ Tasdiqlanganlar ({verified})", callback_data="kb:rev:verified:0")],
        [InlineKeyboardButton(text=f"📖 Hammasi ({pending + verified})", callback_data="kb:rev:all:0")],
        [InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu")],
    ]
    return "🔍 Nimani ko'rib chiqasiz?", InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "kb:review")
async def on_review_filter_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    data = await api_client.knowledge_overview(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = _filter_choice_view(data)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


def _conflict_card(
    entry: dict, group: list[dict], filter_: str, remaining: int, processing: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Ziddiyatli savol kartasi: barcha xodimlar javoblari yonma-yon, rahbar
    birini qabul qiladi yoki birini tahrirlab o'tkazadi (qolganlari o'chadi)."""
    lines = [
        f"{_FILTER_TITLES[filter_]} ({_FILTER_LABELS[filter_]}) — qolgan: {remaining}"
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
            InlineKeyboardButton(text=f"✅ {i}-javobni qabul qilish", callback_data=f"kb:ok:{filter_}:{m['id']}"),
            InlineKeyboardButton(text=f"✏️ {i}-ni tahrirlash", callback_data=f"kb:edit:{filter_}:{m['id']}"),
        ]
        for i, m in enumerate(group, start=1)
    ]
    max_id = max(m["id"] for m in group)
    rows.append([
        InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"kb:rev:{filter_}:{max_id}"),
        InlineKeyboardButton(text="🔀 Filtr", callback_data="kb:review"),
        InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _review_card(entry: dict, filter_: str, remaining: int, processing: int) -> tuple[str, InlineKeyboardMarkup]:
    """Universal karta — yozuv holatiga qarab tugmalar moslashadi (tasdiqlash/
    tasdiqdan qaytarish), qaysi FILTRDA ochilganidan qat'i nazar bir xil."""
    badge = _STATUS_BADGE.get(entry["status"], entry["status"])
    date_flag = "✅" if entry["date_sensitive"] else "❌"
    lines = [
        f"{_FILTER_TITLES[filter_]} ({_FILTER_LABELS[filter_]}) — qolgan: {remaining}"
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
    first_row = [InlineKeyboardButton(text="✏️ Javob yozish", callback_data=f"kb:edit:{filter_}:{eid}")]
    if entry["status"] == "verified":
        first_row.append(
            InlineKeyboardButton(text="🔙 Tasdiqdan qaytarish", callback_data=f"kb:unv:{filter_}:{eid}")
        )
    else:
        first_row.insert(
            0, InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"kb:ok:{filter_}:{eid}")
        )
    rows = [
        first_row,
        [
            InlineKeyboardButton(text="📅 Sana-sezgir", callback_data=f"kb:date:{filter_}:{eid}"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"kb:del:{filter_}:{eid}"),
        ],
        [
            InlineKeyboardButton(text="⏭ Keyingisi", callback_data=f"kb:rev:{filter_}:{eid}"),
            InlineKeyboardButton(text="🔀 Filtr", callback_data="kb:review"),
        ],
        [InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _unified_review_view(data: dict, filter_: str) -> tuple[str, InlineKeyboardMarkup]:
    entry = data.get("entry")
    if entry is None:
        extra = (
            f"\n⏳ {data['processing']} ta yozuv hali AI ishlovida — birozdan keyin qaytib ko'ring."
            if data.get("processing")
            else ""
        )
        return (
            f"✅ «{_FILTER_LABELS[filter_]}» ro'yxati tugadi.{extra}",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔀 Boshqa filtr", callback_data="kb:review")],
                    [InlineKeyboardButton(text="⬅️ Menyu", callback_data="kb:menu")],
                ]
            ),
        )
    group = data.get("conflict_group")
    if group and len(group) > 1:
        return _conflict_card(entry, group, filter_, data["remaining"], data.get("processing", 0))
    return _review_card(entry, filter_, data["remaining"], data.get("processing", 0))


async def _show_review(callback: CallbackQuery, filter_: str, after_id: int) -> None:
    data = await api_client.knowledge_review_next(callback.from_user.id, after_id, mode=filter_)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = _unified_review_view(data, filter_)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("kb:rev:"))
async def on_review_next(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        _, _, filter_, after_id_s = callback.data.split(":", 3)
        await _show_review(callback, filter_, int(after_id_s))
    except ValueError:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)


def _next_after(action: str, entry_id: int) -> int:
    """Amaldan keyin qaysi ID'dan davom etish. «Yakuniy» amallar (tasdiqlash/
    tahrir/o'chirish) — 0'dan qayta skanerlaydi, shunda oldinroq «⏭» bilan
    o'tkazib yuborilgan yozuvlar ham qaytadan chiqadi (doimiy yo'qolib
    qolmaydi). «Qaytariladigan» amallar (tasdiqdan qaytarish/sana-sezgirlik)
    — xuddi shu yozuvni yangilangan holda qayta ko'rsatadi."""
    if action in ("unverify", "toggle_date"):
        return entry_id - 1
    return 0


async def _decide_and_continue(callback: CallbackQuery, filter_: str, entry_id: int, action: str) -> None:
    try:
        await api_client.knowledge_decide(callback.from_user.id, entry_id, action)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403, 404):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await _show_review(callback, filter_, _next_after(action, entry_id))


def _parse_decide_callback(data: str) -> tuple[str, int] | None:
    """"kb:ok:pending:123" → ("pending", 123). Eski (filtr'siz) formatdagi
    tugmalar — None (chaqiruvchi tushunarli xato ko'rsatadi)."""
    parts = data.split(":")
    if len(parts) != 4:
        return None
    _, _, filter_, id_s = parts
    if filter_ not in _FILTER_LABELS or not id_s.isdigit():
        return None
    return filter_, int(id_s)


@router.callback_query(F.data.startswith("kb:ok:"))
async def on_approve(callback: CallbackQuery) -> None:
    parsed = _parse_decide_callback(callback.data)
    if parsed is None:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)
        return
    await _decide_and_continue(callback, *parsed, "approve")


@router.callback_query(F.data.startswith("kb:del:"))
async def on_delete(callback: CallbackQuery) -> None:
    parsed = _parse_decide_callback(callback.data)
    if parsed is None:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)
        return
    await _decide_and_continue(callback, *parsed, "delete")


@router.callback_query(F.data.startswith("kb:date:"))
async def on_toggle_date(callback: CallbackQuery) -> None:
    parsed = _parse_decide_callback(callback.data)
    if parsed is None:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)
        return
    await _decide_and_continue(callback, *parsed, "toggle_date")


@router.callback_query(F.data.startswith("kb:unv:"))
async def on_unverify(callback: CallbackQuery) -> None:
    parsed = _parse_decide_callback(callback.data)
    if parsed is None:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)
        return
    filter_, entry_id = parsed
    try:
        await api_client.knowledge_decide(callback.from_user.id, entry_id, "unverify")
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.json() or {}).get("detail", "Xatolik")
        await callback.answer(detail, show_alert=True)
        return
    await callback.answer("Tasdiqdan qaytarildi")
    await _show_review(callback, filter_, _next_after("unverify", entry_id))


@router.callback_query(F.data.startswith("kb:edit:"))
async def on_edit(callback: CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_decide_callback(callback.data)
    if parsed is None:
        await callback.answer("Bu tugma eskirgan — «🔍 Ko'rib chiqish»ni qaytadan oching", show_alert=True)
        return
    filter_, entry_id = parsed
    await state.set_state(KbEdit.waiting_answer)
    await state.update_data(entry_id=entry_id, filter=filter_)
    await callback.message.answer(
        "✏️ Yangi RASMIY javob matnini yozing (saqlangach yozuv tasdiqlanadi):",
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

    filter_ = data.get("filter", "pending")
    after = _next_after("edit", data["entry_id"])
    next_data = await api_client.knowledge_review_next(message.from_user.id, after, mode=filter_)
    if next_data is not None:
        text, markup = _unified_review_view(next_data, filter_)
        await message.answer(text, reply_markup=markup)



@router.callback_query(F.data == "kb:add")
async def on_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()  # oldingi FSM oqimidan qolgan holat/data bo'lsa tozalanadi
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
    # DIQQAT: state ATAYLAB tozalanmaydi — KbAdd.waiting_category'ga o'tadi.
    # Savol/javob matni shu FSM data'sida saqlanadi (callback_data 64 baytga
    # sig'maydi), lekin holat FAOL bo'lgani uchun endi boshqa oqimga
    # "osilib qolgan" ma'lumot bo'lib aralashib ketmaydi — yakunlanganda
    # (kategoriya tanlanganda) yoki bekor qilinganda BIR JOYDA tozalanadi.
    await state.set_state(KbAdd.waiting_category)
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=f"kbadd:{value}")
            for value, label in _ADD_CATEGORIES[i : i + 3]
        ]
        for i in range(0, len(_ADD_CATEGORIES), 3)
    ]
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="kbadd:cancel")])
    await message.answer("Kategoriya tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await message.answer("Asosiy menyu:", reply_markup=menu_for_user(user))


@router.callback_query(StateFilter(KbAdd.waiting_category), F.data == "kbadd:cancel")
async def on_add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.callback_query(StateFilter(KbAdd.waiting_category), F.data.startswith("kbadd:"))
async def on_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if not data.get("question") or not data.get("answer"):
        # Nazariy holat (state to'g'ri bo'lsa data ham bo'lishi kerak) — ehtiyot
        # chorasi sifatida saqlanadi, foydalanuvchini oqib ketmasin.
        await state.clear()
        await callback.answer("Ma'lumot topilmadi — «➕ Ma'lumot qo'shish»dan qayta boshlang", show_alert=True)
        return

    # Narx/topshirish kategoriyalari odatda sana-sezgir — avtomatik belgilaymiz
    date_sensitive = category in {"narx", "topshirish"}

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
