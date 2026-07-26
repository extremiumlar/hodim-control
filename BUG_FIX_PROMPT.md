# DAVOMAT TIZIMI — BUGLARNI TUZATISH BO'YICHA TOPSHIRIQ

> Bu hujjat 2026-07-26 dagi to'liq auditdan keyin tuzilgan. Tuzatishni boshlashdan
> oldin BUTUNLAY o'qing — ayniqsa "Ehtiyot choralari" va "Qaror talab qiladigan
> nuqtalar" bo'limlarini.

---

## 1. KONTEKST

**Loyiha:** `D:\Project\hodimlar_tizimi` — xodimlar KPI/bonus + davomat tizimi.

**Stek:**
- Backend: FastAPI + SQLAlchemy (async) + Alembic. Baza: SQLite `app.db`.
- Frontend: Vite + React + TS + Tailwind + shadcn/ui + react-query. Papka `web/`.
- Bot: aiogram (`bot/`), scheduler (`scheduler/`), cPanel uchun `scripts/cron_tick.py`.
- Muhit: `.venv/Scripts/python` (tizim python'da paketlar YO'Q).
- Alembic: `python -m alembic -c db/alembic.ini upgrade head`.
- Xizmatlarni qayta ishga tushirish: FAQAT `schtasks /run /tn "HodimlarTizimi_StartAll"`
  (skriptni to'g'ridan-to'g'ri chaqirish MUMKIN EMAS — jarayonlar sessiya bilan o'ladi).
- Jonli sinov: `.venv/Scripts/python.exe test.py` (26 ta tekshiruv, T- ma'lumot bilan).

**Davomat tizimi qanday ishlaydi (joriy holat):**
- Xodim web'da (`/check-in`) GPS + Face ID bilan "Keldim"/"Ketdim" qiladi.
- Face ID: brauzerda `@vladmandic/face-api` 128-o'lchamli deskriptor hisoblaydi,
  serverga yuboradi; server `similarity = 1 − evklid` ≥ 0.5 va `liveness` ≥ 0.5 tekshiradi.
- GPS: eng yaqin faol ofis radiusi (haversine).
- Kechikish: ish jadvali oynasidan (`WorkScheduleOverride` > `WorkScheduleWeekly` >
  default Du-Ju 09:00-18:00), grace 5 daqiqa.
- Qamrov: `ATTENDANCE_TRACKED_ROLES` = Boshliqdan tashqari hamma (employee/hr/rop/dasturchi).
- Guruh digesti: ertalab (default 09:30) va kechqurun (22:00), vaqti bazadan
  (`attendance_digest_config`, botda `/davomat_vaqt`).

**Asosiy fayllar:**
```
api/services/attendance.py          — check-in/out, GPS, Face ID tekshiruvi
api/services/attendance_digest.py   — guruh digesti (collect_day + matnlar)
api/routers/attendance.py           — barcha endpointlar
api/routers/work_schedule.py        — ish jadvali
api/routers/hourly_plan.py          — _effective_today (ish oynasi qoidasi manbai)
web/src/pages/CheckIn.tsx           — xodim UI
web/src/components/FaceCapture.tsx  — kamera + liveness
web/src/lib/face.ts                 — face-api wrapper
web/src/pages/Attendance.tsx        — rahbar paneli
web/src/pages/WorkSchedule.tsx      — ish jadvali UI
bot/handlers/attendance_stats.py    — bot statistikasi + /davomat_vaqt
```

---

## 2. VAZIFA

Quyidagi topilgan buglarni **bosqichma-bosqich** tuzatish. Har bosqichdan keyin
sinov + commit. Barcha bosqichni bir commitga tiqmang.

---

## 3. TUZATISH TARTIBI

### 🔴 BOSQICH 1 — Statistika yolg'on ko'rsatyapti (eng shoshilinch)

**1.1. `absent` statusi hech qachon yozilmaydi**
- Joy: `api/services/attendance.py:117-127` (`_apply_status`) — `check_in_time is None`
  tarmog'iga hech qachon kirilmaydi (funksiya faqat check-in/out ichida, ular esa
  vaqtni allaqachon o'rnatgan). Butun loyihada `AttendanceStatus.absent` faqat shu joyda.
- Oqibat: `GET /attendance?status_filter=absent` doim bo'sh.
- **Tuzatish:** kun oxirida (masalan digest tick ichida yoki alohida job) o'sha kuni
  ishlashi kerak bo'lgan, lekin check-in qilmagan xodimlarga `absent` yozuvi yaratish.
  Tasdiqlangan sababli kunlar (`ExcusedDay` approved) hisobga olinsin.

**1.2. `employee-summary` INNER JOIN — kelmagan xodim ro'yxatda YO'Q**
- Joy: `api/routers/attendance.py:347` — `.join(Attendance, ...)`.
- Oqibat: **umuman kelmagan xodim jadvalda butunlay ko'rinmaydi** — eng yomon xodim
  eng "toza" ko'rinadi. Bu rahbarni chalg'ituvchi eng jiddiy xato.
- **Tuzatish:** `outerjoin` (LEFT JOIN) + `ATTENDANCE_TRACKED_ROLES` filtri User'da,
  sanalar filtri JOIN shartiga (ON) ko'chirilsin (aks holda LEFT JOIN WHERE tufayli
  yana INNER'ga aylanadi). "Kelmagan kunlar" ustuni qo'shilsa yanada yaxshi.

**1.3. Kechikish grace'ni ayirib yozadi**
- Joy: `api/services/attendance.py:165` — `late_minutes = max(0, diff - grace)`.
- Oqibat: 09:06 da kelgan xodim "1 daqiqa kechikdi" bo'lib yoziladi (haqiqiy 6).
  Har kechikkan kun 5 daqiqaga kam ko'rsatiladi.
- **Tuzatish:** grace faqat BO'SAG'A bo'lsin: `late = diff if diff > grace else 0`.
- ⚠️ Bu mavjud yozuvlarga ta'sir qilmaydi (tarix o'zgarmaydi) — buni izohda yozing.

**1.4. Erta ketish / kechikishda yuqori chegara yo'q**
- Joy: `api/services/attendance.py:204-208` va `:163-165`.
- Oqibat: 09:05 da ketgan "535 daqiqa erta ketdi"; 17:59 da kelgan "534 daqiqa kechikdi"
  — bitta kun oylik statistikani portlatadi.
- **Tuzatish:** mantiqiy chegara (masalan ish oynasi uzunligidan oshmasin) yoki
  bunday holatni alohida status bilan belgilash.

---

### 🔴 BOSQICH 2 — Ma'lumot yo'qolishi va poyga holatlari

**2.1. Yarim tundan keyin "Ketdim" bosib bo'lmaydi**
- Joy: `api/services/attendance.py:185-192` — `day = today_local()`.
- Oqibat: 00:00 dan keyin kechagi ochiq yozuv topilmaydi → xodim check-out qila olmaydi,
  yozuv abadiy `check_out_time=NULL`, `worked_minutes=0`.
- **Tuzatish:** check-out avval bugungi ochiq yozuvni, topilmasa KECHAGI ochiq yozuvni
  izlasin (masalan 6 soatlik oyna bilan). Tungi smena qo'llab-quvvatlanishi kerakmi —
  qarang "Qaror nuqtalari".

**2.2. Unutilgan check-out uchun tuzatish yo'li yo'q**
- `worked_minutes` faqat "Ketdim" bosilganda hisoblanadi; bosmagan kun 0 bo'lib qoladi
  va `month_worked_hours` doimiy kam ko'rsatadi. Rahbar tahrirlay olmaydi (Dasturchi
  faqat O'CHIRA oladi).
- **Tuzatish:** (a) kun oxirida avtomatik yopish (ish oynasi tugashida), yoki
  (b) rahbarga yozuvni tahrirlash imkoni. Ikkalasi ham bo'lsa ideal.

**2.3. Check-in poygasi → 500 xato**
- Joy: `api/services/attendance.py:147-170` — SELECT-then-INSERT, qulfsiz.
- Oqibat: ikki marta tez bosilsa `IntegrityError` ushlanmaydi → foydalanuvchiga 500.
- **Tuzatish:** `IntegrityError`ni ushlab, tushunarli `CheckError` ("allaqachon
  check-in qilgansiz") ga aylantirish. Check-out'da ham himoya qo'shilsin.

**2.4. Frontend: bekor qilingandan keyin ham check-in yuboriladi**
- Joy: `web/src/pages/CheckIn.tsx:155-174` + `FaceCapture.tsx:115-153`.
- Oqibat: "Tahlil qilinmoqda..." paytida ✕ bosilsa modal yopiladi, lekin jarayon
  davom etadi (kamera muzlagan freymda yuzni aniqlaydi) va so'rov BARIBIR ketadi.
- **Tuzatish:** `AbortController`/`cancelled` bayrog'i — modal yopilganda `onResult`
  e'tiborga olinmasin; `FaceCapture` unmount bo'lganda sikl to'xtasin.

---

### 🟡 BOSQICH 3 — Mantiqiy xatolar

**3.1. Ish jadvali o'zgartirilsa davomat qayta hisoblanmaydi**
- Joy: `api/routers/work_schedule.py` (weekly/override PUT) — recalc yo'q.
- Oqibat: xodim 09:30 da keldi (late=25), rahbar startni 10:00 qildi → baza 25 da
  qoladi, digest esa yangi jadvaldan hisoblab **o'sha odamni "60 daq erta keldi"**
  deb ham ko'rsatadi (bir odam ham kechikkan, ham erta kelgan).
- **Tuzatish:** jadval o'zgarganda o'sha sanadagi (bugungi va kelajakdagi) davomat
  yozuvlarini qayta hisoblash. O'tgan kunlarga TEGMANG (tarix).
- Muqobil: digest `early_in`ni ham `Attendance`dan hisoblasin (bitta manba).

**3.2. "Eng yaqin ofis" mantiqi noto'g'ri**
- Joy: `api/services/attendance.py:92-114` — faqat eng yaqin ofis olinadi, keyin
  faqat o'sha ofisning radiusi tekshiriladi.
- Oqibat: A ofis 100 m (radius 50), B ofis 120 m (radius 200) — xodim B ning qonuniy
  radiusi ichida, lekin rad etiladi.
- **Tuzatish:** "birorta faol ofis radiusi ichidami" tekshiruvi (radiusdan ichkarilari
  orasidan eng yaqinini tanlash).

**3.3. Digest yuborilmasa ham "yuborildi" belgilanadi**
- Joy: `api/services/attendance_digest.py:289-296` — `sent: False` bo'lsa ham
  `*_last_posted = today` yoziladi.
- Oqibat: guruh sozlanmagan bo'lsa o'sha kun digesti butunlay yo'qoladi.
- **Tuzatish:** faqat haqiqatan yuborilganda belgilash; "dam olish kuni" holati
  alohida (u qayta urinmasligi kerak).

**3.4. Dashboard aralash qamrov**
- Joy: `api/routers/attendance.py:230-245, 281-290` — `total_employees`,
  `checked_in_today`, `late_today`, oylik jamlar BARCHA userlardan; `working_today`,
  `not_checked_in` esa faqat `ATTENDANCE_TRACKED_ROLES` dan.
- Oqibat: Boshliq check-in qilsa `checked_in_today > working_today` bo'lib qoladi.
- **Tuzatish:** hamma joyda `ATTENDANCE_TRACKED_ROLES`. Qo'shimcha: `/me/check-in`
  da ham rol tekshiruvi (Boshliq check-in qilmasin) — yoki qamrovni kengaytirish.

**3.5. N+1 so'rovlar**
- Joy: `attendance_digest.py:108-109` (`collect_day`), `work_schedule.py:258`
  (`all_week`) — har xodimga 2 tadan so'rov.
- **Tuzatish:** dashboard (`routers/attendance.py:254-266`) da to'g'ri yechim bor —
  override/weekly ni BITTA so'rovda olib, lug'atdan foydalanish. O'shani ko'chiring.

**3.6. GPS eskirgan bo'lishi mumkin**
- Joy: `web/src/pages/CheckIn.tsx:137-153` — joylashuv yuz tasdiqlashdan OLDIN olinadi;
  model yuklanishi + urinishlar 2-3 daqiqa cho'zilishi mumkin.
- **Tuzatish:** GPS ni yuz tasdiqlangandan KEYIN (yuborishdan oldin) olish, yoki
  eskirgan bo'lsa qayta olish.

**3.7. Xodim almashtirilganda eski jadval ko'rinadi**
- Joy: `web/src/pages/WorkSchedule.tsx` — javob kelguncha `week`da oldingi xodim
  ma'lumoti turadi; tez "Saqlash" bosilsa BOSHQA xodimning jadvali yozilib ketadi.
- **Tuzatish:** yuklanish paytida formani bloklash + saqlanmagan o'zgarish
  ogohlantirishi.

**3.8. Ofis koordinatasi bo'sh qolsa `0,0`**
- Joy: `web/src/pages/Offices.tsx:20-21` — `z.coerce.number()` bo'sh satrni 0 qiladi.
- Oqibat: ofis "Null Island"da yaratiladi, hech kim check-in qila olmaydi.
- **Tuzatish:** bo'sh qiymatni rad etuvchi validatsiya.

---

### 🟢 BOSQICH 4 — UX va barqarorlik

- **4.1.** Rad sababi faqat qisqa toast — modal ichida qolib, o'qishga ulgursin
  (`CheckIn.tsx:166-173`).
- **4.2.** CDN ishlamasa "Qayta urinish" tugmasi (`FaceCapture.tsx:85-89`);
  modellarni o'z serveringizga ko'chirish ham ko'rib chiqilsin (uchinchi tomon
  shaxsiy GitHub Pages'ga bog'liqlik).
- **4.3.** Bot: backend xatosida jim qolmasin (`attendance_stats.py:67-75,89,109` —
  try/except yo'q); 4096 belgi limitidan oshmasin (`:30-49`).
- **4.4.** GPS xatolari o'zbekcha (`CheckIn.tsx:151`, `Offices.tsx:66` — hozir
  "User denied Geolocation" chiqadi).
- **4.5.** `liveness: result.liveness ?? 1.0` → default **0** bo'lsin
  (`CheckIn.tsx:164` — hozir eng yuqori ishonch, teskari).
- **4.6.** `days=30` aslida 31 kun (`routers/attendance.py:336,371` — `>=` + timedelta).
- **4.7.** Override formasida `start < end` validatsiyasi yo'q (`WorkSchedule.tsx:90-110`).
- **4.8.** Dashboard xatosi ko'rsatilmaydi, avto-yangilanish yo'q (`Attendance.tsx:193-268`).
- **4.9.** Eskirgan izohlar: `attendance_digest.py:10-11`, `routers/attendance.py:248-249,411-413`
  ("faqat employee" deb yozilgan, aslida ATTENDANCE_TRACKED_ROLES).
- **4.10.** `fmtTime` ikki faylda nusxalangan (`CheckIn.tsx:30`, `Attendance.tsx:40`) —
  umumiy yordamchiga chiqarilsin.

---

## 4. QAROR TALAB QILADIGAN NUQTALAR (avval so'rang!)

Bu uchtasi **biznes qarori** — kod yozishdan oldin foydalanuvchidan so'rang:

**A. Face ID xavfsizligi (eng muhim).** Hozir `liveness`, `face_descriptor` va GPS —
hammasi brauzerdan keladi. Xodim o'z tokeni bilan `curl` orqali uydan turib check-in
qila oladi; tiriklik formulasi esa harakatsiz fotoni ham o'tkazadi (0.9 ≥ 0.5).
Variantlar:
1. **Server tomonda tekshirish** — rasm yuboriladi, deskriptor va tiriklik serverda
   hisoblanadi (og'ir: Python'da face recognition kutubxonasi + CPU).
2. **Yumshoq choralar** — qayta ro'yxatdan o'tish rahbar tasdig'iga + audit yozuvi +
   ogohlantirish; GPS aniqligi (`accuracy`) tekshiruvi; bir xil deskriptorni
   qayta ishlatishni aniqlash (nusxa-o'tkazish detektori).
3. **Hozircha qoldirish** — jamoa kichik va ishonchli bo'lsa, xavf qabul qilinadi.

**B. Tungi smena kerakmi?** Hozir `start < end` majburiy, yarim tunga o'tish
qo'llab-quvvatlanmaydi. Agar kerak bo'lsa — jadval modeli o'zgaradi (katta ish).

**C. Unutilgan check-out qanday yopilsin?** (a) ish oynasi tugashida avtomatik,
(b) rahbar qo'lda tahrirlaydi, (c) ikkalasi.

---

## 5. EHTIYOT CHORALARI (MAJBURIY)

1. **Jonli baza.** `app.db` da HAQIQIY ma'lumot bor (8 foydalanuvchi, davomat tarixi,
   audit). Har bosqichdan oldin zaxira: `cp app.db app.db.bak_<sana>`.
2. **Guruhga xabar.** Lokal `.env` HAQIQIY Telegram guruhiga ulangan. Digest bilan
   ishlaganda FAQAT `dry_run=true` ishlating. Lokal bazada digest hozir O'CHIRILGAN
   (`attendance_digest_config.morning_enabled=0, evening_enabled=0`) — shundayligicha
   qoldiring.
3. **Bot lokal polling ishlamaydi** — productionda faol webhook bor, himoya bloklaydi.
   Bot o'zgarishlari faqat deploy'dan keyin ko'rinadi.
4. **Migratsiya** kerak bo'lsa: `down_revision` ni joriy head'ga ulang, `upgrade`
   VA `downgrade` ikkalasini yozing.
5. **Test ma'lumoti** `T-` prefiksi bilan yaratilsin va ish oxirida to'liq o'chirilsin.
6. **AuditLog tozalashda** faqat aniq id yoki tor vaqt oynasi bo'yicha filtrlang —
   ilgari keng filtr haqiqiy tarixiy yozuvlarni o'chirib yuborgan.

---

## 6. SINOV TALABLARI

Har bosqichdan keyin:
1. `.venv/Scripts/python.exe test.py` — 26/26 o'tishi shart (regressiya).
2. `cd web && npx tsc --noEmit` — toza.
3. Tuzatilgan har bug uchun **yangi tekshiruv** `test.py` ga qo'shilsin (masalan
   "absent yozuvi yaratildi", "yarim tundan keyin check-out ishladi").
4. Jonli API sinovi (xizmatlarni `schtasks` bilan qayta ishga tushirib).
5. Digest o'zgarsa — `dry_run=true` bilan matnni ko'rsating.

---

## 7. KUTILGAN NATIJA

- Har bosqich alohida commit (o'zbekcha xabar, nima va NEGA o'zgarganini tushuntiruvchi).
- Yakunda: qaysi buglar tuzatildi, qaysilari qoldi (va nega) — qisqa hisobot.
- `test.py` kengaytirilgan holda (yangi tekshiruvlar bilan).
