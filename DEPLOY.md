# Production'ga o'rnatish (deploy)

Stack: **PostgreSQL + FastAPI (api) + Telegram bot + scheduler + web (nginx'li SPA)** —
hammasi Docker Compose'da. Tashqariga faqat host nginx (TLS) chiqadi.

```
internet ──HTTPS──> host nginx ──> 127.0.0.1:8080 web (SPA + /api proxy) ──> api ──> db
                    (certbot)                                bot ──┘   scheduler ──┘
```

> **MUHIM:** Kamera (Face ID) va GPS faqat **HTTPS**'da ishlaydi — TLS'siz
> xodimlar check-in qila olmaydi. Shuning uchun domen + sertifikat majburiy.

> `verifix/` papkasi — iste'foga chiqqan eski tizim arxivi, deploy qilinmaydi
> (`.dockerignore`da chiqarib tashlangan).

## 1. Server talablari

- Linux server (Ubuntu 22.04+ tavsiya), 1-2 GB RAM yetadi
- Domen (A yozuvi server IP'siga)
- Docker + Docker Compose plugin, nginx, certbot:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx git
```

## 2. Loyihani olish va .env tayyorlash

```bash
git clone https://github.com/extremiumlar/hodim-control.git
cd hodim-control
cp .env.example .env
nano .env
```

`.env`da MAJBURIY o'zgartiriladiganlar:

| Kalit | Qiymat |
|---|---|
| `DEBUG` | `false` (aks holda dev-login ochiq qoladi!) |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` natijasi |
| `BOT_SHARED_SECRET` | yuqoridagi kabi alohida tasodifiy qiymat |
| `POSTGRES_PASSWORD` | kuchli parol |
| `BOT_TOKEN` | BotFather'dan olingan bot tokeni |
| `TELEGRAM_LOGIN_BOT_USERNAME` | bot username (masalan `NB_nazoratchibot`) |
| `TELEGRAM_GROUP_CHAT_ID` | asosiy guruh chat ID (manfiy son) |
| `FRONTEND_URL` | `https://SIZNING_DOMEN` |
| `CRM_TYPE` / `CRM_API_KEY` | CRM ulansa (uysot va h.k.), aks holda `none` |

Eslatma: `DEBUG=false`da placeholder sirlar bilan API **ataylab ishga tushmaydi**.

Frontend build sozlamasi [web/.env.production](web/.env.production)da:
`VITE_TELEGRAM_LOGIN_BOT_USERNAME` o'z botingizga mos ekanini tekshiring
(o'zgartirsangiz web'ni qayta build qilish kerak).

## 3. Ishga tushirish

```bash
docker compose up -d --build
docker compose ps        # 5 xizmat ham "running" bo'lishi kerak
docker compose logs api  # migratsiyalar avtomatik o'tadi (alembic upgrade head)
```

## 4. Birinchi rahbarni yaratish

Yangi bazada hech kim yo'q — saytga Telegram orqali faqat bazadagi foydalanuvchi
kira oladi. O'z Telegram ID'ingizni @userinfobot'dan bilib oling va:

```bash
docker compose exec api python scripts/create_boss.py "Ismingiz" 123456789
```

## 5. HTTPS (majburiy)

```bash
sudo cp deploy/nginx-production.conf /etc/nginx/sites-available/hodimlar
sudo nano /etc/nginx/sites-available/hodimlar   # SIZNING_DOMEN ni almashtiring
sudo ln -s /etc/nginx/sites-available/hodimlar /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d SIZNING_DOMEN           # sertifikat + avto-redirect
```

## 6. Telegram sozlamalari

1. BotFather → `/setdomain` → botga sayt domenini bog'lang (Login Widget uchun shart).
2. Botni asosiy guruhga qo'shing (`TELEGRAM_GROUP_CHAT_ID` o'sha guruh).

## 7. Tekshirish ro'yxati

- `https://DOMEN` ochiladi, Telegram Login ko'rinadi (dev-login YO'Q)
- Boshliq bilan kirib `/users`da xodim yaratish va taklif havolasi ishlaydi
- Telefonda `https://DOMEN/check-in` — kamera va GPS so'raladi (HTTP'da ishlamaydi!)
- `/offices`da kamida bitta faol ofis bor (busiz check-in rad etiladi)
- Bot guruhda javob beradi, scheduler loglari toza: `docker compose logs scheduler`

## 8. Kundalik amallar

```bash
# Yangilash (yangi kod)
git pull && docker compose up -d --build

# Loglar
docker compose logs -f api

# Baza zaxirasi (cron'ga qo'ying)
docker compose exec db pg_dump -U hodimlar hodimlar | gzip > backup_$(date +%F).sql.gz

# Zaxiradan tiklash
gunzip -c backup_YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U hodimlar hodimlar
```

## Muammolarni aniqlash

| Belgi | Sabab / yechim |
|---|---|
| api konteyner o'chib qoladi | `docker compose logs api` — placeholder sirlar (`.env`ni to'ldiring) yoki db tayyor emas |
| Saytda "ruxsatingiz yo'q" | Telegram ID bazada yo'q — 4-bosqich (create_boss) yoki boshliq sizni qo'shsin |
| Telefonda kamera ochilmaydi | HTTPS emas — 5-bosqichni tekshiring |
| Login Widget chiqmaydi | BotFather `/setdomain` qilinmagan yoki `VITE_TELEGRAM_LOGIN_BOT_USERNAME` noto'g'ri |
| CRM raqamlari 0 | `CRM_TYPE`/`CRM_API_KEY` va xodimlarda CRM ID bog'lanmagan (`/users`) |
