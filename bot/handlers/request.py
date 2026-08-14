"""Arizalar — bot (ARIZALAR_REJASI.md, Bosqich 2).

Kirish nuqtasi «📮 Murojaatlarim» hubida (`bot/handlers/appeal.py`) —
alohida menyu tugmasi QO'SHILMAYDI: menyuda allaqachon 8-10 tugma bor.

Yozish oqimi turga qarab shoxlanadi:
  ta'til/kasallik → boshlanish sanasi → necha kun → KALKULYATOR javobi
                    («10 kundan 8 tasi ish kuni») → sabab → yuborish
  avans           → summa → sabab → yuborish
  qolganlari      → sabab → yuborish

Nozik joylar (loyihaning jonli saboqlari):
  - `callback_data` da uzun ma'lumot YO'Q — hammasi FSM'da (anketa.py:441);
  - FSM'ga faqat JSON-mos tiplar (webhook rejimida bazaga tushadi):
    sanalar `isoformat()` STR ko'rinishida saqlanadi;
  - har matn-kutuvchi handlerda `~F.text.in_(ALL_MENU_BUTTONS)`.
"""
import html
from datetime import date, datetime, timedelta

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import ALL_MENU_BUTTONS, BTN_CANCEL, cancel_menu, menu_for_user

router = Router(name="request")

MIN_REASON = 10
MAX_REASON = 2000
MIN_NOTE = 5
MAX_DAYS = 90  # bot orqali so'raladigan eng uzun oraliq

DECIDE_ROLES = {"hr", "boss", "dasturchi"}

# Turlar — API `RequestKind` bilan bir xil qiymatlar.
LEAVE_KINDS = {"vacation", "unpaid", "sick"}
MONEY_KINDS = {"advance"}

_KIND_LABELS = {
    "vacation": "🏖 Mehnat ta'tili",
    "unpaid": "🚫 O'z hisobidan",
    "sick": "🤒 Kasallik",
    "advance": "💵 Avans",
    "certificate": "📄 Ma'lumotnoma",
    "schedule_change": "🗓 Jadval o'zgartirish",
    "resignation": "🚪 Ishdan bo'shash",
    "other": "📝 Boshqa",
}

_STATUS_LABELS = {
    "pending": "🕓 Ko'rib chiqilmoqda",
    "manager_ok": "👤 Rahbar tasdiqladi",
    "hr_ok": "🧑‍💼 HR tasdiqladi — Boshliq navbati",
    "approved": "✅ Tasdiqlangan",
    "rejected": "❌ Rad etilgan",
    "cancelled": "↩️ Qaytarib olingan",
    "revoked": "↩️ Bekor qilingan",
}


class RequestFSM(StatesGroup):
    waiting_start = State()
    waiting_days = State()
    waiting_amount = State()
    waiting_reason = State()


class RequestDecideFSM(StatesGroup):
    waiting_note = State()


class RequestManagerFSM(StatesGroup):
    """Rahbarning RAD etish izohi. Tasdiqda FSM ishlatilmaydi — bir bosishda
    ketadi, aks holda zanjir sekinlashardi."""

    waiting_note = State()


def _fmt_money(v) -> str:
    try:
        return f"{float(v):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(v)


def _kind_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_KIND_LABELS["vacation"], callback_data="request:k:vacation"),
                InlineKeyboardButton(text=_KIND_LABELS["unpaid"], callback_data="request:k:unpaid"),
            ],
            [
                InlineKeyboardButton(text=_KIND_LABELS["sick"], callback_data="request:k:sick"),
                InlineKeyboardButton(text=_KIND_LABELS["advance"], callback_data="request:k:advance"),
            ],
            [
                InlineKeyboardButton(text=_KIND_LABELS["certificate"], callback_data="request:k:certificate"),
                InlineKeyboardButton(text=_KIND_LABELS["schedule_change"], callback_data="request:k:schedule_change"),
            ],
            [
                InlineKeyboardButton(text=_KIND_LABELS["resignation"], callback_data="request:k:resignation"),
                InlineKeyboardButton(text=_KIND_LABELS["other"], callback_data="request:k:other"),
            ],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="request:cancel")],
        ]
    )


def _start_date_kb() -> InlineKeyboardMarkup:
    """Sana tanlash — Telegram'da kalendar og'ir, shuning uchun tayyor
    variantlar + qo'lda kiritish imkoni."""
    today = date.today()
    nxt_mon = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ertadan", callback_data=f"request:d:{(today + timedelta(days=1)).isoformat()}"),
                InlineKeyboardButton(text="Dushanbadan", callback_data=f"request:d:{nxt_mon.isoformat()}"),
            ],
            [InlineKeyboardButton(text="Bugundan", callback_data=f"request:d:{today.isoformat()}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="request:cancel")],
        ]
    )


def _days_kb() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=str(n), callback_data=f"request:n:{n}") for n in (1, 3, 5)]
    row2 = [InlineKeyboardButton(text=str(n), callback_data=f"request:n:{n}") for n in (7, 14, 30)]
    return InlineKeyboardMarkup(
        inline_keyboard=[row, row2, [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="request:cancel")]]
    )


# ─── Kirish ────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "request:new")
async def start_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Qanday ariza yozmoqchisiz?", reply_markup=_kind_kb())
    await callback.answer()


@router.callback_query(F.data == "request:cancel")
async def cancel_inline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.message(StateFilter(RequestFSM.waiting_start), F.text == BTN_CANCEL)
@router.message(StateFilter(RequestFSM.waiting_days), F.text == BTN_CANCEL)
@router.message(StateFilter(RequestFSM.waiting_amount), F.text == BTN_CANCEL)
@router.message(StateFilter(RequestFSM.waiting_reason), F.text == BTN_CANCEL)
@router.message(StateFilter(RequestDecideFSM.waiting_note), F.text == BTN_CANCEL)
async def cancel_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.callback_query(F.data.startswith("request:k:"))
async def choose_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    await state.clear()
    await state.update_data(kind=kind)

    if kind in LEAVE_KINDS:
        await state.set_state(RequestFSM.waiting_start)
        await callback.message.edit_text(
            f"{_KIND_LABELS[kind]}\n\nQaysi kundan boshlanadi?",
            reply_markup=_start_date_kb(),
        )
        await callback.message.answer(
            "Tugmalardan tanlang yoki sanani <code>YYYY-MM-DD</code> "
            "ko'rinishida yozing.",
            reply_markup=cancel_menu(),
        )
    elif kind in MONEY_KINDS:
        await state.set_state(RequestFSM.waiting_amount)
        await callback.message.edit_text(f"{_KIND_LABELS[kind]}\n\nQancha summa kerak?")
        await callback.message.answer(
            "Summani raqam bilan yozing (masalan <code>500000</code>).",
            reply_markup=cancel_menu(),
        )
    else:
        await state.set_state(RequestFSM.waiting_reason)
        await callback.message.edit_text(_KIND_LABELS[kind])
        await callback.message.answer(
            f"Arizangiz mazmunini yozing (kamida {MIN_REASON} belgi).",
            reply_markup=cancel_menu(),
        )
    await callback.answer()


# ─── Ta'til: sana → kunlar → kalkulyator ───────────────────────────────────────


async def _ask_days(target: Message, state: FSMContext, start_iso: str) -> None:
    await state.update_data(start_date=start_iso)  # FSM'da faqat STR (JSON-mos)
    await state.set_state(RequestFSM.waiting_days)
    await target.answer(
        f"Boshlanish: {start_iso}\n\nNecha kun? Tugmadan tanlang yoki raqam yozing.",
        reply_markup=_days_kb(),
    )


@router.callback_query(StateFilter(RequestFSM.waiting_start), F.data.startswith("request:d:"))
async def pick_start(callback: CallbackQuery, state: FSMContext) -> None:
    start_iso = callback.data.split(":", 2)[2]
    await callback.message.edit_text(f"Boshlanish sanasi: {start_iso}")
    await _ask_days(callback.message, state, start_iso)
    await callback.answer()


@router.message(StateFilter(RequestFSM.waiting_start), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def type_start(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        day = date.fromisoformat(text)
    except ValueError:
        await message.answer(
            "Sana formati noto'g'ri. <code>YYYY-MM-DD</code> ko'rinishida yozing.",
            reply_markup=cancel_menu(),
        )
        return  # holat SAQLANADI
    if day < date.today() - timedelta(days=30):
        await message.answer(
            "Sana juda eski (30 kundan oldin) — tekshirib qayta yozing.",
            reply_markup=cancel_menu(),
        )
        return
    await _ask_days(message, state, day.isoformat())


async def _show_calc_and_ask_reason(target: Message, state: FSMContext, tg_id: int) -> None:
    """Kalkulyator javobini ko'rsatib, sabab so'raydi."""
    data = await state.get_data()
    start_iso, days = data["start_date"], data["days"]
    end = date.fromisoformat(start_iso) + timedelta(days=days - 1)
    await state.update_data(end_date=end.isoformat())

    calc = await api_client.request_calc(tg_id, start_iso, end.isoformat())
    if calc is None:
        await target.answer("Oraliqni hisoblab bo'lmadi — sanani tekshiring.", reply_markup=cancel_menu())
        return

    lines = [f"📅 <b>{start_iso} — {end.isoformat()}</b>", calc["summary"]]
    if calc["working_days"] == 0:
        await state.clear()
        user = await api_client.get_user_by_telegram(tg_id)
        await target.answer(
            "\n".join(lines) + "\n\n⚠️ Bu oraliqda ish kuni yo'q — ariza kerak emas.",
            reply_markup=menu_for_user(user),
        )
        return
    if calc["conflict_dates"]:
        lines.append(
            f"⚠️ Bu kunlarda allaqachon sababli kun bor: {', '.join(calc['conflict_dates'][:5])}"
        )

    await state.set_state(RequestFSM.waiting_reason)
    await target.answer("\n".join(lines))
    await target.answer(
        f"Endi sababni yozing (kamida {MIN_REASON} belgi).", reply_markup=cancel_menu()
    )


@router.callback_query(StateFilter(RequestFSM.waiting_days), F.data.startswith("request:n:"))
async def pick_days(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(days=int(callback.data.split(":")[2]))
    await callback.message.edit_text(f"Muddat: {callback.data.split(':')[2]} kun")
    await _show_calc_and_ask_reason(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(StateFilter(RequestFSM.waiting_days), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def type_days(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not 1 <= int(text) <= MAX_DAYS:
        await message.answer(
            f"1 dan {MAX_DAYS} gacha raqam yozing.", reply_markup=cancel_menu()
        )
        return
    await state.update_data(days=int(text))
    await _show_calc_and_ask_reason(message, state, message.from_user.id)


# ─── Avans: summa ──────────────────────────────────────────────────────────────


@router.message(StateFilter(RequestFSM.waiting_amount), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def type_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").replace(" ", "").replace(",", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "Summani faqat raqam bilan yozing (masalan <code>500000</code>).",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(amount=int(raw))
    await state.set_state(RequestFSM.waiting_reason)
    await message.answer(
        f"Summa: {_fmt_money(raw)}\n\nEndi sababni yozing (kamida {MIN_REASON} belgi).",
        reply_markup=cancel_menu(),
    )


# ─── Sabab va yuborish ─────────────────────────────────────────────────────────


@router.message(StateFilter(RequestFSM.waiting_reason), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def type_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if len(reason) < MIN_REASON:
        await message.answer(
            f"Juda qisqa — kamida {MIN_REASON} belgi yozing.", reply_markup=cancel_menu()
        )
        return
    if len(reason) > MAX_REASON:
        await message.answer(
            f"Juda uzun ({len(reason)} belgi). Ko'pi bilan {MAX_REASON}.",
            reply_markup=cancel_menu(),
        )
        return

    data = await state.get_data()
    await state.clear()

    payload = {"kind": data.get("kind"), "reason": reason}
    if data.get("start_date"):
        payload["start_date"] = data["start_date"]
        payload["end_date"] = data["end_date"]
    if data.get("amount"):
        payload["amount"] = data["amount"]

    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        created = await api_client.request_create(message.from_user.id, payload)
    except httpx.HTTPStatusError as exc:
        detail = "Xatolik yuz berdi."
        try:
            body = exc.response.json()
            detail = body.get("detail", detail)
            if isinstance(detail, list) and detail:
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

    tail = ""
    if created.get("working_days"):
        tail = f"\nIsh kunlari: {created['working_days']}"
    await message.answer(
        f"✅ Arizangiz yuborildi.{tail}\n"
        "Javob kelganda shu yerda xabar beramiz. Holatini «📋 Mening "
        "murojaatlarim» dan kuzatib borasiz.",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(RequestFSM.waiting_start), ~F.text)
@router.message(StateFilter(RequestFSM.waiting_days), ~F.text)
@router.message(StateFilter(RequestFSM.waiting_amount), ~F.text)
@router.message(StateFilter(RequestFSM.waiting_reason), ~F.text)
async def non_text(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


# ─── Mening arizalarim ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "request:my")
async def show_my_requests(callback: CallbackQuery) -> None:
    items = await api_client.request_my_list(callback.from_user.id)
    if items is None:
        await callback.answer("Siz tizimda ro'yxatdan o'tmagansiz.", show_alert=True)
        return
    if not items:
        await callback.message.answer("Hozircha ariza yubormagansiz.")
        await callback.answer()
        return

    lines = ["📄 <b>Arizalarim</b>", ""]
    for it in items:
        head = _KIND_LABELS.get(it["kind"], it["kind"])
        detail = ""
        if it.get("start_date"):
            detail = f" · {it['start_date']} — {it['end_date']}"
        elif it.get("amount"):
            detail = f" · {_fmt_money(it['amount'])}"
        lines.append(f"{head}{detail}\n{_STATUS_LABELS.get(it['status'], it['status'])}")
        if it.get("decision_note"):
            lines.append(f"<i>Javob: {html.escape(it['decision_note'])}</i>")
        lines.append("")
    await callback.message.answer("\n".join(lines).strip())
    await callback.answer()


# ─── HR qarori ─────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("request_decide:"))
async def on_decide_start(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[1])
    await state.clear()
    await state.update_data(request_id=item_id)
    await callback.message.answer(
        "Qaror qanday?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="request:v:approved"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data="request:v:rejected"),
                ],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="request:cancel")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("request:v:"))
async def on_verdict(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("request_id"):
        await callback.answer("Sessiya eskirgan — xabardagi tugmani qayta bosing.", show_alert=True)
        return
    await state.update_data(decision=callback.data.split(":")[2])
    await state.set_state(RequestDecideFSM.waiting_note)
    await callback.message.edit_text("Endi qarorning IZOHINI yozing.")
    await callback.message.answer(
        f"Izoh xodimga to'liq ko'rinadi (kamida {MIN_NOTE} belgi).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(RequestDecideFSM.waiting_note), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def on_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if len(note) < MIN_NOTE:
        await message.answer(
            f"Juda qisqa — kamida {MIN_NOTE} belgi.", reply_markup=cancel_menu()
        )
        return

    data = await state.get_data()
    item_id, decision = data.get("request_id"), data.get("decision")
    await state.clear()

    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not item_id or not decision:
        await message.answer(
            "Sessiya topilmadi. Xabardagi tugmani qayta bosing.",
            reply_markup=menu_for_user(user),
        )
        return

    try:
        result = await api_client.request_decide(item_id, message.from_user.id, decision, note)
    except httpx.HTTPStatusError as exc:
        detail = "Xatolik yuz berdi."
        if exc.response.status_code == 403:
            detail = "Bu amal uchun ruxsatingiz yo'q."
        else:
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
    applied = result.get("applied") or {}
    # Materializatsiya natijasi — HR nima yozilganini ko'rsin (ta'til necha
    # kunga tushdi, avans qaysi davrga qo'shildi).
    if applied.get("excused_created"):
        lines.append(f"📅 {applied['excused_created']} ta sababli kun yozildi.")
    if applied.get("period"):
        lines.append(f"💵 Avans {applied['period']} davriga qo'shildi (Boshliq tasdig'i kutilmoqda).")
    if result.get("next_step"):
        lines.append("")
        lines.append(f"📌 <b>Keyingi qadam:</b> {result['next_step']}")
    await message.answer("\n".join(lines), reply_markup=menu_for_user(user))


@router.message(StateFilter(RequestDecideFSM.waiting_note), ~F.text)
async def non_text_note(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


# ─── Bevosita rahbar qadami (Bosqich 4) ────────────────────────────────────────


def _api_error(exc: httpx.HTTPStatusError) -> str:
    if exc.response.status_code == 403:
        return "Bu amal uchun ruxsatingiz yo'q."
    try:
        body = exc.response.json()
        if isinstance(body.get("detail"), str):
            return body["detail"]
    except Exception:
        pass
    return "Xatolik yuz berdi."


@router.callback_query(F.data.startswith("request_mgr:"))
async def on_manager_verdict(callback: CallbackQuery, state: FSMContext) -> None:
    _, raw_id, ok = callback.data.split(":")
    item_id = int(raw_id)

    if ok == "0":
        # Rad etishda izoh MAJBURIY — xodim nega to'xtaganini bilishi kerak.
        await state.clear()
        await state.update_data(mgr_request_id=item_id)
        await state.set_state(RequestManagerFSM.waiting_note)
        await callback.message.answer(
            f"Rad etish SABABINI yozing (kamida {MIN_NOTE} belgi). Xodim uni to'liq ko'radi.",
            reply_markup=cancel_menu(),
        )
        await callback.answer()
        return

    try:
        await api_client.request_manager_decide(item_id, callback.from_user.id, True)
    except httpx.HTTPStatusError as exc:
        await callback.answer(_api_error(exc), show_alert=True)
        return
    except Exception:
        await callback.answer("Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ Siz tasdiqladingiz. Ariza HR ga yuborildi.", reply_markup=None
    )
    await callback.answer()


@router.message(StateFilter(RequestManagerFSM.waiting_note), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def on_manager_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if len(note) < MIN_NOTE:
        await message.answer(f"Juda qisqa — kamida {MIN_NOTE} belgi.", reply_markup=cancel_menu())
        return

    data = await state.get_data()
    item_id = data.get("mgr_request_id")
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not item_id:
        await message.answer(
            "Sessiya topilmadi. Xabardagi tugmani qayta bosing.", reply_markup=menu_for_user(user)
        )
        return

    try:
        await api_client.request_manager_decide(item_id, message.from_user.id, False, note)
    except httpx.HTTPStatusError as exc:
        await message.answer(f"⚠️ {_api_error(exc)}", reply_markup=menu_for_user(user))
        return
    except Exception:
        await message.answer(
            "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    await message.answer(
        "❌ Ariza rad etildi, xodimga xabar yuborildi.", reply_markup=menu_for_user(user)
    )


@router.message(StateFilter(RequestManagerFSM.waiting_note), ~F.text)
async def mgr_non_text_note(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())


# ─── «Ishdagi ta'tilchi» (Bosqich 5) ───────────────────────────────────────────


@router.callback_query(F.data.startswith("request_interrupt:"))
async def on_interrupt(callback: CallbackQuery) -> None:
    """Ta'tildagi xodim ishga kelganda HR ning bir bosishli qarori.

    Izoh so'ralmaydi: bu ariza ustidan qaror emas, faqat qolgan kunlarni
    saqlash yoki bekor qilish. Har ikkala yo'l ham xodimga xabar qiladi."""
    _, raw_id, action = callback.data.split(":")
    try:
        result = await api_client.request_interrupt(
            int(raw_id), callback.from_user.id, action == "cut"
        )
    except httpx.HTTPStatusError as exc:
        await callback.answer(_api_error(exc), show_alert=True)
        return
    except Exception:
        await callback.answer("Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True)
        return

    applied = result.get("applied") or {}
    if action == "cut":
        text = (
            f"✂️ Ta'til qisqartirildi — {applied.get('excused_cancelled', 0)} ta sababli kun "
            f"bekor qilindi (yangi tugash sanasi: {applied.get('new_end_date', '—')})."
        )
    else:
        text = "▶️ Ta'til davom etadi. Kelgani qayd etildi."
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()
