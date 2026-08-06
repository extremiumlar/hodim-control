#!/bin/bash
# hodimlar_tizimi botini cPanel'da DOIMIY FON JARAYONI sifatida tirik saqlaydi
# (chatbot'ning keepalive_userbot.sh naqshi bilan bir xil — u 3+ kun muammosiz
# ishlagani isbotlangan).
#
# Nega polling (webhook emas): Passenger'ga bu hostda ATIGI 1 ta ishchi
# berilgan; webhook rejimida har bir Telegram xabari o'sha yagona ishchidan
# o'tar va web-panel so'rovlari navbatda qotardi. Polling rejimida bot alohida
# jarayonda ishlaydi (bo'sh turgan RAM/CPU'dan foydalanadi), API bilan esa
# in-process gaplashadi (BOT_INPROCESS_API=true) — ishchiga umuman tegmaydi.
#
# Sozlash (crontab):
#   */3 * * * * bash ~/hodimlar-tizimi/deploy/cpanel/keepalive_bot.sh >> ~/hodimlar-tizimi/logs/cron_keepalive.log 2>&1
#
# Server .env'da SHART: FORCE_LOCAL_POLLING=true (webhook-guard'ni chetlab
# o'tish uchun — webhook Telegram'dan ongli ravishda o'chirilgan) va
# BOT_INPROCESS_API=true. Webhook'ni qaytarish: scripts/set_webhook.py --set
# va bu cron qatorini olib tashlash.
set -e

ROOT="$HOME/hodimlar-tizimi"
VENV_PY="$HOME/virtualenv/hodimlar-tizimi/3.11/bin/python"
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/bot_polling.log"

cd "$ROOT"

if pgrep -f "bot\.main" > /dev/null 2>&1; then
    exit 0  # allaqachon ishlab turibdi
fi

nohup "$VENV_PY" -m bot.main >> "$LOG" 2>&1 &
disown
echo "$(date '+%Y-%m-%d %H:%M:%S'): hodimlar bot (polling) qayta ishga tushirildi (PID $!)"
