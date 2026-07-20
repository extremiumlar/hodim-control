"""Bilim bazasi anketasi — bot tomonlari.

Ikki router:
- `router` — Dasturchi boshqaruvi. Kirish: «🧠 Sotuv AI markazi» dashboardidagi
  «2️⃣ Anketa» / «1️⃣ Savol to'plamlari» tugmalari (yoki /anketa buyrug'i);
  savol to'plamlari (Word/.txt yuklash), sessiyani boshlash (kimlarga + qaysi
  to'plam), yakunlash/bekor qilish, javoblarni .txt fayl qilib yuklab olish.
- `answer_router` — xodim javoblarini ushlovchi matn handleri. Dispatcher'da
  ai_watch.reason_text_router'dan OLDIN ulanadi: API'da faol savol kutilmayotgan
  bo'lsa ({"handled": false}) SkipHandler bilan xabar keyingi (AI sabab)
  handlerga o'tadi — mavjud oqimlar buzilmaydi.

Boshlanish vaqti kelganda savollarni API o'zi yuboradi (/anketa/tick — cron yoki
scheduler), shuning uchun bot bu yerda faqat boshqaruv va javob qabul qiladi."""
import base64
import html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
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
from bot.keyboards import BTN_ANKETA, BTN_CANCEL, cancel_menu, menu_for_user

logger = logging.getLogger(__name__)
router = Router(name="anketa")
answer_router = Router(name="anketa_answers")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

_STATUS_LABELS = {
    "scheduled": "🗓 rejalashtirilgan",
    "in_progress": "⏳ davom etmoqda",
    "done": "✅ yakunlangan",
    "cancelled": "🚫 bekor qilingan",
}
_ASSIGN_EMOJI = {"pending": "🕓", "in_progress": "⏳", "done": "✅", "stopped": "⏹"}
_ROLE_LABELS = {
    "boss": "Boshliq", "rop": "ROP", "hr": "HR", "dasturchi": "Dasturchi", "employee": "Xodim",
}


class AnketaSchedule(StatesGroup):
    waiting_datetime = State()


# ─── Asosiy ko'rinish ────────────────────────────────────────────────────────

def _overview_text(data: dict) -> str:
    lines = ["📝 <b>Bilim bazasi anketasi</b>", ""]
    templates = data.get("templates") or []
    if templates:
        lines.append(f"<b>Savol to'plamlari</b> ({len(templates)} ta yuklangan):")
        for t in templates:
            lines.append(f"• {html.escape(t['name'])} — {t['question_count']} savol")
    else:
        lines.append(
            "<b>Savol to'plamlari:</b> hali yuklanmagan — Word (.docx) faylni shu chatga "
            "tashlasangiz, savollar avtomatik ajratiladi."
        )

    session = data.get("session")
    if session:
        lines.append("")
        lines.append(
            f"<b>Oxirgi sessiya:</b> {_STATUS_LABELS.get(session['status'], session['status'])}"
        )
        if session.get("scheduled_at_local"):
            lines.append(f"Boshlanish vaqti: {session['scheduled_at_local']} (Toshkent)")
        for a in session.get("assignments", []):
            emoji = _ASSIGN_EMOJI.get(a["status"], "•")
            label = a.get("label") or f"№{a.get('toplam')}"
            lines.append(
                f"{emoji} {html.escape(a['full_name'])} ({html.escape(label)}): "
                f"{a['answered']}/{a['total']} javob"
            )
    else:
        lines.append("")
        lines.append("Hali sessiya boshlanmagan.")
    return "\n".join(lines)


def _overview_keyboard(data: dict) -> InlineKeyboardMarkup:
    session = data.get("session")
    active = session and session["status"] in {"scheduled", "in_progress"}
    templates = data.get("templates") or []
    rows: list[list[InlineKeyboardButton]] = []
    if active:
        if session["status"] == "in_progress":
            # Yakunlash — javoblar saqlanadi (to'ldirmaganlarni kutmasdan yopish);
            # bekor qilish — javoblar ham o'chadi (sinovni tozalash uchun)
            rows.append([
                InlineKeyboardButton(
                    text="🏁 Yakunlash (javoblar saqlanadi)", callback_data="anketa:finish"
                )
            ])
            # Xatoni tuzatish: hali javob yozmagan xodimning to'plamini
            # almashtirish/uni sessiyadan olib tashlash — javob yozib
            # ulgurganlarga bu tugma chiqmaydi (endi kech, faqat yakunlash/
            # bekor qilish qoladi).
            for a in session.get("assignments", []):
                if a["status"] == "in_progress" and a["answered"] == 0:
                    rows.append([
                        InlineKeyboardButton(
                            text=f"✏️ {a['full_name']} ({a.get('label', '')})",
                            callback_data=f"anketa:aedit:{a['assignment_id']}",
                        )
                    ])
        rows.append([
            InlineKeyboardButton(
                text="❌ Bekor qilish (javoblar o'chadi)", callback_data="anketa:cancel"
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="▶️ Hozir boshlash", callback_data="anketa:now"),
            InlineKeyboardButton(text="🗓 Kun/vaqt belgilash", callback_data="anketa:settime"),
        ])
    rows.append([
        InlineKeyboardButton(
            text=f"📄 Savol to'plamlari ({len(templates)})", callback_data="anketa:tpls"
        )
    ])
    if session:
        rows.append([InlineKeyboardButton(text="📥 Javoblar (.txt)", callback_data="anketa:results")])
    rows.append([InlineKeyboardButton(text="⬅️ Sotuv AI markazi", callback_data="aic:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_overview(message: Message, telegram_id: int) -> None:
    data = await api_client.anketa_overview(telegram_id)
    if data is None:
        await message.answer("Bu bo'lim faqat Dasturchi uchun.")
        return
    await message.answer(_overview_text(data), reply_markup=_overview_keyboard(data))


@router.message(F.text == BTN_ANKETA)
async def anketa_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_overview(message, message.from_user.id)


@router.message(Command("anketa"))
async def anketa_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_overview(message, message.from_user.id)


@router.callback_query(F.data == "anketa:back")
async def on_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    data = await api_client.anketa_overview(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    await callback.message.edit_text(_overview_text(data), reply_markup=_overview_keyboard(data))
    await callback.answer()


# ─── Savol to'plamlari (Word yuklash) ────────────────────────────────────────

@router.message(F.chat.type == "private", F.document)
async def on_document(message: Message, state: FSMContext) -> None:
    """Dasturchi tashlagan .docx/.txt — savol to'plami sifatida yuklanadi.
    Boshqa rollar yoki boshqa formatlar — jimgina o'tkazib yuboriladi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user.get("role") != "dasturchi":
        return

    document = message.document
    name = (document.file_name or "").lower()
    if not (name.endswith(".docx") or name.endswith(".txt")):
        await message.answer(
            "📄 Savol to'plami uchun <b>.docx</b> (yoki .txt) fayl kerak.\n"
            "Eski <code>.doc</code> bo'lsa: Word → «Save as» → «Word Document (.docx)»."
        )
        return
    if (document.file_size or 0) > MAX_UPLOAD_BYTES:
        await message.answer("Fayl juda katta (5 MB dan oshmasin).")
        return

    await message.answer("⏳ Fayl o'qilmoqda — savollar ajratilyapti...")
    try:
        buffer = await message.bot.download(document)
        content = buffer.read()
    except Exception:  # noqa: BLE001 — Telegram yuklab berishida xatolik
        logger.exception("Anketa faylini yuklab olishda xatolik")
        await message.answer("⚠️ Faylni yuklab bo'lmadi — qayta yuborib ko'ring.")
        return

    try:
        result = await api_client.anketa_template_upload(
            message.from_user.id,
            document.file_name or "anketa.docx",
            base64.b64encode(content).decode("ascii"),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await message.answer(f"⚠️ {detail}")
            return
        raise

    preview = "\n".join(f"{i}. {html.escape(q)}" for i, q in enumerate(result["preview"], start=1))
    warn = (
        "\n\n⚠️ Savollar aniq belgilanmagan (raqam/«?» topilmadi) — har qator savol deb "
        "olindi. Ro'yxatni tekshiring."
        if result.get("fallback")
        else ""
    )
    await message.answer(
        f"✅ <b>{html.escape(result['name'])}</b> to'plami yaratildi — "
        f"{result['question_count']} ta savol.\n\n<b>Boshi:</b>\n{preview}{warn}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 To'liq ko'rish", callback_data=f"anketa:tv:{result['id']}")],
                [InlineKeyboardButton(text="⬅️ Anketa menyusi", callback_data="anketa:back")],
            ]
        ),
    )


def _templates_view(templates: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    if templates:
        lines = ["📄 <b>Savol to'plamlari</b>", ""]
        for t in templates:
            lines.append(
                f"• <b>{html.escape(t['name'])}</b> — {t['question_count']} savol "
                f"({t.get('created_at_local') or '-'})"
            )
    else:
        lines = ["📄 <b>Savol to'plamlari</b>", "", "Hali to'plam yuklanmagan."]
    lines.append("")
    lines.append(
        "Yangi to'plam qo'shish: Word (.docx) faylni shu chatga tashlang — savollar "
        "avtomatik ajratiladi (raqamlangan, «?» bilan tugagan yoki ro'yxat ko'rinishidagi "
        "qatorlar savol deb olinadi)."
    )
    rows = [
        [
            InlineKeyboardButton(text=f"👁 {t['name'][:20]}", callback_data=f"anketa:tv:{t['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"anketa:tdel:{t['id']}"),
        ]
        for t in templates
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Anketa menyusi", callback_data="anketa:back")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "anketa:tpls")
async def on_templates(callback: CallbackQuery) -> None:
    data = await api_client.anketa_templates(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = _templates_view(data.get("templates", []))
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:tv:"))
async def on_template_view(callback: CallbackQuery) -> None:
    template_id = int(callback.data.rsplit(":", 1)[1])
    try:
        data = await api_client.anketa_template_detail(callback.from_user.id, template_id)
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.json() or {}).get("detail", "Xatolik")
        await callback.answer(detail, show_alert=True)
        return

    lines = [f"📄 <b>{html.escape(data['name'])}</b> — {data['question_count']} savol", ""]
    section = None
    for i, q in enumerate(data["questions"], start=1):
        if q.get("section") and q["section"] != section:
            section = q["section"]
            lines.append(f"\n<i>{html.escape(section)}</i>")
        lines.append(f"{i}. {html.escape(q['text'])}")
    text = "\n".join(lines)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ To'plamlar", callback_data="anketa:tpls")]]
    )
    if len(text) > 3900:  # Telegram xabar chegarasi — uzun to'plam fayl bo'lib ketadi
        content = "\n".join(
            f"{i}. {q['text']}" for i, q in enumerate(data["questions"], start=1)
        ).encode("utf-8")
        await callback.message.answer_document(
            BufferedInputFile(content, filename=f"{data['name'][:40]}.txt"),
            caption=f"📄 {data['name']} — {data['question_count']} savol",
            reply_markup=markup,
        )
    else:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:tdel:"))
async def on_template_delete_ask(callback: CallbackQuery) -> None:
    template_id = int(callback.data.rsplit(":", 1)[1])
    await callback.message.edit_text(
        "🗑 Bu savol to'plami ro'yxatdan olib tashlansinmi?\n"
        "(O'tgan sessiyalarning savol-javoblari saqlanib qoladi.)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha", callback_data=f"anketa:tdelok:{template_id}"),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:tpls"),
            ]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:tdelok:"))
async def on_template_delete(callback: CallbackQuery) -> None:
    template_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await api_client.anketa_template_delete(callback.from_user.id, template_id)
    except httpx.HTTPStatusError as exc:
        detail = (exc.response.json() or {}).get("detail", "Xatolik")
        await callback.answer(detail, show_alert=True)
        return
    data = await api_client.anketa_templates(callback.from_user.id)
    text, markup = _templates_view((data or {}).get("templates", []))
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer("O'chirildi")


# ─── Sessiyani boshlash: kimlarga → qaysi to'plam → tasdiq ───────────────────

# Qatnashchi spetsifikatsiyasi (callback'da, ichida ':' yo'q):
# std | all | role_boss | role_rop | role_hr | pos_<id>
def _parse_spec(spec: str) -> dict:
    if spec == "all":
        return {"target_type": "all", "position_id": None, "role": None}
    if spec.startswith("role_"):
        return {"target_type": "role", "position_id": None, "role": spec[len("role_"):]}
    if spec.startswith("pos_"):
        return {"target_type": "position", "position_id": int(spec[len("pos_"):]), "role": None}
    return {"target_type": "standart", "position_id": None, "role": None}


def _parse_tsel(tsel: str) -> int | None:
    """`std` — ichki 1-5 to'plam; `t<id>` — yuklangan to'plam."""
    if tsel.startswith("t") and tsel[1:].isdigit():
        return int(tsel[1:])
    return None


async def _targets_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Qatnashchilar tanlovi — vazifa berishdagi kabi: hamma / rol / lavozim,
    hamda «har kimga alohida». mode: now | time."""
    rows = [
        [InlineKeyboardButton(text="👤 Har kimga alohida", callback_data=f"anketa:each:{mode}")],
        [InlineKeyboardButton(text="🎯 Standart (5 sotuvchi)", callback_data=f"anketa:tg:{mode}:std")],
        [InlineKeyboardButton(text="👥 Barcha xodimlar", callback_data=f"anketa:tg:{mode}:all")],
        [
            InlineKeyboardButton(text="👑 Boshliq", callback_data=f"anketa:tg:{mode}:role_boss"),
            InlineKeyboardButton(text="🧭 ROPlar", callback_data=f"anketa:tg:{mode}:role_rop"),
            InlineKeyboardButton(text="🗂 HRlar", callback_data=f"anketa:tg:{mode}:role_hr"),
        ],
    ]
    try:
        positions = await api_client.list_positions()
    except Exception:  # noqa: BLE001 — lavozimlar kelmasa ham asosiy tanlovlar qolsin
        positions = []
    pos_buttons = [
        InlineKeyboardButton(text=f"Lavozim: {p['name']}", callback_data=f"anketa:tg:{mode}:pos_{p['id']}")
        for p in positions
    ]
    for i in range(0, len(pos_buttons), 2):
        rows.append(pos_buttons[i : i + 2])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "anketa:now")
async def on_start_now(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "▶️ Anketa KIMLARGA yuborilsin?", reply_markup=await _targets_keyboard("now")
    )
    await callback.answer()


@router.callback_query(F.data == "anketa:settime")
async def on_set_time(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🗓 Avval anketa KIMLARGA yuborilishini tanlang:",
        reply_markup=await _targets_keyboard("time"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:tg:"))
async def on_target_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    """Guruh tanlandi — endi qaysi savol to'plami berilishini so'raymiz.
    mode/spec shu yerda FSM holatiga yoziladi — keyingi qadamlarning
    callback_data'sida qayta-qayta tashib yurish shart bo'lmaydi (band 6:
    ilgari "anketa:confirm:{spec}:{tsel}:{value}" kabi uch qismli formatlar
    va ularni qo'lda parslash bor edi)."""
    _, _, mode, spec = callback.data.split(":", 3)
    await state.update_data(target_mode=mode, target_spec=spec)

    data = await api_client.anketa_templates(callback.from_user.id)
    templates = (data or {}).get("templates", [])

    rows = [
        [
            InlineKeyboardButton(
                text=f"📄 {t['name'][:28]} ({t['question_count']})",
                callback_data=f"anketa:ts:t{t['id']}",
            )
        ]
        for t in templates
    ]
    rows.append([
        InlineKeyboardButton(
            text="🎯 Ichki 5 to'plam (standart savollar)",
            callback_data="anketa:ts:std",
        )
    ])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back")])
    hint = (
        "Yuklangan to'plam tanlansa — guruhdagi hamma shu savollarni oladi.\n"
        "«Ichki 5 to'plam» — kodga yozilgan standart savollar (har kishiga 1-5 dan biri)."
    )
    await callback.message.edit_text(
        f"📄 Qaysi savol to'plami yuborilsin?\n\n{hint}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


def _preview_text(targets: list[dict]) -> str:
    lines = [f"Qatnashchilar ({len(targets)} kishi):"]
    for t in targets:
        warn = "" if t.get("bot_started") else " ⚠️ botga /start bosmagan"
        label = t.get("label") or f"To'plam №{t.get('toplam')}"
        lines.append(f"• {html.escape(t['full_name'])} — {html.escape(label)}{warn}")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("anketa:ts:"))
async def on_template_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    tsel = callback.data.split(":", 2)[2]
    data = await state.get_data()
    mode = data.get("target_mode", "now")
    spec = data.get("target_spec", "std")
    template_id = _parse_tsel(tsel)
    try:
        preview = await api_client.anketa_preview_targets(
            callback.from_user.id, template_id=template_id, **_parse_spec(spec)
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    targets = preview.get("targets", [])
    await state.update_data(tsel=tsel)

    if mode == "now":
        await state.update_data(scheduled_iso=None)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha, hozir boshlansin", callback_data="anketa:confirm"),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back"),
            ]]
        )
        await callback.message.edit_text(
            f"▶️ Anketa HOZIR boshlansinmi?\n\n{_preview_text(targets)}\n\n"
            "Har biriga birinchi savol darhol yuboriladi.",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    await state.set_state(AnketaSchedule.waiting_datetime)
    await callback.message.edit_text(_preview_text(targets))
    await callback.message.answer(
        "🗓 Boshlanish kun va vaqtini yozing (Toshkent vaqti).\n\n"
        "Qabul qilinadigan ko'rinishlar:\n"
        "• <code>15:30</code> — bugun\n"
        "• <code>bugun 15:30</code> / <code>ertaga 09:00</code>\n"
        "• <code>17.07.2026 09:00</code>",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


# ─── «Har kimga alohida» taqsimoti ──────────────────────────────────────────

def _user_matches_filter(user: dict, filt: str | None) -> bool:
    """Band 7: lavozim/rol bo'yicha tezkor filtr — katta jamoada per-user
    ro'yxatni skroll qilib yurmaslik uchun."""
    if not filt or filt == "all":
        return True
    if filt.startswith("role_"):
        return user["role"] == filt[len("role_"):]
    if filt.startswith("pos_"):
        return user.get("position_id") == int(filt[len("pos_"):])
    return True


async def _quick_filter_rows(prefix: str, active: str | None) -> list[list[InlineKeyboardButton]]:
    """`prefix` — masalan "anketa:pfilter" yoki "anketa:bfilter". Tanlangan
    chip ✅ bilan belgilanadi. Rol/lavozim tanlovlari _targets_keyboard bilan
    bir xil (role_boss/role_rop/role_hr/pos_<id>)."""
    def mark(spec: str, label: str) -> str:
        return f"✅ {label}" if (active or "all") == spec else label

    rows = [[
        InlineKeyboardButton(text=mark("all", "Hammasi"), callback_data=f"{prefix}:all"),
        InlineKeyboardButton(text=mark("role_boss", "👑 Boshliq"), callback_data=f"{prefix}:role_boss"),
        InlineKeyboardButton(text=mark("role_rop", "🧭 ROP"), callback_data=f"{prefix}:role_rop"),
        InlineKeyboardButton(text=mark("role_hr", "🗂 HR"), callback_data=f"{prefix}:role_hr"),
    ]]
    try:
        positions = await api_client.list_positions()
    except Exception:  # noqa: BLE001 — lavozimlar kelmasa ham asosiy filtr qolsin
        positions = []
    pos_buttons = [
        InlineKeyboardButton(
            text=mark(f"pos_{p['id']}", p["name"]), callback_data=f"{prefix}:pos_{p['id']}"
        )
        for p in positions
    ]
    for i in range(0, len(pos_buttons), 3):
        rows.append(pos_buttons[i : i + 3])
    return rows


async def _picker_view(telegram_id: int, state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    data = await state.get_data()
    assign: dict = data.get("assign") or {}
    filt = data.get("picker_filter")
    users = (await api_client.anketa_candidates(telegram_id)).get("users", [])
    templates = (await api_client.anketa_templates(telegram_id) or {}).get("templates", [])
    name_by_id = {str(t["id"]): t["name"] for t in templates}
    filtered = [u for u in users if _user_matches_filter(u, filt)]

    lines = ["👤 <b>Har kimga alohida taqsimot</b>", ""]
    rows: list[list[InlineKeyboardButton]] = list(await _quick_filter_rows("anketa:pfilter", filt))
    for u in filtered:
        key = str(u["user_id"])
        tid = assign.get(key)
        if tid:
            mark = f"✅ {name_by_id.get(str(tid), 'to`plam')[:18]}"
        else:
            mark = "✖️ bermayman"
        role = _ROLE_LABELS.get(u["role"], u["role"])
        extra = f" · {u['position']}" if u.get("position") else ""
        lines.append(f"• {html.escape(u['full_name'])} ({role}{extra}) — {mark}")
        rows.append([
            InlineKeyboardButton(
                text=f"{'✅' if tid else '✖️'} {u['full_name'][:22]}",
                callback_data=f"anketa:pu:{u['user_id']}",
            )
        ])
    if filt and not filtered:
        lines.append("(bu filtrga mos xodim yo'q)")

    chosen = sum(1 for v in assign.values() if v)
    lines.append("")
    lines.append(f"Jami tanlangan: <b>{chosen}</b> kishi. Xodim ustiga bosib to'plam tanlang.")
    if not templates:
        lines.append("\n⚠️ Hali savol to'plami yuklanmagan — Word faylni chatga tashlang.")

    if templates:
        rows.append([
            InlineKeyboardButton(text="📦 Ko'p kishiga bitta to'plam", callback_data="anketa:bulk")
        ])
    rows.append([
        InlineKeyboardButton(text="✅ Tayyor", callback_data="anketa:pdone"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("anketa:each:"))
async def on_each_start(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.rsplit(":", 1)[1]
    await state.clear()
    await state.update_data(pick_mode=mode, assign={})
    text, markup = await _picker_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:pfilter:"))
async def on_picker_filter(callback: CallbackQuery, state: FSMContext) -> None:
    spec = callback.data.split(":", 2)[2]
    await state.update_data(picker_filter=None if spec == "all" else spec)
    text, markup = await _picker_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


# ─── Ko'p kishiga bitta to'plam (bulk) — avval to'plam, keyin xodimlar ──────

async def _bulk_view(telegram_id: int, state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    data = await state.get_data()
    template_id = data.get("bulk_template_id")
    selected: set[int] = set(data.get("bulk_selected") or [])
    filt = data.get("bulk_filter")
    users = (await api_client.anketa_candidates(telegram_id)).get("users", [])
    templates = (await api_client.anketa_templates(telegram_id) or {}).get("templates", [])
    tname = next((t["name"] for t in templates if t["id"] == template_id), "to'plam")
    filtered = [u for u in users if _user_matches_filter(u, filt)]

    lines = [f"📦 <b>{html.escape(tname)}</b> — kimlarga berilsin?", "Xodimlarni belgilang:", ""]
    rows: list[list[InlineKeyboardButton]] = list(await _quick_filter_rows("anketa:bfilter", filt))
    for u in filtered:
        uid = u["user_id"]
        mark = "✅" if uid in selected else "▫️"
        lines.append(f"{mark} {html.escape(u['full_name'])}")
        rows.append([
            InlineKeyboardButton(text=f"{mark} {u['full_name'][:24]}", callback_data=f"anketa:bu:{uid}")
        ])
    if filt and not filtered:
        lines.append("(bu filtrga mos xodim yo'q)")
    lines.append("")

    lines.append(f"Belgilangan: <b>{len(selected)}</b> kishi.")
    rows.append([
        InlineKeyboardButton(text=f"✅ Belgilash ({len(selected)})", callback_data="anketa:bulkdone"),
        InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="anketa:plist"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "anketa:bulk")
async def on_bulk_start(callback: CallbackQuery) -> None:
    templates = (await api_client.anketa_templates(callback.from_user.id) or {}).get("templates", [])
    if not templates:
        await callback.answer("Hali to'plam yuklanmagan", show_alert=True)
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"📄 {t['name'][:28]} ({t['question_count']})",
                callback_data=f"anketa:bulkt:{t['id']}",
            )
        ]
        for t in templates
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:plist")])
    await callback.message.edit_text(
        "📦 Ko'p kishiga qaysi to'plam berilsin?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:bulkt:"))
async def on_bulk_template(callback: CallbackQuery, state: FSMContext) -> None:
    template_id = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(bulk_template_id=template_id, bulk_selected=[], bulk_filter=None)
    text, markup = await _bulk_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:bfilter:"))
async def on_bulk_filter(callback: CallbackQuery, state: FSMContext) -> None:
    spec = callback.data.split(":", 2)[2]
    await state.update_data(bulk_filter=None if spec == "all" else spec)
    text, markup = await _bulk_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:bu:"))
async def on_bulk_toggle_user(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = int(callback.data.rsplit(":", 1)[1])
    data = await state.get_data()
    selected: set[int] = set(data.get("bulk_selected") or [])
    if user_id in selected:
        selected.discard(user_id)
    else:
        selected.add(user_id)
    await state.update_data(bulk_selected=list(selected))
    text, markup = await _bulk_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "anketa:bulkdone")
async def on_bulk_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    template_id = data.get("bulk_template_id")
    selected = data.get("bulk_selected") or []
    if not selected or not template_id:
        await callback.answer("Hech kim belgilanmadi", show_alert=True)
        return
    assign = dict(data.get("assign") or {})
    for uid in selected:
        assign[str(uid)] = template_id
    await state.update_data(assign=assign, bulk_template_id=None, bulk_selected=[], bulk_filter=None)
    text, markup = await _picker_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer(f"{len(selected)} kishiga biriktirildi")


@router.callback_query(F.data.startswith("anketa:pu:"))
async def on_pick_user(callback: CallbackQuery) -> None:
    user_id = int(callback.data.rsplit(":", 1)[1])
    templates = (await api_client.anketa_templates(callback.from_user.id) or {}).get("templates", [])
    rows = [
        [
            InlineKeyboardButton(
                text=f"📄 {t['name'][:28]} ({t['question_count']})",
                callback_data=f"anketa:pt:{user_id}:{t['id']}",
            )
        ]
        for t in templates
    ]
    rows.append([
        InlineKeyboardButton(text="✖️ Bu xodimga bermayman", callback_data=f"anketa:pt:{user_id}:0")
    ])
    rows.append([InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data="anketa:plist")])
    await callback.message.edit_text(
        "📄 Bu xodimga qaysi to'plam berilsin?"
        + ("" if templates else "\n\n⚠️ Hali to'plam yuklanmagan — Word faylni chatga tashlang."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:pt:"))
async def on_pick_template(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, user_id_s, template_id_s = callback.data.split(":", 3)
    data = await state.get_data()
    assign = dict(data.get("assign") or {})
    if template_id_s == "0":
        assign.pop(user_id_s, None)
    else:
        assign[user_id_s] = int(template_id_s)
    await state.update_data(assign=assign)
    text, markup = await _picker_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "anketa:plist")
async def on_pick_list(callback: CallbackQuery, state: FSMContext) -> None:
    text, markup = await _picker_view(callback.from_user.id, state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "anketa:pdone")
async def on_pick_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    assign: dict = data.get("assign") or {}
    if not assign:
        await callback.answer("Hech kim tanlanmadi — kamida bitta xodimga to'plam bering", show_alert=True)
        return

    users = (await api_client.anketa_candidates(callback.from_user.id)).get("users", [])
    templates = (await api_client.anketa_templates(callback.from_user.id) or {}).get("templates", [])
    tname = {str(t["id"]): t["name"] for t in templates}
    name_by_id = {str(u["user_id"]): u["full_name"] for u in users}
    lines = [f"Qatnashchilar ({len(assign)} kishi):"]
    for uid, tid in assign.items():
        lines.append(
            f"• {html.escape(name_by_id.get(uid, '?'))} — "
            f"{html.escape(tname.get(str(tid), 'to`plam'))}"
        )
    preview = "\n".join(lines)

    if data.get("pick_mode") == "now":
        await state.update_data(scheduled_iso=None)
        await callback.message.edit_text(
            f"▶️ Anketa HOZIR boshlansinmi?\n\n{preview}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Ha, boshlansin", callback_data="anketa:cfx"),
                    InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:plist"),
                ]]
            ),
        )
        await callback.answer()
        return

    await state.set_state(AnketaSchedule.waiting_datetime)
    await state.update_data(explicit=True)
    await callback.message.edit_text(preview)
    await callback.message.answer(
        "🗓 Boshlanish kun va vaqtini yozing (Toshkent vaqti).\n"
        "Masalan: <code>ertaga 09:00</code>",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


# ─── Vaqt kiritish va tasdiqlash ────────────────────────────────────────────

def _parse_local_datetime(raw: str) -> datetime | None:
    """Foydalanuvchi kiritgan matnni Toshkent vaqtidagi datetime'ga o'giradi.
    Tushunarsiz format — None (bot qayta so'raydi)."""
    text = " ".join(raw.strip().lower().split())
    now = datetime.now(TASHKENT_TZ).replace(tzinfo=None)

    day_offset = 0
    if text.startswith("bugun"):
        text = text[len("bugun"):].strip()
    elif text.startswith("ertaga"):
        day_offset = 1
        text = text[len("ertaga"):].strip()

    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        t = datetime.strptime(text, "%H:%M")
    except ValueError:
        return None
    base = now.date() + timedelta(days=day_offset)
    return datetime.combine(base, t.time())


@router.message(AnketaSchedule.waiting_datetime, F.text)
async def on_datetime_input(message: Message, state: FSMContext) -> None:
    if message.text == BTN_CANCEL:
        await state.clear()
        user = await api_client.get_user_by_telegram(message.from_user.id)
        await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
        return

    parsed = _parse_local_datetime(message.text)
    if parsed is None:
        await message.answer(
            "Tushunarsiz format. Masalan: <code>ertaga 09:00</code> yoki <code>17.07.2026 09:00</code>"
        )
        return
    now_local = datetime.now(TASHKENT_TZ).replace(tzinfo=None)
    if parsed <= now_local:
        await message.answer("Bu vaqt o'tib bo'lgan — kelajakdagi vaqtni kiriting.")
        return

    data = await state.get_data()
    iso = parsed.strftime("%Y-%m-%dT%H:%M")
    user = await api_client.get_user_by_telegram(message.from_user.id)

    # Tanlangan vaqt FSM holatiga yoziladi (callback_data'ga emas — band 6:
    # tugma endi har doim qisqa literal, "spec:tsel:iso" kabi cheklovsiz
    # cho'zilib ketmaydi). Holat matn kutish bosqichidan chiqadi, lekin
    # to'liq TOZALANMAYDI — tasdiqlash bosilganda kerak bo'lgan target_spec/
    # tsel/assign shu yerda saqlanib qoladi.
    await state.update_data(scheduled_iso=iso)
    await state.set_state(None)
    callback_data = "anketa:cfx" if data.get("explicit") else "anketa:confirm"

    await message.answer(
        f"🗓 Anketa <b>{parsed.strftime('%d.%m.%Y %H:%M')}</b> (Toshkent) da boshlansinmi?\n"
        "Tasdiqlansa, vaqt kelganda bot xodimlarga savollarni o'zi yuboradi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Tasdiqlayman", callback_data=callback_data),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back"),
            ]]
        ),
    )
    await message.answer("Asosiy menyu:", reply_markup=menu_for_user(user))


async def _finish_schedule(callback: CallbackQuery, result: dict) -> None:
    session = result.get("session") or {}
    if session.get("status") == "in_progress":
        text = "🚀 Anketa boshlandi — xodimlarga birinchi savollar yuborildi."
    else:
        text = (
            f"✅ Tasdiqlandi. Anketa <b>{session.get('scheduled_at_local')}</b> (Toshkent) da "
            "avtomatik boshlanadi."
        )
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()


@router.callback_query(F.data == "anketa:confirm")
async def on_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Guruh (spec/tsel) bo'yicha tasdiqlash — hammasi FSM holatidan o'qiladi
    (band 6: ilgari "anketa:confirm:{spec}:{tsel}:{value}" kabi callback_data'ga
    cho'zib yozilardi, endi tugma har doim shu qisqa literal)."""
    data = await state.get_data()
    spec = data.get("target_spec", "std")
    tsel = data.get("tsel", "std")
    scheduled_at = data.get("scheduled_iso")
    try:
        result = await api_client.anketa_schedule(
            callback.from_user.id,
            scheduled_at,
            template_id=_parse_tsel(tsel),
            **_parse_spec(spec),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await state.clear()
    await _finish_schedule(callback, result)


@router.callback_query(F.data == "anketa:cfx")
async def on_confirm_explicit(callback: CallbackQuery, state: FSMContext) -> None:
    """Har kimga alohida taqsimot bilan tasdiqlash (taqsimot ham, vaqt ham FSM'da)."""
    data = await state.get_data()
    scheduled_at = data.get("scheduled_iso")
    assign: dict = data.get("assign") or {}
    if not assign:
        await callback.answer("Taqsimot topilmadi — qaytadan boshlang", show_alert=True)
        return

    payload = [{"user_id": int(uid), "template_id": int(tid)} for uid, tid in assign.items()]
    try:
        result = await api_client.anketa_schedule(
            callback.from_user.id, scheduled_at, target_type="explicit", assignments=payload
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await state.clear()
    await _finish_schedule(callback, result)


# ─── Xatoni tuzatish: hali javob yozmagan xodimni almashtirish/olib tashlash ─

@router.callback_query(F.data.startswith("anketa:aedit:"))
async def on_assignment_edit(callback: CallbackQuery) -> None:
    assignment_id = int(callback.data.rsplit(":", 1)[1])
    await callback.message.edit_text(
        "✏️ Bu xodim uchun nima qilamiz?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Boshqa to'plam berish", callback_data=f"anketa:areass:{assignment_id}")],
                [InlineKeyboardButton(text="🗑 Sessiyadan olib tashlash", callback_data=f"anketa:aremove:{assignment_id}")],
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="anketa:back")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:areass:"))
async def on_assignment_retemplate_start(callback: CallbackQuery) -> None:
    assignment_id = int(callback.data.rsplit(":", 1)[1])
    templates = (await api_client.anketa_templates(callback.from_user.id) or {}).get("templates", [])
    rows = [
        [
            InlineKeyboardButton(
                text=f"📄 {t['name'][:28]} ({t['question_count']})",
                callback_data=f"anketa:areasst:{assignment_id}:t{t['id']}",
            )
        ]
        for t in templates
    ]
    # Ichki 5 to'plam — har biri o'z raqami bilan (bittasiga o'tkazishda "qaysi
    # 5tadan biri" aniq tanlanishi kerak, aylanma emas)
    rows.append([
        InlineKeyboardButton(text=f"🎯 №{n}", callback_data=f"anketa:areasst:{assignment_id}:n{n}")
        for n in range(1, 6)
    ])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anketa:aedit:{assignment_id}")])
    await callback.message.edit_text(
        "🔁 Qaysi to'plam berilsin?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:areasst:"))
async def on_assignment_retemplate_apply(callback: CallbackQuery) -> None:
    _, _, assignment_id_s, tsel = callback.data.split(":", 3)
    assignment_id = int(assignment_id_s)
    template_id: int | None = None
    toplam: int | None = None
    if tsel.startswith("t") and tsel[1:].isdigit():
        template_id = int(tsel[1:])
    elif tsel.startswith("n") and tsel[1:].isdigit():
        toplam = int(tsel[1:])
    try:
        await api_client.anketa_assignment_retemplate(
            callback.from_user.id, assignment_id, template_id=template_id, toplam=toplam
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403, 404):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.answer("Yangilandi — xodimga yangi birinchi savol yuborildi")
    data = await api_client.anketa_overview(callback.from_user.id)
    if data is not None:
        await callback.message.edit_text(_overview_text(data), reply_markup=_overview_keyboard(data))


@router.callback_query(F.data.startswith("anketa:aremove:"))
async def on_assignment_remove_ask(callback: CallbackQuery) -> None:
    assignment_id = int(callback.data.rsplit(":", 1)[1])
    await callback.message.edit_text(
        "🗑 Bu xodim sessiyadan butunlay olib tashlansinmi? U endi anketa savollarini olmaydi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ha, olib tashla", callback_data=f"anketa:aremoveok:{assignment_id}"),
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anketa:aedit:{assignment_id}"),
            ]]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("anketa:aremoveok:"))
async def on_assignment_remove_apply(callback: CallbackQuery) -> None:
    assignment_id = int(callback.data.rsplit(":", 1)[1])
    try:
        await api_client.anketa_assignment_remove(callback.from_user.id, assignment_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403, 404):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.answer("Olib tashlandi")
    data = await api_client.anketa_overview(callback.from_user.id)
    if data is not None:
        await callback.message.edit_text(_overview_text(data), reply_markup=_overview_keyboard(data))


# ─── Sessiyani yakunlash / bekor qilish / natijalar ─────────────────────────

@router.callback_query(F.data == "anketa:finish")
async def on_finish_session(callback: CallbackQuery) -> None:
    try:
        result = await api_client.anketa_finish(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text(
        f"🏁 Sessiya yakunlandi: {result['done']} xodim to'liq tugatgan, "
        f"{result['stopped']} xodimniki to'xtatildi (yozgan javoblari saqlandi).\n\n"
        "Endi «📚 Bilim bazasi» → «🔄 Anketadan yuklash» bilan javoblarni bazaga "
        "olishingiz mumkin.",
        reply_markup=None,
    )
    await callback.answer("Yakunlandi")


@router.callback_query(F.data == "anketa:cancel")
async def on_cancel_session(callback: CallbackQuery) -> None:
    try:
        await api_client.anketa_cancel(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text("🚫 Sessiya bekor qilindi.", reply_markup=None)
    await callback.answer("Bekor qilindi")


@router.callback_query(F.data == "anketa:results")
async def on_results(callback: CallbackQuery) -> None:
    try:
        data = await api_client.anketa_results(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await callback.answer("Hali sessiya yo'q", show_alert=True)
            return
        raise
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    session = data.get("session") or {}
    lines = [
        "NURLI DIYOR — BILIM BAZASI ANKETASI (javoblar)",
        f"Sessiya #{session.get('id')} · holat: {session.get('status')}",
        f"Boshlangan: {session.get('started_at_local') or '-'} · Yakunlangan: {session.get('finished_at_local') or '-'}",
        "=" * 60,
    ]
    for u in data.get("users", []):
        lines.append("")
        label = u.get("label") or f"To'plam №{u.get('toplam')}"
        lines.append(f"XODIM: {u['full_name']} — {label} ({u['status']})")
        lines.append("-" * 60)
        if not u["answers"]:
            lines.append("(hali javob yo'q)")
        for ans in u["answers"]:
            lines.append(f"{ans['n']}. {ans['question']}")
            lines.append(f"JAVOB ({ans['answered_at_local']}): {ans['answer']}")
            lines.append("")
    content = "\n".join(lines).encode("utf-8")
    filename = f"anketa_javoblar_sessiya_{session.get('id', 0)}.txt"
    await callback.message.answer_document(BufferedInputFile(content, filename=filename))
    await callback.answer()


# ─── Xodim javoblari ────────────────────────────────────────────────────────

@answer_router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/"),
    StateFilter(None),
)
async def on_possible_answer(message: Message) -> None:
    """Menyu/FSM/buyruqlardan o'tgan oddiy matn — faol anketa savoli kutilayotgan
    xodimniki bo'lishi mumkin. API tekshiradi: kutilmayotgan bo'lsa SkipHandler —
    xabar keyingi handlerga (AI sabab oqimi) o'tadi."""
    try:
        result = await api_client.anketa_answer(message.from_user.id, message.text)
    except httpx.HTTPError:
        # Anketa oqimini aniqlab bo'lmadi — xabarni boshqa oqimlarga o'tkazamiz,
        # aks holda API qisqa uzilishida xodim javoblari ham, AI sabablari ham yo'qoladi.
        logger.exception("Anketa javobini tekshirishda xatolik")
        raise SkipHandler

    if not result.get("handled"):
        raise SkipHandler

    for text in result.get("messages", []):
        await message.answer(text)
