"""Sotuv playbook — bot boshqaruvi (faqat Boshliq/Dasturchi).

Kirish: «📚 Bilim bazasi» menyusidagi «🧭 Sotuv playbook» tugmasi (yoki /playbook).
Amallar: 🔨 qurish (AI ishi cron'da bosqichma-bosqich, tayyor bo'lgach xabar),
🔍 yozuvlarni birma-bir ko'rib tasdiqlash/o'chirish, 📥 .txt eksport."""
import html
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import api_client

logger = logging.getLogger(__name__)
router = Router(name="playbook")

_KIND_LABELS = {"etiroz": "🛡 E'tiroz bilan ishlash", "uslub": "🗣 Uslub/ohang", "qoida": "📏 Qoida"}


async def _overview_view(telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    data = await api_client.playbook_overview(telegram_id)
    if data is None:
        return None
    counts = data.get("counts", {})
    lines = ["🧭 <b>Sotuv playbook</b>", ""]
    lines.append("Sotuvchilar uslubidan o'rganilgan «vaziyat → texnika → ibora» qo'llanma.")
    lines.append("")
    lines.append(f"✅ Tasdiqlangan: {counts.get('verified', 0)}")
    lines.append(f"🕓 Tasdiq kutmoqda: {counts.get('unverified', 0)}")
    if data.get("building"):
        lines.append(f"\n⏳ Qurilmoqda: {data['building']['label']}...")
    elif data.get("last_build_status") == "failed":
        lines.append("\n⚠️ Oxirgi qurish muvaffaqiyatsiz — qayta urinib ko'ring.")
    if not data.get("ai_enabled"):
        lines.append("\n⚠️ AI o'chiq (.env: AI_ENABLED) — qurish ishlamaydi.")

    rows = []
    if not data.get("building"):
        label = "🔨 Qayta qurish" if counts else "🔨 Qurish"
        rows.append([InlineKeyboardButton(text=label, callback_data="pb:build")])
    if counts.get("unverified"):
        rows.append([
            InlineKeyboardButton(
                text=f"🔍 Ko'rib chiqish ({counts['unverified']})", callback_data="pb:review:0"
            )
        ])
    if counts:
        rows.append([InlineKeyboardButton(text="📥 Playbook (.txt)", callback_data="pb:export")])
    rows.append([InlineKeyboardButton(text="⬅️ Bilim bazasi", callback_data="kb:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "pb:menu")
async def on_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    view = await _overview_view(callback.from_user.id)
    if view is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    text, markup = view
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.message(Command("playbook"))
async def on_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    view = await _overview_view(message.from_user.id)
    if view is None:
        await message.answer("Bu bo'lim faqat Boshliq/Dasturchi uchun.")
        return
    text, markup = view
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "pb:build")
async def on_build(callback: CallbackQuery) -> None:
    try:
        result = await api_client.playbook_build(callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await callback.message.edit_text(
        f"🔨 Playbook qurish boshlandi ({result.get('targets', 0)} sotuvchi tahlil qilinadi).\n"
        "Jarayon bir necha daqiqa davom etadi: profillar → mijoz e'tirozlari → yakuniy "
        "qo'llanma. Tayyor bo'lgach sizga xabar keladi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Playbook", callback_data="pb:menu")]]
        ),
    )
    await callback.answer()


def _entry_card(entry: dict, remaining: int) -> tuple[str, InlineKeyboardMarkup]:
    kind = _KIND_LABELS.get(entry["kind"], entry["kind"])
    lines = [
        f"🔍 <b>Playbook ko'rib chiqish</b> — qolgan: {remaining}",
        "",
        f"Turi: {kind}",
        "",
        f"<b>Vaziyat:</b> {html.escape(entry['situation'])}",
        f"<b>Texnika:</b> {html.escape(entry['technique'])}",
    ]
    if entry.get("phrases"):
        lines.append("")
        lines.append("<b>Namunaviy iboralar:</b>")
        for p in entry["phrases"]:
            src = f" — {html.escape(p['source'])}" if p.get("source") else ""
            lines.append(f"• «{html.escape(p['text'])}»{src}")

    eid = entry["id"]
    rows = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pb:ok:{eid}"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"pb:del:{eid}"),
        ],
        [
            InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=f"pb:review:{eid}"),
            InlineKeyboardButton(text="⬅️ Playbook", callback_data="pb:menu"),
        ],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_next(callback: CallbackQuery, after_id: int) -> None:
    data = await api_client.playbook_review_next(callback.from_user.id, after_id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    entry = data.get("entry")
    if entry is None:
        await callback.message.edit_text(
            "✅ Ko'rib chiqiladigan playbook yozuvi qolmadi.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Playbook", callback_data="pb:menu")]]
            ),
        )
        await callback.answer()
        return
    text, markup = _entry_card(entry, data["remaining"])
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("pb:review:"))
async def on_review(callback: CallbackQuery) -> None:
    await _show_next(callback, int(callback.data.rsplit(":", 1)[1]))


async def _decide_and_next(callback: CallbackQuery, entry_id: int, action: str) -> None:
    try:
        await api_client.playbook_decide(callback.from_user.id, entry_id, action)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 403, 404):
            detail = (exc.response.json() or {}).get("detail", "Xatolik")
            await callback.answer(detail, show_alert=True)
            return
        raise
    await _show_next(callback, 0)


@router.callback_query(F.data.startswith("pb:ok:"))
async def on_approve(callback: CallbackQuery) -> None:
    await _decide_and_next(callback, int(callback.data.rsplit(":", 1)[1]), "approve")


@router.callback_query(F.data.startswith("pb:del:"))
async def on_delete(callback: CallbackQuery) -> None:
    await _decide_and_next(callback, int(callback.data.rsplit(":", 1)[1]), "delete")


@router.callback_query(F.data == "pb:export")
async def on_export(callback: CallbackQuery) -> None:
    data = await api_client.playbook_export(callback.from_user.id)
    if data is None:
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return
    entries = data.get("entries", [])
    if not entries:
        await callback.answer("Playbook hali bo'sh", show_alert=True)
        return

    lines = ["NURLI DIYOR — SOTUV PLAYBOOK", "=" * 60]
    current_kind = None
    for e in entries:
        if e["kind"] != current_kind:
            current_kind = e["kind"]
            lines.append("")
            lines.append(f"### {_KIND_LABELS.get(current_kind, current_kind)}")
            lines.append("-" * 60)
        status = "tasdiqlangan" if e["status"] == "verified" else "tasdiq kutmoqda"
        lines.append(f"VAZIYAT: {e['situation']}")
        lines.append(f"TEXNIKA: {e['technique']}")
        for p in e.get("phrases", []):
            src = f" — {p['source']}" if p.get("source") else ""
            lines.append(f"  IBORA: «{p['text']}»{src}")
        lines.append(f"  ({status})")
        lines.append("")
    content = "\n".join(lines).encode("utf-8")
    await callback.message.answer_document(BufferedInputFile(content, filename="sotuv_playbook.txt"))
    await callback.answer()
