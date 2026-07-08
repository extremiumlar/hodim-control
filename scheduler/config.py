import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_SHARED_SECRET = os.getenv("BOT_SHARED_SECRET", "please-change-this-bot-secret")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")

# ─── Vaqt/interval sozlamalari (barcha jadval tunablari shu yerda) ───────────────
# Vazifa eslatmalari (6.3-bo'lim): kunduzi bitta, kechga yaqin har soatda.
REMINDER_HOURS = [13, 16, 17, 18]
DAILY_SUMMARY_HOUR = 19

# CRM webhook o'rniga zaxira: deyarli real-vaqtli bo'lishi uchun tez-tez so'raladi.
# amoCRM ulanganda API rate-limitga e'tibor bering (oraliqni kattalashtirish kerak
# bo'lishi mumkin).
CRM_SYNC_INTERVAL_SECONDS = 30

# Lid statistikasi snapshoti: butun bazani sekin sahifalaydi — tez-tez emas.
LEAD_SNAPSHOT_INTERVAL_MINUTES = 30
LEAD_SNAPSHOT_FREEZE_HOUR = 23  # kun yakunida oxirgi holatni "muzlatish"
LEAD_SNAPSHOT_FREEZE_MINUTE = 57

# Oylik bonus — oyning oxirgi kuni (8-bo'lim).
MONTHLY_BONUS_DAY = "last"
MONTHLY_BONUS_HOUR = 23
MONTHLY_BONUS_MINUTE = 30

# misfire_grace_time: scheduler band/o'chiq bo'lgani sabab job o'z vaqtida ishlamasa,
# butunlay o'tkazib yubormasdan grace davri ichida bitta marta ishga tushiradi.
MISFIRE_GRACE_DEFAULT = 3600
MISFIRE_GRACE_SHORT = 600
