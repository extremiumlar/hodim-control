"""Kadr hujjatlari botda (yangi TZ 3.4 / S-11).

Ikki oqim:
  • «📁 Hujjatlarim» — HAR QANDAY xodim o'z hujjatlari ro'yxatini ko'radi
    va bittasini bosib faylni qaytadan oladi;
  • «📎 Hujjat yuklash» — HR xodim tanlaydi → tur tanlaydi → faylni
    yuboradi. Fayl SERVERGA yuklanmaydi, Telegram `file_id` si API'ga
    uzatiladi (`bot/handlers/celebration.py` naqshi).

⚠️ FSM cPanel webhook rejimida bazada saqlanadi (`DbFsmStorage`) —
«faylni yubordim, bot yutib yubordi» holati bo'lmaydi (anketa oqimida
uchragan tuzoq).
"""
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_DOC_UPLOAD, BTN_MY_DOCS, cancel_menu, menu_for_user

router = Router(name="documents")
logger = logging.getLogger(__name__)

_HR = {"hr", "boss", "dasturchi"}

#  Bitta sahifada nechta xodim ko'rsatiladi. Telegram inline klaviaturasi
#  juda uzun bo'lsa xabar umuman yuborilmaydi (limit), shuning uchun
#  ro'yxat bo'laklanadi.
_PAGE = 8


class DocFSM(StatesGroup):
    waiting_file = State()


def _muddat_belgisi(d: dict) -> str:
    """Muddati o'tgan / yaqinlashgan hujjat ro'yxatda AJRATIB ko'rsatiladi
    (S-11 qabul mezoni). Hisob serverda — bu yerda faqat belgi tanlanadi."""
    qoldi = d.get("days_left")
    if qoldi is None:
        return ""
    if d.get("is_expired"):
        return f" ⛔ muddati {abs(qoldi)} kun oldin tugagan"
    if qoldi <= 30:
        return f" ⚠️ {qoldi} kun qoldi"
    return f" · {qoldi} kun"


# ─────────────────────────────────────────────────────────────
# XODIM: «Hujjatlarim»
# ─────────────────────────────────────────────────────────────


@router.message(F.text == BTN_MY_DOCS)
async def my_documents(message: Message, state: FSMContext) -> None:
    await state.clear()
    docs = await api_client.my_documents(message.from_user.id)
    if not docs:
        await message.answer(
            "📁 Sizda hali hujjat yo'q.\n\n"
            "Mehnat shartnomasi, diplom va boshqa hujjatlarni HR yuklaydi."
        )
        return

    lines = ["📁 <b>Hujjatlarim</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for d in docs:
        lines.append(f"• {d['name']} — {d['doc_type_label']}{_muddat_belgisi(d)}")
        rows.append(
            [InlineKeyboardButton(text=f"📥 {d['name'][:40]}", callback_data=f"doc:get:{d['id']}")]
        )
    lines += ["", "Faylni olish uchun pastdagi tugmani bosing."]
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("doc:get:"))
async def send_document(callback: CallbackQuery) -> None:
    try:
        doc_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    try:
        res = await api_client.send_my_document(callback.from_user.id, doc_id)
    except Exception:
        logger.exception("Hujjatni yuborishda xato")
        await callback.answer("Yuborib bo'lmadi — keyinroq urinib ko'ring", show_alert=True)
        return
    if res.get("delivered"):
        await callback.answer("Yuborildi 📥")
    else:
        await callback.answer("Hozir yuborib bo'lmadi", show_alert=True)


# ─────────────────────────────────────────────────────────────
# HR: «Hujjat yuklash»
# ─────────────────────────────────────────────────────────────


async def _hr(telegram_id: int) -> dict | None:
    user = await api_client.get_user_by_telegram(telegram_id)
    if not user or user.get("role") not in _HR:
        return None
    return user


def _employees_markup(items: list[dict], page: int) -> InlineKeyboardMarkup:
    bolak = items[page * _PAGE : (page + 1) * _PAGE]
    rows = [
        [InlineKeyboardButton(text=u["full_name"][:50], callback_data=f"doc:emp:{u['id']}")]
        for u in bolak
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"doc:page:{page - 1}"))
    if (page + 1) * _PAGE < len(items):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"doc:page:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_DOC_UPLOAD)
async def start_upload(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not await _hr(message.from_user.id):
        return
    items = await api_client.document_employees(message.from_user.id)
    if not items:
        await message.answer("Faol xodim topilmadi.")
        return
    await message.answer(
        "📎 <b>Hujjat yuklash</b>\n\nKimning hujjati?",
        reply_markup=_employees_markup(items, 0),
    )


@router.callback_query(F.data.startswith("doc:page:"))
async def page_employees(callback: CallbackQuery) -> None:
    if not await _hr(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    page = int(callback.data.split(":")[2])
    items = await api_client.document_employees(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=_employees_markup(items, page))
    await callback.answer()


@router.callback_query(F.data.startswith("doc:emp:"))
async def pick_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _hr(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    user_id = int(callback.data.split(":")[2])
    await state.update_data(doc_user_id=user_id)
    turlar = await api_client.document_types(callback.from_user.id)
    rows = [
        [InlineKeyboardButton(text=t["label"], callback_data=f"doc:type:{t['value']}")]
        for t in turlar
    ]
    await callback.message.edit_text(
        "Hujjat turini tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("doc:type:"))
async def ask_file(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _hr(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("doc_user_id"):
        await callback.answer("Avval xodimni tanlang", show_alert=True)
        return
    doc_type = callback.data.split(":")[2]
    await state.update_data(doc_type=doc_type)
    await state.set_state(DocFSM.waiting_file)
    await callback.message.answer(
        "Endi <b>faylni</b> yuboring (hujjat yoki rasm).\n\n"
        "Izohga hujjat nomini yozishingiz mumkin. Amal muddati bo'lsa "
        "izohning oxiriga sanani <code>2027-12-31</code> ko'rinishida qo'shing "
        "— tugash sanasi shundan olinadi.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(DocFSM.waiting_file), F.text == BTN_CANCEL)
async def cancel_upload(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


def _parse_caption(caption: str, fallback: str) -> tuple[str, str | None]:
    """Izohdan (nom, tugash sanasi) ajratadi.

    Sana izohning ISTALGAN joyida `YYYY-MM-DD` ko'rinishida bo'lishi
    mumkin — HR uni odatda oxiriga yozadi, lekin oldiga yozsa ham
    ishlashi kerak. Sana nomdan olib tashlanadi."""
    import re

    matn = (caption or "").strip()
    sana = None
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", matn)
    if m:
        sana = m.group(1)
        matn = (matn[: m.start()] + matn[m.end() :]).strip(" -–—,;")
    return (matn or fallback), sana


@router.message(StateFilter(DocFSM.waiting_file), F.document | F.photo)
async def receive_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id, doc_type = data.get("doc_user_id"), data.get("doc_type")
    if not user_id or not doc_type:
        await state.clear()
        return

    if message.document:
        file_id, file_type = message.document.file_id, "document"
        fallback = message.document.file_name or "Hujjat"
    else:
        #  Rasmda bir nechta o'lcham keladi — eng kattasi oxirgisi.
        file_id, file_type = message.photo[-1].file_id, "photo"
        fallback = "Rasm"

    nom, muddat = _parse_caption(message.caption or "", fallback)
    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        res = await api_client.upload_document(
            telegram_id=message.from_user.id,
            user_id=user_id,
            doc_type=doc_type,
            name=nom,
            file_id=file_id,
            file_type=file_type,
            expires_at=muddat,
        )
    except Exception:
        logger.exception("Hujjat yuklashda xato")
        await message.answer(
            "Saqlab bo'lmadi — keyinroq urinib ko'ring.", reply_markup=menu_for_user(user)
        )
        await state.clear()
        return

    await state.clear()
    xabar = f"✅ Saqlandi: <b>{res.get('name')}</b> ({res.get('doc_type_label')})"
    if res.get("expires_at"):
        xabar += f"\nAmal qiladi: {res['expires_at']} gacha"
    xabar += "\n\nFayl Telegram'da qoladi — serverda joy egallamaydi."
    await message.answer(xabar, reply_markup=menu_for_user(user))


@router.message(StateFilter(DocFSM.waiting_file))
async def wrong_file(message: Message) -> None:
    """Kutilayotgani fayl, kelgani boshqa narsa — FSM ni buzmasdan eslatamiz.
    Aks holda foydalanuvchi matn yozib, javob ololmay qolardi."""
    await message.answer("Hujjat yoki rasm yuboring (yoki «❌ Bekor qilish»).")
