"""Telegram «/» menyusi va slash-buyruq ruxsatlari — BOT tomoni.

Qoida (kim qaysi buyruqni ko'radi/ishlata oladi) BU YERDA EMAS —
`api/services/sections.py: ALL_COMMANDS` da. Bu modul faqat:
  · serverdan kelgan tayyor ro'yxatni Telegram «/» menyusiga chizadi;
  · buyruq matnini ajratadi (`/reja@bot_nomi` ham to'g'ri o'qiladi);
  · ruxsat yo'q bo'lsa SABABINI aniqlaydi (rolmi yoki noto'g'ri joymi).

Bu — `bot/keyboards.py: main_menu` bilan bir xil naqsh: server hisoblaydi,
bot chizadi. Aks holda rol shartlari yana ikki joyda yashagan bo'lardi.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
)

logger = logging.getLogger(__name__)

PRIVATE = "private"
GROUP = "group"

#  Rol nomining ko'rinadigan shakli — xato matnida («Sizning lavozimingiz:»)
#  va `/start` salomida ishlatiladi. Bitta joyda: ilgari `start.py` da
#  `ROLE_NAMES` nomi bilan alohida nusxasi bor edi.
ROLE_LABELS = {
    "employee": "Xodim",
    "hr": "HR",
    "rop": "ROP",
    "boss": "Boshliq",
    "dasturchi": "Dasturchi",
}

#  Ro'yxatdan o'tmagan (yoki hali /start bosmagan) odam ko'radigan yagona
#  buyruq. Qolganini u baribir ishlata olmaydi — menyuda ko'rsatish faqat
#  chalkashlik tug'dirardi.
_DEFAULT_COMMANDS = [BotCommand(command="start", description="Botni ishga tushirish")]

#  setMyCommands ni har xabarda qayta chaqirmaslik uchun: {scope_kaliti: barmoq izi}.
#  Jarayon qayta ishga tushsa kesh bo'shaydi va ro'yxat bir marta yangilanadi —
#  bu xavfsiz (Telegram bir xil ro'yxatni qayta yozishga ruxsat beradi).
_synced: dict[str, str] = {}


def extract_command(text: str | None, bot_username: str | None = None) -> str | None:
    """«/reja qolgan matn» yoki «/reja@Hodimlar_bot» dan `reja` ni ajratadi.

    Guruhda Telegram buyruqqa bot nomini qo'shadi; `@boshqa_bot` ga
    yo'naltirilgan buyruq bizniki EMAS — `None` qaytadi (aks holda bitta
    guruhda ikki bot bo'lsa, ikkalasi ham javob berardi)."""
    if not text or not text.startswith("/"):
        return None
    head = text.split(maxsplit=1)[0][1:]
    if not head:
        return None
    if "@" in head:
        head, _, target = head.partition("@")
        if bot_username and target.lower() != bot_username.lower():
            return None
    head = head.strip().lower()
    return head or None


def chat_scope(chat_type: str) -> str:
    """Telegram chat turini buyruq qamroviga o'giradi (kanal — guruh kabi)."""
    return PRIVATE if chat_type == PRIVATE else GROUP


def find_spec(specs: list[dict] | None, name: str) -> dict | None:
    """Serverdan kelgan ro'yxatdan buyruq tavsifini topadi."""
    for spec in specs or []:
        if spec.get("command") == name:
            return spec
    return None


def visible_commands(specs: list[dict] | None, scope: str) -> list[BotCommand]:
    """Shu qamrov uchun «/» menyusiga chiziladigan buyruqlar."""
    return [
        BotCommand(command=s["command"], description=s.get("description") or s["command"])
        for s in (specs or [])
        if s.get("allowed") and scope in (s.get("scopes") or [])
    ]


#  `check_access` natijalari.
OK = "ok"
UNKNOWN = "unknown"  # reestrda yo'q (eskirgan buyruq) — handler o'zi hal qiladi
WRONG_SCOPE = "scope"  # to'g'ri buyruq, noto'g'ri joy (guruh/shaxsiy)
NO_ACCESS = "role"  # lavozimi yetmaydi


def check_access(specs: list[dict] | None, name: str, scope: str) -> tuple[str, dict | None]:
    """Buyruqni bajarish mumkinmi — va mumkin bo'lmasa NEGA.

    Sof funksiya (tarmoq yo'q): `CommandGuard` ham, testlar ham shu yerdan
    bir xil qarorni oladi. Guruh-maqsad tekshiruvi (`group_purposes`) bu
    yerda EMAS — u biriktirilgan guruhlar ro'yxatini talab qiladi, ya'ni
    async; uni guard `OK` dan keyin alohida tekshiradi."""
    spec = find_spec(specs, name)
    if spec is None:
        return UNKNOWN, None
    if scope not in (spec.get("scopes") or []):
        return WRONG_SCOPE, spec
    if not spec.get("allowed"):
        return NO_ACCESS, spec
    return OK, spec


def _fingerprint(commands: list[BotCommand]) -> str:
    return "|".join(f"{c.command}:{c.description}" for c in commands)


async def _apply(bot: Bot, key: str, commands: list[BotCommand], scope) -> bool:
    """setMyCommands — faqat ro'yxat o'zgargan bo'lsa. `True` = yuborildi."""
    fp = _fingerprint(commands)
    if _synced.get(key) == fp:
        return False
    try:
        await bot.set_my_commands(commands, scope=scope)
    except Exception:  # noqa: BLE001
        # Odatiy sabab: xodim o'sha guruh a'zosi emas, yoki bot guruhdan
        # chiqarilgan. Bu oqimni to'xtatmasligi kerak — menyu bezak, ruxsat
        # nazorati esa alohida (command_guard) ishlaydi.
        logger.warning("«/» menyusini o'rnatib bo'lmadi (%s)", key, exc_info=True)
        return False
    _synced[key] = fp
    return True


async def set_default_commands(bot: Bot) -> None:
    """Umumiy menyu: shaxsiy chatda `/start`, guruhlarda — hech nima.

    Guruhda bo'sh ro'yxat ATAYLAB: guruh a'zolarining ko'pchiligi oddiy
    xodim, ularda guruh buyrug'i yo'q. Rahbarlar esa `chat_member` qamrovi
    orqali O'Z ro'yxatini oladi (`sync_group_member`)."""
    await _apply(bot, "default", _DEFAULT_COMMANDS, BotCommandScopeDefault())
    await _apply(bot, "all_groups", [], BotCommandScopeAllGroupChats())


async def sync_private(bot: Bot, telegram_id: int, specs: list[dict] | None) -> None:
    """Xodimning SHAXSIY chatidagi «/» menyusi — lavozimiga mos."""
    await _apply(
        bot,
        f"chat:{telegram_id}",
        visible_commands(specs, PRIVATE),
        BotCommandScopeChat(chat_id=telegram_id),
    )


async def sync_group_member(bot: Bot, chat_id: int, telegram_id: int,
                            specs: list[dict] | None) -> None:
    """Xodimning AYNAN SHU GURUHDAGI «/» menyusi.

    Telegram'da guruh menyusini har bir a'zo uchun alohida berish yagona
    yo'li — `chat_member` qamrovi. Shuning uchun ro'yxat guruhga emas,
    (guruh, xodim) juftligiga yoziladi."""
    await _apply(
        bot,
        f"member:{chat_id}:{telegram_id}",
        visible_commands(specs, GROUP),
        BotCommandScopeChatMember(chat_id=chat_id, user_id=telegram_id),
    )
