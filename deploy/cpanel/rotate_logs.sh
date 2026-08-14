#!/bin/sh
# Log rotatsiyasi — cPanel (shared hosting) uchun: tizim logrotate'i mavjud emas,
# shuning uchun oddiy POSIX sh bilan qilinadi. Kunlik crontab'dan chaqiriladi:
#
#   40 4 * * * bash ~/hodimlar-tizimi/deploy/cpanel/rotate_logs.sh >> ~/hodimlar-tizimi/logs/rotate.log 2>&1
#
# Nega 04:40: tungi og'ir ishlar (03:30 diff reconcile ~6-7 daqiqa, 04:38 lid
# snapshot) tugagan payt.
#
# ── NEGA `mv` EMAS, `cp` + truncate (copytruncate) ──
# 2026-08-14 gacha bu skript `mv "$log" "$log.1"` qilardi va izohda bu "xavfsiz"
# deb yozilgandi: cron.log'ga yozuvchi yagona narsa crontab'dagi `>>`
# yo'naltirish bo'lib, u HAR DAQIQA yangi jarayonda faylni yo'l bo'yicha qayta
# ochadi. O'sha mulohaza O'ZI TO'G'RI, lekin ENDI YETARLI EMAS — logs/ ichida
# `nohup` bilan ishga tushgan UZOQ jarayonlar yozadigan fayllar ham bor:
#   bot_polling.log     <- `nohup python -m bot.main >> ...`   (keepalive_bot.sh)
#   userbot_hisob3.log  <- `nohup python userbot.py >> ...`    (keepalive_userbot.sh)
# Ular fayl deskriptorini START PAYTIDA BIR MARTA oladi. `mv` dan keyin fd
# ko'chirilgan faylga ergashadi, `gzip -f` esa uni unlink qiladi — natijada
# jarayon O'CHIRILGAN inode'ga yozishda davom etadi: loglar ko'rinmas bo'lib
# qoladi VA disk joyi jarayon qayta ishga tushmaguncha band turaveradi
# (`/proc/<pid>/fd` da "(deleted)" bo'lib ko'rinadi).
#
# copytruncate buni yopadi: fayl JOYIDA qoladi (inode o'zgarmaydi), nusxasi
# olinadi va asl fayl bo'shatiladi — fd baribir to'g'ri faylga ishora qilaveradi.
# Ikkala jarayonning fd'si ham O_APPEND bilan ochilgan (tekshirilgan:
# /proc/<pid>/fdinfo/1 -> flags=0102001). O_APPEND'da yadro HAR yozuvdan oldin
# faylning oxiriga o'tadi, shuning uchun truncate'dan keyin yozuv 0-ofsetdan
# boshlanadi va "teshikli" (sparse) fayl HOSIL BO'LMAYDI. Agar kelajakda bu
# yerga O_APPEND'siz (`>` bilan ochilgan) log qo'shilsa — o'sha fayl uchun
# copytruncate NOTO'G'RI bo'ladi, jarayon eski ofsetdan yozib nol bilan
# to'ldirilgan bo'shliq qoldiradi.
# Yagona narxi: `cp` va truncate orasidagi mikro-oynada kelgan yozuv yo'qoladi.
#
# Har bir *.log fayl MAX_BYTES'dan oshsa: eski arxivlar suriladi
# (log.1.gz -> log.2.gz ...), joriy fayl nusxasi log.1 ga olinib gzip qilinadi,
# eng eskisi (KEEP dan oshgani) o'chadi. Bo'shatilgan faylga rotatsiya belgisi
# yoziladi — logni o'qiganda tarix qayerda ekani ko'rinsin.

MAX_BYTES=$((5 * 1024 * 1024))  # 5MB — toza ishlashda ~1 haftalik yozuv
KEEP=8                          # ~2 oylik siqilgan tarix

# Argument berilsa — faqat o'sha papka (qo'lda sinash uchun), aks holda
# ikkala loyihaning logs/ papkasi. chatbot 2026-08-14 gacha QAMRALMAGAN edi:
# `userbot_hisob2.log` rotatsiyasiz 158 MB ga yetib, 1 GB kvotaning oltidan
# birini yeb qo'ygan.
if [ -n "$1" ]; then
    LOG_DIRS="$1"
    NOISE_LOGS=""
else
    LOG_DIRS="$HOME/hodimlar-tizimi/logs $HOME/chatbot/logs"
    # Sof shovqin: arxiv saqlashning ma'nosi yo'q, shunchaki bo'shatiladi.
    # pip o'z logini cheksiz o'stiradi — 2026-08-14 da 61 MB bo'lgan.
    NOISE_LOGS="$HOME/.pip/pip.log"
fi

for dir in $LOG_DIRS; do
    [ -d "$dir" ] || continue

    for log in "$dir"/*.log; do
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

        # cp muvaffaqiyatsiz bo'lsa (joy tugadi va h.k.) faylni BO'SHATMAYMIZ —
        # aks holda log ham yo'qolardi, nusxa ham bo'lmasdi.
        if ! cp -f "$log" "$log.1"; then
            echo "$(date '+%Y-%m-%d %H:%M') XATO: $log nusxalanmadi, rotatsiya o'tkazib yuborildi"
            continue
        fi
        : > "$log"   # truncate — cp'dan KEYIN darhol, yo'qotish oynasi qisqa bo'lsin
        gzip -f "$log.1"
        echo "$(date '+%Y-%m-%d %H:%M') log rotatsiya: avvalgi $size bayt $(basename "$log").1.gz ga siqildi" >> "$log"
    done
done

for log in $NOISE_LOGS; do
    [ -f "$log" ] || continue
    size=$(stat -c %s "$log" 2>/dev/null || echo 0)
    [ "$size" -gt "$MAX_BYTES" ] || continue
    : > "$log"
    echo "$(date '+%Y-%m-%d %H:%M') $log bo'shatildi ($size bayt, arxivsiz — sof shovqin)"
done
