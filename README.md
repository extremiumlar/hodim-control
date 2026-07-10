# Xodimlar KPI/Bonus tizimi

Telegram bot + FastAPI backend + React sayt orqali ishlaydigan xodimlar nazorati va KPI/bonus tizimi.

**Joriy holat: barcha 4 bosqich tayyor** — DB sxemasi, bot onboarding/vazifa/sababli-kun oqimlari, norma boshqaruvi (bot + sayt), mobilograf video+reaksiya tasdig'i, kunlik eslatma/xulosa scheduler, CRM-agnostik adapter (amoCRM to'liq, 1C stub) + qo'lda kiritish, oylik bonus hisob-kitobi (placeholder formula) + botga push-xabar, xodim profili sahifasi (tendensiya grafigi + kunlik natijalar + bonus tarixi), .xlsx hisobot eksporti, to'liq audit jurnali sahifasi va bosh sahifaning 20 soniyalik avtomatik yangilanishi ishlaydi. Spetsifikatsiyaning barcha 4 bosqichi (12-bo'lim) amalga oshirildi.

## Repo tuzilishi

```
/db         — SQLAlchemy modellar, Alembic migratsiyalari, seed skripti
/api        — FastAPI backend
/bot        — aiogram Telegram bot
/scheduler  — APScheduler asosidagi eslatma/xulosa/CRM sync/bonus job'lari
/crm        — CRM-agnostik adapterlar (base.py, amocrm.py, onec.py)
/web        — React + TypeScript + Vite sayt
docker-compose.yml, Dockerfile'lar — Docker o'rnatilgach ishlatish uchun tayyor
```

## 1. Talablar

- Python 3.11+
- Node.js 20+
- Telegram bot token — [@BotFather](https://t.me/BotFather) orqali `/newbot` bilan yarating (test uchun alohida bot yarating, production botiga aralashtirmang)
- (Ixtiyoriy, keyinroq) Docker Desktop — PostgreSQL bilan production'ga o'tish uchun

## 2. Birinchi marta sozlash (Docker'siz, lokal)

### 2.1. Muhit fayli

```bash
cp .env.example .env
```

`.env` faylini oching va kamida quyidagilarni to'ldiring:

- `BOT_TOKEN` — BotFather bergan token
- `TELEGRAM_LOGIN_BOT_USERNAME` — botingiz username'i (masalan `mening_test_botim`, `@` belgisisiz)
- `TELEGRAM_GROUP_CHAT_ID` — mobilograf video va kunlik xulosa yuboriladigan guruh ID'si (2-bosqich uchun; qanday olish 2.8-bo'limda)

`DATABASE_URL` standart holatda SQLite'ga (`sqlite+aiosqlite:///./app.db`) ishora qiladi — hech narsa o'rnatish shart emas.

> ⚠️ **Production'ga chiqishdan oldin:** `.env`da `DEBUG=false` qiling va barcha standart sirlarni (`BOT_SHARED_SECRET`, JWT maxfiy kaliti va h.k.) tasodifiy kuchli qiymatlarga almashtiring — `.env.example`dagi qiymatlar faqat lokal sinov uchun.

### 2.2. Backend (Python)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r api/requirements.txt -r bot/requirements.txt -r scheduler/requirements.txt
```

### 2.3. Ma'lumotlar bazasini yaratish

```bash
alembic -c db/alembic.ini upgrade head
```

Bu `app.db` (SQLite) faylini va barcha jadvallarni yaratadi.

### 2.4. Birinchi `boss` foydalanuvchini yaratish

O'zingizning shaxsiy Telegram ID'ingizni bilish uchun Telegram'da [@userinfobot](https://t.me/userinfobot) botiga yozing — u sizga `id` raqamini beradi.

```bash
python -m db.seed <telegram_id> "Ismingiz Familiyangiz"
```

### 2.5. Backend'ni ishga tushirish

```bash
uvicorn api.main:app --reload
```

Swagger hujjatlari: http://localhost:8000/docs

### 2.6. Botni ishga tushirish (alohida terminal oynasida)

```bash
# venv faollashtirilgan bo'lishi kerak
python -m bot.main
```

Endi Telegram'da botingizga `/start` yozing — "boss" sifatida ro'yxatdan o'tasiz va asosiy menyu chiqadi.

### 2.7. Saytni ishga tushirish (yana bir terminal oynasida)

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

Brauzerda http://localhost:5173 oching.

### 2.8. Mobilograf/xulosa guruhini sozlash (2-bosqich, ixtiyoriy)

Mobilograf video tasdiqlash va kunlik guruh xulosasi uchun bitta Telegram guruh kerak:

1. Telegram'da yangi guruh yarating (yoki mavjudini ishlating), botingizni shu guruhga a'zo qiling.
2. Guruhga istalgan xabar yozing, so'ng shu guruh chat ID'sini bilish uchun guruhga [@userinfobot](https://t.me/userinfobot) botini vaqtincha qo'shing (yoki botingiz logida `chat.id`ni ko'ring — odatda `-100` bilan boshlanadigan manfiy son bo'ladi).
3. `.env` faylida `TELEGRAM_GROUP_CHAT_ID` qiymatini shu son bilan to'ldiring va botni qayta ishga tushiring.

Bu qadam ixtiyoriy — sozlanmagan bo'lsa, mobilograf va kunlik xulosa funksiyalari jim o'tkazib yuboriladi (xato bermaydi), qolgan funksiyalar (vazifa, sababli kun, norma) odatdagidek ishlayveradi.

### 2.9. Scheduler'ni ishga tushirish (yana bir terminal oynasida, 2-bosqich)

```bash
# venv faollashtirilgan bo'lishi kerak
python -m scheduler.main
```

Scheduler kun davomida (13:00, 16:00, 17:00, 18:00 `Asia/Tashkent`) bajarilmagan vazifalar uchun eslatma yuboradi. Kechqurun esa guruhga **kunlik yagona digest** (vazifa + qo'ng'iroq/lid/tashrif + AI xulosa — bitta xabar) jo'natiladi; vaqti bazadan boshqariladi, boss botda `/statistika_vaqt 19:30` bilan o'zgartiradi (standart 19:10). Yakshanba kechqurun (`scheduler/config.py` dagi `WEEKLY_DIGEST_*`) guruhga **haftalik raqamli yakun** (shu hafta vs o'tgan hafta) boradi. Eslatma vaqtlarini tezroq sinash uchun `REMINDER_HOURS`ni vaqtincha o'zgartiring, yoki API'dagi `/tasks/send-reminders`, `/reports/daily-digest` va `/reports/weekly-digest` endpointlarini to'g'ridan-to'g'ri (Swagger orqali, `X-Bot-Secret` header bilan, `dry_run=true` parametri yubormasdan matnni ko'rsatadi) chaqirib sinang.

**Talab bo'yicha statistika:** belgilangan vaqtni kutmasdan, HR/ROP/Boshliq sozlangan guruhda `/statistika` buyrug'ini yuborsa (yoki botdagi "📊 Umumiy statistika" tugmasi), bot darhol kunlik digestni hisoblab jo'natadi (aynan shu `/reports/daily-digest` endpointini chaqiradi).

**Muhim eslatma — Telegram Login Widget lokal muhitda:** Telegram Login Widget odatda faqat BotFather orqali ro'yxatdan o'tkazilgan haqiqiy domenda ishlaydi (`/setdomain`), `localhost`da ko'pincha ishlamaydi. Shu sababli lokal sinov uchun login sahifasida **"Dev-login"** blokini qo'shdik — u faqat `.env`da `DEBUG=true` bo'lganda ko'rinadi. O'zingizning (yoki HR/ROP sifatida yaratilgan foydalanuvchining) Telegram ID'ini kiritib, parolsiz kirasiz. Production'ga chiqishda `DEBUG=false` qiling — bu blok avtomatik yashiriladi va faqat haqiqiy Telegram Login ishlaydi (buning uchun avval BotFather'da `/setdomain` orqali saytingiz domenini ro'yxatdan o'tkazing).

## 3. To'liq oqimni qo'lda sinash

1. Saytga (http://localhost:5173) boss sifatida dev-login orqali kiring.
2. **"Foydalanuvchilar"** bo'limida yangi xodim qo'shing (masalan rol = "Xodim"). Yaratilgach bot-havola ko'rsatiladi.
3. Xodim sifatida (boshqa Telegram akkaunt yoki o'zingiz sinov uchun) shu havolani Telegram'da oching — bot `/start` bilan ochiladi va xodim avtomatik ro'yxatdan o'tadi.
4. Saytdagi **"Bosh sahifa"**dan shu xodimga vazifa bering — u botda darhol xabar sifatida keladi, ostida "✅ Bajardim" tugmasi bor.
5. Xodim tugmani bossin — sayt jadvalida vazifa holati "✅ Bajarildi" bo'ladi (sahifani yangilang).
6. Xodim botdan **"🙋 Sababli kun so'rash"** tugmasini bosib sababni yozsin.
7. HR rolidagi foydalanuvchi (yoki shu sinovda boss ham HR vazifasini bajaradi — HR foydalanuvchi yo'q bo'lsa so'rov boss'ga boradi) botda "✅ Tasdiqlayman"/"❌ Rad etaman" tugmalarini ko'radi, birini bossin.
8. Xodimga natija haqida bot orqali avtomatik xabar keladi; saytning **"Sababli kunlar"** bo'limida holat yangilanadi.

## 3.1. 2-bosqich oqimlarini sinash

**Norma boshqaruvi:**
1. Saytda **"Normalar"** bo'limida biror xodimning "Suhbatlar normasi"/"Tashriflar normasi" qiymatini o'zgartirib "Saqlash"ni bosing — yangilangan qiymat darhol ko'rinadi.
2. Yoki ROP/Boshliq sifatida botda `/norma_ozgartir` buyrug'ini yuboring — bot ketma-ket "Kimning?" → "Qaysi ko'rsatkich?" → "Yangi qiymat?" deb so'raydi, oxirida tasdiq xabari keladi. Saytdagi jadvalda ham yangilanadi.

**Mobilograf video tasdig'i** (2.8-bo'limda guruh sozlangan bo'lishi kerak):
1. Xodim (bot bilan ulangan, `role=employee`) sozlangan guruhga video (mp4) yuborsin.
2. Manager (`manager_id` shu xodimga ishora qiladigan foydalanuvchi) yoki `boss` roli o'sha video xabariga ✅ emoji-reaksiya qo'ysin — bu tasdiq hisoblanadi.
3. Reaksiyani olib tashlasa, tasdiq ham bekor bo'ladi (qayta ✅ bosilmaguncha `pending` holatida qoladi).

**Kunlik eslatma va digest:** 2.9-bo'limdagi scheduler ishga tushirilgan bo'lsa, belgilangan soatlarda avtomatik ishlaydi; tezroq sinash uchun Swagger (`/docs`) orqali `/tasks/send-reminders` va `/reports/daily-digest` endpointlarini `X-Bot-Secret` header bilan qo'lda chaqiring (`dry_run=true` — yubormasdan matnni qaytaradi).

## 3.2. 3-bosqich oqimlarini sinash

**Muhim eslatma — CRM:** hozircha haqiqiy CRM hisobingiz sozlanmagan bo'lishi mumkin (`CRM_TYPE=none` standart holat). Bu butunlay normal — spetsifikatsiya "kunlik natijalar CRM'dan **yoki qo'lda** to'ladi" deb belgilaydi, shuning uchun quyidagi oqim qo'lda kiritish orqali sinaladi.

- `CRM_TYPE=amocrm` + `CRM_API_KEY` + `CRM_AMOCRM_SUBDOMAIN` — `/crm/amocrm.py` adapteri; hozircha amoCRM Events (suhbat) va bajarilgan Tasks (tashrif) sonini hisoblaydi.
- `CRM_TYPE=uysot` + `CRM_API_KEY` (Uysot Open API tokeni, "Call History: Read" va "Lead: Read" ruxsatlari bilan) — `/crm/uysot.py` adapteri:
  - **Suhbatlar** — `call-history/filter`dan xodimning shu kungi qo'ng'iroqlar soni (`crm_external_id` = Uysot `employeeNum`, odatda email).
  - **Tashriflar** — `lead/filter`dan `CRM_UYSOT_VISIT_PIPE_STATUS_ID` bosqichidagi lidlar soni (`crm_visit_external_id` = Uysot lid javobgarining `responsibleById`si). Bosqich ID'sini bilish uchun `GET /v1/open-api/pipe/all`ni tokeningiz bilan chaqiring. **Cheklov:** Uysot lidning bosqichga qachon o'tgani emas, oxirgi tahrirlangan vaqtini beradi — shuning uchun bu taxminiy hisob.

Xodimlarni CRM'ga bog'lash **sayt orqali** ("Foydalanuvchilar" bo'limi, faqat Boshliq/Dasturchi uchun) amalga oshiriladi:
- **"CRM bog'lash"** — bugun qo'ng'iroq qilgan Uysot operatorlari (email bo'yicha) ro'yxati, Telegram orqali ulangan foydalanuvchini tanlab bog'lash mumkin.
- **"Tashrif bog'lash"** — bugun tashrif qayd etilgan operatorlar, bu safar Uysot **ism** beradi (email emas) — tizim ismlarni solishtirib avtomatik taklif qiladi, tasdiqlab "Bog'lash"ni bosish kifoya.
- Har bir foydalanuvchining qatorida "CRM ID" ustunidan `crm_external_id`ni ham qo'lda tahrirlash mumkin.

Bog'langandan so'ng, **"Normalar"** sahifasida har bir ko'rsatkich yonida bugungi CRM/qo'lda qiymat jonli ko'rinadi (norma bilan solishtirib) — shu orqali `/norms/team` API'si orqali normani real vaqtda tekshirish mumkin.

**Kunlik natijani qo'lda kiritish va bonusni hisoblash:**
1. Saytda **"Normalar"** bo'limidan xodim ismiga bosib uning **profiliga** o'ting (yoki Bosh sahifadagi vazifa jadvalidan).
2. "Kunlik natijani qo'lda kiritish" formasi orqali bir nechta kun uchun suhbat/tashrif sonlarini kiriting (masalan joriy oyning turli kunlari uchun) — "Kunlik natijalar tarixi" jadvalida darhol ko'rinadi.
3. Bonusni hisoblash uchun Swagger (`/docs`) orqali `POST /bonuses/calculate-monthly`ni `X-Bot-Secret` header va bo'sh body (`{}`) bilan chaqiring (yoki scheduler oyning oxirgi kuni 23:30'da avtomatik chaqiradi).
4. Xodimga botda "💰 Bonusingiz hisoblandi..." xabari keladi (summasiz); xodim profilidagi **"Bonus tarixi"** bo'limida davr, summa va "tafsilot" (breakdown) ko'rinadi.
5. Botda **"💰 Oylik KPI'm"** tugmasini bossangiz, hisoblangan davr borligi haqida qisqa xabar keladi; **"📊 Bugungi normam"** endi haqiqiy kunlik natija/norma nisbatini ko'rsatadi (agar norma belgilangan bo'lsa).

## 3.3. 4-bosqich oqimlarini sinash

1. Xodim profilida (3.2-bo'limdagi kabi ochilgan) endi **"Tendensiya"** grafigi ko'rinadi — kiritilgan kunlik natijalar (suhbat/tashrif) chiziqli grafik sifatida chiziladi. Kamida 2 xil sanaga natija kiritsangiz, chiziq aniqroq ko'rinadi.
2. **"Hisobotlar"** bo'limida davr (masalan joriy oyning 1-kunidan bugungacha) tanlab **"Excel yuklab olish"**ni bosing — `.xlsx` fayl yuklab olinadi, unda har bir xodim bo'yicha suhbat/tashrif jami, vazifa bajarilishi, sababli kunlar va (agar davr aniq bitta oy bo'lsa) bonus summasi bor.
3. **"Audit"** bo'limida barcha muhim o'zgarishlar (foydalanuvchi qo'shish, norma o'zgartirish, sababli kun qarori, vazifa berish/bajarish, mobilograf tasdig'i, bonus hisob-kitobi) — kim, kimga, qachon, qanday o'zgartirgani bilan ko'rinadi; harakat turi va sana bo'yicha filtrlash mumkin.
4. **Bosh sahifa** endi har 20 soniyada avtomatik yangilanadi — boshqa oynada/qurilmada vazifa "Bajarildi" deb belgilansa, sahifani qo'lda yangilamasdan ham holat o'zgarganini ko'rasiz (WebSocket emas, oddiy polling — MVP uchun yetarli).

## 4. Docker bilan ishga tushirish (Docker o'rnatilgach)

```bash
cp .env.example .env
# .env faylida BOT_TOKEN, TELEGRAM_LOGIN_BOT_USERNAME to'ldiring
docker compose up --build
```

Bu holatda `DATABASE_URL` avtomatik PostgreSQL konteyneriga ishora qiladi (`docker-compose.yml` ichida belgilangan), SQLite ishlatilmaydi. Migratsiyalar konteyner ishga tushganda avtomatik qo'llaniladi (`api/docker-entrypoint.sh`). Birinchi `boss`ni yaratish uchun:

```bash
docker compose exec api python -m db.seed <telegram_id> "Ismingiz"
```

Sayt: http://localhost:5173, API: http://localhost:8000, Postgres: `localhost:5432`. `scheduler` xizmati ham avtomatik ishga tushadi (alohida buyruq shart emas).

## 5. Doiradan tashqari qolgan narsalar

Spetsifikatsiyaning 15-bo'limiga ko'ra ongli ravishda qurilmagan: native mobil ilova, to'lov tizimi integratsiyasi, ko'p tillilik. Bulardan tashqari, amoCRM adapteri haqiqiy hisob ma'lumotlari (aniq maydon xaritasi) bilan hali sinovdan o'tkazilmagan (3.2-bo'limga qarang) va bonus formulasi hali placeholder (`api/services/bonus.py`) — kompaniya formulani belgilagach shu faylni o'zgartirish kifoya qiladi.
