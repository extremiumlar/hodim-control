import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import api_client
from bot.group_registry import invalidate

router = Router(name="group_admin")
logger = logging.getLogger(__name__)

PURPOSE_LABELS = {
    "mobilograf": "Mobilogrof (video nazorati)",
    "main": "Asosiy guruh (issiq lid, davomat, /statistika)",
    "stats": "Qo'shimcha statistika guruhi",
}


async def _require_dasturchi(message: Message) -> dict | None:
    """Faqat Dasturchi — bu bot-tomon (UI) tekshiruvi; API tomonda
    `monitored_groups._require_dasturchi` yana bir bor qat'iy tasdiqlaydi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user.get("role") != "dasturchi":
        return None
    return user


def _purpose_help(prefix: str) -> str:
    options = "\n".join(f" · <b>{key}</b> — {label}" for key, label in PURPOSE_LABELS.items())
    return f"{prefix}\n{options}"


@router.message(Command("guruh_biriktir"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_guruh_biriktir(message: Message, command: CommandObject) -> None:
    """Guruh ICHIDA yuborilganda joriy chatni shu maqsadga belgilaydi —
    "mobilograf"/"main" uchun eskisi avtomatik almashadi (guruhni o'zgartirish)."""
    if not await _require_dasturchi(message):
        return

    purpose = (command.args or "").strip().lower()
    if purpose not in PURPOSE_LABELS:
        await message.answer(_purpose_help("Maqsadni ko'rsating: <code>/guruh_biriktir &lt;maqsad&gt;</code>"))
        return

    try:
        await api_client.set_monitored_group(
            message.from_user.id, purpose, message.chat.id, title=message.chat.title
        )
    except httpx.HTTPStatusError:
        logger.exception("Guruhni biriktirishda xatolik")
        await message.answer("⚠️ Guruhni biriktirib bo'lmadi.")
        return

    invalidate()
    await message.answer(f"✅ Bu guruh endi <b>{PURPOSE_LABELS[purpose]}</b> uchun belgilandi.")


@router.message(Command("guruh_ochir"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_guruh_ochir(message: Message, command: CommandObject) -> None:
    """Guruh ICHIDA yuborilganda joriy chatni shu maqsaddan olib tashlaydi."""
    if not await _require_dasturchi(message):
        return

    purpose = (command.args or "").strip().lower()
    if purpose not in PURPOSE_LABELS:
        await message.answer(_purpose_help("Maqsadni ko'rsating: <code>/guruh_ochir &lt;maqsad&gt;</code>"))
        return

    try:
        await api_client.remove_monitored_group(message.from_user.id, purpose, message.chat.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Bu guruh shu maqsad uchun ro'yxatda topilmagan edi.")
            return
        logger.exception("Guruhni ro'yxatdan olib tashlashda xatolik")
        await message.answer("⚠️ Amalni bajarib bo'lmadi.")
        return

    invalidate()
    await message.answer(f"✅ Bu guruh <b>{PURPOSE_LABELS[purpose]}</b> ro'yxatidan olib tashlandi.")


@router.message(Command("guruhlar"), F.chat.type == "private")
async def cmd_guruhlar(message: Message) -> None:
    """Shaxsiy chatda — barcha faol guruh-maqsad bog'lanishlarini ko'rsatadi."""
    if not await _require_dasturchi(message):
        return

    try:
        rows = await api_client.list_monitored_groups()
    except httpx.HTTPStatusError:
        logger.exception("Guruhlar ro'yxatini olishda xatolik")
        await message.answer("⚠️ Ro'yxatni olib bo'lmadi.")
        return

    by_purpose: dict[str, list[dict]] = {}
    for row in rows:
        by_purpose.setdefault(row["purpose"], []).append(row)

    lines = ["<b>Kuzatuv guruhlari:</b>"]
    for purpose, label in PURPOSE_LABELS.items():
        group_rows = by_purpose.get(purpose, [])
        if not group_rows:
            lines.append(f"\n<b>{label}</b>: sozlanmagan")
            continue
        lines.append(f"\n<b>{label}</b>:")
        for row in group_rows:
            title = row.get("title") or "(nomsiz)"
            lines.append(f" · {title} — <code>{row['chat_id']}</code>")

    await message.answer("\n".join(lines))
