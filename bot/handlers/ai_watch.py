"""Operator AI bot tomonlari: erkin matnli sabab oqimi (7-bosqich), eski sabab
tugmalari (orqaga moslik) va rahbar boshqaruvi /ai_sozlama + /ai_vaqt (6-bosqich).

Sabab oqimi: API (ai-watch/tick) orqada qolgan operatorga nudge + "sababini yozib
yuboring" so'rovini yuboradi; operator O'Z SO'ZLARI bilan yozadi, matn API'ga
boradi — u yerda AI tasniflaydi va da'vo faktlar (CRM'dagi ochiq lidlar, terilgan
raqamlar) bilan solishtiriladi. Matn ushlagich `reason_text_router`da bo'lib, u
dispatcherga ENG OXIRIDA ulanadi — menyu tugmalari, buyruqlar va FSM oqimlaridan
o'tmagan xabarlargina yetib keladi (StateFilter(None) FSM'dagi foydalanuvchiga
tegmaslikni kafolatlaydi).

Boshqaruv: rahbar AI qismlarini (nudge/kun yakuni/haftalik) yoqib-o'chiradi va
xulosa vaqtini o'zgartiradi — odam-qaror tamoyili."""
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client

logger = logging.getLogger(__name__)
router = Router()
# Alohida router — bot/main.py da ENG OXIRIDA include qilinadi (pastga qarang).
reason_text_router = Router()

_TOGGLE_LABELS = {
    "nudges_enabled": "🔔 Soatlik nudge",
    "group_summary_enabled": "🤖 AI xulosa (kunlik digest ichida)",
    "weekly_enabled": "📈 Haftalik xulosa (shaxsiy)",
    "hot_leads_enabled": "🔥 Issiq lid",
}


def _config_view(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    master = "yoqiq ✅" if cfg.get("ai_enabled") and cfg.get("push_enabled") else "O'CHIQ ❌ (.env: AI_ENABLED/AI_NUDGE_ENABLED)"
    hot_lead_master = "yoqiq ✅" if cfg.get("hot_lead_push_enabled") else "O'CHIQ ❌ (.env: HOT_LEAD_ENABLED)"
    lines = [
        "🤖 <b>Operator AI sozlamalari</b>",
        f"Bosh kalit (server): {master}",
        f"Issiq lid (server): {hot_lead_master}",
        f"Provayder: {cfg.get('provider')}",
        "AI xulosa kunlik digest bilan birga guruhga chiqadi"
        " (vaqti: /statistika_vaqt).",
        "",
        "Qismlarni tugma bilan yoqing/o'chiring:",
    ]
    rows = [
        [InlineKeyboardButton(
            text=f"{label}: {'✅' if cfg.get(field) else '❌'}",
            callback_data=f"aicfg:{field}",
        )]
        for field, label in _TOGGLE_LABELS.items()
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("ai_sozlama"))
async def cmd_ai_config(message: Message) -> None:
    cfg = await api_client.get_ai_config(message.from_user.id)
    if cfg is None:
        await message.reply("Bu buyruq faqat rahbarlar uchun.")
        return
    text, markup = _config_view(cfg)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("aicfg:"))
async def on_toggle(callback: CallbackQuery) -> None:
    field = callback.data.split(":", 1)[1]
    if field not in _TOGGLE_LABELS:
        await callback.answer("Noma'lum sozlama")
        return
    cfg = await api_client.get_ai_config(callback.from_user.id)
    if cfg is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    updated = await api_client.set_ai_config(callback.from_user.id, **{field: not cfg.get(field)})
    if updated is None:
        await callback.answer("O'zgartirish faqat Boshliq uchun", show_alert=True)
        return
    text, markup = _config_view(updated)
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 — matn o'zgarmagan bo'lsa ham toast beramiz
        logger.debug("Sozlama xabarini tahrirlab bo'lmadi", exc_info=True)
    state = "yoqildi ✅" if updated.get(field) else "o'chirildi ❌"
    await callback.answer(f"{_TOGGLE_LABELS[field]} {state}")


@router.message(Command("ai_vaqt"))
async def cmd_ai_time(message: Message, command: CommandObject) -> None:
    """ESKI buyruq — AI xulosaning alohida vaqti endi yo'q: u kunlik digest bilan
    birga chiqadi. Foydalanuvchini yagona vaqt buyrug'iga yo'naltiramiz."""
    await message.reply(
        "AI xulosa endi kunlik digest bilan BITTA xabarda chiqadi.\n"
        "Yuborish vaqtini o'zgartirish: /statistika_vaqt 19:30"
    )


@reason_text_router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/"),
    StateFilter(None),
)
async def on_reason_text(message: Message) -> None:
    """Boshqa hech bir handler olmagan oddiy matn — sabab kutilayotgan operatorniki
    bo'lishi mumkin. API tekshiradi: pending so'rov bo'lsa AI tahlil + fakt tekshiruv
    natijasini qaytaradi, bo'lmasa {"handled": false} — bot jim qoladi (hozirgi
    "notanish matnga javob yo'q" xatti-harakati saqlanadi)."""
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:  # noqa: BLE001 — chat action bezak, xatosi oqimni to'xtatmasin
        pass

    try:
        result = await api_client.post_shortfall_reason_text(message.from_user.id, message.text)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return  # ro'yxatdan o'tmagan foydalanuvchi — jim
        logger.exception("Sabab matnini yuborishda API xatosi")
        await message.reply("⚠️ Xabarni qayta ishlashda xatolik — birozdan keyin qayta yozib ko'ring.")
        return
    except httpx.HTTPError:
        logger.exception("Sabab matnini yuborishda tarmoq xatosi")
        await message.reply("⚠️ Xabarni qayta ishlashda xatolik — birozdan keyin qayta yozib ko'ring.")
        return

    if not result.get("handled"):
        return  # sabab kutilmayotgan edi — oddiy matn, aralashmaymiz

    await message.reply(result.get("reply") or "✅ Sabab qayd etildi.")


@router.callback_query(F.data.startswith("sfv:"))
async def on_reason_verify(callback: CallbackQuery) -> None:
    """Rahbar (ROP/Boshliq) avtomatik tekshirib bo'lmagan sababni tasdiqlaydi yoki
    rad etadi. callback_data: "sfv:<reason_id>:<1|0>". Birinchi qaror yakuniy —
    keyin bosgan rahbarga "allaqachon hal qilingan" ko'rsatiladi."""
    try:
        _, reason_id_s, decision_s = callback.data.split(":", 2)
        reason_id = int(reason_id_s)
        approve = decision_s == "1"
    except ValueError:
        await callback.answer("Xato ma'lumot")
        return

    try:
        result = await api_client.post_reason_verify(callback.from_user.id, reason_id, approve)
    except Exception:  # noqa: BLE001 — API xatosida rahbarni jim qoldirmaymiz
        logger.exception("Sabab tasdiqlashda xatolik")
        await callback.answer("Xatolik — birozdan keyin urinib ko'ring", show_alert=True)
        return

    if result is None:
        await callback.answer("Bu amal faqat ROP/Boshliq uchun", show_alert=True)
        return

    if result.get("already"):
        status = "tasdiqlangan ✅" if result.get("verified") else "rad etilgan ❌"
        suffix = f"\n\n☑️ Allaqachon hal qilingan: <b>{status}</b>"
        await callback.answer("Bu sabab allaqachon hal qilingan")
    else:
        status = "tasdiqlandi ✅" if approve else "rad etildi ❌"
        suffix = f"\n\n☑️ Sizning qaroringiz: <b>{status}</b> (operatorga xabar yuborildi)"
        await callback.answer(f"Sabab {status}")

    # Tugmalarni olib tashlab, qarorni xabar ostiga yozamiz (qayta bosilmasin)
    try:
        if callback.message:
            await callback.message.edit_text(
                f"{callback.message.html_text}{suffix}", reply_markup=None
            )
    except Exception:  # noqa: BLE001 — edit ishlamasa toast yetadi
        logger.debug("Tasdiqlash xabarini tahrirlab bo'lmadi", exc_info=True)


@router.callback_query(F.data.startswith("sfr:"))
async def on_shortfall_reason(callback: CallbackQuery) -> None:
    # ESKI tugmali xabarlar uchun orqaga moslik (yangi nudge'lar tugmasiz).
    # callback_data: "sfr:<YYYY-MM-DD>:<soat>:<kod>"
    try:
        _, day, hour_s, code = callback.data.split(":", 3)
        hour = int(hour_s)
    except ValueError:
        await callback.answer("Xato ma'lumot", show_alert=False)
        return

    try:
        result = await api_client.post_shortfall_reason(callback.from_user.id, day, hour, code)
    except Exception:  # noqa: BLE001 — API xatosida operatorni jim qoldirmaymiz
        logger.exception("Sababni saqlashda xatolik")
        await callback.answer("Saqlashda xatolik — birozdan keyin urinib ko'ring", show_alert=True)
        return

    label = result.get("label", "")
    # Tugmalarni olib tashlaymiz (qayta-qayta bosilmasin) va tasdiqni matn ostiga qo'shamiz
    try:
        if callback.message:
            await callback.message.edit_text(
                f"{callback.message.html_text}\n\n✅ Sabab qayd etildi: <b>{label}</b>",
                reply_markup=None,
            )
    except Exception:  # noqa: BLE001 — edit ishlamasa (eski xabar) toast yetadi
        logger.debug("Nudge xabarini tahrirlab bo'lmadi", exc_info=True)
    await callback.answer("Qayd etildi")
