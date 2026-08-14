"""E'tiroz va shikoyatlar — bot (KUNDALIK_ETIROZ_REJASI.md, Bosqich 5).

Ikki mustaqil oqim:

1. **Yozish** (xodim): «⚖️ E'tiroz / Shikoyat» →
   - E'tiroz: mavzu (davomat/oylik) → nishon (API bergan kunlar ro'yxati yoki
     oxirgi payslip davri) → matn → yuboriladi;
   - Shikoyat: mavzu → «Kimga» (HR/Boshliq) → anonimmi → matn → ixtiyoriy
     rasm/hujjat → yuboriladi.

2. **Qaror** (HR/Boshliq/Dasturchi): xabardagi «🔎 O'rganyapman» / «✅ Hal
   qilish» tugmalari → qaror turi → izoh (majburiy) → API.

NOZIK JOYLAR (loyihaning jonli saboqlari):
  - `callback_data` da UZUN ma'lumot YO'Q — hammasi FSM'da (`anketa.py:441`:
    64 baytlik chegara). Bu yerda callback'lar qisqa literal yoki `id`.
  - FSM ma'lumoti JSON-mos bo'lishi shart (webhook rejimida bazaga tushadi,
    `api/services/fsm_storage.py:45`) — sanalar `isoformat()` str sifatida.
  - Har matn-kutuvchi handlerda `~F.text.in_(ALL_MENU_BUTTONS)` — aks holda
    menyu tugmasining MATNI murojaat/izoh bo'lib ketardi (UX2-W4/C3).
"""
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import (
    ALL_MENU_BUTTONS,
    BTN_APPEAL,
    BTN_CANCEL,
    BTN_REQUESTS,
    cancel_menu,
    menu_for_user,
)

router = Router(name="appeal")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

MIN_TEXT = 10
MAX_TEXT = 3000
MIN_NOTE = 5

DECIDE_ROLES = {"hr", "boss", "dasturchi"}

_STATUS_LABELS = {
    "pending": "🕓 Ko'rib chiqilmoqda",
    "in_review": "🔎 O'rganilmoqda",
    "accepted": "✅ Qondirildi",
    "rejected": "❌ Rad etildi",
    "resolved": "✅ Hal qilindi",
}
_KIND_LABELS = {"objection": "E'tiroz", "complaint": "Shikoyat"}
_TOPIC_LABELS = {
    "attendance": "Davomat",
    "payroll": "Oylik",
    "work_env": "Ish sharoiti",
    "team": "Jamoa",
    "other": "Boshqa",
}
_ATT_STATUS = {"late": "kechikish", "absent": "kelmagan"}


class AppealFSM(StatesGroup):
    """Yozish oqimi. Bosqichlar orasida ma'lumot `state.update_data` da
    to'planadi (callback_data'da emas)."""

    waiting_text = State()
    waiting_file = State()


class AppealDecideFSM(StatesGroup):
    waiting_note = State()


def _local_dm(iso: str) -> str:
    """Naive-UTC ISO → mahalliy "dd.MM" (lead_stats.py naqshi)."""
    try:
        return f"{datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ):%d.%m}"
    except (TypeError, ValueError):
        return "--.--"


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Ariza yozish", callback_data="request:new")],
            [InlineKeyboardButton(text="📣 E'tiroz bildirish", callback_data="appeal:new:objection")],
            [InlineKeyboardButton(text="📨 Shikoyat yozish", callback_data="appeal:new:complaint")],
            [InlineKeyboardButton(text="📋 Mening murojaatlarim", callback_data="appeal:my")],
        ]
    )


# Ikkala matn ham ushlanadi: `BTN_APPEAL` — xodim qurilmasidagi ESKI
# klaviatura keshi (Telegram uni o'zi yangilamaydi), `BTN_REQUESTS` — yangi.
@router.message(F.text == BTN_REQUESTS)
@router.message(F.text == BTN_APPEAL)
async def show_appeal_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "📮 <b>Murojaatlarim</b>\n\n"
        "<b>Ariza</b> — kelajakka so'rov: ta'til, avans, ma'lumotnoma.\n"
        "<b>E'tiroz</b> — allaqachon chiqarilgan qarorga qarshi (kechikish "
        "jarimasi, kelmagan kun, oylik hisobi).\n"
        "<b>Shikoyat</b> — erkin mavzu (ish sharoiti, jamoa). Xohlasangiz "
        "anonim yuborasiz.",
        reply_markup=_start_kb(),
    )


@router.callback_query(F.data == "appeal:my")
async def show_my_appeals(callback: CallbackQuery) -> None:
    items = await api_client.appeal_my_list(callback.from_user.id)
    if items is None:
        await callback.answer("Siz tizimda ro'yxatdan o'tmagansiz.", show_alert=True)
        return
    if not items:
        await callback.message.answer("Hozircha murojaat yubormagansiz.")
        await callback.answer()
        return

    lines = ["📋 <b>Mening murojaatlarim</b>", ""]
    for it in items:
        head = f"{_KIND_LABELS.get(it['kind'], it['kind'])} · {_TOPIC_LABELS.get(it['topic'], it['topic'])}"
        lines.append(
            f"{_local_dm(it['created_at'])} — {head}\n"
            f"{_STATUS_LABELS.get(it['status'], it['status'])}"
        )
        if it.get("decision_note"):
            lines.append(f"<i>Javob: {html.escape(it['decision_note'])}</i>")
        lines.append("")
    await callback.message.answer("\n".join(lines).strip())
    await callback.answer()


# ─── Yozish oqimi: tur → mavzu ────────────────────────────────────────────────


@router.callback_query(F.data.startswith("appeal:new:"))
async def choose_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    await state.clear()
    await state.update_data(kind=kind)

    if kind == "objection":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🕐 Davomat (kechikish/kelmagan kun)",
                                      callback_data="appeal:topic:attendance")],
                [InlineKeyboardButton(text="💵 Oylik hisobi", callback_data="appeal:topic:payroll")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")],
            ]
        )
        text = "E'tirozingiz nima haqida?"
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏢 Ish sharoiti", callback_data="appeal:topic:work_env")],
                [InlineKeyboardButton(text="👥 Jamoa / munosabatlar", callback_data="appeal:topic:team")],
                [InlineKeyboardButton(text="📝 Boshqa", callback_data="appeal:topic:other")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")],
            ]
        )
        text = "Shikoyatingiz nima haqida?"
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "appeal:cancel")
async def cancel_inline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.message(StateFilter(AppealFSM.waiting_text), F.text == BTN_CANCEL)
@router.message(StateFilter(AppealFSM.waiting_file), F.text == BTN_CANCEL)
@router.message(StateFilter(AppealDecideFSM.waiting_note), F.text == BTN_CANCEL)
async def cancel_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.callback_query(F.data.startswith("appeal:topic:"))
async def choose_topic(callback: CallbackQuery, state: FSMContext) -> None:
    topic = callback.data.split(":")[2]
    data = await state.get_data()
    kind = data.get("kind")
    if not kind:
        await callback.answer("Sessiya eskirgan — «⚖️ E'tiroz / Shikoyat» ni qayta bosing.", show_alert=True)
        return
    await state.update_data(topic=topic)

    if kind == "objection" and topic == "attendance":
        targets = await api_client.appeal_attendance_targets(callback.from_user.id)
        if not targets:
            await callback.message.edit_text(
                "Oxirgi 30 kunda kechikish yoki kelmagan kun topilmadi — "
                "e'tiroz bildirish uchun asos yo'q.\n\n"
                "Agar davomat yozuvi noto'g'ri deb hisoblasangiz, «📨 Shikoyat» "
                "orqali yozing."
            )
            await state.clear()
            await callback.answer()
            return
        # Sana FSM'ga emas, callback'ga: u qisqa (10 belgi) va tanlov bir
        # bosqichli. Ro'yxatning o'zi ham FSM'ga tushmaydi.
        rows = [
            [InlineKeyboardButton(
                text=f"{t['date']} — {_ATT_STATUS.get(t['status'], t['status'])}"
                     + (f" ({t['late_minutes']} daq)" if t["late_minutes"] else ""),
                callback_data=f"appeal:day:{t['date']}",
            )]
            for t in targets[:20]
        ]
        rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")])
        await callback.message.edit_text(
            "Qaysi kun bo'yicha e'tiroz bildirasiz?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await callback.answer()
        return

    if kind == "objection" and topic == "payroll":
        await callback.message.edit_text(
            "Qaysi oy uchun? Davrni <code>YYYY-MM</code> ko'rinishida yozing "
            "(masalan 2026-07)."
        )
        await state.set_state(AppealFSM.waiting_text)
        await state.update_data(stage="period")
        await callback.message.answer("Davrni yozing:", reply_markup=cancel_menu())
        await callback.answer()
        return

    # Shikoyat: kimga yuborishni xodim o'zi tanlaydi (shikoyat HR haqida
    # bo'lishi mumkin — backend ham shu tanlovni hurmat qiladi).
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 HR ga", callback_data="appeal:to:hr")],
            [InlineKeyboardButton(text="👔 Boshliqqa", callback_data="appeal:to:boss")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")],
        ]
    )
    await callback.message.edit_text("Shikoyatingiz kimga borsin?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("appeal:day:"))
async def choose_day(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(ref_date=callback.data.split(":", 2)[2])
    await state.set_state(AppealFSM.waiting_text)
    await state.update_data(stage="text")
    await callback.message.edit_text(f"Tanlandi: {callback.data.split(':', 2)[2]}")
    await callback.message.answer(
        "Endi e'tirozingizni yozing — nima uchun bu qaror noto'g'ri deb "
        f"hisoblaysiz (kamida {MIN_TEXT} belgi).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("appeal:to:"))
async def choose_recipient(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(recipient_role=callback.data.split(":")[2])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🙈 Anonim yuborish", callback_data="appeal:anon:1")],
            [InlineKeyboardButton(text="🙂 Ismim bilan", callback_data="appeal:anon:0")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")],
        ]
    )
    await callback.message.edit_text(
        "Shikoyatni qanday yuboramiz?\n\n"
        "<i>Anonim yuborilsa qabul qiluvchi ismingizni ko'rmaydi.</i>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("appeal:anon:"))
async def choose_anon(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(is_anonymous=callback.data.split(":")[2] == "1")
    await state.set_state(AppealFSM.waiting_text)
    await state.update_data(stage="text")
    await callback.message.edit_text("Yaxshi.")
    await callback.message.answer(
        f"Endi shikoyatingizni yozing (kamida {MIN_TEXT} belgi).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


# ─── Matn bosqichi (davr yoki murojaat matni) ──────────────────────────────────


@router.message(StateFilter(AppealFSM.waiting_text), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def receive_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()

    # Oylik e'tirozida avval DAVR so'raladi — bir xil holat, ikki bosqich
    # (`stage`), chunki ikkalasi ham erkin matn.
    if data.get("stage") == "period":
        if len(text) != 7 or text[4] != "-" or not text[:4].isdigit() or not text[5:].isdigit():
            await message.answer(
                "Davr formati noto'g'ri. <code>YYYY-MM</code> ko'rinishida yozing "
                "(masalan 2026-07).",
                reply_markup=cancel_menu(),
            )
            return  # holat SAQLANADI — qayta yozsin
        await state.update_data(ref_period=text, stage="text")
        await message.answer(
            "Endi e'tirozingizni yozing — oylik hisobida nima noto'g'ri deb "
            f"hisoblaysiz (kamida {MIN_TEXT} belgi).",
            reply_markup=cancel_menu(),
        )
        return

    if len(text) < MIN_TEXT:
        await message.answer(
            f"Juda qisqa — kamida {MIN_TEXT} belgi yozing. Qabul qiluvchi "
            "muammoni tushunishi kerak.",
            reply_markup=cancel_menu(),
        )
        return
    if len(text) > MAX_TEXT:
        await message.answer(
            f"Juda uzun ({len(text)} belgi). Ko'pi bilan {MAX_TEXT} belgi.",
            reply_markup=cancel_menu(),
        )
        return

    await state.update_data(text=text)

    # Shikoyatga ixtiyoriy ilova (skrinshot/hujjat). E'tirozda so'ralmaydi:
    # u allaqachon aniq yozuvga (kun/davr) bog'langan.
    if data.get("kind") == "complaint":
        await state.set_state(AppealFSM.waiting_file)
        await message.answer(
            "Rasm yoki hujjat biriktirasizmi? Yuboring yoki «O'tkazib yuborish»ni bosing.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="➡️ O'tkazib yuborish", callback_data="appeal:nofile")]
                ]
            ),
        )
        return

    await _submit(message, state)


@router.message(StateFilter(AppealFSM.waiting_text), ~F.text)
async def non_text_stage(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


# ─── Ilova bosqichi (faqat shikoyat) ──────────────────────────────────────────


@router.callback_query(StateFilter(AppealFSM.waiting_file), F.data == "appeal:nofile")
async def skip_file(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("Ilovasiz yuborilmoqda...")
    await _submit(callback.message, state, actor_id=callback.from_user.id)
    await callback.answer()


@router.message(StateFilter(AppealFSM.waiting_file), F.photo | F.document)
async def receive_file(message: Message, state: FSMContext) -> None:
    if message.photo:
        # Telegram bir nechta o'lchamda yuboradi — oxirgisi eng katta.
        await state.update_data(file_id=message.photo[-1].file_id, file_type="photo")
    else:
        await state.update_data(file_id=message.document.file_id, file_type="document")
    await _submit(message, state)


@router.message(StateFilter(AppealFSM.waiting_file), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def file_stage_text(message: Message) -> None:
    await message.answer(
        "Rasm/hujjat yuboring yoki «O'tkazib yuborish» tugmasini bosing.",
        reply_markup=cancel_menu(),
    )


async def _submit(message: Message, state: FSMContext, actor_id: int | None = None) -> None:
    """Yig'ilgan ma'lumotni API'ga yuboradi.

    `actor_id` — callback orqali chaqirilganda kerak: u yerda `message.from_user`
    BOTNING o'zi bo'ladi (xabarni bot yuborgan), xodim emas."""
    data = await state.get_data()
    telegram_id = actor_id or message.from_user.id
    await state.clear()

    payload = {
        "kind": data.get("kind"),
        "topic": data.get("topic"),
        "text": data.get("text", ""),
        "is_anonymous": bool(data.get("is_anonymous")),
        "recipient_role": data.get("recipient_role", "hr"),
        "ref_date": data.get("ref_date"),
        "ref_period": data.get("ref_period"),
        "file_id": data.get("file_id"),
        "file_type": data.get("file_type"),
    }

    user = await api_client.get_user_by_telegram(telegram_id)
    try:
        await api_client.appeal_create(telegram_id, payload)
    except httpx.HTTPStatusError as exc:
        detail = "Xatolik yuz berdi."
        try:
            body = exc.response.json()
            detail = body.get("detail", detail)
            if isinstance(detail, list) and detail:  # 422 — pydantic ro'yxati
                detail = detail[0].get("msg", "Ma'lumot noto'g'ri")
        except Exception:
            pass
        await message.answer(f"⚠️ {detail}", reply_markup=menu_for_user(user))
        return
    except Exception:
        await message.answer(
            "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    who = "Boshliqqa" if payload["recipient_role"] == "boss" else "HR ga"
    await message.answer(
        f"✅ Murojaatingiz {who} yuborildi.\n"
        "Ko'rib chiqilgach shu yerda javob olasiz. Holatini «📋 Mening "
        "murojaatlarim» dan kuzatib borishingiz mumkin.",
        reply_markup=menu_for_user(user),
    )


# ─── Payslip xabaridagi «⚖️ E'tiroz» tugmasi ──────────────────────────────────


@router.callback_query(F.data.startswith("appeal_payslip:"))
async def appeal_from_payslip(callback: CallbackQuery, state: FSMContext) -> None:
    """Oylik tasdiqlanganda keladigan shaxsiy xabardan bir bosishda e'tiroz —
    davr oldindan to'ldirilgan holda (OYLIK_JARIMA_REJASI.md 1.5-band qarzi)."""
    period = callback.data.split(":", 1)[1]
    await state.clear()
    await state.update_data(
        kind="objection", topic="payroll", ref_period=period, stage="text"
    )
    await state.set_state(AppealFSM.waiting_text)
    await callback.message.answer(
        f"⚖️ <b>{period} oyligi bo'yicha e'tiroz</b>\n\n"
        f"Nima noto'g'ri deb hisoblaysiz? Batafsil yozing (kamida {MIN_TEXT} belgi).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


# ─── Qaror oqimi (HR / Boshliq / Dasturchi) ───────────────────────────────────


def _appeal_error(exc: httpx.HTTPStatusError) -> str:
    if exc.response.status_code == 403:
        return "Bu amal uchun ruxsatingiz yo'q."
    if exc.response.status_code == 404:
        return "Murojaat topilmadi."
    if exc.response.status_code == 400:
        return "Bu murojaat allaqachon hal qilingan."
    return "Xatolik yuz berdi."


@router.callback_query(F.data.startswith("appeal_review:"))
async def on_review(callback: CallbackQuery) -> None:
    item_id = int(callback.data.split(":")[1])
    try:
        await api_client.appeal_review(item_id, callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        await callback.answer(_appeal_error(exc), show_alert=True)
        return

    # Xabar matni saqlanadi (murojaat mazmuni kerak), faqat klaviatura
    # yangilanadi: «O'rganyapman» endi kerak emas, «Hal qilish» qoladi.
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Hal qilish", callback_data=f"appeal_decide:{item_id}")]
            ]
        )
    )
    await callback.answer("Xodimga «ko'rib chiqilmoqda» deb xabar berildi.")


@router.callback_query(F.data.startswith("appeal_decide:"))
async def on_decide_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Qaror turini so'raymiz. Murojaat turi (e'tiroz/shikoyat) callback'da
    yo'q, shuning uchun ikkala variantni ham beramiz — mos kelmasa backend
    400 qaytaradi va foydalanuvchi aniq xabar oladi."""
    item_id = int(callback.data.split(":")[1])
    await state.clear()
    await state.update_data(appeal_id=item_id)
    await callback.message.answer(
        "Qaror qanday?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Qondirish (e'tiroz)", callback_data="appeal:v:accepted")],
                [InlineKeyboardButton(text="✔️ Hal qilindi (shikoyat)", callback_data="appeal:v:resolved")],
                [InlineKeyboardButton(text="❌ Rad etish", callback_data="appeal:v:rejected")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="appeal:cancel")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("appeal:v:"))
async def on_decide_verdict(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("appeal_id"):
        await callback.answer("Sessiya eskirgan — xabardagi tugmani qayta bosing.", show_alert=True)
        return
    await state.update_data(decision=callback.data.split(":")[2])
    await state.set_state(AppealDecideFSM.waiting_note)
    await callback.message.edit_text("Endi qarorning IZOHINI yozing.")
    await callback.message.answer(
        f"Izoh xodimga to'liq ko'rinadi — nega shunday qaror qilinganini "
        f"tushuntiring (kamida {MIN_NOTE} belgi).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(AppealDecideFSM.waiting_note), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def on_decide_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if len(note) < MIN_NOTE:
        await message.answer(
            f"Juda qisqa — kamida {MIN_NOTE} belgi. Xodim nega shunday "
            "qaror qilinganini bilishi kerak.",
            reply_markup=cancel_menu(),
        )
        return  # holat SAQLANADI

    data = await state.get_data()
    item_id, decision = data.get("appeal_id"), data.get("decision")
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not item_id or not decision:
        await message.answer(
            "Sessiya topilmadi. Xabardagi tugmani qayta bosing.",
            reply_markup=menu_for_user(user),
        )
        return

    try:
        result = await api_client.appeal_decide(item_id, message.from_user.id, decision, note)
    except httpx.HTTPStatusError as exc:
        detail = _appeal_error(exc)
        try:
            body = exc.response.json()
            if isinstance(body.get("detail"), str):
                detail = body["detail"]
        except Exception:
            pass
        await message.answer(f"⚠️ {detail}", reply_markup=menu_for_user(user))
        return
    except Exception:
        await message.answer(
            "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    lines = ["✅ Qaror saqlandi, xodimga xabar yuborildi."]
    # `next_step` — e'tiroz QONDIRILGANDA keladi. Bu modul hech narsani
    # o'zi hisoblamaydi, shuning uchun tuzatishni qo'lda kiritish kerakligi
    # aynan shu yerda eslatiladi (aks holda qaror "qog'ozda" qolib ketardi).
    if result.get("next_step"):
        lines.append("")
        lines.append(f"📌 <b>Keyingi qadam:</b> {result['next_step']}")
    await message.answer("\n".join(lines), reply_markup=menu_for_user(user))


@router.message(StateFilter(AppealDecideFSM.waiting_note), ~F.text)
async def non_text_note(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())
