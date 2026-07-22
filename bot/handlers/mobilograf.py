import logging

from aiogram import F, Router
from aiogram.types import Message, MessageReactionUpdated, ReactionTypeEmoji

from bot import api_client
from bot import group_registry

router = Router(name="mobilograf")
logger = logging.getLogger(__name__)

CONFIRM_EMOJI = "✅"


def _has_confirm_emoji(reactions: list) -> bool:
    return any(isinstance(r, ReactionTypeEmoji) and r.emoji == CONFIRM_EMOJI for r in reactions)


async def _is_mobilograf_chat(message: Message) -> bool:
    return message.chat.id in await group_registry.get_group_ids("mobilograf")


async def _is_mobilograf_reaction_chat(event: MessageReactionUpdated) -> bool:
    return event.chat.id in await group_registry.get_group_ids("mobilograf")


@router.message(_is_mobilograf_chat, F.video | F.video_note)
async def on_mobilograf_video(message: Message) -> None:
    video_type = "dumaloq" if message.video_note else "oddiy"
    try:
        await api_client.create_mobilograf_video(
            telegram_id=message.from_user.id,
            telegram_message_id=message.message_id,
            group_chat_id=message.chat.id,
            video_type=video_type,
        )
    except Exception:
        # Foydalanuvchi xodim sifatida ro'yxatdan o'tmagan bo'lishi mumkin — jim o'tkazamiz,
        # guruhda notinch xabarlar yuborilmasin.
        logger.info("Mobilograf video e'tiborga olinmadi (xodim topilmadi bo'lishi mumkin)")


@router.message(_is_mobilograf_chat, F.reply_to_message, F.text)
async def on_mobilograf_reply_confirm(message: Message) -> None:
    """Amaliyotda boshliq ko'pincha Telegramning "ushlab turib" reaksiyasini
    emas, videoga REPLY qilib matnda ✅ yuborishni ishlatadi — bu oddiy matnli
    xabar (message_reaction emas), shuning uchun alohida ushlanadi. Ruxsat
    tekshiruvi (boshliq/dasturchi/rahbar) API tomonda — xuddi native reaksiya
    bilan bir xil (`react_mobilograf_video`, action="add")."""
    if CONFIRM_EMOJI not in (message.text or ""):
        return

    try:
        result = await api_client.react_mobilograf_video(
            group_chat_id=message.chat.id,
            telegram_message_id=message.reply_to_message.message_id,
            reactor_telegram_id=message.from_user.id,
            action="add",
        )
    except Exception:
        logger.exception("Mobilograf reply-tasdiqlashda xatolik")
        return

    if result is None:
        # Reply qilingan xabar mobilograf video emas (yoki topilmadi) — jim o'tkazamiz.
        return


@router.message_reaction(_is_mobilograf_reaction_chat)
async def on_mobilograf_reaction(event: MessageReactionUpdated) -> None:
    if not event.user:
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
