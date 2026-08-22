"""O'quv paneli — xodim tomoni, bot (yangi TZ 3.1 / S-35).

Oqim: «📚 Darsliklarim» → tayinlangan kurslar → ketma-ket material
(«Ko'rdim, keyingisi») → test → natija (foiz, o'tdi/o'tmadi, qayta
urinish).

⚠️ FSM ISHLATILMAYDI. Butun holat BAZADA (`current_material`,
`current_q`) — bot restart bo'lsa ham xodim qolgan joyidan davom
etadi (S-35 qabul mezoni). Inline tugmalarda `assignment_id` bor,
ya'ni xotirada hech narsa saqlanmaydi.

⚠️ OCHIQ savol javobi — anketa protokoli bo'yicha: erkin matn
`/courses/bot/answer-text` ga boradi, u BAZADAN javob kutilayotganini
aniqlaydi va `{"handled": bool}` qaytaradi. Mos holat bo'lmasa xabar
keyingi oqimlarga (AI sabab va h.k.) o'tadi — kurs oqimi boshqa
modullarning matnini o'g'irlab qolmasin.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_MY_COURSES

router = Router(name="courses")
logger = logging.getLogger(__name__)

#  Telegram inline klaviaturasi juda uzun bo'lsa xabar UMUMAN
#  yuborilmaydi — kurslar ro'yxati bo'laklanadi.
_MAX_COURSES = 10


def _holat_belgisi(k: dict) -> str:
    if k.get("passed"):
        return "✅"
    if k.get("pending_review"):
        return "🕓"
    if k.get("status") == "finished":
        return "❌"
    if k.get("status") == "in_progress":
        return "▶️"
    return "🆕"


@router.message(F.text == BTN_MY_COURSES)
async def my_courses(message: Message) -> None:
    try:
        kurslar = await api_client.my_courses(message.from_user.id)
    except Exception:  # noqa: BLE001
        logger.exception("Kurslarni olishda xato")
        await message.answer("Hozir ochib bo'lmadi — keyinroq urinib ko'ring.")
        return

    if not kurslar:
        await message.answer(
            "📚 Sizga hali kurs tayinlanmagan.\n\n"
            "Kurs tayinlanganda shu yerda ko'rinadi."
        )
        return

    lines = ["📚 <b>Darsliklarim</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for k in kurslar[:_MAX_COURSES]:
        belgi = _holat_belgisi(k)
        qator = f"{belgi} {k['title']}"
        if k.get("is_mandatory"):
            qator += " · <b>majburiy</b>"
        if k.get("due_date"):
            qator += f" · muddat {k['due_date']}"
        if k.get("percent") is not None:
            qator += f" · {k['percent']}%"
        lines.append(qator)
        rows.append([
            InlineKeyboardButton(
                text=f"{belgi} {k['title'][:40]}",
                callback_data=f"crs:open:{k['assignment_id']}",
            )
        ])
    if len(kurslar) > _MAX_COURSES:
        lines.append(f"\n… va yana {len(kurslar) - _MAX_COURSES} ta")
    await message.answer(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


def _material_matni(p: dict) -> str:
    band = p.get("item") or {}
    bosh = (
        f"📖 <b>{band.get('title', '')}</b>\n"
        f"<i>Material {p['material_index'] + 1}/{p['material_total']}</i>"
    )
    if band.get("body"):
        bosh += f"\n\n{band['body'][:3000]}"
    if band.get("url"):
        bosh += f"\n\n🔗 {band['url']}"
    return bosh


def _savol_matni(p: dict) -> str:
    band = p.get("item") or {}
    matn = (
        f"❓ <b>Savol {p['question_index'] + 1}/{p['question_total']}</b>"
        f" · {band.get('points', 1)} ball\n\n{band.get('text', '')}"
    )
    if band.get("is_open"):
        matn += "\n\n<i>Javobingizni matn bilan yozing.</i>"
    return matn


def _bosqich_klaviaturasi(p: dict) -> InlineKeyboardMarkup | None:
    aid = p["assignment_id"]
    if p["stage"] == "material":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Ko'rdim, keyingisi", callback_data=f"crs:next:{aid}"
            )
        ]])
    if p["stage"] == "savol":
        band = p.get("item") or {}
        variantlar = band.get("options") or []
        if variantlar:
            #  Har variant alohida qatorda — matn uzun bo'lishi mumkin.
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=v[:60], callback_data=f"crs:ans:{aid}:{i}")]
                for i, v in enumerate(variantlar)
            ])
        return None  # ochiq savol — matn kutiladi
    if p["stage"] == "tugadi":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏁 Yakunlash", callback_data=f"crs:fin:{aid}")
        ]])
    return None


async def _bosqichni_korsat(target, p: dict) -> None:
    """Joriy bosqichni chiqaradi (material / savol / yakunlash)."""
    if p["stage"] == "material":
        band = p.get("item") or {}
        klav = _bosqich_klaviaturasi(p)
        #  ⚠️ Fayl SERVERDAN emas, Telegram `file_id` bilan yuboriladi —
        #  u allaqachon Telegram'da turibdi, biz faqat ko'rsatamiz.
        try:
            if band.get("kind") == "video" and band.get("file_id"):
                await target.answer_video(band["file_id"], caption=_material_matni(p),
                                          reply_markup=klav)
                return
            if band.get("kind") == "photo" and band.get("file_id"):
                await target.answer_photo(band["file_id"], caption=_material_matni(p),
                                          reply_markup=klav)
                return
            if band.get("kind") == "document" and band.get("file_id"):
                await target.answer_document(band["file_id"], caption=_material_matni(p),
                                             reply_markup=klav)
                return
        except Exception:  # noqa: BLE001
            #  Fayl o'chirilgan yoki `file_id` boshqa botga tegishli
            #  bo'lishi mumkin — kurs SHU YERDA to'xtab qolmasin.
            logger.exception("Material faylini yuborib bo'lmadi")
            await target.answer(
                _material_matni(p) + "\n\n⚠️ Faylni ochib bo'lmadi — HR ga ayting.",
                reply_markup=klav,
            )
            return
        await target.answer(_material_matni(p), reply_markup=klav)
        return

    if p["stage"] == "savol":
        await target.answer(_savol_matni(p), reply_markup=_bosqich_klaviaturasi(p))
        return

    await target.answer(
        "✅ Barcha material va savollar tugadi.\nNatijani olish uchun yakunlang.",
        reply_markup=_bosqich_klaviaturasi(p),
    )


@router.callback_query(F.data.startswith("crs:open:"))
async def open_course(callback: CallbackQuery) -> None:
    aid = int(callback.data.split(":")[2])
    try:
        p = await api_client.course_progress(callback.from_user.id, aid)
    except Exception:  # noqa: BLE001
        logger.exception("Kurs holatini olishda xato")
        await callback.answer("Ochib bo'lmadi", show_alert=True)
        return
    if p.get("status") == "finished":
        await callback.message.answer(
            "Bu kurs yakunlangan. Natijani «Darsliklarim» ro'yxatida ko'rasiz."
        )
        await callback.answer()
        return
    await _bosqichni_korsat(callback.message, p)
    await callback.answer()


@router.callback_query(F.data.startswith("crs:next:"))
async def next_material(callback: CallbackQuery) -> None:
    aid = int(callback.data.split(":")[2])
    try:
        p = await api_client.course_next_material(callback.from_user.id, aid)
    except Exception:  # noqa: BLE001
        logger.exception("Keyingi materialga o'tishda xato")
        await callback.answer("Hozir bo'lmadi", show_alert=True)
        return
    #  Tugma olib tashlanadi — ikki marta bosib, ikki material
    #  o'tkazib yuborilmasin.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await _bosqichni_korsat(callback.message, p)
    await callback.answer()


@router.callback_query(F.data.startswith("crs:ans:"))
async def answer_choice(callback: CallbackQuery) -> None:
    _, _, aid, choice = callback.data.split(":")
    try:
        p = await api_client.course_answer(
            callback.from_user.id, int(aid), choice=int(choice)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Javobni yuborishda xato")
        await callback.answer("Hozir bo'lmadi", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    #  ⚠️ To'g'ri/noto'g'ri DARHOL aytilmaydi — xodim savollarni ketma-ket
    #  o'tsin, natija yakunda chiqadi. Aks holda u noto'g'ri javobdan keyin
    #  kursni tashlab ketishi mumkin.
    await callback.answer("Javob qabul qilindi")
    await _bosqichni_korsat(callback.message, p)


@router.callback_query(F.data.startswith("crs:fin:"))
async def finish_course(callback: CallbackQuery) -> None:
    aid = int(callback.data.split(":")[2])
    try:
        r = await api_client.course_finish(callback.from_user.id, aid)
    except Exception:  # noqa: BLE001
        logger.exception("Kursni yakunlashda xato")
        await callback.answer("Hozir bo'lmadi", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass

    if r.get("pending_review"):
        matn = (
            f"🕓 <b>Javoblaringiz qabul qilindi</b>\n"
            f"Ball: {r['score']}/{r['max_score']}\n\n"
            "Ochiq savollar bor — ularni HR ko'rib chiqadi va yakuniy "
            "natija shundan keyin ma'lum bo'ladi."
        )
        await callback.message.answer(matn)
        await callback.answer()
        return

    belgi = "🎉" if r["passed"] else "❌"
    matn = (
        f"{belgi} <b>Natija: {r['percent']}%</b>\n"
        f"Ball: {r['score']}/{r['max_score']} · "
        f"o'tish chegarasi {r.get('pass_percent')}%\n"
        f"Urinish: {r['attempt_no']}\n\n"
        + ("Tabriklaymiz, kurs o'tildi!" if r["passed"] else "Afsuski, chegaradan o'tmadi.")
    )
    klav = None
    if r.get("can_retry"):
        matn += "\n\nQayta urinib ko'rishingiz mumkin."
        klav = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Qayta urinish", callback_data=f"crs:try:{aid}")
        ]])
    elif not r["passed"]:
        matn += "\n\n⚠️ Urinishlar tugadi — HR bilan bog'laning."
    await callback.message.answer(matn, reply_markup=klav)
    await callback.answer()


@router.callback_query(F.data.startswith("crs:try:"))
async def retry_course(callback: CallbackQuery) -> None:
    aid = int(callback.data.split(":")[2])
    try:
        p = await api_client.course_retry(callback.from_user.id, aid)
    except Exception:  # noqa: BLE001
        logger.exception("Qayta urinishda xato")
        await callback.answer("Hozir bo'lmadi", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await callback.message.answer(f"🔄 {p['attempt_no']}-urinish boshlandi.")
    await _bosqichni_korsat(callback.message, p)
    await callback.answer()


# ═════════════════════════════════════════════════════════════
# OCHIQ SAVOL JAVOBI — anketa protokoli
#
# ⚠️ ALOHIDA router: u `bot/setup.py` da «erkin matn» zanjiriga
# qo'shiladi. Bu yerdagi handler HAR QANDAY matnni ko'radi, lekin
# javob kutilayotganini BAZADAN so'raydi va mos holat bo'lmasa
# `SkipHandler` bilan xabarni keyingi oqimga uzatadi.
#
# Zanjir tartibi MUHIM: kurs javobi AI sabab ushlagichidan OLDIN
# turishi kerak, aks holda ochiq javob AI ga ketib qolardi.
# ═════════════════════════════════════════════════════════════

answer_text_router = Router(name="courses_answer_text")


@answer_text_router.message(F.text, ~F.text.startswith("/"))
async def open_answer(message: Message) -> None:
    from aiogram.dispatcher.event.bases import SkipHandler

    from bot.keyboards import ALL_MENU_BUTTONS

    matn = (message.text or "").strip()
    #  Menyu tugmasi javob EMAS — u boshqa bo'limga o'tish.
    if not matn or matn in ALL_MENU_BUTTONS:
        raise SkipHandler
    try:
        res = await api_client.course_answer_text(message.from_user.id, matn)
    except Exception:  # noqa: BLE001 — kurs oqimi butun botni to'smasin
        logger.exception("Ochiq javobni tekshirishda xato")
        raise SkipHandler from None
    if not res.get("handled"):
        raise SkipHandler
    await message.answer("✅ Javob qabul qilindi.")
    await _bosqichni_korsat(message, res)
