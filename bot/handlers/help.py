"""`/buyruqlar` — xodim O'ZIGA ruxsat etilgan buyruqlar ro'yxatini ko'radi.

Telegram'ning «/» menyusi ham shu ro'yxatni ko'rsatadi, lekin u:
  · qurilma keshiga bog'liq (rol o'zgarganda darrov yangilanmasligi mumkin);
  · guruhda a'zo o'zi ochmasa ko'rinmaydi.
Shuning uchun buyruq ko'rinishi ham kerak — va u har chaqirilganda «/»
menyusini ham jimgina yangilab qo'yadi (o'z-o'zini tuzatish)."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import api_client
from bot.commands import GROUP, PRIVATE, chat_scope, sync_group_member, sync_private

router = Router(name="help")
logger = logging.getLogger(__name__)


@router.message(Command("buyruqlar"))
async def cmd_buyruqlar(message: Message) -> None:
    """Ro'yxat SHU chat turiga mos: guruhda guruh buyruqlari, shaxsiy chatda
    shaxsiy buyruqlar — xodim ishlamaydigan buyruqni ko'rib adashmasin."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.reply(
            "⛔ Siz tizimda ro'yxatdan o'tmagansiz.\n"
            "HR yoki rahbaringizdan taklif havolasini so'rang, so'ng /start bosing."
        )
        return

    specs = user.get("bot_commands") or []
    scope = chat_scope(message.chat.type)
    mine = [s for s in specs if s.get("allowed") and scope in (s.get("scopes") or [])]

    joy = "shu guruhda" if scope == GROUP else "shaxsiy chatda"
    if not mine:
        await message.reply(
            f"Sizning lavozimingizda {joy} ishlatiladigan buyruq yo'q.\n"
            "Barcha ishlaringiz pastdagi menyu tugmalari orqali bajariladi."
        )
        return

    lines = [f"<b>Sizga ruxsat etilgan buyruqlar</b> ({joy}):", ""]
    lines += [f"/{s['command']} — {s.get('description') or ''}".rstrip(" —") for s in mine]

    #  Shaxsiy chatda guruh buyruqlari ham borligini eslatib qo'yamiz —
    #  rahbar «/statistika qayerda?» deb qidirmasin.
    if scope == PRIVATE:
        group_only = [
            s for s in specs
            if s.get("allowed") and GROUP in (s.get("scopes") or [])
            and PRIVATE not in (s.get("scopes") or [])
        ]
        if group_only:
            lines += ["", "<i>Faqat guruh ichida ishlaydi:</i>"]
            lines += [f"/{s['command']} — {s.get('description') or ''}".rstrip(" —")
                      for s in group_only]

    await message.reply("\n".join(lines))

    #  «/» menyusini ham yangilab qo'yamiz (kesh eskirgan bo'lsa tuzaladi).
    try:
        if scope == GROUP:
            await sync_group_member(message.bot, message.chat.id, message.from_user.id, specs)
        else:
            await sync_private(message.bot, message.from_user.id, specs)
    except Exception:  # noqa: BLE001
        logger.warning("«/» menyusini yangilab bo'lmadi", exc_info=True)
