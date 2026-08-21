"""Slash-buyruqlar uchun markazlashgan ruxsat nazorati.

MUAMMO NIMA EDI
───────────────
Har handler o'z tekshiruvini o'zi yozardi va ularning KO'PCHILIGI ruxsat
yo'q holatda JIMGINA `return` qilardi: `/guruhlar`, `/guruh_biriktir`,
`/norm_set`, `/norm_del`, `/att_fix`, `/unlock`, `/undo`, `/sotuv_ai`.
Xodim buyruqni bosardi — bot umuman javob bermasdi va u buyruq buzuqmi,
internet yo'qmi, yoki ruxsati yo'qmi — bilmasdi.

Bundan tashqari ba'zi buyruqlar `F.chat.type` yoki `_is_stats_chat`
FILTRI bilan cheklangan edi. Filtr mos kelmasa handler UMUMAN ishga
tushmaydi — ya'ni «noto'g'ri joyda yozdingiz» degan xabar ham chiqmasdi.

YECHIM
──────
`outer_middleware` — filtrlardan OLDIN ishlaydi, shuning uchun handler
filtri buyruqni «yutib yuborishidan» avval to'xtata oladi. Qoida esa
serverdan (`api/services/sections.py`) tayyor holda keladi: bu modul rol
hisoblamaydi, faqat javobga qarab to'sadi va SABABINI aytadi.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot import api_client, group_registry
from bot.commands import (
    GROUP,
    NO_ACCESS,
    ROLE_LABELS,
    UNKNOWN,
    WRONG_SCOPE,
    chat_scope,
    check_access,
    extract_command,
    sync_group_member,
)

logger = logging.getLogger(__name__)

#  `/start` — yagona ochiq buyruq: ro'yxatdan o'tmagan odam ham bosadi
#  (aynan u orqali hisobga bog'lanadi).
_PUBLIC = {"start"}

_PURPOSE_LABELS = {
    "main": "asosiy guruh",
    "stats": "statistika guruhi",
    "mobilograf": "mobilograf guruhi",
}


class CommandGuard(BaseMiddleware):
    """Har slash-buyruqni lavozim va joy bo'yicha tekshiradi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        bot = data.get("bot")
        username = None
        if bot is not None:
            try:
                username = (await bot.me()).username  # aiogram natijani keshlaydi
            except Exception:  # noqa: BLE001
                username = None

        name = extract_command(event.text, username)
        if name is None or name in _PUBLIC:
            return await handler(event, data)

        scope = chat_scope(event.chat.type)

        try:
            user = await api_client.get_user_by_telegram(event.from_user.id)
        except Exception:  # noqa: BLE001
            # Backend javob bermasa buyruqni TO'SMAYMIZ — handler o'zining
            # eski tekshiruvi bilan davom etadi (himoya ikki qavatli).
            logger.warning("Buyruq nazorati: foydalanuvchini olib bo'lmadi", exc_info=True)
            return await handler(event, data)

        if user is None:
            #  Guruhda JIM turamiz: begona odam yozgan tasodifiy «/...» ga
            #  javob berib guruhni ifloslantirmaslik uchun.
            if scope == GROUP:
                return await handler(event, data)
            await event.answer(
                "⛔ Siz tizimda ro'yxatdan o'tmagansiz.\n"
                "HR yoki rahbaringizdan taklif havolasini so'rang, so'ng /start bosing."
            )
            return None

        specs = user.get("bot_commands")
        verdict, spec = check_access(specs, name, scope)

        if verdict == UNKNOWN:
            #  Reestrda yo'q buyruq (masalan eskirgan `/ai_vaqt`) — eski
            #  xatti-harakat saqlanadi, handler o'zi hal qiladi.
            return await handler(event, data)
        if verdict == WRONG_SCOPE:
            await event.reply(_scope_error(name, spec.get("scopes") or []))
            return None
        if verdict == NO_ACCESS:
            await event.reply(_role_error(name, spec, user))
            return None

        purposes = spec.get("group_purposes") or []
        if scope == GROUP and purposes and not await _in_any_purpose(event.chat.id, purposes):
            await event.reply(_purpose_error(name, purposes))
            return None

        #  Ruxsat bor: shu guruhdagi «/» menyusini jimgina yangilab qo'yamiz —
        #  rol o'zgargan bo'lsa ro'yxat o'zidan-o'zi to'g'rilanadi.
        if scope == GROUP and bot is not None:
            try:
                await sync_group_member(bot, event.chat.id, event.from_user.id, specs)
            except Exception:  # noqa: BLE001
                logger.warning("Guruh «/» menyusini yangilab bo'lmadi", exc_info=True)

        data["bot_user"] = user
        return await handler(event, data)


async def _in_any_purpose(chat_id: int, purposes: list[str]) -> bool:
    for purpose in purposes:
        if await group_registry.is_in_group(chat_id, purpose):
            return True
    return False


def _scope_error(name: str, scopes: list[str]) -> str:
    joy = "guruh ichida" if GROUP in scopes else "shaxsiy chatda"
    return (
        f"⛔ <code>/{name}</code> bu yerda ishlamaydi.\n"
        f"Bu buyruq faqat <b>{joy}</b> ishlatiladi."
    )


def _role_error(name: str, spec: dict, user: dict) -> str:
    lavozim = ROLE_LABELS.get(user.get("role"), user.get("role") or "noma'lum")
    position = (user.get("position") or {}).get("name")
    lavozim_satri = f"{lavozim} · {position}" if position else lavozim
    return (
        f"⛔ <code>/{name}</code> — sizda bu buyruqqa ruxsat yo'q.\n"
        f"Bu buyruq <b>{spec.get('audience') or 'boshqa lavozim'}</b> uchun.\n"
        f"Sizning lavozimingiz: <b>{lavozim_satri}</b>.\n\n"
        "O'zingizga ruxsat etilgan buyruqlar: /buyruqlar"
    )


def _purpose_error(name: str, purposes: list[str]) -> str:
    nomlar = " yoki ".join(_PURPOSE_LABELS.get(p, p) for p in purposes)
    return (
        f"⛔ <code>/{name}</code> bu guruhda ishlamaydi.\n"
        f"U faqat <b>{nomlar}</b> sifatida biriktirilgan guruhda ishlaydi "
        "(<code>/guruh_biriktir</code> bilan belgilanadi)."
    )
