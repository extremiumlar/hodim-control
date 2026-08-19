# «Hodimlar tizimi» — AI agent uchun to'liq tizim xaritasi

> **Bu hujjat kimga:** loyihani birinchi marta ko'rayotgan AI agentga.
> **Maqsad:** agent tizimning HAR BIR bo'limini alohida tushunsin — nima uchun
> qurilgan, qanday ishlaydi, hozir qaysi holatda, qayerda bo'shliq bor — va
> shundan keyin **g'oyalar (idea)** bera olsin.
>
> **Agentga topshiriq (o'qib bo'lgach):** har bo'lim uchun alohida
> (1) hozirgi yechimning kuchli/zaif tomoni, (2) 2–3 aniq yaxshilash g'oyasi,
> (3) umuman yo'q bo'lgan, lekin shu biznesga foyda beradigan yangi g'oya.
> Umumiy «hammasi zo'r» xulosa kerak emas — bo'limma-bo'lim, aniq.

---

## 0. Bir jumlada: bu nima?

O'zbekistondagi qurilish/ko'chmas mulk kompaniyasi (**Nuriddin Building**) uchun
qurilgan **ichki xodimlar boshqaruv tizimi**: davomat (Face ID + GPS), ish
normalari, CRM'dan avtomatik statistika, ish haqi va jarima hisobi, xodim
murojaatlari, va butun boshqa AI qatlami (operator nazorati, bilim bazasi,
sotuv AI). Bir kompaniya uchun, ~18 xodim, jonli ishlayapti.

**Uchta interfeys, bitta backend:**

| Interfeys | Kim ishlatadi | Nima uchun |
|---|---|---|
| **Telegram bot** (aiogram) | hamma xodim | asosiy kundalik ish quroli — xabarnomalar, tugmalar, tez amallar |
| **Web sayt** (React+Vite) | rahbarlar + xodim kabineti | jadvallar, sozlamalar, tahlil, chuqur ish |
| **Mobil ilova** (React Native/Expo, Android APK) | xodimlar | Face ID davomat (kamera/GPS nativ), push |

Mobil ilova bo'limlarining KO'PCHILIGI aslida saytning `?embed=1` rejimidagi
WebView'i — **sayt deploy qilinsa ilovadagi bo'limlar ham yangilanadi**, APK
qayta tarqatish shart emas.

---

## 1. Texnik stek va topologiya

```
db/       SQLAlchemy modellar (2043 qator, ~70 jadval) + Alembic migratsiyalari (~75 ta)
api/      FastAPI backend — 41 router, 33 servis  ← TIZIMNING YURAGI
bot/      aiogram bot — 28 handler
web/      React 18 + TS + Vite + shadcn/ui + react-query — 22 rahbar sahifa + 12 xodim kabineti sahifasi
mobile/   Expo/React Native (lokal APK build, EAS'siz)
scheduler/ APScheduler (Docker/VPS rejimi uchun) — 30+ job
scripts/cron_tick.py  cPanel rejimi uchun — har daqiqada bir marta, scheduler mantiqini takrorlaydi
crm/      CRM-agnostik adapterlar: uysot.py (jonli), amocrm.py, onec.py (stub)
verifix/  ESKI Django tizimi — ARXIV, ishlamaydi (pastda alohida bo'lim)
```

**Production (hozir jonli):** cPanel shared hosting, `nuriddin-building.uz`,
PostgreSQL. Passenger + `a2wsgi` FastAPI'ni WSGI'ga o'raydi.
Bot **polling** rejimida alohida jarayon (webhook EMAS — pastda sabab).
Scheduler o'rniga **har daqiqalik cron** (`scripts/cron_tick.py`).

**⚠️ Eng muhim infratuzilma cheklovi:** Passenger'ga bu hostda **ATIGI 1 ta
ishchi jarayon** berilgan → bir vaqtda ATIGI 1 so'rov ishlanadi → FastAPI
async bo'lishining foydasi nol. Bitta sekin so'rov butun saytni qotiradi.
Shu sababli barcha og'ir cron ishlari **in-process** bajariladi (HTTP orqali
o'z-o'ziga so'rov yubormaydi). Batafsil: `SAYT_QOTISHI_TAHLIL.md`.

**Lokal dev:** SQLite (`app.db`), venv `.venv/Scripts/python`,
alembic `python -m alembic -c db/alembic.ini upgrade head` (loyiha ILDIZIDAN).

---

## 2. Rollar va ruxsat modeli — buni tushunmasdan hech narsa tushunilmaydi

Tizimda **ikkita mustaqil o'lchov** bor va ular ATAYLAB ajratilgan:

### 2.1. `Role` — ruxsat darajasi (5 ta, qattiq kodlangan)

| Rol | Kim | Qamrov |
|---|---|---|
| `employee` | oddiy xodim | faqat o'zi |
| `rop` | sotuv bo'limi boshlig'i | **faqat o'z jamoasi** (lavozim `managed_by_roles` orqali) |
| `hr` | HR | deyarli hamma xodim (global), lekin pul tasdiqlash cheklangan |
| `boss` | Boshliq (kompaniya egasi) | hammasi |
| `dasturchi` | super-admin (IT) | hammasi + qulflarni ochish + yozuv tahrirlash |

### 2.2. `Position` — lavozim (bazadan sozlanadi, cheksiz)

`positions` jadvali. Har lavozimda **3 ta JSON maydon** — butun tizim shulardan
o'qiydi:

- **`metrics`** — `["suhbat","tashrif","oddiy_video","dumaloq_video"]` — bu
  lavozimda qaysi ko'rsatkich kuzatiladi. Normalar, KPI, statistika, soatlik
  reja — hammasi shundan.
- **`menu_flags`** — `{"tasks":true,"norm":true,"kpi":true,"payroll":true,...}` —
  botda va kabinetda qaysi tugma ko'rinadi.
- **`managed_by_roles`** — `["rop"]` yoki `["hr"]` — bu lavozimga kim norma/vazifa
  bera oladi.

**⚠️ Nozik joy (yaqinda tuzatilgan, commit `14b57d3`):** `metrics = []`
(ataylab bo'sh) va `metrics = None` (sozlanmagan) — **UCH XIL holat**:
`None` → eski standart `suhbat+tashrif`; `[]` → hech narsa kuzatilmaydi;
to'ldirilgan → o'sha. Ilgari ikkalasi bir xil ko'rilardi va Bugalter/Kassir/
Yurist «Suhbatlar soni» normasini ko'rar edi.

### 2.3. Shaxsiy bayroqlar (`User` dagi ustunlar — roldan mustaqil)

Egasining «ma'lum bir odamlarga bersin» talabidan tug'ilgan naqsh — yangi rol
YARATILMAYDI, aniq huquq bitta ustun bilan beriladi:

- `can_edit_attendance` — davomat vaqtini qo'lda tuzatish (beruvchi: faqat
  Dasturchi; o'z yozuvini o'zi tuzata olmaydi)
- `skip_location_check` — GPS'siz check-in (mobilograf, kuryer uchun; **Face ID
  baribir tekshiriladi**)
- `can_edit_fine_policy` — jarima qoidasini o'zgartirish (beruvchi: Dasturchi
  yoki Boshliq)
- `hot_lead_enabled` — issiq lid taqsimotida qatnashadimi
- `is_seat` — «o'rin» (Telegram bog'lanishi qayta-egallanadigan lavozim)

**G'oya berish uchun savol:** bu «bayroq» naqshi 5 tagacha yetdi — qachon u
RBAC (ruxsatlar jadvali) ga aylantirilishi kerak? Yoki shundayligicha yaxshimi?

---

## 3. BO'LIMMA-BO'LIM

Har bo'lim uchun bir xil struktura: **Maqsad → Ma'lumot modeli → Oqim →
Kod → Hozirgi holat → Ochiq muammo/g'oya nuqtasi**.

---

### 3.1. VERIFIX — eski tizim (ARXIV, ishlamaydi)

**Nima edi:** `verifix/` — alohida **Django + Next.js** tizimi, o'z bazasi
(`db.sqlite3`) bilan. Ilgari `/verifix` URL ostida davomat uchun ishlatilgan.
Ichida: `accounts`, `attendance`, `audit`, `leave`, `notifications`, `payroll`,
`reports`, `tasks` ilovalari.

**Nima bo'ldi (2026-07-14, egasining buyrug'i bilan):** TO'LIQ INTEGRATSIYA —
bitta backend, bitta baza, bitta auth. Ma'lumot ko'chirildi
(`scripts/migrate_verifix.py`, idempotent): 3 ofis, 3 yuz deskriptori,
4 davomat yozuvi.

**Hozirgi holat:**
- `/verifix` → **302 redirect** → `/check-in`
- `/admin` → **302 redirect** → `/attendance`
- Django (8002) va Next (3000) serverlari ishga tushirilmaydi
- Papka **arxiv** sifatida repoda qoladi (123 manba fayli), deploy qilinmaydi
  (`.dockerignore`da)

**⚠️ TUZOQ:** `/admin` yo'li **BAND** — `web/vite.config.ts` dagi
`verifixRedirect()` middleware uni React Router ko'rishidan OLDIN, HTTP 302
bilan `/attendance`ga tashlaydi. Shuning uchun Dasturchi paneli `/dasturchi`
yo'lida (`/admin` da EMAS). Yangi web route qo'shishdan oldin shu funksiyani
tekshirish shart.

**Nega hali ham qimmatli:** `verifix/backend/leave/` — **tayyor ta'til moduli**
(model, approve/finish, check-in bloklash, to'lovli/to'lovsiz payroll, testlar).
Arizalar moduli aynan shundan andoza olgan. `verifix/backend/attendance/
services.py:77-93` — ta'tildagi xodimning check-in qilishini bloklash mantiqi.

**G'oya nuqtasi:** arxivdan yana nima olish mumkin? Yoki butunlay o'chirilsinmi
(repo hajmi, chalkashlik)?

---

### 3.2. DAVOMAT (kelib-ketish) — tizimning eng murakkab bo'limi

**Maqsad:** xodim ishga kelganini/ketganini soxtalashtirib bo'lmaydigan qilib
qayd etish, kechikishni aniq o'lchash (chunki kechikish → jarima → pul).

#### Ma'lumot modeli
- `attendance` — `UNIQUE(user_id, date)`, holat: `present | late | absent |
  weekend | excused`, `late_minutes`, check-in/out vaqti (naive-UTC saqlanadi,
  Toshkent bo'yicha hisoblanadi)
- `office_locations` — ofis nuqtalari (lat/lon/radius, faol/nofaol)
- `users.face_descriptor` — face-api.js 128-o'lchamli deskriptor (JSON matn)
- `attendance_reminders`, `attendance_digest_config`, `face_reregistration_requests`

#### Check-in oqimi (3 qatlam)
1. **Face ID** — brauzerda `@vladmandic/face-api` deskriptor hisoblaydi,
   server faqat masofani solishtiradi (`similarity = 1 − evklid ≥ 0.5`)
2. **Tiriklik (liveness)** — pastda alohida
3. **GPS** — eng yaqin FAOL ofis radiusi (haversine).
   `skip_location_check` bayrog'i bo'lsa o'tkazib yuboriladi.

#### ⛔ Tiriklik (liveness) — muhim texnik saboq

**HARAKATGA ASOSLANGAN TIRIKLIK ISHLAMAYDI — qaytarilmasin.**
Ikki urinish, ikkisi ham jonli muvaffaqiyatsiz:
1. Xom piksel oynasi (0.5..25px) → **real xodimlar o'tolmadi** (qo'lda ushlangan
   telefon 150ms da 25px dan oshadi)
2. Yuz o'lchamiga nisbatan, yuqori chegarasiz → **rasm o'tib ketdi**

**Sabab printsipial:** o'rtacha landmark siljishi tirik yuz bilan qimirlayotgan
rasmni AJRATIB BERMAYDI — ikkalasi ham qattiq jism siljishi.

**Ishlaydigan yechim** (`web/src/lib/face.ts::captureLiveFace`): **noqattiq
deformatsiya** — ko'z pirpiratish (EAR tushishi) YOKI og'iz ochish (MAR oshishi).
**Uch qatlam himoya, birini olib tashlamang:** (1) burilishga moslash
(`tiltFactor` — busiz rasmni orqaga egib «ko'z yumildi» qilish mumkin),
(2) xom piksel chegarasi (normalizatsiya shovqinni kuchaytirmasin),
(3) poza izchilligi (rasmni sinov O'RTASIDA egish 38% → 0.6%).

O'lchangan natija (sintetik 3D proyeksiya usuli bilan):
**real xodim 0.03% rad, rasm 0.34% qabul.**
UX: passiv kutish — «kameraga qarab turing», 7s dan keyin yumshoq eslatma, 18s limit.
**Qolgan cheklov:** pirpiratayotgan VIDEO qayta o'ynatilsa o'tadi.

#### Kechikish hisobi
Ish jadvalidan (`work_schedule`) olinadi, `ATTENDANCE_GRACE_MINUTES=5`.
Sababli kun (`ExcusedDay approved`) bo'lsa holat `late` EMAS, `excused`.

#### Qamrov
`ATTENDANCE_TRACKED_ROLES` — **Boshliqdan tashqari HAMMA** (employee + hr + rop +
dasturchi). Yagona konstanta (`api/services/attendance.py`) — dashboard,
late-stats, digest, work_schedule hammasi shundan (aks holda web panel bilan
guruh digesti turli son ko'rsatardi).

#### Digest (guruhga avtomatik)
- **09:30 ertalabki** — kim keldi / kechikdi / hali kelmadi / sababli
- **22:00 kechki** — kun yakuni: ish vaqti, kechikish, «Ketdim» bosmaganlar,
  erta kelgan/ketganlar
- Vaqt **bazadan** (`attendance_digest_config`), bot `/davomat_vaqt` bilan
  o'zgartiriladi. Dam olish kunida yuborilmaydi.

#### Interfeyslar
- **Web rahbar** `/attendance` — 4 tab (Bugun / Jadval / Hisobot / Sozlamalar),
  oylik matritsa (kun×xodim), kechikish statistikasi, leaflet ofis xaritasi
- **Web/mobil xodim** `/check-in` — yuz ro'yxati + GPS+Face modal
- **Bot** — «✅ Keldim/Ketdim» (URL tugma), «🕐 Davomat statistikasi»

#### ⚠️ Regressiya sabog'i (egasi topgan)
Matritsa katagiga `isInert` qo'shilganda `weekend` ham kirib ketgan va
**dam olish kunini tuzatish butunlay imkonsiz** bo'lib qolgan edi (60 katak
o'lik). **Qoida:** katakni «bosilmaydigan» qilishdan oldin — u orqali
qilinadigan AMAL boshqa yo'l bilan mavjudmi, deb tekshirish shart.

**G'oya nuqtasi:** video-replay hujumi; ta'tildagi xodimning check-in qilishi
(hali bloklanmagan); NFC/Wi-Fi asosidagi qo'shimcha signal; ofisdan chiqib
ketishni aniqlash.

---

### 3.3. LAVOZIMLAR (Position)

**Maqsad:** rolni (ruxsat) ish funksiyasidan (nima o'lchanadi) ajratish.

**Web:** `Positions.tsx` — lavozim yaratish, `metrics` / `menu_flags` /
`managed_by_roles` ni checkbox bilan sozlash.

**Jonli holat (2026-08-14):** Operator, Manager — `["suhbat","tashrif"]`;
Mobilogrof — `["oddiy_video","dumaloq_video"]`; Bugalter/Kassir/Yurist/Prorab
yordamchisi — `[]` (ataylab bo'sh). 4 xodim umuman lavozimsiz.

**Ochiq savol (egasiga berilgan, javob kelmagan):** `Prorab` va
`Mashenist kranchik` lavozimlarida hali `suhbat/tashrif` metrikalari turibdi —
bu ish turiga mos emas.

**G'oya nuqtasi:** qurilish lavozimlari (prorab, kranchi, usta) uchun QANDAY
metrika mantiqiy? Hozir tizim faqat sotuv metrikalarini biladi.

---

### 3.4. NORMALAR

**Maqsad:** har xodimga kunlik reja (necha suhbat, necha tashrif, necha video).

**Model:** `norms` — `user_id + metric_type + value + effective_from`.
**TARIXIY:** hech qachon UPDATE qilinmaydi, faqat yangi qator qo'shiladi →
o'tgan oy hisobi buzilmaydi. **Yumshoq o'chirish** (`deleted_at`) —
Dasturchi rejimi uchun; barcha o'qish `deleted_at IS NULL` bilan filtrlanadi.

**Lavozimga to'liq moslashgan zanjir** (2026-08-14 da jonli tekshirilgan —
hech qayerda `suhbat/tashrif` hardcode EMAS):
```
Position.metrics → norms.py::metrics_for(user)
                 → stats.py::today_metric_rows()  (qiymat + norma)
                 → web/src/pages/Norms.tsx        (dinamik ustunlar)
                 → bot /norma_ozgartir            (faqat lavozim metrikalarini taklif qiladi)
                 → web/src/pages/me/{Norm,Stats,Kpi}.tsx
```

**Kim belgilaydi:** `can_manage_norms` — HR/Boshliq/Dasturchi global; ROP faqat
`managed_by_roles` ga `"rop"` yozilgan lavozimlar + «yetim» xodimlar.

**Hozirgi jonli holat:** normasi bor — 4 xodim (Albina 3, Hayot 2,
Firuzabonu 2, Shahnoza 2). Normasi yo'q — Mobilogrof, Mashenist, Prorab.
**Mobilograf video normasi mexanizmi TAYYOR — faqat qiymat kiritilmagan.**

**G'oya nuqtasi:** normani QO'LDA belgilash o'rniga avtomatik (avto-reja
allaqachon bor — 3.9 ga qarang, lekin faqat qo'ng'iroqqa); norma tarixi
grafigi; norma bajarilishiga qarab avtomatik tuzatish.

---

### 3.5. LIDLAR va CRM (Uysot) integratsiyasi

**Bu bo'lim tizimning eng nozik va eng ko'p qon to'kilgan qismi.**

#### Manba: Uysot CRM (tashqi SaaS)
`crm/uysot.py` — Open API (`X-Open-Api-Token`). CRM-agnostik interfeys
(`crm/base.py`) — kelajakda amoCRM/1C/o'z CRM'ga almashtirish uchun.

#### Nima o'qiladi
| Ma'lumot | Jadval | Qanday |
|---|---|---|
| Lid bosqichlari kesimi | `lead_stage_daily` | `/lead/filter` butun bazani sahifalab skanerlaydi (~184 sahifa ≈ 6.5 daq) |
| Qo'ng'iroqlar | `operator_calls_daily`, `hourly_actual` | call-history (kiruvchi/chiquvchi, `missed`, `duration`) |
| Bosqich o'tishlari | `lead_events`, `crm_lead_state` | diff-skaner + webhook |
| Yangi lidlar | `hot_lead` | 3.8 ga qarang |

#### ⚠️ Uysot Open API haqida qattiq o'rganilgan faktlar
- `/lead/filter` natijani **ID (yaratilish) bo'yicha** tartiblaydi,
  `updatedTimestamp` bo'yicha EMAS → «eski yozuvga yetganda to'xta» ISHLAMAYDI,
  butun bazani skanerlash shart
- `size` max **50**
- `start/finish` = unix-**sekund**, **YARATILGAN** sana bo'yicha (ISO sana 400 beradi)
- Rate limit: **daqiqasiga 60 so'rov**
- Ro'yxat javobida kontakt ism/telefon **YO'Q** — `GET /lead/{id}` alohida kerak
- call-history maydonlari: `contacted` = 1200/1200 **false** (o'lik),
  `qualityScore` = 0 (o'lik), `hangupCause` doim "ANSWER" (o'lik).
  **Ishlaydigan signal faqat `missed` va `duration`.**

#### 429 bo'roni — hal qilingan
Uysot'ga **3 ta jarayon** chiqadi (cron_tick + Passenger + bot) × 50 = 150 so'rov/daq,
Uysot limiti 60 → 429 bo'ronlari **strukturaviy**, tasodif emas.
Yechim: markaziy `_SharedRateBudget` (`CRM_UYSOT_MAX_REQUESTS_PER_MINUTE`),
`_limited_request` (429 cooldown, Retry-After), og'ir skanlar
`SCAN_THROTTLE_SECONDS=2.0`. **Yangi Uysot so'rovi FAQAT shu orqali qo'shilsin.**

#### 🔴 «Tashrif» ta'rifi — ikki marta noto'g'ri bo'lgan, endi qat'iy
**QOIDA (2026-08-13, egasining qarori):** tashrif = **FAQAT bosqich o'tishi**
(`stage_change`). `first_seen` (skaner lidni birinchi marta ko'rgani)
SANALMAYDI — chunki operator mijoz bilan gaplashib bo'lgach lidni CRM'ga
kiritadi va DARHOL «Tashrif» qo'yadi. Oqibati bo'lgan edi: bir kunda
**149 soxta tashrif**.
Yagona mezon: `api/services/lead_diff.py::_is_visit_event()`.
O'tmishni tuzatish: `POST /daily-results/recalc-visits`.
Kredit **dual**: yopgan odamga ham, olib kelgan odamga ham.

#### Webhook
Uysot HMAC imzo yuboradi (`x-webhook-signature`), lekin **algoritm
hujjatlashtirilmagan** → vaqtinchalik mezon: ishonchli IP
(`CRM_WEBHOOK_TRUSTED_IPS`) + imzo sarlavhasi MAVJUD bo'lsa qabul.
**⚠️ Imzo TEKSHIRILMAYDI** — o'sha IP'ni bilgan har kim soxta lid yubora oladi.
Uysot'dan spetsifikatsiya so'ralishi kerak.

#### 🔴 HOZIRGI ENG KATTA TO'SIQ
**Uysot Open API tokeni 2026-07-31 dan o'lik.** Tarixiy eksport ham, yangi
ma'lumot ham to'xtagan. Bu butun voronka/target loyihasining old sharti.
(2026-08-04 da bir marta 27 soat jimgina o'lik qolgan edi — shundan
«Tizim qo'riqchisi» tug'ildi, 3.20 ga qarang.)

#### Mapping bo'shliqlari
CRM'da lidi bor, lekin tizimga bog'lanmagan operatorlar bor
(`crm_visit_external_id` hech bir userda yo'q) → ular statistikada
«Boshqa operatorlar» bo'lib chiqadi. Ikki xil ID kerak:
`crm_external_id` (email — qo'ng'iroq uchun) va `crm_visit_external_id`
(responsibleById — lid uchun).

**G'oya nuqtasi:** token o'lganda tizim qanday ishlashi kerak (degraded rejim)?
Uysot o'rniga o'z CRM (3.22)?

---

### 3.6. STATISTIKA

Uch darajali: **shaxsiy → guruh digesti → web tahlil**.

#### 3.6.1. Shaxsiy (bot)
- «📈 Statistikam» — bugun/hafta/oy, `week_totals` (dushanbadan)
- «🧲 Lidlar statistikasi» — oy→kun→operator drill-down.
  Format: `📞 Gaplashilgan lidlar N (kiruvchi X, chiquvchi Y)` +
  `🧲 Ishlangan lidlar M | Tashrif` + bosqichlar ro'yxati

**⚠️ Muhim tuzatilgan chalkashlik:** «Gaplashilgan lidlar» = **QO'NG'IROQLAR**,
lidlar EMAS. Bir lidga bir necha qo'ng'iroq bo'ladi. Ilgari lidning
`updatedTimestamp`i sanalardi va Firuza 130 gaplashgan bo'lsa 75 ko'rsatilardi.

#### 3.6.2. Guruh digestlari (avtomatik, Telegram guruhga)
| Digest | Vaqt | Manba | Fayl |
|---|---|---|---|
| Kunlik | 19:10 (sozlanadi, `group_post_config`) | snapshot jadvallar (CRM'ga murojaat YO'Q) | `daily_digest.py` |
| Haftalik | Yakshanba 20:00 | shu 7 kun vs oldingi 7 kun, % o'zgarish | `weekly_digest.py` |
| Oylik | Oy oxiri 20:30 | + bonus | `monthly_digest.py` |
| Davomat ertalab/kechqurun | 09:30 / 22:00 | attendance | `attendance_digest.py` |
| Kecha yakuni tuzatishi | 09:00 | ≥10% VA ≥5 qo'ng'iroq oshgan bo'lsagina | `stats.py` |

Kunlik digest tarkibi: operator kesimida 📞 qo'ng'iroq (kechaga delta) ·
🧲 lid · 🏠 tashrif · ✅ vazifa · ❄️ sovutilgan issiq lid · sababli/faoliyatsizlar
· **AI xulosa** (yoqiq bo'lsa, oxirida).

**AI xulosa faktlar bilan:** `_dip_episodes` (KOD, AI emas) soatlik kumulyativ
reja-vs-fakt'dan pasayish epizodlarini topadi (gap≥3 VA <75%), AI'dan aniq
vaqt bilan «14:00–16:00 orqada qoldi, keyin to'g'irladi» deyish TALAB qilinadi,
taxmin taqiqlangan.

**⚠️ Tick semantikasi:** `>=` («vaqt o'tgan va bugun yuborilmagan»), `==` EMAS —
scheduler bir daqiqa kechiksa ham digest tushadi. `*_last_posted` qo'riqchi.

#### 3.6.3. Web «Statistika» sahifasi (faqat rahbar)
`GET /stats/web/overview` (30 kun seriya + 7 kun sabablari),
`/stats/web/operator-summary` (today/week/month, oldingi teng davrga %).
Sof SVG grafik. Digest yig'uvchilari qayta ishlatilgan → **raqamlar digest
bilan mos**.

**G'oya nuqtasi:** hozir statistika «nima bo'ldi» ni aytadi; «nima bo'ladi»
(prognoz) va «nima qilish kerak» (tavsiya) yo'q.

---

### 3.7. HISOBOT (Excel eksport)

`api/services/export.py`:
- **`build_report_xlsx`** — «Hisobot» varag'i (xodim×davr: suhbat, tashrif,
  qo'ng'iroq, gaplashgan h:mm, lid) + **«Kunlik»** varaq (kun×xodim, faoliyatsiz
  qatorlar yo'q)
- **`build_payroll_xlsx`** — bitta kitobda «Xulosa» + **HAR XODIM UCHUN ALOHIDA
  VARAQ**. `_safe_sheet_name` ism+`#user_id` bilan Excel 31-belgi cheklovidan
  himoyalaydi.

Kirish: bot «📥 Hisobot (Excel)», web Payroll sahifasidagi «Excel» tugmasi.
ROP faqat o'z jamoasini eksport qiladi.

**Ma'lum kamchilik:** `wb.save()` `to_thread`siz chaqiriladi → katta eksport
yagona Passenger ishchisini bloklaydi.

**G'oya nuqtasi:** PDF payslip? Avtomatik oylik hisobot pochtaga? Google Sheets
sinxronizatsiya?

---

### 3.8. ISSIQ LID (speed-to-lead)

**Maqsad:** yangi lid tushganda operator DARHOL qo'ng'iroq qilsin — javob
tezligi o'lchansin.

#### Oqim (hozirgi, 2026-08-06 dan)
1. Har 2 daqiqada tick → CRM'dan yangi lidlar (6h oyna + watermark)
2. **Operatorga shaxsiy DM** (guruhga YOZILMAYDI). CRM'da mas'ul yo'q bo'lsa
   bot O'ZI taqsimlaydi (`_pick_operator`: bugun eng kam lid olgan, ishdan
   ketmagan, `hot_lead_enabled=true` xodim)
3. **Eslatmalar 3/5/7/9-daqiqada** — boshliq ohangida, SENLAB, jarima bilan
4. **Sovish** — HR panelidan sozlanadigan `hot_lead_cool_minutes` (boshlang'ich
   10) o'tsa: guruhga **«❄️ ISSIQ LID SOVUTILDI»** + mas'ul ismi + jarima summasi
   (`hot_lead_fine`)
5. Tuzatilsa (`fine_amount=None`) — **tuzatuvchi xabar guruhga BORMAYDI**
   (egasi: «bardoq bo'lmasin»)

**«Qabul» mezoni = CRM call-history'dagi HAQIQIY qo'ng'iroq**, Telegram tugmasi
EMAS. Tugma 2026-07-22 da olib tashlangan.

#### ⚠️ Ikki jonli tuzoq (ikkalasi ham qonli tajriba)
- **MOI_ZVONKI manbasi:** lid operator qo'ng'irog'idan KEYIN avto-yaraladi →
  qo'ng'iroq `created_ts`dan OLDIN bo'ladi → soxta eskalatsiya
- **`PRE_CREATION_GRACE_SECONDS` 10 daqiqadan 2 SOATGA oshirildi:** operator
  mijoz bilan TO'LIQ gaplashib bo'lgach lidni kiritadi → tizim uni
  «qo'ng'iroq qilmadi» deb hisoblab, gaplashib turgan odamga ogohlantirish
  yuborardi

**⚠️ Yoqishdan oldin `baseline` top-up SHART** — aks holda 6h oynadagi eski
lidlar birdan DM bo'lib ketadi.

**Uch metrika:** yaratilish→aniqlash · aniqlash→qabul · yaratilish→birinchi
qo'ng'iroq (`first_call_sec`).

---

### 3.9. OPERATOR AI TIZIMI — 7 bosqichli, jonli ishlayapti

Bu alohida katta quyi-tizim. To'rt ustun:

#### (1) Avto-reja — qo'lda norma o'rniga datadan target
- `hourly_actual` (user×date×hour kompozit sifat) ←— CRM call-history
- `operator_profile` (user×hour **median** baseline, 30 kun, faqat `date<today`)
- `hourly_target` = `0.7×shaxsiy + 0.3×jamoa benchmark`, **+10% stretch**;
  ish oynasiga moslashadi, tushlik (13:00) o'tkaziladi
- Joblar: `ai_snapshot` (15 daq), `ai_build_targets` (06:00),
  `ai_compute_profiles` (yakshanba 05:00)

#### (2) Kompozit kuzatuv — miqdor + sifat
Miqdor = qo'ng'iroq soni; Sifat = javob-darajasi (`missed=False`/jami) +
o'rtacha suhbat sekundi; Anomaliya = qisqa qo'ng'iroq (javob berilgan +
`duration < 15s`); Konversiya = `LeadStageDaily`dan.

#### (3) «Nima uchun» halqasi — anti-aldash mexanizmi ⭐
Bu tizimning eng original qismi:

```
watch_rules.py (KOD, AI emas) → trigger?
   ↓ ha (done < plan×0.7 VA farq ≥3, yoki anomaliya)
AI nudge (Gemini/Claude) + «✍️ sababini yozib yuboring» → pending yozuv
   ↓ operator ERKIN MATN yozadi
ai_coach.classify_reason_text  → AI tasnif (no_answer/no_base/tech/meeting/other)
   ↓
_verify_claim (hukmni KOD chiqaradi, AI EMAS):
   • no_base («lid tugadi») → CRM'da ochiq lidlarni sanaydi (count_open_leads)
   • no_answer → terilgan raqamlar vs reja (≥70% tasdiq, <50% zid)
   • tech/meeting/other → hukmsiz (None)
   ↓
verified=False → operatorga fakt ko'rsatiladi + BOSS/ROP'ga ogohlantirish DM
verified=None → ROP'ga «✅ Tasdiqlash / ❌ Rad etish» tugmalari bilan DM
```

**Jonli anti-aldash isboti:** Shahnoza (28/45, chindan orqada) «Qayerdan olaman
nomer qomadi eee» deb yozdi → AI `no_base` tasnifi → CRM skani **23 ta ochiq
lid** topib da'voni RAD etdi → boss/rop'ga ogohlantirish ketdi. **Butun zanjir
jonli ishladi.**

**Adolat filtrlari (ko'r-ko'rona ayblamaslik):** dam kuni / ish oynasi tashqarisi
/ tushlik / birinchi soat grace / `ExcusedDay approved` / `OperatorBusyPeriod`
→ skip. Shovqin: kuniga max 3 nudge, 2h cooldown.

#### (3b) Harakatsizlik nazorati (`idle_watch.py`) — alohida signal
Soatlik reja-vs-fakt EMAS, xom «so'nggi qo'ng'iroqdan beri necha daqiqa» —
tezroq (5-10 daq) va **OMMAVIY** (guruhga) eskalatsiya. Faqat «suhbat»
metrikali lavozimlar. Operatorda ochiq lid yo'q bo'lsa signal bermaydi.
Yaqinda shaxsiy nudge ketgan bo'lsa ustiga ommaviy YO'Q (pile-on bo'lmasin).

#### (4) Issiq lid — 3.8 da alohida

#### AI provayder
`OPERATOR_AI_PROVIDER` = `gemini` (httpx REST, SDK'siz, `thinkingBudget: 0`
SHART) yoki `anthropic`. **AI xato/o'chiq bo'lsa deterministik fallback matn** —
tizim hech qachon jim qolmaydi. Har chaqiruv `ai_message_log`ga yoziladi
(audit + xotira + cooldown hisobi).

**Ohang (system promptda qattiq):** (1) holatni xotirjam ayt (2) «keling birga
tuzataylik» (3) oxirida oqibat. «atigi/qoniqarsiz» kabi so'zlar taqiqlangan.
**Maxfiylik:** AI'ga faqat agregat — mijoz PII/audio hech qachon bermaydi.

#### Ikki bosqichli gate
`AI_ENABLED` (matn generatsiyasi) VA `AI_NUDGE_ENABLED` (haqiqiy push) —
**ikkalasi kerak**. Ustiga runtime toggle `ai_config` (Boshliq `/ai_sozlama`
bilan boshqaradi).

**G'oya nuqtasi:** hozir AI faqat sotuv operatorlarini kuzatadi. Boshqa
lavozimlar uchun qanday signal bo'lishi mumkin? AI ohangi ishlayaptimi
(xodimlar reaksiyasi)?

---

### 3.10. OYLIK (payroll) + JARIMA + QO'SHIMCHA ISH

**Eng katta biznes-modul.** Reja: `OYLIK_JARIMA_REJASI.md` (63 KB, 8 bosqich).
Barcha bosqichlar (0–7) + Dasturchi interfeysi BAJARILGAN.

#### Jadvallar (8 ta)
`salary_rates` · `kpi_rates` · `overtime_profiles` · `fine_policies` ·
`overtime_entries` · `payroll_periods` · `payslips` · `payslip_items` ·
`payroll_adjustments`

#### Ikki takrorlanuvchi arxitektura naqshi (butun tizimda ishlatiladi)
1. **3 darajali qamrov:** `global → position → user`; qidiruv `user > position >
   global`. (`FinePolicy`, `KpiRate`)
2. **Tarixiylik:** `effective_from`, hech qachon UPDATE emas, faqat yangi qator.
   → o'tgan oy payslip'i o'zgarmaydi. (`Norm`, `SalaryRate`, `KpiRate`)

#### HR qarorlari (og'zaki berilgan, kodda mustahkamlangan — **taklif emas, qaror**)
1. Kechikish limiti **daqiqada** (kun bo'yicha emas). Limit tugagach har
   kechikkan kunga qat'iy summa (`fine_mode='per_day'`)
2. Jarima **to'g'ridan-to'g'ri oylikdan** (`fine_applies_to='net_salary'`).
   ⚠️ O'zbekiston mehnat qonunchiligida ushlab qolish cheklangan bo'lishi
   mumkin — HR/yurist tekshiruvi tavsiya etilgan, lekin qaror qat'iy
3. Oylik jarima **cap majburiy**, qiymati HR web'dan
4. Kelmagan kun — kunlik ulush EMAS, alohida qat'iy summa (`absent_mode='fixed'`)
5. Overtime koeffitsienti — tizimda default YO'Q, HR majburiy kiritadi
6. Overtime norma soati — ish jadvalidan avtomatik
7. **ROP payrollni ko'radi, lekin faqat o'z jamoasi**, sozlash huquqisiz →
   `PAYROLL_VIEW_ROLES` vs `PAYROLL_MANAGE_ROLES`
8. Avans — HR qo'lda, `PayrollAdjustment(minus)`
9. Oylik hisob — keyingi oyning 1-kuni ertalab (06:00)

⭐ **Nozik qoida:** «limitni TO'LDIRGAN kunning o'zi hali bepul, undan KEYINGI
kechikkan kun birinchi jarimali» — test yozishda 2 marta chalkashtirilgan.

#### KPI/bonus
Ilgari stavkalar `bonus.py` da KONSTANTA edi (`PLACEHOLDER_RATE_PER_CONVERSATION
= 2000`) → HR o'zgartira olmasdi, tarixiy emasdi, mobilograf KPI'si doim 0 edi.
Endi `kpi_rates` jadvali (3 darajali + tarixiy). **Jadval BO'SH holda
chiqarilgan** — qiymatlarni HR saytdan kiritadi. Stavka topilmasa bonus 0
(xavfsiz tomonga og'ish).

#### Avtomatik joblar
`monthly_payroll` (keyingi oy 1-kuni 06:00) · `payroll_late_warnings` (kunlik
07:30 — limitga yaqinlashganga ogohlantirish) · `payroll_overtime_auto_detect`
(kunlik 01:00)

#### 🔴 HOZIRGI OCHIQ MUAMMOLAR (`OYLIK_MUAMMOLAR_REJASI.md`, 2026-08-15)
Egasi 4 ta muammo aytgan, tahlil yozilgan, **tuzatish hali qilinmagan**:

1. **KPI stavkani sozlamalar panelidan oylikka o'tkazish** —
   (a) qismi bajarilgan, lekin: KPI puli faqat BOT orqali hisoblanadi; stavka
   «kelajakdan» kuchga kiradi; bonus faqat `employee` roliga hisoblanadi
2. **Qo'shimcha ishni avtomat hisoblab, vaqtini qo'shib-ayirib berish** —
   mantiq yozilgan, 3 ta to'siq bor
3. **Oylik belgilash panelida sayt qotib qoladi** — ildiz: 1 Passenger ishchi +
   sahifa ikkita og'ir so'rov yuboradi
4. **Ish haqi noto'g'ri hisoblanyapti** — ⭐ **eng katta ildiz sabab:
   KELAJAKDAGI kunlar «kelmagan» deb sanaladi**. Oy tugamagan bo'lsa,
   bugundan keyingi kunlar hisobga umuman kirmasligi kerak.
   Ikkinchi: stavka bugungi sana bilan kiritiladi → prorata buziladi.
   ⚠️ Egasining «1-avgustgacha hamma ma'lumot reset bo'lsin» talabi —
   hujjatda **XAVFLI AMAL** deb belgilangan.

#### Ma'lum cheklovlar
- Tungi (yarim tundan oshgan) smenalar uchun overtime avto-aniqlash ishlamaydi
- `fine_applies_to='bonus_first'` item-darajasidagi breakdown qurilmagan

**G'oya nuqtasi:** bu bo'limda eng ko'p g'oya kerak — kelajak kunlar muammosi,
prorata, «tayyor» vs «tasdiqlangan» oqimi, xodimga tushunarli payslip.

---

### 3.11. ISH KUNDALIGI (work log)

**Maqsad (egasining talabi, 2026-08-13):** har xodim kun davomida bajargan
ishlarini yozib borsin.

**Model:** `work_log_entries` — `user_id + date + text (3..2000) + source`.
`DailyResult`dan farqi: u kunda BITTA qator va RAQAM, bu esa kun ichida
**BIR NECHTA erkin MATNLI yozuv**, har biri vaqt tamg'asi bilan
(→ oy oxirida «to'qib chiqarilgan» hisobotning oldini oladi).

**Qulf qoidasi:** faqat egasi va faqat `date == bugun (Toshkent)` bo'lganda
tahrirlaydi/o'chiradi. **`editable` bayrog'ini SERVER hisoblaydi** (mijoz
yuborgan sanaga ishonilmaydi). O'chirish yumshoq.

**⭐ Ataylab qilingan chegara: PUL MANTIG'IGA ULANMAYDI** — yozmaganlik jarima
keltirmaydi, faqat rahbar hisobotida (coverage) ko'rinadi.

**Interfeys:** bot «📝 Ish kundaligi» (faqat qo'shish); tahrirlash/o'chirish
FAQAT sayt/ilova kabinetida (`/me/work-log`) — ataylab.
Kechki eslatma (jonli tasdiq: 2026-08-13 da 8 xodimga yetgan).

**Holat: TO'LIQ TAYYOR VA JONLI (deploy qilingan).**

**G'oya nuqtasi:** kundalikdan AI oylik xulosa (Bosqich 7, qilinmagan);
kundalik + KPI bog'liqligi; rahbar uchun coverage ustuni.

---

### 3.12. E'TIROZ va SHIKOYAT (Appeal)

**Maqsad:** xodim qarorga qarshi chiqa olsin yoki muammo aytsin.

#### Ikki tur, farqi printsipial
| | E'tiroz (`objection`) | Shikoyat (`complaint`) |
|---|---|---|
| Nima | ANIQ qarorga qarshi | erkin mavzu |
| Mavzu | `attendance` (davomat kuni), `payroll` (payslip) | `work_env`, `team`, `other` |
| Kimga | **Har doim HR**, anonim BO'LMAYDI | HR yoki Boshliq (tanlanadi) |
| Anonimlik | yo'q | **bor** |
| Qaror | `accepted` / `rejected` | `resolved` / `rejected` |

#### ⭐⭐ ENG MUHIM TAMOYIL: **APPEAL HECH NARSANI HISOBLAMAYDI**
`accepted` bo'lganda tizim davomat yoki pulni **AVTOMATIK O'ZGARTIRMAYDI**.
API faqat `next_step` matnini qaytaradi («Sababli kunlar» / «Payroll tuzatish»).
Tuzatish MAVJUD mexanizmlar orqali qo'lda: `ExcusedDay` (+`recompute_attendance`)
yoki `PayrollAdjustment`.

**Nega:** aks holda ikkita mustaqil hisob yo'li paydo bo'lardi va payslip raqami
qaysi yo'ldan kelganini hech kim ayta olmasdi.

#### Maxfiylik (backendda, frontendda emas)
- HR faqat `recipient_role == 'hr'` bo'lganini ko'radi; begonaga **404**
  (403 EMAS — 403 «bor, lekin ko'rolmaysan» degani, bu ham ma'lumot)
- Anonimlikda `user_id` bazada HAR DOIM saqlanadi (suiiste'mol tekshiruvi),
  lekin API javobida ism yashiriladi. Muallif o'zini ko'radi
- Boshliq va Dasturchi hammasini ko'radi

**Ilova:** Telegram `file_id` (fayl serverda saqlanmaydi).
**SLA:** eslatma + eskalatsiya izlari (`sla_reminded_at`, `escalated_at`) —
cron ikki jarayonda ishlashi mumkinligi uchun.

**Holat: TO'LIQ TAYYOR VA JONLI.**

---

### 3.13. ARIZALAR (EmployeeRequest)

**Maqsad:** ta'til, avans, ma'lumotnoma, ishdan bo'shash — rasmiy so'rov.

#### ⭐ Markaziy g'oya: ariza TURI emas, **OQIBATI** muhim
| Guruh | Turlar | Tasdiqlanganda nima yoziladi |
|---|---|---|
| **A — davomatga** | `vacation`, `unpaid`, `sick` | `ExcusedDay` qatorlari (oraliqning har ish kuni) |
| **B — pulga** | `advance` | `PayrollAdjustment(advance, pending)` |
| **C — hech narsa** | `certificate`, `schedule_change`, `resignation`, `other` | HR qo'lda bajaradi |

**Shuning uchun `Appeal` jadvaliga QO'SHILMAGAN** — Appeal ataylab hech narsani
hisoblamaydi, ariza esa yozishi SHART. Ikki xil mavjudot.

#### Qaytarish mexanizmi
`source_request_id` — **teskari FK** uch jadvalda (`ExcusedDay`,
`PayrollAdjustment`, ...). Bekor qilinganda aynan shu qatorlar topib
qaytariladi. JSON ro'yxat saqlashdan farqi: «bu sababli kun qayerdan paydo
bo'lgan?» degan teskari savolga ham javob beradi, yetim qator qolmaydi.

**Qarorlar:** ta'til faqat ish kunlariga (`api/services/workdays.py`
kalkulyatori); mavjud sababli kunga tegilmaydi; bekor qilishda `ExcusedDay`
**`rejected`** qilinadi (o'chirilmaydi); pending avans o'chiriladi lekin
**approved TEGILMAYDI**; avansda davr qulfi tekshiriladi.

**Status zanjiri:** `pending → manager_ok (ROP) → hr_ok → approved`
(chegaradan oshgan summa Boshliqqa boradi). `cancelled` (xodim qaytarib oldi) vs
`revoked` (tasdiqlangach bekor qilindi).

**Bot:** «📮 Murojaatlarim» hubi — ariza + e'tiroz + shikoyat birga.
Ta'tilda JONLI kalkulyator (sana→kun→balans).
**Web:** `Requests.tsx` (rahbar, materializatsiya natijasi paneli) +
`me/Requests.tsx` (xodim, 8 turli grid).

**Holat: DEPLOY QILINGAN** (`44d3b9b`, Bosqich 0–5).

#### ⚠️ Qabul qilinmagan takliflar (sabab bilan — takrorlanmasin)
- **`SELECT FOR UPDATE` RAD** — SQLite'da sintaksis xatosi, lokal dev butunlay
  yiqilardi. O'rniga: idempotent holat o'tishi + UNIQUE + bitta tranzaksiya
- **To'liq JSONB payload QISMAN rad** — qidiriladigan `start_date/end_date/
  amount` alohida ustun bo'lib qoladi (JSON'da indeks yo'q)
- «Ishdagi ta'tilchi» — `TaskModel` EMAS (vazifa statistikasini buzardi),
  inline tugma + `interrupted_at`

**Qolgan bo'shliq:** global bayramlar jadvali YO'Q (egasining qaroriga ko'ra
qoldirilgan) → kalkulyator faqat dam kunlarini biladi, bayramlarni bilmaydi.

---

### 3.14. SABABLI KUNLAR (ExcusedDay)

`excused_days` — `UNIQUE(user_id, date)` (2026-08-13 da qo'shildi: ilgari
cheklov faqat KODDA edi, ariza moduli oraliqni birvarakayiga yozgani uchun
poyga holatida dublikat paydo bo'lardi).

**Ikki yo'l:**
1. **Xodim so'raydi** → HR/Boshliq tasdiqlaydi (`pending → approved/rejected`)
2. **HR nomidan belgilaydi** (`_record_excused_day_for_user`) → **darhol
   `approved`** (kirituvchi allaqachon vakolatli, qayta tasdiq shart emas).
   Rollar: `hr, boss, dasturchi` — **ROP YO'Q**. Faqat `role=='employee'` ga

**`is_paid`** — to'lovli/to'lovsiz. `monthly` stavkada to'lovsiz kun ayiriladi;
`daily/hourly` da tegilmaydi.

---

### 3.15. VAZIFALAR (Tasks)

`tasks` — `pending | done | overdue | cancelled`.
Bot: «📤 Vazifa berish» (rahbar) / «📋 Vazifalarim» (xodim, «Bajardim» tugmasi) /
«📋 Vazifalar nazorati». Kunlik digestda ✅ ustuni bo'lib chiqadi.

**G'oya nuqtasi:** eng kam ishlangan modul — takrorlanuvchi vazifalar,
shablonlar, muddat eslatmasi, vazifa↔KPI bog'liqligi yo'q.

---

### 3.16. MOBILOGRAF VIDEOLAR

**Maqsad:** mobilograf guruhga video tashlaydi → rahbar **reaksiya** qo'yib
tasdiqlaydi → norma/KPI hisobiga kiradi.

`mobilograf_videos` — `video_type`: `oddiy` (F.video) yoki `dumaloq`
(F.video_note) — ikkalasi ALOHIDA norma/hisob. `status`: pending/confirmed/
rejected. `source`: `telegram_reaction` yoki `manual` (guruh ishlamay qolganda
HR qo'lda kiritadi).

Metrikalar: `["oddiy_video","dumaloq_video"]` — `Position.metrics` orqali.
Hisob: `stats.py::_confirmed_videos_count`.

**Holat:** mexanizm to'liq ishlaydi, **norma qiymati kiritilmagan** (Sherzod
Mobilogrof: 0 ta norma). KPI stavkasi ham 0 edi — endi `kpi_rates` dan.

---

### 3.17. TABRIK VIDEOLARI (Celebration) — eng yangi modul

**Maqsad (egasining talabi, 2026-08-14):** CRM'da lid **«Tashrif»** yoki
**«Shartnoma qilindi»** bosqichiga o'tganda umumiy guruhga interaktiv video
borsin.

**Model:** `celebration_media` (video/GIF, kind: visit/contract) ·
`celebration_posts` · `celebration_claps` (👏 tugmasi).

**Video serverda SAQLANMAYDI** — Telegram `file_id` naqshi (`send_file_id`).
**Ikki yuklash yo'li, bir servis:** bot «🎬 Tabrik videolari» (tayyor `file_id`)
va sayt `/celebration` (fayl → Telegram → `file_id`; multipart uchun `apiUpload`,
chunki `apiFetch` doim JSON Content-Type qo'yadi).

**Nozik joylar:**
- `first_seen` tabrik BERMAYDI (3.5 dagi tashrif qoidasi bilan bir xil)
- Takrorlanishning yagona to'sig'i: `celebration_posts.lead_event_id` **UNIQUE**
  (voqeani webhook ham, diff-skaner ham yozadi)
- 6 soatdan eski voqea e'lon qilinmaydi
- **Video yo'q ekan guruhga hech narsa yuborilmaydi (ataylab)**

**Holat: DEPLOY QILINGAN.** Server `.env` da
`CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS=8060,8788`.
**QOLGAN YAGONA QADAM:** egasi/HR ikkita video yuklashi.

---

### 3.18. ANKETA → BILIM BAZASI → PLAYBOOK → SOTUV AI (4 bosqichli zanjir)

Bu alohida quyi-tizim: **xodimlarning boshidagi bilimni chiqarib olib,
strukturaga solib, AI'ga beradigan konveyer.**

#### (1) Anketa
Dasturchi Word (.docx) faylni botga tashlaydi → `api/services/docx_parse.py`
(**STDLIB zipfile+re, `python-docx` ATAYLAB yo'q** — cPanel deploy oddiy
`git pull` bo'lib qolsin) savollarni ajratadi → `anketa_templates`.

Boshlash: kimga (👤 har kimga alohida / standart / hamma / rol / lavozim) →
qaysi to'plam → tasdiq → `/anketa/tick` (har daqiqa) boshlaydi → bot savol
beradi, xodim javob yozadi, keyingi savol.

**Holat BAZADA** (`anketa_assignments.current_q`), **FSM'da EMAS** — webhook/
restartga chidamli.

**⚠️ Bot matn-handler tartibi juda nozik:** `anketa.answer_router` →
`ai_watch.reason_text_router` (ENG OXIRGI). Yangi erkin-matn handler qo'shilsa
tartibni saqlash SHART.

#### (2) Bilim bazasi (`knowledge_entries`)
Anketa javoblari ingest qilinadi (JAVOB darajasida idempotent —
`anketa_answers.ingested_at`). Holatlar:
`draft → unverified/unknown/conflict → verified`.

**AI FAKT QO'SHMAYDI** — 3 urinishdan keyin deterministik fallback.
5 xodimda bir xil savol bo'lsa AI birlashtiradi yoki `conflict` belgilaydi.
Sana-sezgir `verified` yozuv 30 kunda eskirsa kunlik tick eslatadi.

**Og'ir AI ishlovi cron tick'da bo'lib bajariladi** (~3 chaqiruv/tick) —
cPanel gateway ~180s limiti sababli.

#### (3) Sotuv playbook (`playbook_builds`, `playbook_entries`)
Bosqichli qurish: `profiles → objections → synthesis`.
Top sotuvchi **deterministik** aniqlanadi (60 kunlik `daily_results`
tashrif→suhbat nisbati), e'tirozlar `shortfall_reason.raw_text` dan (!),
sintez faqat `verified` yozuvlarga tayanadi.
`kind`: `etiroz | uslub | qoida` (vaziyat→texnika→iboralar).
Qayta qurishda `unverified` o'chadi, `verified` qoladi.

#### (4) Sotuv AI (`/sales-ai/ask`)
System promptga **FAQAT `verified`** knowledge + playbook TO'LIQ joylanadi
(**RAG yo'q** — baza kichik). Javob berolmagan savol `knowledge_entries`ga
`unknown` bo'lib tushadi → Boss mavjud review oqimida to'ldiradi
(**o'z-o'zini to'ldiruvchi halqa**).

Bot: «🤖 Sotuv AI» FSM rejimi (sotuv metrikali xodimlar + rahbarlar).
**Mijozga to'g'ridan-to'g'ri rejim ATAYLAB yo'q.**

#### ASL MAQSAD (egasi aytgan)
Anketa javoblari **TASHQI mijoz-chatbotiga data** — hodimlar tizimi yig'ib-
tozalab beruvchi. Eksport: `GET /knowledge/dataset?key=...` (faqat `verified`).

#### AI markazi
`bot/handlers/ai_center.py` + `api/routers/ai_center.py` — to'rttasi bitta
dashboardga yig'ilgan, «keyingi eng mantiqiy qadam» (`recommendation`)
hisoblanadi.

**G'oya nuqtasi:** bu zanjir juda original, lekin `unknown` halqasi qanchalik
ishlayapti? Playbook amalda ishlatilyaptimi? Mijoz-chatbot ulanganmi?

---

### 3.19. SOZLAMALAR — qayerda nima sozlanadi

**Bu savol tez-tez chalkashtiriladi. To'rt xil joy bor:**

| Qayerda | Nima | Kim o'zgartiradi |
|---|---|---|
| **`.env` (server)** | AI provayder/kalit, gate bayroqlari (`AI_ENABLED`, `AI_NUDGE_ENABLED`, `HOT_LEAD_ENABLED`, `HOURLY_PLAN_ENABLED`), CRM token va pipe-status ID'lari, chegaralar, FCM | faqat dasturchi (deploy) |
| **DB konfiguratsiya jadvallari** | `ai_config` (AI toggle'lari) · `group_post_config` (digest vaqti) · `attendance_digest_config` · `monitored_groups` (qaysi guruh nima uchun) · `request_policies` | Boshliq/Dasturchi bot yoki web orqali |
| **Web «Sozlamalar» panellari** | `PayrollSettings.tsx` (jarima qoidasi, KPI stavka, overtime, **🔥 issiq lid bloki**) · `Positions.tsx` (lavozim) · `Offices.tsx` (ofis nuqtalari) · `Norms.tsx` | HR / Boshliq |
| **Foydalanuvchi bayroqlari** | `can_edit_attendance`, `skip_location_check`, `can_edit_fine_policy`, `hot_lead_enabled` | Dasturchi (ba'zisi Boshliq) |

**⚠️ Tuzoq:** server `.env` repodagi defaultdan USTUN. `api/config.py` va
`.env.example` ni o'zgartirish YETMAYDI.
**⚠️ Tuzoq:** foydalanuvchi kompyuterida global OS env'da `AI_PROVIDER=ollama`
bor edi va pydantic-settings'da OS env `.env` dan USTUN → shu sabab
`OPERATOR_` prefiksli alias ishlatiladi.

**G'oya nuqtasi:** sozlamalar 4 joyga sochilgan. Yagona «Sozlamalar» sahifasi
kerakmi? Qaysilari `.env`dan bazaga ko'chirilishi kerak?

---

### 3.20. AUDIT, DASTURCHI REJIMI, TIZIM QO'RIQCHISI

#### Audit jurnali
`audit_logs` — `actor_id`, `target_user_id`, `action`, `before/after` (JSON).
Barcha pul amallari, norma o'zgarishi, davomat tuzatishi, override —
hammasi yoziladi. Web: `AuditLogs.tsx`. Bot: «🧾 Audit jurnali».

#### Dasturchi rejimi (super-admin) — `/dasturchi` yo'lida
`api/routers/admin_override.py` + `AdminOverride.tsx`. 5 tab:
1. **Yozuvlar** — 11 jadval uchun generik tahrirlash/o'chirish/tiklash
   (`ENTITY_REGISTRY`, PATCH oq ro'yxati bilan)
2. **Normalar** — cheklovsiz amal
3. **Payroll** — qulf ochish / majburan hisoblash / davrni bekor qilish
   (nomini qayta terib tasdiqlash bilan)
4. **Tizim** — davomat qayta hisoblash, force-role
5. **Override tarixi**

Bot: `/norm_set`, `/norm_del`, `/att_fix`, `/unlock`, `/undo`.

**⭐ Arxitektura ko'prigi:** `admin_override` JWT talab qiladi, bot esa faqat
X-Bot-Secret bilan ishlaydi → `POST /auth/bot-token` (bot-secret bilan
himoyalangan, FAQAT `role='dasturchi'` ga JWT beradi). Mantiq TAKRORLANMAGAN,
faqat autentifikatsiya ko'prigi.

**Yumshoq o'chirish FAQAT `Norm` + `SalaryRate` + `KpiRate` ga** (ongli qaror,
tor qamrov).

#### Tizim qo'riqchisi (`system_health.py`)
**Sabab:** 2026-08-04 da Uysot tokeni bekor qilinib tizim **27 soat jimgina
ko'r** qoldi — yangi lid xabari bormadi, statistika muzladi. Xato faqat
`logs/cron.log`da edi, tasodifan topildi.

Uch mustaqil tekshiruv:
- **`crm`** — polling va webhook'ning ENG YANGISI 2 soatdan ortiq jim bo'lsa
- **`backup`** — eng yangi `pg_*.sql.gz` 26 soatdan eski bo'lsa
- **`attendance`** — ish kunida 11:00 dan keyin NOL check-in bo'lsa
  (jonli ma'lumot: barqaror 13 check-in → nol = haqiqiy nosozlik)

**Manzil:** FAQAT `dasturchi` rolidagi foydalanuvchiga shaxsiy DM (texnik
xabar, sotuv guruhiga kerak emas). Dasturchi topilmasa hech kimga yuborilmaydi.
Shovqin: `CRM_HEALTH_REALERT_HOURS=6`, tiklanganda «🟢» bir marta.

**Ustiga tashqi «tirikman» kaliti:** ichki qo'riqchi cron ICHIDA yashaydi, cron
o'lsa u ham o'ladi → `cron_tick.py` har sikl oxirida `logs/cron_heartbeat`
yozadi → `/health` uni `cron_age_seconds` sifatida ochadi → **GitHub Actions**
har 30 daqiqada tekshiradi (`.github/workflows/watchdog.yml`).

**Kunlik avtomatik zaxira:** `deploy/cpanel/backup_db.sh`, crontab `30 3 * * *`,
pg_dump+gzip, 14 kun, atomik yozish.

---

### 3.21. PUSH BILDIRISHNOMALAR

**Yo'l qarori: FCM HTTP v1, Expo Push relay'i EMAS** (Expo `projectId` talab
qiladi, bizda build butunlay lokal; ustiga bildirishnoma matnida oylik/bonus
SUMMASI bo'ladi).

**7 toifa:** `late_warning · tasks · decisions · plan_reminders · approvals ·
sales_signals · digests`. Standart ROLGA bog'liq.
`plan_reminders` va `digests` ATAYLAB o'chiq (birinchisi kuniga bir necha marta,
ikkinchisi push'da o'qilmaydi).

**⚠️ ENG MUHIM TUZOQ — xabar yo'qolishi:** `should_skip_telegram`ning BIRINCHI
sharti `sent_push > 0` bo'lishi SHART. Ilgari faqat «qurilma bor va toifa
yoqiq» tekshirilardi → FCM sozlanmagan bo'lsa push ham ketmasdi, Telegram ham
o'tkazib yuborilardi → **xabar BUTUNLAY yo'qolardi**.

**Tinch soatlar:** 22:00–08:00 (ovozsiz, to'xtatilmaydi).
**Login kodi** toifa sozlamalari va tinch soatlarni ATAYLAB chetlab o'tadi.

**Holat:** Firebase ulangan (`planning-with-ai-a29c2`), server access token
olmoqda. **Jonli telefonda haqiqiy push hali sinalmagan.**
**iOS uchun nativ push YO'Q** (PWA ishlatiladi) — Web Push alohida ish.

---

### 3.22. MOBIL ILOVA va XODIM KABINETI

#### Xodim kabineti (web `/me/*`)
**Muammo edi:** xodim uchun web faqat `/check-in` edi. Audit ko'rsatdiki sabab
UI'da emas — **JWT bilan kirgan xodim uchun API qatlami YO'Q edi** (xodim
ma'lumotlari `verify_bot_secret` + `telegram_id` orqali, **99 joyda**).

**Yechim naqshi (buzilmasin):** **bitta mantiq — ikki yupqa adapter.**
Etaloni `api/routers/payroll.py::_late_status_for_user`: bot endpointi shaxsni
`telegram_id`dan yechadi, web `Depends(get_current_user)` dan oladi, ikkisi ham
BIR XIL yordamchiga boradi.

Botdagi 9 funksiyaning 8 tasi ko'chirildi (Sotuv AI'siz): ish jadvali, oylik,
normam, vazifalarim, bugungi rejam, statistikam, oylik KPI'm, lidlar
statistikasi, sababli kun. Ustiga: kundalik, murojaatlar, arizalar.

#### Mobil ilova
- Expo SDK 57, expo-router, **lokal APK build** (EAS/Expo hisobi ATAYLAB yo'q)
- Kirish: **deep-link + bir martalik token** (`/auth/app-login/start|confirm|poll`)
  + 4 xonali juftlik kodi
- **Face ID yo'li: WebView** (server-side embedding RAD ETILDI — model
  almashtirilsa saqlangan barcha `face_descriptor` yaroqsiz bo'lardi va HAMMA
  xodim yuzini qayta ro'yxatdan o'tkazardi)
- Yuz modellari uchinchi tomon CDN'idan **o'z serverimizga** ko'chirilgan
  (`web/public/models/`, 7 fayl ~7MB). `.gitattributes`da `*-shard[0-9] binary`
  — CRLF konvertatsiyasi modelni buzsa Face ID hammada ishlamay qoladi

**⭐ Eng muhim:** bo'limlar web'dan kelgani uchun **sayt deploy qilinsa
ilovadagi bo'limlar darhol yangilanadi — APK qayta tarqatish SHART EMAS.**

**⛔ APK saytdan tarqatilmaydi** (2026-08-14) — disk kvotasi atigi 1 GB.
Tarqatish qo'lda (Telegram/USB).

**⚠️ Ko'rinish shartlarining UCH NUSXASI:** `mobile/lib/sections.ts` +
`web/src/lib/employeeNav.ts` + `bot/keyboards.py::main_menu`.
Biri o'zgarsa uchalasi ham. **To'g'ri yechim — `GET /me/sections`** (qilinmagan).

**Samsung Auto Blocker:** One UI 6.1+ do'kondan tashqari HAR QANDAY APK'ni
to'sadi, hatto adb orqali ham. Xodimlarga tarqatishda majburiy qadam.

---

### 3.23. TELEGRAM LOGIN XAVFSIZLIGI

Audit 3 zaiflik topdi, uchalasi yopildi:
1. **Hash replay** — `used_telegram_login_hashes`; hash insert+commit BIRINCHI
   (user qidirishdan OLDIN)
2. **Rate-limit (DoS)** — DB-asosli sliding-window; `/auth/telegram-login`
   (15/900s), `/auth/dev-login` (20/3600s). `X-Forwarded-For` production'da
   TO'G'RI uzatilishi SHART
3. **Invite muddati** — `User.invite_expires_at`, `invite_token_ttl_days=7`

**Sayt kirishida 4 xonali kod MOBIL ILOVAGA push bilan boradi**
(`code_delivery: screen|push`). Zaxira: qurilma topilmasa saytda ochiladi.

---

### 3.24. GURUHLAR (monitored_groups)

`monitored_groups` — qaysi Telegram guruh nima uchun:
`mobilograf` / `main` (bir vaqtda faqat BITTA faol — yangisi eskisini
o'chiradi) / `stats` (bir nechtasi bo'lishi mumkin).
Faqat Dasturchi o'zgartiradi.

---

## 4. Reja bor, kod YO'Q (agentga alohida qiziq bo'lishi mumkin)

### 4.1. VORONKA va TESKARI TARGET tizimi ⭐
**Egasining topshirig'i (2026-08-15, eng yangi):** «oyiga 10 uy sotish»
maqsadidan **TESKARI** hisoblab har bosqichga target qo'yish — nechta tashrif
kerak, nechta suhbat, nechta lid, qancha auditoriya va rasxot.

**Hujjat:** `VORONKA_TARGET_REJASI.html` (repo ildizida, hali commit qilinmagan).

**Voronkaning PASTKI yarmi ALLAQACHON o'lchanadi:** `LeadEvent`,
`lead_diff.daily_operator_breakdown` (tashrif + shartnoma), pipe-status ID'lari,
`OperatorCallsDaily` + `HourlyActual`, `Norm` tizimi, guruh digesti.

**YETISHMAYDI:** konversiya foizi hisoblanmaydi · kogorta yo'q · lid manbai
faqat `HotLead.source` da · **reklama xarajati hech qayerda yo'q** ·
auditoriya/qamrov yo'q · «oylik maqsad» obyekti yo'q · teskari kalkulyator yo'q.

**Uch tamoyil:**
1. **AVVAL O'LCHASH, keyin rejalashtirish** — kalkulyator birinchi qilinsa,
   o'ylab topilgan konversiyalarga qurilgan soxta reja chiqadi
2. **VAQT SILJISHI:** «shu oy lidi ÷ shu oy shartnomasi» NOTO'G'RI — kogorta kerak
3. **TA'RIFLAR kod yozishdan OLDIN kelishilsin** (suhbat nima? sotuv nima?
   1 shartnoma = 1 uymi?)

**Egadan kutilayotgan javob:** «sotuv» ta'rifi, 1 shartnoma = 1 uymi,
«suhbat» ta'rifi, maqsadni kim qo'yadi.
**To'siq:** Uysot tokeni o'lik.

### 4.2. O'Z CRM'ini qurish
Uysot o'rniga (sekin, xizmati yomon). 1-bosqich (o'rganish) tugagan —
Uysot kabinetiga jonli kirib, fetch/XHR hook bilan REAL so'rovlar yozib olingan.
Hujjat: `D:\Project\crm\UYSOT_CRM_TAHLIL.md` + `CRM_YOL_XARITASI.md` (9 bosqich,
~5–7 oy). Tamoyil: **pul eng oxirida**; Uysot litsenziyasi 6-bosqich
tasdiqlanmaguncha saqlanadi (sug'urta).

### 4.3. Sayt qotishini ildizidan tugatish
`SAYT_QOTISHI_TAHLIL.md` — 5 bosqichli reja. Bosqich 1–4 qisman bajarilgan
(ko'p tick in-process'ga ko'chirilgan). **Ochiq savol:** serverda root bormi?
Bo'lsa Passenger'ni butunlay chetlab o'tish (doimiy uvicorn + ProxyPass)
muammoni ildizi bilan yopadi.

---

## 5. Loyihaning ARXITEKTURA TAMOYILLARI (takrorlanuvchi naqshlar)

Agent yangi g'oya berishda bularni buzmasligi kerak:

1. **Bitta mantiq — ikki yupqa adapter.** Bot (telegram_id + X-Bot-Secret) va
   web (JWT + `get_current_user`) BIR XIL yordamchiga boradi. Mantiq
   takrorlanmaydi.
2. **Tarixiylik:** stavka/norma hech qachon UPDATE qilinmaydi, faqat yangi qator
   `effective_from` bilan → o'tmish buzilmaydi.
3. **3 darajali qamrov:** `global → position → user`, qidiruv teskari.
4. **Yumshoq o'chirish** (`deleted_at`) — pul/norma tegishli jadvallarda.
   Barcha o'qish `deleted_at IS NULL` bilan filtrlansin.
5. **Appeal hech narsani hisoblamaydi; Request hisoblaydi.** Ikkita hisob yo'li
   bo'lmasin.
6. **Sozlanmagan holat xavfsiz tomonga og'adi** — stavka yo'q → bonus 0;
   jarima qoidasi yo'q → jarima 0; video yo'q → tabrik yuborilmaydi.
7. **AI hukm chiqarmaydi — KOD chiqaradi.** AI faqat tasniflaydi va matn yozadi.
   Fakt tekshiruvi (`_verify_claim`) deterministik.
8. **AI o'chiq/xato bo'lsa deterministik fallback** — tizim jim qolmaydi.
9. **Ikki bosqichli gate:** env bayroq (`AI_ENABLED`) VA runtime toggle
   (`ai_config`) — ikkalasi kerak.
10. **Og'ir ish in-process, HTTP orqali EMAS** — Passenger'ning yagona
    ishchisi band bo'lmasin. Yangi tick qo'shsangiz shu naqshni takrorlang.
11. **Adolat filtrlari** — dam kuni / tushlik / ish oynasi tashqarisi /
    sababli kun / band davri → hech qanday ayblov yo'q.
12. **Faqat kerakda gapir** — cooldown, kunlik limit, `last_posted` qo'riqchi.

---

## 6. HOZIRGI OG'RIQLI NUQTALAR (ustuvorlik bo'yicha)

| # | Muammo | Ta'sir | Holat |
|---|---|---|---|
| 1 | **Uysot Open API tokeni o'lik (2026-07-31 dan)** | butun CRM statistikasi to'xtagan | hal qilinmagan, egasi tomonida |
| 2 | **Passenger konkurentlik = 1** | sayt soatiga ~20 daq qotadi | qisman yumshatilgan, ildiz ochiq |
| 3 | **Oylik hisobi noto'g'ri** — kelajakdagi kunlar «kelmagan» sanaladi | pul xatosi | tahlil bor, kod tegilmagan |
| 4 | KPI stavkasi faqat bot orqali hisoblanadi | HR panelida ko'rinmaydi | tahlil bor |
| 5 | Webhook imzosi tekshirilmaydi | IP'ni bilgan soxta lid yubora oladi | Uysot'dan spek kutilyapti |
| 6 | Disk kvotasi 1 GB | to'lib qolsa hammasi to'xtaydi | 537/1024 MB, kuzatilyapti |
| 7 | Ko'rinish shartlarining 3 nusxasi | biri o'zgarsa uchalasi | `GET /me/sections` qilinmagan |
| 8 | Global bayramlar jadvali yo'q | ta'til kalkulyatori noto'liq | egasi qoldirgan |
| 9 | Jonli push telefonda sinalmagan | push ishlashi noma'lum | egasi tekshirishi kerak |
| 10 | Tabrik videolari yuklanmagan | modul jim turadi | egasi yuklashi kerak |

---

## 7. AGENTGA: qaysi bo'limlarda g'oya eng kerak

Egasining o'zi eng ko'p vaqt sarflagan va eng ko'p muammo aytgan joylar:

1. **Oylik/payroll** — 4 ta ochiq muammo, pul bilan bog'liq, eng sezgir
2. **Voronka/target** — yangi katta loyiha, hali ta'riflar ham kelishilmagan
3. **Davomat** — texnik jihatdan pishgan, lekin video-replay va ta'tildagi
   xodim teshiklari bor
4. **Normalar** — qurilish lavozimlari uchun metrika umuman o'ylanmagan
5. **Operator AI** — faqat sotuv qo'ng'irog'iga qurilgan; boshqa ishlarga
   moslashtirish g'oyasi yo'q
6. **Vazifalar** — eng kam ishlangan modul
7. **Sozlamalar** — 4 joyga sochilgan

---

## 8. Foydali fayllar ro'yxati (agent so'rasa)

| Fayl | Nima |
|---|---|
| `OYLIK_JARIMA_REJASI.md` (63 KB) | oylik/jarima to'liq spetsifikatsiyasi, 8 bosqich |
| `OYLIK_MUAMMOLAR_REJASI.md` (30 KB) | **eng yangi** — 4 ta ochiq oylik muammosi |
| `ARIZALAR_REJASI.md` (32 KB) | arizalar moduli |
| `KUNDALIK_ETIROZ_REJASI.md` (36 KB) | kundalik + e'tiroz/shikoyat |
| `SAYT_QOTISHI_TAHLIL.md` (29 KB) | Passenger muammosi, 5 bosqichli reja |
| `MOBIL_ILOVA_REJASI.md` (25 KB) | mobil ilova + APK tarqatish tuzoqlari |
| `VORONKA_TARGET_REJASI.html` | teskari target tizimi (yangi) |
| `UYSOT_CRM_TAHLIL.md` | Uysot ichki API xaritasi |
| `XODIM_KABINETI_PROMPT.md` | kabinet migratsiyasi |
| `BOT_BUYRUQLARI.md` | bot slash-buyruqlari |
| `test.py` (320 KB!) | yagona test fayli, ~400 tekshiruv, `T-` prefiksli ma'lumot |

---

## 9. Muhim ogohlantirishlar (agent kod yozsa)

- ⛔ **CRM'dan (Uysot) ruxsatsiz HECH NARSA o'chirilmaydi va tahrirlanmaydi** —
  superuser seansi ochiq
- ⚠️ **Lokal testlar HAQIQIY xodimlarga Telegram xabar yuboradi** — lokal `.env`
  production bot tokeni va production guruhlariga ulangan.
  `api.notify.send_message` ni patch qilish SHART
- ⚠️ **Bir vaqtda bir necha Claude sessiyasi ishlaydi** — hech qachon
  `git add .` qilinmasin, faqat o'z fayllari
- ⚠️ **Migratsiya ikki dialektda sinalishi shart** (lokal SQLite, prod PostgreSQL)
  — `batch_alter_table` ishlating; sana parametri `str` bo'lmasin (PG 500 beradi)
- ⚠️ **crontab FAQAT fayl orqali** — `crontab -l | ... | crontab -` naqshi
  crontabni ikki marta BUTUNLAY o'chirib yuborgan
- ⚠️ **`pkill -f 'bot.main'` SSH'da ISHLATILMAYDI** — buyruqning o'zi shu
  naqshga tushib seansni uzadi

---

*Hujjat 2026-08-15 da tuzildi. Manba: jonli kod (`db/models.py` 2043 qator,
41 router, 33 servis), 33 ta xotira fayli, 11 ta reja hujjati, git tarixi.*
