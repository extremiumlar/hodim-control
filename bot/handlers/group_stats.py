from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID
from bot.handlers.stats import send_global_stats

router = Router(name="group_stats")

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}


@router.message(Command("statistika"), F.chat.id == TELEGRAM_GROUP_CHAT_ID)
async def cmd_statistika(message: Message) -> None:
    """Guruhda /statistika — umumiy kunlik xulosa + qo'ng'iroqlar, hamda har bir
    xodimning lid bosqich statistikasini (alohida xabar) guruhga yuboradi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        await message.reply("Bu buyruq faqat HR/ROP/Boshliq uchun mavjud.")
        return

    await send_global_stats(message, to_group=True)
    # Har bir xodimning lid bosqich statistikasi (alohida postlar)
    result = await api_client.post_lead_stats_to_group()
    if not result.get("posted"):
        await message.reply("Lid bo'yicha statistika yuborilmadi (bugun faoliyat yo'q yoki guruh sozlanmagan).")


@router.message(Command("statistika_vaqt"))
async def cmd_statistika_vaqt(message: Message, command: CommandObject) -> None:
    """Boshliq guruhga avtomatik yuborish vaqtini o'zgartiradi: /statistika_vaqt 20:00.
    Argumentsiz — joriy vaqtni ko'rsatadi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"boss", "dasturchi"}:
        await message.reply("Vaqtni faqat Boshliq o'zgartira oladi.")
        return

    arg = (command.args or "").strip()
    if not arg:
        cur = await api_client.get_group_post_time(message.from_user.id)
        await message.reply(
            f"Guruhga avtomatik yuborish vaqti: {cur['hour']:02d}:{cur['minute']:02d}\n"
            "O'zgartirish: /statistika_vaqt 20:00"
        )
        return

    try:
        hh, mm = arg.split(":")
        hour, minute = int(hh), int(mm)
    except (ValueError, AttributeError):
        await message.reply("Format noto'g'ri. Masalan: /statistika_vaqt 20:00")
        return
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        await message.reply("Vaqt noto'g'ri (soat 0-23, daqiqa 0-59).")
        return

    res = await api_client.set_group_post_time(message.from_user.id, hour, minute)
    if res is None:
        await message.reply("Ruxsat yo'q.")
    else:
        await message.reply(f"✅ Guruhga yuborish vaqti {res['hour']:02d}:{res['minute']:02d} ga o'zgartirildi.")
