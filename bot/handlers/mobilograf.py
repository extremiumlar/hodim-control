import logging

from aiogram import F, Router
from aiogram.types import Message, MessageReactionUpdated, ReactionTypeEmoji

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID

router = Router(name="mobilograf")
logger = logging.getLogger(__name__)

CONFIRM_EMOJI = "✅"


def _has_confirm_emoji(reactions: list) -> bool:
    return any(isinstance(r, ReactionTypeEmoji) and r.emoji == CONFIRM_EMOJI for r in reactions)


@router.message(F.chat.id == TELEGRAM_GROUP_CHAT_ID, F.video)
async def on_mobilograf_video(message: Message) -> None:
    if not TELEGRAM_GROUP_CHAT_ID:
        return

    try:
        await api_client.create_mobilograf_video(
            telegram_id=message.from_user.id,
            telegram_message_id=message.message_id,
            group_chat_id=message.chat.id,
        )
    except Exception:
        # Foydalanuvchi xodim sifatida ro'yxatdan o'tmagan bo'lishi mumkin — jim o'tkazamiz,
        # guruhda notinch xabarlar yuborilmasin.
        logger.info("Mobilograf video e'tiborga olinmadi (xodim topilmadi bo'lishi mumkin)")


@router.message_reaction(F.chat.id == TELEGRAM_GROUP_CHAT_ID)
async def on_mobilograf_reaction(event: MessageReactionUpdated) -> None:
    if not TELEGRAM_GROUP_CHAT_ID or not event.user:
        return

    old_has = _has_confirm_emoji(event.old_reaction)
    new_has = _has_confirm_emoji(event.new_reaction)

    if new_has and not old_has:
        action = "add"
    elif old_has and not new_has:
        action = "remove"
    else:
        return

    try:
        await api_client.react_mobilograf_video(
            group_chat_id=event.chat.id,
            telegram_message_id=event.message_id,
            reactor_telegram_id=event.user.id,
            action=action,
        )
    except Exception:
        logger.exception("Mobilograf reaksiyasini qayta ishlashda xatolik")
