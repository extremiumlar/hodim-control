# Xodim kabineti + mobil UX — ish prompti

> Bu fayl — bajaruvchi agent uchun topshiriq. Audit natijasida yozilgan
> (2026-07-30). Ishni boshlashdan oldin **to'liq o'qing**, keyin 7-bo'limdagi
> ochiq savollarni foydalanuvchiga bering va javob olgach 4-bo'limdan
> boshlang.

---

## 1. Vazifa

Xodim uchun web/mobil tajriba hozir **bir sahifadan** iborat: `/check-in`.
Botda xodimning 9 ta funksiyasi bor, web'da 0 ta. Sababi UI'da unutilgan
narsa emas — **JWT bilan kirgan xodim uchun API qatlami mavjud emas**.

Maqsad: xodim telefonidan botdagi hamma narsani (va undan qulayroq) qila
oladigan **to'liq kabinet** qurish, va yo'l-yo'lakay mobil frontenddagi
aniqlangan nuqsonlarni tuzatish.

**Ko'lam:** audit hisobotining 2- va 3-bo'limlari.
**Ko'lamdan TASHQARI:** 1-bo'lim (davomatni soxtalashtirish zaifligi) va
4-bo'lim (Passenger/offline) — ular alohida ish sifatida olib boriladi.
Sababi: 1-bo'lim davomat ishonchini tiklash bo'yicha alohida arxitektura
qarorini talab qiladi va bu ishni bloklab qo'yadi.

---

## 2. Boshlashdan oldin bilish kerak bo'lgan kontekst

### 2.1 Loyiha tuzilishi
| Papka | Nima |
|---|---|
| `api/routers/` | FastAPI endpointlar (29 fayl) |
| `api/services/` | biznes mantiq (`attendance.py`, `payroll.py`, ...) |
| `api/schemas.py` | Pydantic sxemalar (yagona fayl) |
| `bot/` | aiogram bot — xodimlarning HOZIRGI asosiy interfeysi |
| `web/src/` | React SPA (vite + react-query + shadcn/ui) |
| `web/src/lib/queries.ts` | barcha react-query hooklari |
| `mobile/` | Expo/React Native ilova (Android APK) |
| `webdist/` | **build natijasi, git'da kuzatiladi** — deploy shundan o'qiladi |

### 2.2 Dev muhiti
```
# Backend
uvicorn api.main:app --reload            # 127.0.0.1:8000

# Frontend
cd web && npm run dev                    # https://localhost:5173 (o'z-o'zidan imzolangan sertifikat)
VITE_NO_SSL=1 npx vite --port 5174       # HTTPS'siz — brauzer bilan avtomatik tekshirish uchun

# Tekshirish
cd web && npx tsc -b                     # web tiplari
cd mobile && npx tsc --noEmit            # mobil tiplari
```

**Brauzerda xodim sifatida kirish** (`.env`da `DEBUG=false`, ya'ni dev-login
o'chiq — `.env` ni O'ZGARTIRMANG). Tokenni o'zingiz yasab, localStorage'ga
qo'ying:
```
# 1. Bazadan xodim toping
python -c "import sqlite3; c=sqlite3.connect('file:app.db?mode=ro',uri=True); \
print([tuple(r) for r in c.execute(\"select id,full_name,role from users where role='employee' and is_active=1 limit 5\")])"

# 2. Token yasang (jwt_secret .env dan olinadi)
.venv/Scripts/python.exe -c "from api.security import create_access_token; print(create_access_token(8,'employee'))"

# 3. Brauzerda (5174 originida):
#    localStorage.setItem('access_token','<token>')
#    keyin sahifani yangilang
```
API'ni ko'tarish: `.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000`.
8000 band bo'lsa — parallel sessiyada allaqachon ishlab turgan bo'lishi
mumkin, **o'ldirmang**, shundan foydalanavering.

### 2.3 Deploy oqimi

**`webdist/` AVTOMATIK yangilanadi** — `.githooks/pre-commit`
(`core.hooksPath=.githooks`): `web/src/` staged bo'lsa, hook `npm run build`
qilib `webdist/` ni qayta yozadi va commitga qo'shadi. Build yiqilsa commit
to'xtaydi. Ya'ni qo'lda nusxalash **kerak emas**.

DIQQAT — hook faqat `web/src/` ga qaraydi. Agar SIZ faqat `web/public/`
yoki `web/index.html` ni o'zgartirsangiz hook ISHLAMAYDI va `webdist`
eskirib qoladi. Bunday holda qo'lda:
```
cd web && npm run build
robocopy "web\dist" "webdist" /MIR      # yoki cp -r web/dist/. webdist/
```

Serverga chiqarish: commit → push → serverda `git pull` +
`touch tmp/restart.txt`. Deploy'ni **faqat foydalanuvchi so'raganda** qiling.

SSH: `ssh -i ~/.ssh/id_ed25519_hodimlar_cpanel -p 30151 nuriddi5@167.235.222.200`
(domen DNS orqali topilmaydi — **IP** ishlatiladi), papka `~/hodimlar-tizimi`.

Kesh tuzog'i: `/api/health` ilova o'lik bo'lsa ham keshdan 200 qaytaradi.
Har doim `?cb=$(date +%s)` qo'shib tekshiring.

---

## 3. Arxitektura qarori — buni buzmang

### 3.1 Etalon naqsh loyihada ALLAQACHON bor
[api/routers/payroll.py:974-989](api/routers/payroll.py:974) — bitta mantiq,
ikki yupqa adapter:

```python
# Bot uchun: shaxsni telegram_id'dan yechadi
@router.get("/my/{telegram_id}/late-status", dependencies=[Depends(verify_bot_secret)])
async def my_late_status(telegram_id: int, db=Depends(get_db)):
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return await _late_status_for_user(db, user)      # ← mantiq

# Web uchun: shaxsni TOKENDAN oladi
@router.get("/me/late-status")
async def my_late_status_web(user: User = Depends(get_current_user), db=Depends(get_db)):
    return await _late_status_for_user(db, user)      # ← O'SHA mantiq
```

**Har bir yangi `/me/...` endpoint aynan shu shaklda bo'lishi kerak.**

### 3.2 Qat'iy qoidalar
1. **Mantiq servis/yordamchi funksiyada, routerda EMAS.** Signature doim
   `(db, user, ...)` — `telegram_id` emas, `user_id` emas.
2. **Mantiq TAKRORLANMAYDI.** Agar mantiq hozir router ichida bo'lsa
   (masalan [payroll.py:921](api/routers/payroll.py:921) `my_payslip` —
   so'rov ham, xaritalash ham router ichida): avval yordamchiga **ajratib
   oling**, bot endpointini shu yordamchiga ulang, **bot ishlashini
   tekshiring**, keyingina `/me` variantini qo'shing.
3. **`/me` endpointlar mijozdan shaxsni QABUL QILMAYDI.** Path'da,
   query'da, tanada `user_id`/`telegram_id` bo'lmasin — faqat
   `Depends(get_current_user)`. Bu 1-bo'lim zaifligini yomonlashtirmaslik
   uchun majburiy. E'tibor bering: `POST /excused-days` hozir `telegram_id`ni
   TANADA oladi (`ExcusedDayCreate`) — JWT varianti uchun alohida sxema
   kerak, mavjudini qayta ishlatib bo'lmaydi.
   Rate-limit kerak bo'lsa tayyor vosita bor: `rate_limit(nom, urinish,
   soniya)` — `api/deps.py:68`, namuna `api/routers/auth.py:45,74`.
4. **Yozish amallari uchun ruxsat qayta tekshiriladi.** Masalan "sababli
   kun so'rash" — xodim faqat O'ZI uchun so'rov yubora oladi.
5. **Bot xatti-harakati o'zgarmaydi.** Bot — ilova o'rnatmagan xodimlar
   uchun zaxira, u ishlashdan to'xtamasligi kerak.

---

## 4. Bosqichlar

Har bosqich **alohida commit**. Keyingisiga o'tishdan oldin chiqish mezoni
bajarilishi shart.

### Bosqich 0 — Xaritalash (kod yozilmaydi)

9 ta funksiyaning har biri uchun aniqlang va jadval qilib yozing:

| Funksiya | Bot handleri | Bot chaqiradigan API | Mantiq qayerda | `(db, user)` yordamchisi bormi |
|---|---|---|---|---|
| 🗓 Ish jadvali | | `/work-schedule/{tg}/me/week` | `_effective_week` | ✅ bor |
| 💵 Mening oyligim | | `/payroll/my/{tg}` | router ichida | ❌ ajratish kerak |
| 📊 Bugungi normam | | | | |
| 📋 Vazifalarim | | | | |
| 📋 Bugungi rejam | | | | |
| 📈 Statistikam | | | | |
| 💰 Oylik KPI'm | | | | |
| 🙋 Sababli kun so'rash | | | | |
| 📚 Bilim bazasi | | | | |

Boshlash nuqtalari: `bot/keyboards.py` (tugma matnlari) →
`bot/handlers/*.py` (`F.text == BTN_*`) → `bot/api_client.py` (chaqirilgan
yo'l) → `api/routers/*.py`.

Shu bilan birga yozib qo'ying: bot xodimga **aynan nimani ko'rsatadi**
(matn shabloni, qaysi raqamlar). Web'da xuddi shu raqamlar chiqishi kerak —
bu keyinchalik to'g'rilikni tekshirish mezoni bo'ladi.

**Chiqish mezoni:** jadval to'ldirilgan, har qatorda "yordamchi bor" yoki
"ajratish kerak" yozilgan. Foydalanuvchiga ko'rsatilgan.

---

### Bosqich 1 — Xodim navigatsiyasi (frontend skeleton)

Bu birinchi bo'lishi kerak: hozir xodimda navigatsiya **umuman yo'q**
([Layout.tsx:255](web/src/Layout.tsx:255)), ya'ni yangi sahifalarga o'tish
joyi yo'q.

Qadamlar:
1. Xodim uchun `Layout` qobig'ini almashtirish. Telefon uchun **pastdagi
   tab-bar** (barmoq yetadigan joy), sidebar/drawer emas — xodim 5-6 ta
   bo'limdan ortiq ko'rmaydi. Ko'p bo'lsa: 4 tab + "Yana" sahifasi.
2. Barcha bo'limlar uchun marshrutlarni ro'yxatga olish, har biri hozircha
   **placeholder** ("Tez orada"). Mobil ilovada shu yondashuv qo'llangan
   ([mobile/app/home.tsx](mobile/app/home.tsx)) — xodim nima kelayotganini
   ko'radi, lekin bo'sh sahifaga urilmaydi.
3. `Position.menu_flags` bo'yicha filtrlash — bot allaqachon shunday
   qiladi (`bot/keyboards.py: main_menu`), web ham **o'sha** flaglarni
   ishlatishi kerak, aks holda bir xodim botda va web'da boshqa-boshqa
   menyu ko'radi.
4. Brend nomini birlashtirish (3.8): mobil ilova "N.B hodimlar",
   web hamon "Xodimlar KPI/Bonus" — [Layout.tsx:260](web/src/Layout.tsx:260),
   [web/index.html:6](web/index.html:6). Bitta nom tanlang.

**Chiqish mezoni:** xodim rolida kirib, tab-bar orqali barcha bo'limlarga
o'tib ko'rish mumkin; hech biri xato bermaydi; rahbar uchun hech narsa
o'zgarmagan (sidebar avvalgidek).

---

### Bosqich 2 — Davomat ekranidagi mobil nuqsonlar

Kichik, lekin xodim eng ko'p ishlatadigan ekran. Yangi sahifalar
qo'shilishidan oldin bu mustahkam bo'lsin.

1. **Yuz konturi kichik ekranda videodan chiqib ketadi**
   ([FaceCapture.tsx:331](web/src/components/FaceCapture.tsx:331)):
   kontur `w-48 h-60` — qat'iy 192×240 px, video esa `aspect-[4/3] w-full`.
   O'lchangan holat (modal `p-4` + karta `p-5` = 72 px chekka):

   | Ekran | Video | Kontur |
   |---|---|---|
   | 320 px | 248×186 | 54 px chiqadi |
   | 360 px | 288×216 | 24 px chiqadi |
   | 390 px | 318×238 | 2 px chiqadi |
   | 412 px | 340×255 | joyida |

   Kontur video o'lchamiga **nisbatan** (foizda yoki container query)
   bo'lishi kerak. 360 px — eng keng tarqalgan Android o'lchami.

2. **Modalda vertikal scroll yo'q**
   ([CheckIn.tsx:374](web/src/pages/CheckIn.tsx:374)): `fixed inset-0 p-4`
   + `max-w-lg p-5`, lekin `max-h` va `overflow-y-auto` yo'q. Past ekranda
   yoki landscape'da video+matn+tugma kesiladi va scroll qilib bo'lmaydi.

**Chiqish mezoni:** brauzerda 320 / 360 / 390 / 412 px kengliklarda
tekshirilgan — kontur video ichida, modal to'liq scroll bo'ladi.
Skrinshot bilan ko'rsatilgan.

---

### Bosqich 3 — Sessiya va login (avval SO'RANG)

Bu ikkisi xavfsizlikka tegadi, shuning uchun **amalga oshirishdan oldin
foydalanuvchi bilan variantni tasdiqlang**.

1. **Har kuni qaytadan login** — `.env: JWT_EXPIRE_MINUTES=1440`,
   refresh-token yo'q. Kuniga 2 marta ishlatiladigan davomat ilovasi uchun
   og'ir. Variantlar: refresh-token qo'shish / uzoq muddatli token +
   rotatsiya / qurilmaga bog'langan sessiya. Har birining xavfi bor —
   tanlovni foydalanuvchi qilsin.
2. **Login uchinchi tomon skriptiga bog'langan**
   ([Login.tsx:39](web/src/pages/Login.tsx:39)) —
   `https://telegram.org/js/telegram-widget.js`. Telegram sekinlashsa yoki
   bloklansa **hech kim saytga kira olmaydi**. Zaxira yo'l kerak (mobil
   ilovadagi deep-link oqimi allaqachon bor — `/auth/app-login/*`, web
   uchun ham shundan foydalanish mumkin).
   iPhone PWA'da qo'shimcha muammo: Safari→Telegram→Safari qaytishi
   standalone rejimdan chiqib ketishi mumkin.

**Chiqish mezoni:** xodim kunda bir marta login qilishga majbur emas;
`telegram.org` bloklangan holatda ham kirish yo'li bor (sinovda
tekshirilgan — masalan DevTools'da domenni bloklab).

---

### Bosqich 4 — Funksiyalarni bittalab ulash

Har bir funksiya **alohida to'liq tsikl**: backend → sxema → hook →
sahifa → tekshirish → commit. Bir vaqtda bittasini qiling.

Tavsiya etilgan tartib (xodim uchun qiymati bo'yicha):
1. 🗓 Ish jadvali *(yordamchi bor — eng oson, naqshni shu bilan o'rnatasiz)*
2. 💵 Mening oyligim
3. 📊 Bugungi normam
4. 📋 Vazifalarim *(yozish amali bor: bajarildi deb belgilash)*
5. 📋 Bugungi rejam
6. 📈 Statistikam
7. 💰 Oylik KPI'm
8. 🙋 Sababli kun so'rash *(yozish amali)*
9. 📚 Bilim bazasi / 🤖 Sotuv AI

Har biri uchun tartib:
1. Kerak bo'lsa mantiqni `(db, user)` yordamchisiga ajratish, bot
   endpointini shunga ulash, **bot ishlashini tekshirish**.
2. `/me/...` JWT endpoint qo'shish (3.1 naqshi bo'yicha).
3. `api/schemas.py`ga sxema (mavjud bo'lsa qayta ishlatish).
4. `web/src/lib/queries.ts`ga react-query hook.
5. Mobil-birinchi sahifa: 360 px uchun loyihalash, keyin kattaroq ekran.
   Jadval emas — karta/ro'yxat. Tugmalar barmoq uchun (≥44 px).
6. Placeholder'ni almashtirish.

**Har bir funksiyaning chiqish mezoni (majburiy):**
- `npx tsc -b` toza
- Bot **o'zgarmagan** — o'sha xodim uchun bot javobi avvalgidek
- **Web va bot bir xil raqamlarni ko'rsatadi** (bitta xodimni tanlab,
  ikkisini yonma-yon solishtirib tekshirish). Farq bo'lsa — mantiq
  takrorlangan yoki noto'g'ri ajratilgan.
- 360 px ekranda gorizontal scroll yo'q
- Ma'lumot yo'q holati (bo'sh ro'yxat, hali hisoblanmagan oylik) chiroyli
  ko'rinadi, xato emas

---

### Bosqich 5 — Tezlik ✅ BAJARILDI (2026-07-30)

O'LCHANDI (jonli sayt, siqilgan holda) va auditdagi xulosa TUZATILDI:
«birinchi ochishda ~8.3 MB» noto'g'ri edi — u siqilmagan hajmlarga va
«modellar sahifa ochilishida yuklanadi» degan taxminga asoslangan.

| | Oldin | Keyin |
|---|---|---|
| `/check-in` ochilishida JS | 345 KB | **3.4 KB** |
| Modellar sahifa ochilishida | 0 (allaqachon to'g'ri) | 0 |
| Kamera oqimida | 4 499 KB | 4 499 KB + 343 KB chunk |
| `/models` `Cache-Control` | **yo'q** | `public, max-age=2592000` |

Ikki o'zgarish: (1) `FaceCapture` lazy — tab-bar qo'shilgach `/check-in`
xodimning kirish sahifasi bo'lib qolgan edi, ya'ni jadvalini ko'rmoqchi
bo'lgan xodim ham yuz kutubxonasini yuklardi; (2) `SPAStaticFiles` endi
`/models/` ga uzoq kesh sarlavhasi qo'yadi (`.htaccess` EMAS — bu hostda
u ilovani 500 ga tushirgan).

Quyidagi asl matn tarix uchun qoldirildi.

### Bosqich 5 — Tezlik (asl reja)

1. **Birinchi ochishda ~8.3 MB** — `CheckIn` chunk 1.34 MB + yuz modellari
   7 MB. Tekshiring: modellar sahifa ochilganda yuklanadimi yoki kamera
   ochilganda? Faqat kerak bo'lganda yuklanishi kerak.
2. **`/models` uchun `Cache-Control` yo'q.** Jonli serverda o'lchangan:
   - `/assets/CheckIn-*.js` → `Cache-Control: max-age=2592000` ✅
   - `/models/face_recognition_model-shard1` → yo'q, faqat `ETag`

   Ya'ni har ochilishda 7 ta fayl qayta so'raladi. Fayllar
   **o'zgarmaydi** (model versiyasi qotgan), shuning uchun uzoq muddatli
   kesh xavfsiz. Statik fayllar Passenger/`StaticFiles` orqali beriladi
   ([deploy/cpanel/passenger_wsgi.py](deploy/cpanel/passenger_wsgi.py)) —
   `.htaccess` yoki mount sozlamasi orqali qo'shish mumkin.

**Chiqish mezoni:** oldin/keyin **o'lchangan** raqamlar bilan ko'rsatilgan
(birinchi ochish hajmi, ikkinchi ochishdagi so'rovlar soni).

---

### Bosqich 6 — Rahbar uchun mobil ✅ BAJARILDI (2026-07-30, commit `0f51940`)

[DataTable.tsx:117](web/src/components/DataTable.tsx:117) — faqat
`overflow-x-auto` + `whitespace-nowrap` edi. Endi `md`dan kichik ekranda
har bir qator alohida KARTA ("ustun nomi — qiymat" juftliklari), qiymatlar
aynan `cell` render'idan keladi (badge/tugma/select — hammasi ishlaydi).
Bo'sh holat va skelet bitta joyda e'lon qilinadi, ikkala ko'rinishda ham
ishlatiladi. Yo'l-yo'lakay: `Users.tsx` grid bolalariga `min-w-0`
(DataTable'ga aloqasi yo'q, oldindan mavjud nuqson — o'lchash paytida
chiqdi).

Tekshirildi (360 px, dasturchi roli): `/attendance` 22 karta overflow 0,
`/users` 8 karta overflow 59→0, `/payroll` 7 karta overflow 0. Desktop
(1280 px): jadval joyida, mobil blok `display:none`, sidebar o'zgarmagan.

#### Yakunlandi (2026-07-31) — `DataTable`ni chetlab o'tgan jadvallar

`0f51940` tugallanmagan qolgan edi: **`DataTable`ni ISHLATMAYDIGAN** ikki
xom jadval e'tibordan chetda qolgan — `components/statistics/OperatorTable.tsx`
(«Operator kesimi», 6 ustun) va `components/users/CrmMappingSection.tsx`
(CRM/Tashrif bog'lash, 4 ustun × 2 ta).

**Nega o'lchov ularni ko'rsatmagan** (kelgusi tekshiruvlar uchun muhim):
`0f51940` sahifa darajasidagi overflow'ni o'lchagan
(`documentElement.scrollWidth - clientWidth`), u esa bu nuqsonni **ushlamaydi** —
shadcn `Table` o'zining `overflow-auto` wrapper'i bilan keladi, ya'ni jadval
sahifani kengaytirmaydi, o'z ichida jimgina scroll bo'ladi. To'g'ri o'lchov:
`table.parentElement.scrollWidth - table.parentElement.clientWidth`.
Ustiga, ikkalasi ham standart holatda ekranda YO'Q edi — «Operator kesimi»
«Bugun» tabida bo'sh (bugungi CRM ma'lumoti hali yo'q), CRM bog'lash esa
faqat `operators.length > 0` bo'lganda render bo'ladi.

O'lchandi (360 px): Operator kesimi **255 px**, CRM bog'lash **466 px**
yashirin gorizontal scroll → ikkalasi ham endi **0**.

Karta uslubi `components/MobileCard.tsx` ga chiqarildi (`MobileCard` /
`MobileCardRow`) va `DataTable` ham shunga o'tkazildi — uch joyda takrorlansa
chekka/ajratuvchi bir joyda o'zgarib ikkinchisida eskirib qolardi.
Ikki tuzoq o'lchov paytida ushlandi: (1) `MobileCardRow` qiymatiga
`break-words` kerak — Uysot identifikatori EMAIL, bo'sh joysiz uzun satr
kartadan chiqib 8 px sahifa overflow berdi; (2) `UserSelect`ka `min-w-0`
(flex bolasining `min-width: auto` — `0f51940` buni `Users.tsx` grid'ida
tuzatgan edi, bu yerda qaytadan chiqdi).

⚠️ Bu ish **`3a6f71b`** commit'iga tushib qolgan («CRM sync: … N+1») —
parallel sessiya bir vaqtda `git commit` qilib, staged fayllarimni o'z
commit'iga qo'shib yuborgan. Commit sarlavhasi bu frontend ishini
ta'riflamaydi; kod to'g'ri va push qilingan, tarix qayta yozilmadi.

**Chiqish mezoni:** 360 px da asosiy rahbar sahifalari gorizontal
scrollsiz o'qiladi; desktop ko'rinishi buzilmagan. ✅
O'lchandi: 320/360 px `/statistics` va `/users` — sahifa overflow 0, jadval
ichki scroll 0; 1280 px — `/statistics` jadval 9 qator (8 operator + Jami),
`/users` 2 jadval (8 xodim + 4 CRM operator), mobil bloklar yashirin.
Regressiya yo'q: `/attendance` 29 karta, `/payroll` bo'sh holat — overflow 0.

---

### Bosqich 7 — Yakuniy tekshiruv ✅ BAJARILDI (2026-07-31)

- ✅ Barcha rollar bilan o'tib ko'rish: employee, rop, hr, boss, dasturchi
  — har biriga JWT yasab (`create_access_token`), `localStorage`ga qo'yib
  brauzerda tekshirildi (SSL'siz yordamchi instans, 5174-port —
  `web/package.json`da `dev:nossl`, `.claude/launch.json`da `web-nossl`).
- ✅ 320 / 360 / 412 px + desktop (1280 px) — barcha rolларда
  `scrollWidth - clientWidth === 0`, konsolda xato yo'q.
- ✅ Bot to'liq ishlayapti (9 funksiya) — `bot/` papkasi Bosqich 1-6
  davomida BUTUNLAY tegilmagan (`git diff --stat 2b5afd2~1 0f51940 --
  bot/` bo'sh). Xodim (Firuzabonu, `telegram_id=1286546988`) uchun bot
  (`X-Bot-Secret`) va web (`Depends(get_current_user)`) javoblari
  yonma-yon solishtirildi — ish jadvali va bugungi normam bayt-ma-bayt
  bir xil chiqdi.
- ✅ `npx tsc -b` (web) va `npx tsc --noEmit` (mobile) — ikkalasi ham toza.
- ✅ `MOBIL_ILOVA_REJASI.md` yangilangan.
- Deploy — **qilinmadi**, foydalanuvchi so'ramagan. Bosqich 5/6 commitlari
  hozircha faqat lokalda, `origin/master`ga push qilinmagan.

Sinovda ishlatilgan foydalanuvchi: xodim Firuzabonu (`id=8`,
`telegram_id=1286546988`) — barcha 9 funksiyaning sahifasi (jadval,
normam, rejam, oyligim, KPI'm, lidlar, vazifalarim, statistikam, sababli
kun formasi) 320-412 px'da ochilib tekshirildi; yozish amali (sababli
kun so'rovi) real Telegram xabar yubormaslik uchun submit qilinmadi —
forma ko'rinishi va validatsiyasi tekshirilgani yetarli deb topildi.

---

## 5. Har bosqichda majburiy tartib

1. O'zgartirishdan oldin tegishli faylni **o'qing** (taxmin qilmang)
2. Kichik qadamlar, tez-tez `tsc`
3. Brauzerda **haqiqatan tekshirib ko'ring** (`VITE_NO_SSL=1` instansi bilan
   360 px), "ishlashi kerak" degan xulosa yaramaydi
4. Commit xabari repo uslubida: birinchi qatorda nima, keyin **NEGA** —
   mavjud commitlarga qarang (`git log`), ular sababni tushuntiradi
5. Bir bosqich tugagach foydalanuvchiga qisqa hisobot: nima qilindi, nima
   o'lchandi, nima qoldi

---

## 6. QILMANG

**Mobil ilova (APK):**
- `expo prebuild` **ishlatmang** — `mobile/android/` ni qayta yaratadi va
  release imzo sozlamalari, CMake staging yo'li (`C:/hb`, Windows MAX_PATH)
  hamda kamera/GPS ruxsatlari yo'qoladi
- `mobile/android/app/build.gradle` dagi `signingConfigs` ga tegmang —
  imzo o'zgarsa eski ilova ustiga o'rnatilmaydi
- AndroidManifest.xml **izohida `--` yozmang** — XML parse xatosi beradi
  va manifest merger yiqiladi (xato xabari sababni ko'rsatmaydi)
- `mobile/`da `npm install` → `--legacy-peer-deps` kerak
  (`@expo/ui` → `vaul` → `react-dom@19.2.8` vs `react@19.2.3`, oldindan
  mavjud ziddiyat)
- Hermes bayt-kodini `grep` bilan tekshirmang — satrlar jadvalida qisqa
  satr uzunining prefiksi bo'lib saqlanadi va noto'g'ri xulosa chiqadi

**Backend:**
- Router ichiga mantiq yozmang
- Bot-secret endpointlarni buzmang (yordamchiga ajratganda ham)
- `/me` endpointga mijozdan shaxs qabul qilmang
- Migratsiya kerak bo'lsa `alembic revision` — qo'lda SQL emas

**Umumiy:**
- Yuz modelini almashtirmang, ikkinchi model qo'shmang — saqlangan
  `User.face_descriptor` yaroqsiz bo'lib, hamma xodim yuzini qaytadan
  ro'yxatdan o'tkazadi
- Deploy'ni o'zboshimchalik bilan qilmang
- `webdist` — odatda pre-commit hook AVTOMATIK yangilaydi (2.3-band). Faqat
  `web/src` tegilmagan (masalan faqat `web/public` yoki `index.html`)
  o'zgarishda qo'lda yangilash kerak, aks holda sayt eski JS beradi
- 1-bo'lim (soxtalashtirish) zaifligini bu ishda tuzatmang, lekin
  **yomonlashtirmang** ham

---

## 6.5 ⚠️ KPI/bonus stavkalari HALI PLACEHOLDER

Bosqich 4.7 da aniqlandi. `api/services/bonus.py`:

```python
PLACEHOLDER_RATE_PER_CONVERSATION = 2000
PLACEHOLDER_RATE_PER_VISIT = 5000
PLACEHOLDER_RATE_PER_VIDEO = 0
```

`breakdown` ichida so'zma-so'z: `"formula": "placeholder: lavozim
metrikalari * stavka (real formula keyinroq belgilanadi)"`.

Bazadagi summalar real ko'rinadi (masalan 577 000 so'm) va **ikki joyda
xodimga ko'rinadi**:
1. «Oylik KPI'm» sahifasi — summa to'liq ko'rsatiladi (2026-07-30 dagi qaror)
2. **Oylik varaqasi** — `payslip.bonus_amount` aynan shu jadvaldan keladi
   (`api/services/payroll.py:589`) va «Jami» summasiga qo'shiladi

Hozircha hech kim ko'rmagan, chunki birorta payslip `approved` emas.

**HR birinchi oylik varaqasini TASDIQLASHDAN OLDIN haqiqiy stavkalar
belgilanishi kerak** — aks holda xodim placeholder asosidagi summani
oladi va keyin u o'zgarsa ishonch yo'qoladi. Stavka o'zgarganda faqat
`api/services/bonus.py` dagi uchta konstanta o'zgaradi, qolgan hech narsa
(API/bot/sayt) tegilmaydi — fayl izohida shunday yozilgan.

## 7. Ochiq savollar — boshlashdan oldin foydalanuvchiga bering

1. **Sessiya (Bosqich 3):** har kunlik loginni qanday yechamiz —
   refresh-token, uzoq token + rotatsiya, yoki qurilmaga bog'langan
   sessiya? Har birining xavfi boshqa.
2. **9 funksiyaning hammasi web'da kerakmi?** Ba'zilari (masalan Sotuv AI
   suhbati) botda tabiiyroq bo'lishi mumkin. Faqat kerakliga vaqt sarflash
   uchun.
3. **Navigatsiya:** pastdagi tab-bar (tavsiya) yoki drawer? Nechta tab?
4. **Yozish amallari birinchi bosqichda kerakmi** (vazifani bajarildi deb
   belgilash, sababli kun so'rash), yoki avval faqat **o'qish** qilib,
   yozishni keyin qo'shamizmi?
5. **Bot bilan munosabat:** web to'liq ishlagach bot funksiyalari
   qoladimi (zaxira sifatida) yoki qisqartiriladimi?

---

## 8. Ish tugaganining belgisi

- Xodim telefonda kabinetga kirib, botdagi barcha kerakli funksiyani qila
  oladi va **raqamlar bot bilan bir xil**
- Xodimda ishlaydigan navigatsiya bor
- Davomat ekrani 320 px dan boshlab to'g'ri ko'rinadi
- Xodim har kuni qaytadan login qilmaydi
- Telegram bloklansa ham saytga kirish yo'li bor
- Birinchi ochish hajmi o'lchanib kamaytirilgan
- Rahbar sahifalari telefonda o'qiladi
- Bot ishlashdan to'xtamagan
- `MOBIL_ILOVA_REJASI.md` yangilangan
