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

# Davomat (kelib-ketish) digesti guruhga: ertalab — kim keldi/kechikdi/kelmadi;
# kechqurun — kun yakuni (ish vaqti, chiqmaganlar). Dam olish kunida (hech kim
# ishlamasa) yuborilmaydi.
ATTENDANCE_MORNING_HOUR = 9
ATTENDANCE_MORNING_MINUTE = 30
ATTENDANCE_EVENING_HOUR = 22
ATTENDANCE_EVENING_MINUTE = 0

# CRM webhook o'rniga zaxira: DailyResult (suhbat/tashrif) sinxroni. Har ishga
# tushish bugungi BUTUN call-history'ni sahifalab o'qiydi (kun oxirida 10-15
# sahifa) + tashrif-bosqich lidlarini — 30s intervalda bu yolg'iz o'zi Uysot'ning
# 60 so'rov/daqiqa umumiy limitining uchdan birigacha yeyayotgan edi (2026-08-03,
# 429 bo'roni tahlili). 120s ga tushirildi: bu ma'lumot bot/sayt "bugungi norma"
# ko'rinishlarini boqadi — 2 daqiqalik kechikish sezilmaydi, byudjet esa 4
# barobar tejaladi.
CRM_SYNC_INTERVAL_SECONDS = 120

# Lid statistikasi snapshoti (LeadStageDaily — haftalik/oylik digest va bot
# "Lidlar statistikasi"ni ta'minlaydi). Tarix: bu job ilgari butun CRM bazasini
# (~184 sahifa, jonli o'lchov 2026-07-25: ~375s) skanerlaydigan ENG KATTA
# so'rov-iste'molchi edi; 2026-08-03 dan lid qismi LOKAL LeadEvent/CrmLeadState
# hisobiga o'tkazildi (api/routers/stats.py) — endi CRM'ga faqat bugungi
# qo'ng'iroqlar skani (`_snapshot_calls`, kun oxirida 10-15 sahifa) chiqadi.
# Interval 30 daqiqada qoldirildi: qo'ng'iroq statistikasi uchun yetarli,
# so'rov byudjetida esa katta zaxira beradi.
LEAD_SNAPSHOT_INTERVAL_MINUTES = 30
LEAD_SNAPSHOT_FREEZE_HOUR = 23  # kun yakunida oxirgi holatni "muzlatish"
LEAD_SNAPSHOT_FREEZE_MINUTE = 57

# Diff-engine (lead_diff.py): lidlarning HAQIQIY bosqich/mas'ul o'zgarishini
# (LeadEvent) kuzatadi — LEAD_SNAPSHOT'dan farqli, chegaralangan (so'nggi
# CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS kun yaratilgan) tez skan bo'lgani uchun
# tez-tez ishlashi mumkin — guruh digesti deyarli real-vaqtli bo'ladi. Jonli
# o'lchovda (2026-07-21) 30 kunlik oyna ~60-70s davom etdi — 5 daqiqalik
# interval bemalol yetadi (CRM lid soni o'ssa CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS
# yoki shu intervalni kattalashtirish kerak). Tungi to'liq solishtiruv
# (reconcile) kam trafik vaqtida BUTUN bazani qamraydi.
LEAD_DIFF_INTERVAL_MINUTES = 5
LEAD_DIFF_RECONCILE_HOUR = 3
LEAD_DIFF_RECONCILE_MINUTE = 30

# Oylik bonus — oyning oxirgi kuni (8-bo'lim).
MONTHLY_BONUS_DAY = "last"
MONTHLY_BONUS_HOUR = 23
MONTHLY_BONUS_MINUTE = 30

# Oylik digest — oyning oxirgi kuni kechqurun (bonus hisobidan OLDIN chiqadi,
# shuning uchun bonus qatori odatda keyingi oy boshida qo'lda /oylik bilan ko'rinadi).
MONTHLY_DIGEST_DAY = "last"
MONTHLY_DIGEST_HOUR = 20
MONTHLY_DIGEST_MINUTE = 30

# Ertalabki "kecha yakuni" tuzatishi: kechagi yakuniy raqam kechqurungi digestdagidan
# sezilarli oshgan bo'lsagina guruhga qisqa xabar (API o'zi taqqoslaydi va hal qiladi).
YESTERDAY_CORRECTION_HOUR = 9
YESTERDAY_CORRECTION_MINUTE = 0

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

# Real-vaqtli harakatsizlik nazorati (4-band, idle_watch.py): 20 daqiqalik
# chegarani o'z vaqtida ilg'ash uchun soatlikdan (ai_watch) ancha tezroq.
IDLE_WATCH_INTERVAL_MINUTES = 5

# «Keldim/Ketdim bosishni unutmang» eslatmasi. Oldindan ogohlantirish oynasi
# API tomonda (`attendance_reminder_before_start_min`, default 15 daqiqa) —
# shu interval undan KICHIK bo'lishi kerak, aks holda oyna sakrab o'tilib,
# eslatma umuman yuborilmay qolishi mumkin.
ATTENDANCE_REMINDER_INTERVAL_MINUTES = 5

# Ish kundaligi eslatmasi («bugun hali hech narsa yozmadingiz»). API tomondagi
# oyna kengroq (ish tugashiga 30 daqiqa qolganidan to 2 soat keyingacha,
# work_log.py) — 10 daqiqalik interval oynani sakrab o'tolmaydi va kuniga
# baribir bitta xabar ketadi (UNIQUE iz).
WORK_LOG_REMINDER_INTERVAL_MINUTES = 10

# E'tiroz/shikoyat SLA tekshiruvi — kuniga bir marta yetadi (chegara 3 va 5
# KUN). Ish kuni boshida, HR stoliga o'tirganda ko'rsin.
APPEALS_SLA_HOUR = 10
APPEALS_SLA_MINUTE = 7

# Telegram login xavfsizligi: replay-himoya hash'lari va rate-limit urinish
# yozuvlarini tozalash chastotasi — vaqtinchalik jadvallar, shoshilinch emas.
LOGIN_SECURITY_CLEANUP_INTERVAL_MINUTES = 60

# misfire_grace_time: scheduler band/o'chiq bo'lgani sabab job o'z vaqtida ishlamasa,
# butunlay o'tkazib yubormasdan grace davri ichida bitta marta ishga tushiradi.
MISFIRE_GRACE_DEFAULT = 3600
MISFIRE_GRACE_SHORT = 600

# ─── Payroll avtomatikasi (OYLIK_JARIMA_REJASI.md, Bosqich 6) ───────────────────
# Oylik ish haqi — keyingi oyning 1-kuni ertalab (9-bo'lim, savol 10, QAROR).
# Oylik bonus (kechagi oyning oxirgi kuni 23:30) va kechagi kunning davomat
# yopilishi (22:00)dan YETARLICHA keyin — ikkalasi ham allaqachon tugagan bo'ladi.
MONTHLY_PAYROLL_DAY = 1
MONTHLY_PAYROLL_HOUR = 6
MONTHLY_PAYROLL_MINUTE = 0

# Kechikish limiti ogohlantirishi (1.5-band) — ish kuni boshlanishidan oldin,
# xodim "bugun ehtiyot bo'lishi kerak"ligini bilib ishga chiqsin.
LATE_WARNING_HOUR = 7
LATE_WARNING_MINUTE = 30

# Qo'shimcha ish avtomatik aniqlash (1.3-band) — kam trafik vaqtida (tungi),
# HR ish kuni boshlanguncha nomzodlar tayyor bo'lishi uchun.
OVERTIME_AUTO_DETECT_HOUR = 1
OVERTIME_AUTO_DETECT_MINUTE = 0
