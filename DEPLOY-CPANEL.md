# cPanel'ga o'rnatish (shared hosting)

Bu qo'llanma **oddiy cPanel shared hosting** uchun (ahost va shu kabi). Docker yo'q.
Bitta Python App (Passenger + FastAPI) **ham API'ni, ham React saytni** xizmat
qiladi — asosiy domenda, subdomensiz:

```
misol.uz/            → React sayt (FastAPI webdist/ dan)
misol.uz/api/*       → API + bot webhook (FastAPI)
cron (har daqiqa)    → scheduler o'rniga scripts/cron_tick.py
SQLite (app.db)      → baza (8 xodim uchun yetarli)
```

passenger_wsgi.py rejimni o'zi aniqlaydi: ilova ildizida `webdist/` (React build)
bo'lsa — asosiy domen rejimi (yuqoridagi); bo'lmasa — faqat API (subdomen rejimi).

> Docker/VPS uchun `DEPLOY.md`dan foydalaning — bu boshqa yo'l.

Quyida `misol.uz` — sizning domeningiz, `nuriddi5` — cPanel foydalanuvchi nomingiz.
Ularni o'zingiznikiga almashtiring. cPanel'da 3 oyna kerak: **Setup Python App**,
**Terminal**, **File Manager**.

---

## 1. SSL tekshirish

cPanel → **SSL/TLS Status** yoki **AutoSSL** → `misol.uz` uchun sertifikat faol
ekanini tekshiring (kamera/GPS check-in va Telegram webhook HTTPS talab qiladi).

> Subdomen (`api.misol.uz`) da alohida ishlatmoqchi bo'lsangiz ham mumkin — u holda
> `webdist/` yuklamaysiz (React'ni asosiy domenda alohida qo'yasiz) va
> API_BASE_URL'dan `/api` qismini olib tashlaysiz. Quyida asosiy domen yo'li.

---

## 2. Kodni yuklash (Terminal oynasi)

```bash
cd ~
git clone https://github.com/extremiumlar/hodim-control.git hodimlar
cd hodimlar
cp deploy/cpanel/passenger_wsgi.py .      # Passenger kirish nuqtasi ildizga
cp .env.example .env
mkdir -p logs
```

`.env`ni tahrirlang (File Manager'da yoki `nano .env`):

| Kalit | Qiymat |
|---|---|
| `DEBUG` | `false` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./app.db` |
| `JWT_SECRET` | tasodifiy: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `BOT_SHARED_SECRET` | boshqa tasodifiy qiymat (webhook manzilida ishlatiladi) |
| `BOT_TOKEN` | BotFather tokeni |
| `BOT_WEBHOOK_ENABLED` | `true` |
| `API_BASE_URL` | `https://misol.uz/api`  (asosiy domen rejimida `/api` bilan!) |
| `FRONTEND_URL` | `https://misol.uz` |
| `TELEGRAM_LOGIN_BOT_USERNAME` | bot username (masalan `NB_nazoratchibot`) |
| `TELEGRAM_GROUP_CHAT_ID` | asosiy guruh chat ID |
| `CRM_TYPE` / `CRM_API_KEY` | CRM ulansa; aks holda `none` |

---

## 3. Python App yaratish (Setup Python App oynasi)

cPanel → **Setup Python App** → **Create Application**:
- **Python version**: 3.11 (yoki mavjud eng yangi 3.10+)
- **Application root**: `hodimlar-tizimi` (2-bosqichda clone qilingan papka)
- **Application URL**: `misol.uz` (asosiy domen)
- **Application startup file**: `passenger_wsgi.py`
- **Application Entry point**: `application`

**Create** bosing. cPanel virtualenv yaratadi va yuqorida virtualenv'ni faollashtirish
buyrug'ini ko'rsatadi (masalan `source /home/cpuser/virtualenv/hodimlar/3.11/bin/activate && cd /home/cpuser/hodimlar`). Uni nusxalab oling.

### Kutubxonalarni o'rnatish (Terminal oynasi)

```bash
source /home/cpuser/virtualenv/hodimlar/3.11/bin/activate
cd /home/cpuser/hodimlar
pip install -r deploy/cpanel/requirements.txt
```

### Bazani tayyorlash (migratsiya)

```bash
alembic -c db/alembic.ini upgrade head
```

`app.db` fayli ildizda paydo bo'ladi.

### Birinchi rahbarni yaratish

O'z Telegram ID'ingizni @userinfobot'dan biling, so'ng:

```bash
python scripts/create_boss.py "Ismingiz" 123456789
```

### Ilovani qayta ishga tushirish

Setup Python App oynasida **Restart** bosing (yoki `touch tmp/restart.txt`).
Tekshiring: `https://api.misol.uz/health` → `{"status":"ok"}`.

---

## 4. Saytni (frontend) joylash

Asosiy domen rejimida sayt FastAPI orqali ilova ildizidagi `webdist/` papkasidan
xizmat qilinadi (SPA yo'nalishi passenger_wsgi.py ichida hal qilingan — `.htaccess`
kerak emas).

Build'ni **o'z kompyuteringizda** qilasiz (bu yerda Node bor):

```bash
cd web
# Sayt API'ni bir xil domenning /api yo'lidan chaqiradi (bu fayl gitignore'da):
echo "VITE_API_BASE_URL=/api" > .env.production.local
echo "VITE_DEBUG=false" >> .env.production.local
echo "VITE_TELEGRAM_LOGIN_BOT_USERNAME=NB_nazoratchibot" >> .env.production.local
npm run build
```

`web/dist/` ichidagi HAMMA narsani serverda ilova ildizidagi **`webdist/`** papkasiga
yuklang (File Manager yoki `scp`). Ya'ni `~/hodimlar-tizimi/webdist/index.html`,
`~/hodimlar-tizimi/webdist/assets/...` bo'lishi kerak. So'ng App'ni **Restart** qiling.

---

## 5. Telegram bot webhook (Terminal oynasi)

Ilova ishga tushgach, webhook'ni ro'yxatdan o'tkazing:

```bash
source /home/cpuser/virtualenv/hodimlar/3.11/bin/activate
cd /home/cpuser/hodimlar
python scripts/set_webhook.py
python scripts/set_webhook.py --info    # holatni tekshirish
```

Bu Telegram'ga `https://misol.uz/api/bot/webhook/<BOT_SHARED_SECRET>` manzilini
beradi (API_BASE_URL + /bot/webhook) — bot xabarlari shu API ichida ishlanadi.

BotFather → `/setdomain` → botga `misol.uz` domenini bog'lang (sayt Login Widget uchun).

---

## 6. Scheduler o'rniga cron (Cron Jobs oynasi)

cPanel → **Cron Jobs** → **Add New Cron Job**:
- **Common Settings**: *Once Per Minute* (`* * * * *`)
- **Command**:

```
cd /home/cpuser/hodimlar && /home/cpuser/virtualenv/hodimlar/3.11/bin/python scripts/cron_tick.py >> /home/cpuser/hodimlar/logs/cron.log 2>&1
```

Bitta cron kifoya — `cron_tick.py` joriy vaqtni tekshirib, o'sha daqiqada kerakli
ishlarni (CRM sync, eslatma, digest, bonus va h.k.) o'zi hal qiladi.

---

## 7. Tekshirish ro'yxati

- `https://misol.uz/api/health` → `{"status":"ok"}`
- `https://misol.uz` ochiladi, Telegram Login ko'rinadi (dev-login YO'Q)
- Boshliq bilan kirib `/users`da xodim yaratish ishlaydi
- **Telefonda** `https://misol.uz/check-in` — kamera va GPS so'raladi (HTTPS shart!)
- `/offices`da kamida bitta faol ofis bor (busiz check-in rad etiladi)
- Botga `/start` yozing — javob beradi (webhook ishlayapti)
- 1-2 daqiqadan keyin `logs/cron.log`da tik yozuvlari ko'rinadi

---

## 8. Yangilash (kod o'zgarganda)

```bash
cd /home/cpuser/hodimlar
git pull
source /home/cpuser/virtualenv/hodimlar/3.11/bin/activate
pip install -r deploy/cpanel/requirements.txt   # yangi kutubxona bo'lsa
alembic -c db/alembic.ini upgrade head          # yangi migratsiya bo'lsa
touch tmp/restart.txt                            # Passenger'ni qayta yuklash
```

Frontend o'zgarsa: kompyuterda `npm run build` → `dist`ni `public_html`ga qayta yuklang.

Baza zaxirasi (SQLite — oddiy fayl nusxasi):
```bash
cp app.db backups/app_$(date +%F).db
```

---

## Muammolarni aniqlash

| Belgi | Sabab / yechim |
|---|---|
| `api.misol.uz` 500 beradi | Setup Python App → **Restart**; `logs/`va cPanel Error Log'ni ko'ring; ko'pincha `.env` to'ldirilmagan yoki `pip install` tugamagan |
| Sayt ochiladi, lekin login/ma'lumot kelmaydi | `web/.env.production.local`da `VITE_API_BASE_URL` noto'g'ri yoki `FRONTEND_URL` (.env) CORS'ga mos emas — ikkalasi `misol.uz`/`api.misol.uz` bo'lsin, so'ng saytni qayta build |
| Bot javob bermaydi | `python scripts/set_webhook.py --info` — `last_error_message`ni o'qing; `BOT_WEBHOOK_ENABLED=true` va ilova restart qilinganmi |
| Bot ba'zan "qotib qoladi" | Bot API'ga o'ziga HTTP so'rov yuboradi — Passenger kamida 2 jarayonga ruxsat berishi kerak (Setup Python App'da instance sonini oshiring). Muqobil: botni polling rejimida boshqa doimiy mashinada (masalan ofis kompyuteri, `start_all` + `API_BASE_URL=https://api.misol.uz`) ishlating va bu yerda `BOT_WEBHOOK_ENABLED=false` qiling |
| Telefonda kamera ochilmaydi | HTTPS emas — AutoSSL sertifikatini tekshiring |
| CRM raqamlari 0 | `CRM_TYPE`/`CRM_API_KEY` va xodimlarda CRM ID bog'lanmagan (`/users`) |
| cron ishlamayapti | `logs/cron.log`ni ko'ring; cron buyrug'idagi yo'llar (virtualenv, ilova papkasi) to'g'rimi tekshiring |

## Muqobil: bot va scheduler'ni boshqa mashinada

Agar cPanel'da webhook bilan muammo bo'lsa (Passenger jarayon cheklovi), eng
ishonchli yo'l — **API + sayt + baza cPanel'da**, **bot + scheduler esa doimiy
yoniq mashinada** (ofis kompyuteri yoki arzon mini-server):

1. cPanel `.env`da `BOT_WEBHOOK_ENABLED=false`, webhook'ni o'chiring:
   `python scripts/set_webhook.py --delete`
2. O'sha mashinada loyihani klonlab, `.env`da `API_BASE_URL=https://api.misol.uz`
   qo'ying va `bot.main` (polling) hamda `scheduler.main`ni ishga tushiring
   (Windows'da `scripts/start_all.ps1` shuni qiladi).

Bunda cPanel faqat sayt va API'ni (doim kerakli qism) ko'taradi, bot/scheduler
esa oddiy polling — hech qanday webhook murakkabligisiz.
