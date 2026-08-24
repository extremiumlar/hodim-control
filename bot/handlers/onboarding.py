"""«📋 Birinchi kunlarim» — xodim tomoni, bot (yangi TZ 3.2 / S-47).

Qadamlar ro'yxati va har biri uchun «bajardim» tugmasi.

⚠️ FSM ISHLATILMAYDI — kutiladigan matn yo'q, faqat ko'rsatish va
inline tugmalar. Holat BAZADA (`onboarding_progress`).

⚠️ QADAM VAZIFA SIFATIDA HAM KELADI (S-46). Bu ro'yxat ularning
UMUMIY ko'rinishi: xodim «qancha qoldi?» degan savolga bir joydan
javob olsin. Ikkalasi bitta holatga tayanadi, ya'ni bir joyda
belgilansa ikkinchisida ham bajarilgan bo'lib turadi.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_ONBOARDING

router = Router(name="onboarding")
logger = logging.getLogger(__name__)

#  Telegram inline klaviaturasi juda uzun bo'lsa xabar UMUMAN
#  yuborilmaydi — tugmalar cheklanadi.
_MAX_TUGMA = 8

_TUR_BELGI = {
    "task": "📌",
    "document": "📄",
    "course": "📚",
    "briefing": "🦺",
    "meeting": "🤝",
}


def _matn(p: dict) -> str:
    q = [f"📋 <b>Birinchi kunlarim</b> — {p['done']}/{p['total']}"]
    if p.get("template_name"):
        q.append(f"<i>{p['template_name']}</i>")
    if p.get("overdue"):
        q.append(f"\n⚠️ Kechikkan qadam: <b>{p['overdue']}</b>")
    q.append("")

    for b in p.get("items", []):
        belgi = "✅" if b["done"] else _TUR_BELGI.get(b["kind"], "▫️")
        qator = f"{belgi} {b['title']}"
        if b["due_date"] and not b["done"]:
            qator += f" — {b['due_date']}"
        #  ⚠️ Kechikkan qadam AJRATIB ko'rsatiladi (TZ 3.2 qabul mezoni).
        if b.get("overdue"):
            qator += " ⏰ <b>kechikdi</b>"
        q.append(qator)

    keyingi = p.get("next_stage")
    if keyingi:
        q.append(f"\n🎯 Keyingi bosqich: <b>{keyingi['label']}</b>"
                 f" ({keyingi['due_date']})")
    return "\n".join(q)[:3500]


def _klaviatura(p: dict) -> InlineKeyboardMarkup | None:
    """Faqat BAJARILMAGAN qadamlar uchun tugma.

    ⚠️ Boshqa modul bajaradigan qadamga («kurs», «hujjat») tugma
    QO'YILMAYDI: uni bu yerdan belgilash mumkin bo'lsa, xodim
    kursni o'tmasdan «bajardim» deb qo'yardi va holat yolg'on
    bo'lardi. Bunday qadamlar manba modulda bajarilganda o'zi
    belgilanadi (S-45)."""
    qatorlar = []
    for b in p.get("items", []):
        if b["done"] or b["kind"] in ("course", "document"):
            continue
        qatorlar.append([
            InlineKeyboardButton(
                text=f"✅ {b['title'][:40]}",
                callback_data=f"onb:done:{b['id']}",
            )
        ])
        if len(qatorlar) >= _MAX_TUGMA:
            break
    return InlineKeyboardMarkup(inline_keyboard=qatorlar) if qatorlar else None


async def _korsat(target, p: dict) -> None:
    await target.answer(_matn(p), reply_markup=_klaviatura(p))


@router.message(F.text == BTN_ONBOARDING)
async def my_onboarding(message: Message) -> None:
    try:
        p = await api_client.my_onboarding(message.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Onboarding rejasini olishda xato")
        await message.answer("Hozir ochib bo'lmadi — keyinroq urinib ko'ring.")
        return
    if not p:
        await message.answer(
            "📋 Sizda faol onboarding rejasi yo'q.\n\n"
            "Yangi xodim uchun reja ishga qabul qilinganda ochiladi."
        )
        return
    await _korsat(message, p)


@router.callback_query(F.data.startswith("onb:done:"))
async def mark_done(callback: CallbackQuery) -> None:
    item_id = int(callback.data.split(":")[2])
    try:
        p = await api_client.onboarding_mark_done(callback.from_user.id, item_id)
    except Exception:  # noqa: BLE001
        logger.exception("Onboarding qadamini belgilashda xato")
        await callback.answer("Belgilab bo'lmadi", show_alert=True)
        return

    await callback.answer("✅ Belgilandi")
    #  Ro'yxatni YANGILAB qo'yamiz — xodim nima qolganini darhol ko'rsin.
    try:
        await callback.message.edit_text(_matn(p), reply_markup=_klaviatura(p))
    except Exception:  # noqa: BLE001
        #  Matn o'zgarmagan bo'lsa Telegram xato beradi — bu muhim emas.
        logger.debug("Ro'yxatni yangilab bo'lmadi", exc_info=True)

    if p.get("status") == "done":
        await callback.message.answer(
            "🎉 <b>Barcha qadam bajarildi!</b>\n\n"
            "Onboarding tugadi. HR ga xabar berildi."
        )
