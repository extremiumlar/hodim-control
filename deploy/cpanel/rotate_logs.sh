#!/bin/sh
# Log rotatsiyasi — cPanel (shared hosting) uchun: tizim logrotate'i mavjud emas,
# shuning uchun oddiy POSIX sh bilan qilinadi. Kunlik crontab'dan chaqiriladi:
#
#   40 4 * * * bash ~/hodimlar-tizimi/deploy/cpanel/rotate_logs.sh >> ~/hodimlar-tizimi/logs/rotate.log 2>&1
#
# Nega 04:40: tungi og'ir ishlar (03:30 diff reconcile ~6-7 daqiqa, 04:38 lid
# snapshot) tugagan payt — uzoq ishlayotgan jarayonning fd'si eski (mv qilingan)
# faylga yozib, dumi bo'linib qolmasin.
#
# Nega `mv` xavfsiz: cron.log'ga yozuvchi yagona narsa — crontab'dagi `>>`
# yo'naltirish, u HAR DAQIQA yangi jarayonda faylni yo'l bo'yicha qayta ochadi.
# mv'dan keyingi birinchi tick yangi (bo'sh) faylni o'zi yaratadi — copytruncate
# ham, signal ham kerak emas.
#
# Har bir logs/*.log fayl MAX_BYTES'dan oshsa: eski arxivlar suriladi
# (log.1.gz -> log.2.gz ...), joriy fayl log.1 ga ko'chirilib gzip qilinadi,
# eng eskisi (KEEP dan oshgani) o'chadi. Yangi log faylga rotatsiya belgisi
# yoziladi — cron.log o'qiganda tarix qayerda ekani ko'rinsin.

LOG_DIR="${1:-$HOME/hodimlar-tizimi/logs}"
MAX_BYTES=$((5 * 1024 * 1024))  # 5MB — toza ishlashda ~1 haftalik yozuv
KEEP=8                          # ~2 oylik siqilgan tarix

for log in "$LOG_DIR"/*.log; do
    [ -f "$log" ] || continue
    size=$(stat -c %s "$log" 2>/dev/null || echo 0)
    [ "$size" -gt "$MAX_BYTES" ] || continue

    # Arxivlarni bittaga surish: .7.gz -> .8.gz, ... .1.gz -> .2.gz
    # (eski .8.gz ustidan yoziladi — eng qadimgisi shu tariqa o'chadi)
    i=$KEEP
    while [ "$i" -ge 2 ]; do
        prev=$((i - 1))
        [ -f "$log.$prev.gz" ] && mv -f "$log.$prev.gz" "$log.$i.gz"
        i=$prev
    done

    mv -f "$log" "$log.1"
    gzip -f "$log.1"
    echo "$(date '+%Y-%m-%d %H:%M') log rotatsiya: avvalgi $size bayt $(basename "$log").1.gz ga siqildi" >> "$log"
done
