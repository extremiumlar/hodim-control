"""Telegram bot orqali xabar yuborish."""
from __future__ import annotations
import logging
import requests
from django.conf import settings

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(text: str, chat_id: str | None = None) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat = chat_id or settings.TELEGRAM_GROUP_CHAT_ID
    if not token or not chat:
        log.warning("Telegram konfiguratsiyasi yo'q, xabar yuborilmadi: %s", text)
        return False
    try:
        r = requests.post(
            API.format(token=token),
            json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        if r.status_code != 200:
            log.error("Telegram xato: %s", r.text)
            return False
        return True
    except requests.RequestException as e:
        log.error("Telegram so'rov xatosi: %s", e)
        return False


def notify_late_check_in(att):
    text = (
        f"⚠️ <b>Kechikish</b>\n"
        f"Hodim: {att.user.get_full_name() or att.user.username}\n"
        f"Vaqt: {att.check_in_time:%H:%M}\n"
        f"Kechikish: <b>{att.late_minutes} daqiqa</b>"
    )
    send_telegram(text)


def notify_early_leave(att):
    text = (
        f"🚪 <b>Erta ketish</b>\n"
        f"Hodim: {att.user.get_full_name() or att.user.username}\n"
        f"Ketgan vaqti: {att.check_out_time:%H:%M}\n"
        f"Erta ketish: <b>{att.early_leave_minutes} daqiqa</b>"
    )
    send_telegram(text)


def notify_absent(user, threshold: str = "09:30"):
    text = (
        f"❌ <b>Kelmadi</b>\n"
        f"Hodim: {user.get_full_name() or user.username}\n"
        f"Soat {threshold} bo'ldi, hali check-in qilmagan."
    )
    send_telegram(text)
