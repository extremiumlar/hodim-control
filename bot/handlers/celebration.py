"""Tabrik videolari paneli (Dasturchi / HR / Boshliq) + guruhdagi «👏» tugmasi.

Panel: joriy holatni ko'rsatadi, video (yoki GIF) yuklashni so'raydi, sinov
yuboradi, turni o'chiradi. Video SERVERGA yuklanmaydi — Telegram'ning
`file_id` si API'ga uzatiladi (`api/services/celebration.py`).

⚠️ Video KUTISH holati (`waiting_media`) — FSM. cPanel webhook rejimida FSM
bazada saqlanadi (`DbFsmStorage`), shuning uchun "video yubordim, bot yutib
yubordi" holati bo'lmaydi (anketa oqimida uchragan tuzoq).
"""
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_CELEBRATION, cancel_menu, menu_for_user

router = Router(name="celebration")
logger = logging.getLogger(__name__)

_ALLOWED = {"dasturchi", "hr", "boss"}
_KIND_TITLES = {"visit": "🎉 Tashrif", "contract": "🤝 Shartnoma"}


def _panel_markup(items: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for it in items:
        kind = it["kind"]
        title = _KIND_TITLES.get(kind, kind)
        verb = "almashtirish" if it["configured"] else "yuklash"
        rows.append(
            [InlineKeyboardButton(text=f"{title}: video {verb}", callback_data=f"celeb:set:{kind}")]
        )
        if it["configured"]:
            rows.append(
                [
                    InlineKeyboardButton(text="🧪 Sinov", callback_data=f"celeb:test:{kind}"),
                    InlineKeyboardButton(text="🚫 O'chirish", callback_data=f"celeb:off:{kind}"),
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _panel_text(items: list[dict]) -> str:
    lines = ["🎬 <b>Tabrik videolari</b>", ""]
    for it in items:
        title = _KIND_TITLES.get(it["kind"], it["kind"])
        if not it["stages_configured"]:
            lines.append(f"{title}: ⚠️ CRM bosqichi sozlanmagan — dasturchiga ayting")
            continue
        if it["configured"]:
            turi = "GIF" if it["file_type"] == "animation" else "video"
            lines.append(f"{title}: ✅ {turi} o'rnatilgan · yuborilgan: {it['posts_total']} ta")
            if it["caption"]:
                lines.append(f"   ✍️ Qo'shimcha matn: <i>{it['caption']}</i>")
        else:
            lines.append(f"{title}: ⛔ video yo'q — guruhga hech narsa yuborilmaydi")
    lines += [
        "",
        "Video yoki GIF yuboring — CRM'da lid o'sha bosqichga o'tgan zahoti",
        "umumiy guruhga «👏 Tabriklash» tugmasi bilan chiqadi.",
    ]
    return "\n".join(lines)


class CelebrationFSM(StatesGroup):
    waiting_media = State()


async def _actor(telegram_id: int) -> dict | None:
    user = await api_client.get_user_by_telegram(telegram_id)
    if not user or user.get("role") not in _ALLOWED:
        return None
    return user


@router.message(F.text == BTN_CELEBRATION)
async def open_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not await _actor(message.from_user.id):
        return
    items = await api_client.celebration_media(message.from_user.id)
    await message.answer(_panel_text(items), reply_markup=_panel_markup(items))


@router.callback_query(F.data.startswith("celeb:set:"))
async def ask_media(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _actor(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    kind = callback.data.split(":")[2]
    await state.set_state(CelebrationFSM.waiting_media)
    await state.update_data(kind=kind)
    await callback.message.answer(
        f"{_KIND_TITLES.get(kind, kind)} uchun <b>video</b> yoki <b>GIF</b> yuboring.\n\n"
        "Izoh yozib yuborsangiz — u har tabrikning oxiriga qo'shiladi.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(CelebrationFSM.waiting_media), F.text == BTN_CANCEL)
async def cancel_media(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(StateFilter(CelebrationFSM.waiting_media), F.video | F.animation | F.document)
async def receive_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data.get("kind")
    if not kind:
        await state.clear()
        return

    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.animation:
        file_id, file_type = message.animation.file_id, "animation"
    else:
        # Telegram GIF'ni ba'zan hujjat sifatida yuboradi (mime video/mp4)
        doc = message.document
        if not doc or not (doc.mime_type or "").startswith("video"):
            await message.answer("Bu video emas. Video yoki GIF yuboring.")
            return
        file_id, file_type = doc.file_id, "animation"

    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        await api_client.set_celebration_media(
            telegram_id=message.from_user.id,
            kind=kind,
            file_id=file_id,
            file_type=file_type,
            caption=(message.caption or "").strip() or None,
        )
    except Exception:
        logger.exception("Tabrik videosini saqlashda xato")
        await message.answer("Saqlab bo'lmadi — keyinroq urinib ko'ring.", reply_markup=menu_for_user(user))
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ {_KIND_TITLES.get(kind, kind)} videosi o'rnatildi.\n"
        "Endi CRM'da lid shu bosqichga o'tganda guruhga shu video boradi.",
        reply_markup=menu_for_user(user),
    )
    items = await api_client.celebration_media(message.from_user.id)
    await message.answer(_panel_text(items), reply_markup=_panel_markup(items))


@router.callback_query(F.data.startswith("celeb:test:"))
async def test_media(callback: CallbackQuery) -> None:
    if not await _actor(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    kind = callback.data.split(":")[2]
    res = await api_client.test_celebration(callback.from_user.id, kind)
    if res.get("ok"):
        await callback.answer("Sinov sizga yuborildi (guruhga emas)", show_alert=True)
    else:
        await callback.answer(res.get("reason") or "Yuborib bo'lmadi", show_alert=True)


@router.callback_query(F.data.startswith("celeb:off:"))
async def disable_media(callback: CallbackQuery) -> None:
    if not await _actor(callback.from_user.id):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    kind = callback.data.split(":")[2]
    await api_client.disable_celebration(callback.from_user.id, kind)
    await callback.answer("O'chirildi — bu tur uchun guruhga video ketmaydi", show_alert=True)
    items = await api_client.celebration_media(callback.from_user.id)
    await callback.message.edit_text(_panel_text(items), reply_markup=_panel_markup(items))


@router.callback_query(F.data.startswith("celebrate:clap:"))
async def on_clap(callback: CallbackQuery) -> None:
    """Guruhdagi «👏 Tabriklash». Tugma matnini API yangilaydi (editMessageReplyMarkup),
    bu yerda faqat bosgan odamga javob qaytariladi."""
    try:
        post_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    try:
        res = await api_client.celebration_clap(post_id, callback.from_user.id)
    except Exception:
        logger.exception("Tabrik bosishida xato")
        await callback.answer()
        return

    if not res.get("ok"):
        await callback.answer()
    elif res.get("already"):
        await callback.answer("Siz allaqachon tabrikladingiz 👏")
    else:
        await callback.answer("Tabrikingiz qo'shildi 👏")
