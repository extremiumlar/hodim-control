#!/bin/bash
# Kunlik avtomatik zaxira nusxa (PostgreSQL) — cPanel cron uchun.
#
# NEGA QURILDI (2026-08-05): serverda avtomatik zaxira nusxa UMUMAN yo'q edi —
# `backups/` papkada faqat deploy oldidan qo'lda olingan 2 ta fayl bor edi.
# Ya'ni baza buzilsa oxirgi qo'lda olingan nusxadan keyingi hamma narsa
# (davomat, oylik, lid tarixi) yo'qolardi.
#
# Crontab (kuniga bir marta, kam trafik vaqtida):
#   30 3 * * * bash /home/nuriddi5/hodimlar-tizimi/deploy/cpanel/backup_db.sh \
#       >> /home/nuriddi5/hodimlar-tizimi/logs/backup.log 2>&1
#
# Natija: backups/pg_YYYYmmdd_HHMM.sql.gz + RETENTION_DAYS kundan eskisi
# o'chiriladi. Qo'lda (deploy oldidan) olingan `pg_before_*` fayllarga
# TEGILMAYDI — ular ataylab saqlanadi.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="$ROOT/backups"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="$BACKUP_DIR/pg_${STAMP}.sql.gz"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

mkdir -p "$BACKUP_DIR"

# DATABASE_URL .env dan; asyncpg drayveri pg_dump uchun olib tashlanadi.
# DIQQAT: qiymat log'ga CHIQMAYDI (parol bor) — faqat holat yoziladi.
DB_URL="$(grep '^DATABASE_URL=' "$ROOT/.env" | cut -d= -f2- | tr -d '\r\n' | sed 's/+asyncpg//')"
if [ -z "$DB_URL" ]; then
    log "XATO: .env da DATABASE_URL topilmadi — zaxira olinmadi."
    exit 1
fi
case "$DB_URL" in
    postgres*) ;;
    *) log "O'TKAZIB YUBORILDI: DATABASE_URL PostgreSQL emas (SQLite bo'lsa fayl o'zi nusxalanadi)."; exit 0 ;;
esac

# Vaqtinchalik faylga yozib, muvaffaqiyatda YAKUNIY nomga ko'chiramiz —
# yarim yozilgan fayl hech qachon "tayyor zaxira" bo'lib ko'rinmasin
# (qo'riqchi eng yangi faylga qarab hukm chiqaradi).
TMP="$OUT.part"
if ! pg_dump "$DB_URL" 2>/tmp/pgdump_err_$$ | gzip -c > "$TMP"; then
    log "XATO: pg_dump muvaffaqiyatsiz — $(head -c 300 /tmp/pgdump_err_$$ 2>/dev/null)"
    rm -f "$TMP" /tmp/pgdump_err_$$
    exit 1
fi
rm -f /tmp/pgdump_err_$$

# Bo'sh/juda kichik fayl — shubhali (baza bo'sh emas), zaxira deb qabul qilmaymiz
SIZE=$(stat -c%s "$TMP" 2>/dev/null || echo 0)
if [ "$SIZE" -lt 10000 ]; then
    log "XATO: zaxira juda kichik (${SIZE} bayt) — buzilgan deb hisoblanib o'chirildi."
    rm -f "$TMP"
    exit 1
fi

mv "$TMP" "$OUT"
log "TAYYOR: $(basename "$OUT") ($(du -h "$OUT" | cut -f1))"

# Eskilarini tozalash — FAQAT avtomatik nusxalar (pg_YYYYmmdd_HHMM.sql.gz).
# `pg_before_*` (deploy oldidan qo'lda olingan) fayllar tegilmaydi.
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -name 'pg_20*.sql.gz' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "Tozalandi: $DELETED ta eski nusxa (>${RETENTION_DAYS} kun)."
fi

TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Zaxira papkasi hajmi: $TOTAL"
