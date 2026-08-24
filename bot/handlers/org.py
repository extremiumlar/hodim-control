"""«Mening o'rnim» — xodim tomoni, bot (yangi TZ 3.16 / S-41).

Bir xabarda to'rt narsa: tuzilmadagi o'rni (rahbarim → men →
menga bo'ysunadiganlar), lavozim yo'riqnomasi, kuzatiladigan
ko'rsatkichlari va «✅ Tanishdim» tugmasi.

⚠️ FSM ISHLATILMAYDI. Bu yerda kutiladigan matn yo'q — faqat
ko'rsatish va bitta tugma. Tanishuv holati BAZADA
(`acknowledgements`), inline tugmada esa hech qanday holat
saqlanmaydi.

⚠️ BUTUN SXEMA BOTDA CHIQARILMAYDI. TZ botdan «sxemadagi O'Z
o'rni» ni so'raydi, butun daraxtni emas: 20-30 tugunli daraxt
Telegram xabarida o'qilmaydigan bo'lib ketardi. Butun sxemani
xodim saytdagi «Mening o'rnim» sahifasida ko'radi.

⚠️ ISH HAQI VA BAHO BU YERGA HECH QACHON QO'SHILMAYDI (TZ 3.16
qabul mezoni) — server ham ularni bermaydi, bot ham so'ramaydi.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_MY_PLACE

router = Router(name="org")
logger = logging.getLogger(__name__)

#  Telegram bitta xabarda 4096 belgidan ko'pini qabul qilmaydi.
#  Yo'riqnoma uzun bo'lishi mumkin, shuning uchun kesamiz.
_MAX_MATN = 3500


def _royxat(sarlavha: str, bandlar: list) -> str:
    if not bandlar:
        return ""
    qatorlar = "\n".join(f"  • {str(b)}" for b in bandlar)
    return f"\n\n<b>{sarlavha}</b>\n{qatorlar}"


def _matn(p: dict) -> str:
    men = p.get("me") or {}
    lavozim = men.get("position") or {}
    q = [f"🏢 <b>{men.get('full_name', '')}</b>"]
    q.append(
        f"Lavozim: {lavozim.get('name')}" if lavozim.get("name")
        else "Lavozim: <i>belgilanmagan</i>"
    )

    rahbar = p.get("manager")
    q.append(
        f"Rahbarim: {rahbar['full_name']}" if rahbar
        else "Rahbarim: <i>belgilanmagan</i>"
    )

    boysunuvchilar = p.get("subordinates") or []
    if boysunuvchilar:
        q.append(f"Menga bo'ysunadiganlar: {len(boysunuvchilar)} ta")
        q.append("\n".join(f"  • {u['full_name']}" for u in boysunuvchilar))

    korsatkichlar = p.get("metrics") or []
    if korsatkichlar:
        q.append("\n<b>Kuzatiladigan ko'rsatkichlarim</b>")
        q.append("\n".join(f"  • {m['label']}" for m in korsatkichlar))

    matn = "\n".join(q)

    y = p.get("description")
    if not y:
        matn += (
            "\n\n⚠️ Lavozimingiz uchun yo'riqnoma hali kiritilmagan — "
            "HR ga ayting."
        )
        return matn[:_MAX_MATN]

    matn += f"\n\n📋 <b>Yo'riqnoma</b> (v{y['version']}"
    if y.get("effective_from"):
        matn += f", {y['effective_from']} dan"
    matn += ")"
    if y.get("purpose"):
        matn += f"\n<i>{y['purpose']}</i>"
    matn += _royxat("Vazifalarim", y.get("duties") or [])
    matn += _royxat("Huquqlarim", y.get("rights") or [])
    matn += _royxat("Javobgarligim", y.get("responsibility") or [])
    matn += _royxat("Talablar", y.get("requirements") or [])

    tanishuv = p.get("acknowledgement") or {}
    if tanishuv.get("acknowledged"):
        matn += "\n\n✅ Siz bu yo'riqnoma bilan tanishgansiz."
    else:
        matn += "\n\n⬇️ Yo'riqnomani o'qib, «Tanishdim» tugmasini bosing."
    return matn[:_MAX_MATN]


def _klaviatura(p: dict) -> InlineKeyboardMarkup | None:
    """«Tanishdim» — faqat yo'riqnoma bor va hali tanishmagan bo'lsa."""
    if not p.get("description"):
        return None
    tanishuv = p.get("acknowledgement") or {}
    if tanishuv.get("acknowledged"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tanishdim", callback_data="org:ack")
    ]])


@router.message(F.text == BTN_MY_PLACE)
async def my_place(message: Message) -> None:
    try:
        p = await api_client.my_place(message.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("«Mening o'rnim» ni olishda xato")
        await message.answer("Hozir ochib bo'lmadi — keyinroq urinib ko'ring.")
        return
    if p is None:
        await message.answer("Ma'lumot topilmadi — HR ga ayting.")
        return
    await message.answer(_matn(p), reply_markup=_klaviatura(p))


@router.callback_query(F.data == "org:ack")
async def acknowledge(callback: CallbackQuery) -> None:
    """«Tanishdim» — sayt bilan BITTA endpoint, ya'ni bitta holat."""
    try:
        natija = await api_client.acknowledge_instruction(callback.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Tanishuvni qayd etishda xato")
        await callback.answer("Qayd etib bo'lmadi", show_alert=True)
        return

    if not natija.get("ok"):
        await callback.answer("Qayd etib bo'lmadi", show_alert=True)
        return

    #  ⚠️ Tugmani OLIB TASHLAYMIZ. Aks holda xodim uni qayta bosardi va
    #  «tanishdim» sanasi yangilanmasa ham (server IDEMPOTENT) tugma
    #  ishlamayotgandek ko'rinardi.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        logger.debug("Tugmani olib tashlab bo'lmadi", exc_info=True)
    await callback.answer(
        f"✅ Tanishdingiz (v{natija.get('version')})", show_alert=True
    )
