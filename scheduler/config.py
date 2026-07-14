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

# Haftalik raqamli yakun (kod digesti, AI'siz ham ishlaydi) — yakshanba kechqurun.
# Kunlik digest vaqti bu yerda EMAS — bazadan (boss, /statistika_vaqt) sozlanadi.
WEEKLY_DIGEST_DOW = "sun"
WEEKLY_DIGEST_HOUR = 20
WEEKLY_DIGEST_MINUTE = 0

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

# Oylik digest — oyning oxirgi kuni kechqurun (bonus hisobidan OLDIN chiqadi,
# shuning uchun bonus qatori odatda keyingi oy boshida qo'lda /oylik bilan ko'rinadi).
MONTHLY_DIGEST_DAY = "last"
MONTHLY_DIGEST_HOUR = 20
MONTHLY_DIGEST_MINUTE = 30

# ─── Operator AI (avto-reja dvigateli) ─────────────────────────────────────────
# API tomonda `AI_ENABLED` o'chiq bo'lsa bu endpointlar no-op (`disabled`) — CRM/DB
# ga yuk tushmaydi. Yoqilganda: har necha daqiqada bugungi actual snapshoti; har kuni
# ertalab kunlik reja tuziladi; haftada bir marta profillar qayta hisoblanadi.
AI_SNAPSHOT_INTERVAL_MINUTES = 15  # bugungi soatlik actual (yengil, early-stop skan)
AI_BUILD_TARGETS_HOUR = 6  # kunlik reja ish boshlanishidan oldin tuziladi
AI_COMPUTE_PROFILES_DOW = "sun"  # profillar haftada (yakshanba) qayta hisoblanadi
AI_COMPUTE_PROFILES_HOUR = 5  # build-targets (06:00) dan oldin ishlashi uchun
# Soatlik kuzatuv (nudge) daqiqasi: soat boshidan keyin — endpoint o'zi yangi
# snapshot oladi, shuning uchun :00 bilan to'qnashuv muhim emas, lekin soat
# yakunlangach baholagan ma'qul.
AI_WATCH_MINUTE = 5
# Haftalik AI trend (shaxsiy xabarlar) — haftalik digestdan 10 daqiqa keyin:
# operator avval guruhdagi raqamli yakunni, keyin shaxsiy AI xulosasini ko'radi.
AI_WEEKLY_DOW = "sun"
AI_WEEKLY_HOUR = 20
AI_WEEKLY_MINUTE = 10
# Issiq lid (speed-to-lead): yangi lidni tez ilg'ash uchun qisqa interval. Har tick
# ~1 filter so'rovi (+ yangi lid bo'lsa detal), rate limit (60/min)ga bemalol sig'adi.
HOT_LEAD_POLL_MINUTES = 2

# misfire_grace_time: scheduler band/o'chiq bo'lgani sabab job o'z vaqtida ishlamasa,
# butunlay o'tkazib yubormasdan grace davri ichida bitta marta ishga tushiradi.
MISFIRE_GRACE_DEFAULT = 3600
MISFIRE_GRACE_SHORT = 600
