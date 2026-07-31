"""Xodimga xabar yuborishning YAGONA kirish nuqtasi — Telegram + push.

Nega alohida modul: `telegram_notify.send_message` 45 joyda chaqiriladi va
uning o'zi push haqida hech narsa bilmaydi. Har chaqiruv joyiga push kodini
qo'shish o'rniga, chaqiruvlar shu yerdan o'tadi — toifa, tinch soatlar va
"ilova faol bo'lsa Telegramni takrorlamaslik" qoidasi bitta joyda qoladi.

`send_message`ning o'zi O'ZGARMAGAN va hamon ishlaydi: guruh chatiga
yuborish (`main_chat_id`) yoki inline tugmali bot oqimlari uchun u to'g'ridan
to'g'ri ishlatilaveradi — u yerda "foydalanuvchi" tushunchasi yo'q.
"""

from __future__ import annotations

import html
import re

from sqlalchemy.ext.asyncio import AsyncSession

from api.services import push as push_service
from api.telegram_notify import send_message
from db.models import User

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Telegram HTML matnini push uchun oddiy matnga aylantiradi.

    Push bildirishnomasi HTML ko'rsatmaydi — teg qo'shilsa foydalanuvchi
    `<b>` belgilarini o'qiydi. Teglar olib tashlanib, HTML entity'lar
    (`&amp;` va h.k.) qaytariladi.
    """
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _split_title_body(text: str, title: str | None) -> tuple[str, str]:
    """Sarlavha berilmagan bo'lsa, matnning birinchi qatorini sarlavha qiladi.

    Bot xabarlari odatda "🆕 <b>Yangi vazifa</b>\\n..." ko'rinishida — birinchi
    qator aynan sarlavha bo'lib xizmat qiladi, ya'ni qo'lda takrorlash shart
    emas.
    """
    plain = strip_html(text)
    if title:
        return title, plain
    head, _, rest = plain.partition("\n")
    return (head, rest.strip()) if rest.strip() else ("N.B hodimlar", head)


async def notify_user(
    db: AsyncSession,
    user: User,
    category: str,
    text: str,
    *,
    title: str | None = None,
    reply_markup: dict | None = None,
    data: dict | None = None,
    force_telegram: bool = False,
) -> dict:
    """Xodimga xabar yuboradi: push + (kerak bo'lsa) Telegram.

    `text` — Telegram uchun HTML matn (mavjud chaqiruvlardagi kabi).
    `data` — push bosilganda ilova ochadigan bo'lim, masalan
    `{"path": "/me/tasks"}`.

    `force_telegram=True` — Telegram HAR DOIM yuborilsin. Bu inline tugmadagi
    amal ilovada MAVJUD BO'LMAGANDA kerak (masalan sababli kunni tasdiqlash
    hozircha faqat botda). Vazifadagi «✅ Bajardim» esa ilovada ham bor
    (`/me/tasks`), shuning uchun u uchun `force_telegram` SHART EMAS —
    aks holda eng tez-tez keladigan xabar doim ikki marta chalinardi.

    Qaytaradi: `{"push": <nechta qurilma>, "telegram": <yuborildimi>}`.
    """
    push_title, push_body = _split_title_body(text, title)
    sent_push = await push_service.send_push(
        db, user, category, push_title, push_body, data=data
    )

    # Telegram faqat push HAQIQATAN ketgan bo'lsa o'tkazib yuboriladi —
    # `sent_push` shuning uchun uzatiladi (FCM sozlanmagan/kalit buzilgan
    # bo'lsa xabar yo'qolib qolmasin).
    skip_telegram = not force_telegram and await push_service.should_skip_telegram(
        db, user, category, sent_push
    )
    sent_telegram = False
    if user.telegram_id and not skip_telegram:
        sent_telegram = await send_message(user.telegram_id, text, reply_markup) is not None

    return {"push": sent_push, "telegram": sent_telegram}
