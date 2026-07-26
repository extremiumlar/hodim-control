# DAVOMAT TIZIMI — BUGLARNI TUZATISH TOPSHIRIG'I

> **Kimga:** shu loyihada ishlaydigan dasturchi yoki AI agentga.
> **Qachon tuzilgan:** 2026-07-26, to'liq audit (backend + frontend/bot) natijasida.
> **Qanday ishlatiladi:** «BUG_FIX_PROMPT.md ni o'qib, N-bosqichni bajar» deng —
> boshqa hech narsa tushuntirish shart emas, hamma narsa shu yerda.
>
> ⚠️ **Kod yozishdan oldin 0-bo'limdagi 3 ta savolga javob oling.** Ular biznes
> qarori — noto'g'ri taxmin qilsangiz, ishning yarmi behuda ketadi.

---

## 0. AVVAL SO'RANG (kod yozishdan oldin)

### Savol A — Face ID xavfsizligi bilan nima qilamiz? ⚠️ ENG MUHIM

**Hozirgi holat (kod bilan isbotlangan):**
- `api/schemas.py` `MeCheckRequest`: `latitude`, `longitude`, `face_descriptor` (128 float),
  `liveness` (0..1) — **hammasi brauzer yuborgan JSON**. Server hech birini mustaqil
  tekshirmaydi.
- `web/src/lib/face.ts:139-144` tiriklik formulasi:
  ```
  liveness = 0.4 (baza) + 0.25 (≥3 freym) + 0.25 (aniqlik≥0.4) + 0.2 (harakat)
  ```
  → **harakat umuman bo'lmasa ham 0.9** chiqadi, chegara esa 0.5. Ya'ni qog'oz/ekrandagi
  foto bloklanmaydi.
- `api/routers/attendance.py` `register_face`: har kim istalgan payt, tasdiqsiz,
  liveness'siz, **audit yozuvisiz** o'z deskriptorini ixtiyoriy vektorga almashtira oladi.

**Amaliy oqibat:** xodim o'z JWT tokeni bilan uydan turib bitta `curl` buyrug'i bilan
check-in qila oladi:
```bash
curl -X POST https://<domen>/api/attendance/me/check-in \
  -H "Authorization: Bearer <o'z tokeni>" \
  -d '{"latitude":<ofis>,"longitude":<ofis>,"face_descriptor":[...],"liveness":1.0}'
```

**Variantlar:**

| # | Variant | Ish hajmi | Himoya darajasi |
|---|---|---|---|
| 1 | **Server tomonda tekshirish** — brauzer rasm yuboradi, deskriptor va tiriklik serverda hisoblanadi | Katta (Python face-recognition + CPU/xotira, cPanel'da og'ir) | Yuqori |
| 2 | **Yumshoq choralar** — qayta ro'yxatdan o'tish rahbar tasdig'iga + audit + ogohlantirish; GPS `accuracy` tekshiruvi; bir xil deskriptor takrorlanishini aniqlash; tiriklik formulasida harakatni MAJBURIY qilish | O'rta | O'rta (halol bo'lmagan xodimni qiyinlashtiradi, to'xtatmaydi) |
| 3 | **Xavfni qabul qilish** — jamoa kichik va ishonchli, hozircha qoldiriladi | Yo'q | Yo'q |

**→ Foydalanuvchi qaysi variantni tanlaydi?** Javobsiz 2-4 bosqichga o'tmang
(1-bosqich bundan mustaqil, uni boshlash mumkin).

### Savol B — Tungi smena kerakmi?
Hozir jadvalda `start < end` majburiy (`work_schedule.py`), yarim tunga o'tuvchi smena
(masalan 20:00–04:00) **printsipial qo'llab-quvvatlanmaydi**. Agar kerak bo'lsa —
jadval modeli va butun kechikish hisobi o'zgaradi (katta ish, alohida reja kerak).

### Savol C — Unutilgan "Ketdim" qanday yopilsin?
(a) ish oynasi tugashida avtomatik yopish · (b) rahbar qo'lda tahrirlaydi ·
(c) ikkalasi. Bu 2.2-bandning yechimini belgilaydi.

---

## 1. LOYIHA KONTEKSTI

### Stek va muhit
| Nima | Qiymat |
|---|---|
| Backend | FastAPI + SQLAlchemy (async) + Alembic, SQLite `app.db` |
| Frontend | Vite + React + TS + Tailwind + shadcn/ui + **react-query** |
| Bot | aiogram (`bot/`), scheduler (`scheduler/`), cPanel cron (`scripts/cron_tick.py`) |
| Python | **`.venv/Scripts/python.exe`** (tizim python'da paketlar YO'Q) |
| Alembic | `.venv/Scripts/python.exe -m alembic -c db/alembic.ini upgrade head` |
| Joriy head | `a1b2c3d4e5f6` |
| Xizmatlar | **FAQAT** `schtasks /run /tn "HodimlarTizimi_StartAll"` orqali (skriptni to'g'ridan chaqirsangiz jarayonlar sessiya bilan o'ladi) |
| Regressiya testi | `.venv/Scripts/python.exe test.py` → **26/26 o'tishi shart** |
| Frontend tekshiruv | `cd web && npx tsc --noEmit` |

### Baza holati (2026-07-26)
```
faol foydalanuvchilar: 8  (boss 1, dasturchi 1, hr 1, rop 1, employee 4)
davomat yozuvlari:     5  (hammasi status='late' — bu ham alomat, 1.3-bandga qarang)
yuz ro'yxatdan o'tgan: 4
faol ofislar:          3
ish jadvali sozlangan: atigi 1 foydalanuvchi (qolganlari defaultda)
```
⚠️ Bu **jonli ma'lumot** — sinov uchun emas. Har bosqichdan oldin zaxira oling.

### Davomat oqimi (qanday ishlaydi)
```
Xodim /check-in sahifasida:
  1. "Keldim" bosadi
  2. Brauzer GPS oladi (navigator.geolocation)
  3. Kamera ochiladi → face-api 5 freym → descriptor + liveness hisoblanadi
  4. POST /attendance/me/check-in {lat, lng, face_descriptor, liveness}
  5. Server: _validate_face (has_face + liveness≥0.5 + similarity≥0.5)
             _validate_location (eng yaqin faol ofis radiusi, haversine)
             kechikish = hozirgi vaqt − ish oynasi boshi − grace(5 daq)
  6. attendance jadvaliga yoziladi (uq: user_id + date)

Ish oynasi qoidasi (YAGONA manba — hourly_plan._effective_today):
  WorkScheduleOverride (aniq sana) > WorkScheduleWeekly (hafta kuni) >
  default: Du-Ju 09:00-18:00, Sha/Yak dam

Qamrov: ATTENDANCE_TRACKED_ROLES = Boshliqdan tashqari hamma
        (employee, hr, rop, dasturchi)

Guruh digesti: ertalab (09:30) + kechqurun (22:00), vaqti bazadan
               (attendance_digest_config), botda /davomat_vaqt bilan sozlanadi
```

### Fayl xaritasi
```
api/services/attendance.py          check-in/out, GPS, Face ID  ← eng ko'p bug shu yerda
api/services/attendance_digest.py   guruh digesti (collect_day + matn quruvchilar)
api/routers/attendance.py           barcha endpointlar
api/routers/work_schedule.py        ish jadvali CRUD
api/routers/hourly_plan.py          _effective_today — ish oynasi qoidasi MANBAI
api/timeutil.py                     TASHKENT_TZ, today_local, work_minutes
db/models.py                        Attendance, OfficeLocation, AttendanceDigestConfig,
                                    WorkScheduleWeekly/Override
web/src/pages/CheckIn.tsx           xodim UI (Keldim/Ketdim + yuz modali)
web/src/components/FaceCapture.tsx  kamera + freym olish
web/src/lib/face.ts                 face-api wrapper + liveness formulasi
web/src/pages/Attendance.tsx        rahbar paneli (dashboard + jadvallar)
web/src/pages/WorkSchedule.tsx      ish jadvali UI
web/src/lib/queries.ts              react-query hooklari (qk kalitlari shu yerda)
bot/handlers/attendance_stats.py    bot statistikasi + /davomat_vaqt
test.py                             regressiya testi (ildizda)
```

### Kod uslubi (mavjud naqshga rioya qiling)
- **Izohlar o'zbekcha**, faqat "nima uchun" ni tushuntiradi (kod nima qilishini emas).
- Yangi endpoint → mavjud router naqshi (`Depends(get_db)`, `verify_bot_secret` bot uchun,
  JWT + rol tekshiruvi web uchun).
- Frontend: react-query hooki `queries.ts` da, tur `lib/api/types.ts` da,
  endpoint `lib/api/endpoints.ts` da — uchtasi birga.
- **Pre-commit hook** `web/src` o'zgarsa frontend'ni avtomatik build qilib `webdist/`
  ni commitga qo'shadi — bu normal, aralashmang.

---

## 2. TUZATISH BOSQICHLARI

> Har bosqich = alohida commit. Bir commitga hammasini tiqmang.
> Har banddan keyin: **reproduktsiya → tuzatish → qabul mezoni tekshiruvi → test.py**.

---

## 🔴 BOSQICH 1 — Statistika yolg'on ko'rsatyapti

**Nega birinchi:** rahbar hozir noto'g'ri raqamlarga qarab qaror qabul qilyapti.
Bu bosqich Face ID qaroridan (Savol A) **mustaqil** — darhol boshlash mumkin.

### 1.1 — `absent` statusi hech qachon yozilmaydi

**Joy:** `api/services/attendance.py` `_apply_status()`
```python
def _apply_status(att: Attendance, is_working: bool) -> None:
    att.is_weekend = not is_working
    if not is_working:
        att.status = AttendanceStatus.weekend.value
    elif att.check_in_time is None:          # ← BU TARMOQQA HECH QACHON KIRILMAYDI
        att.status = AttendanceStatus.absent.value
    ...
```
`_apply_status` faqat `perform_check_in` (check_in_time allaqachon o'rnatilgan) va
`perform_check_out` (check_in majburiy) ichida chaqiriladi. Butun loyihada
`AttendanceStatus.absent` **faqat shu bitta qatorda** uchraydi (grep bilan tasdiqlangan).

**Reproduktsiya:**
```bash
# Bugun hech kim check-in qilmagan bo'lsin, keyin:
curl -H "Authorization: Bearer <boss>" "http://127.0.0.1:8000/attendance?status_filter=absent"
# → [] (bo'sh), holbuki 7 kishi kelmagan
```

**Tuzatish yo'nalishi:** kun oxirida (digest tick ichida yoki alohida job) o'sha kuni
ishlashi kerak bo'lgan, lekin check-in qilmagan xodimlarga `absent` yozuvi yaratish.
Tasdiqlangan sababli kunlar (`ExcusedDay` status='approved') **chiqarib tashlansin**.
Idempotent bo'lsin (ikki marta ishlasa dublikat yaratmasin — `uq_attendance_user_date` bor).

**Qabul mezoni:**
- [ ] Ish kuni tugagach kelmagan xodimga `status='absent'` yozuvi bor
- [ ] Sababli kunli xodimga `absent` yozilmaydi
- [ ] Ikki marta ishga tushirilsa dublikat yo'q
- [ ] `GET /attendance?status_filter=absent` natija qaytaradi

### 1.2 — Kelmagan xodim statistikada BUTUNLAY ko'rinmaydi ⚠️

**Joy:** `api/routers/attendance.py` `employee_summary()`
```python
.join(Attendance, Attendance.user_id == User.id)      # ← INNER JOIN
.where(Attendance.date >= since, User.role.in_(ATTENDANCE_TRACKED_ROLES))
```

**Nega jiddiy:** INNER JOIN tufayli davr ichida **birorta ham** yozuvi yo'q xodim
natijaga umuman tushmaydi. Ya'ni **bir oy ishga kelmagan xodim jadvalda yo'q** —
rahbar uni "muammosiz" deb o'ylaydi. Eng yomon xodim eng toza ko'rinadi.

**Reproduktsiya:** hech qachon check-in qilmagan xodim yarating → `/attendance/employee-summary`
da u yo'q.

**Tuzatish yo'nalishi:** `outerjoin` ga o'tkazing. ⚠️ **Tuzoq:** LEFT JOIN'dan keyin
`WHERE Attendance.date >= since` yozsangiz, u NULL qatorlarni kesib yana INNER'ga
aylantiradi — sana shartini **JOIN shartiga (ON)** ko'chiring:
```python
.outerjoin(Attendance, and_(Attendance.user_id == User.id, Attendance.date >= since))
.where(User.role.in_(ATTENDANCE_TRACKED_ROLES), User.is_active.is_(True))
```
Qo'shimcha qiymat: "kelmagan kunlar" ustunini ham qo'shing (1.1 bajarilgandan keyin
`absent` yozuvlarini sanash mumkin).

**Qabul mezoni:**
- [ ] Hech qachon kelmagan xodim jadvalda ko'rinadi (0 kun, 0 daqiqa bilan)
- [ ] Mavjud xodimlarning raqamlari **o'zgarmagan** (regressiya yo'q)
- [ ] Boshliq hamon ro'yxatda yo'q

### 1.3 — Kechikish grace'ni ayirib yozadi

**Joy:** `api/services/attendance.py`
```python
att.late_minutes = max(0, diff - grace) if diff > grace else 0
#                              ^^^^^^^ grace CHEGIRMA bo'lib ishlayapti
```

**Oqibat:** 09:00 boshlanishda 09:06 da kelgan xodimga `late_minutes = 1` yoziladi
(haqiqiy kechikish 6 daqiqa). Har kechikkan kun 5 daqiqaga kam ko'rsatiladi; oylik
statistikada bu sezilarli xato. Digest "+1 daq" deydi, xodim aslida 6 daqiqa kech kelgan.

**Tuzatish:** grace faqat **bo'sag'a** bo'lsin:
```python
att.late_minutes = diff if diff > grace else 0
```

**Qabul mezoni:**
- [ ] 09:03 (grace ichida) → `late_minutes = 0`
- [ ] 09:06 → `late_minutes = 6` (1 emas)
- [ ] Mavjud yozuvlar **o'zgarmaydi** (tarixni qayta yozmang — izohda buni yozing)

### 1.4 — Kechikish/erta ketishda yuqori chegara yo'q

**Joy:** `api/services/attendance.py` (kechikish) va erta ketish hisobi.

**Oqibat:** 17:59 da kelgan xodim "534 daqiqa kechikdi" (`absent` emas!); 09:05 da
ketgan "535 daqiqa erta ketdi". Bitta kun oylik jamni portlatadi.

**Tuzatish yo'nalishi:** mantiqiy chegara (masalan kechikish ish oynasi uzunligidan
oshmasin) yoki juda kech kelishni alohida belgilash. Tanlagan yechimingizni izohda
asoslang.

**Qabul mezoni:**
- [ ] Ish oynasi tugagandan keyin check-in qilingan holat oqilona qiymat beradi
- [ ] Oddiy kechikish (5-60 daq) hisoblari o'zgarmagan

---

## 🔴 BOSQICH 2 — Ma'lumot yo'qolishi va poyga holatlari

### 2.1 — Yarim tundan keyin "Ketdim" bosib bo'lmaydi

**Joy:** `api/services/attendance.py` `perform_check_out()`
```python
day = today_local()
att = await db.scalar(
    select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
)
if att is None or att.check_in_time is None:
    raise CheckError("Avval «Keldim» qilishingiz kerak.")
```

**Reproduktsiya:** xodim 20:00 da check-in qildi, 00:30 da "Ketdim" bosdi →
"Avval «Keldim» qilishingiz kerak" xatosi. Kechagi yozuv **abadiy**
`check_out_time=NULL`, `worked_minutes=0` bo'lib qoladi.

**Tuzatish yo'nalishi:** check-out avval bugungi ochiq yozuvni izlasin, topilmasa —
**kechagi ochiq yozuvni** (masalan 6 soatlik oyna bilan cheklab). Erta ketish/ishlangan
vaqt o'sha yozuvning o'z kuniga nisbatan hisoblansin.

**Qabul mezoni:**
- [ ] 23:00 check-in → 01:00 check-out ishlaydi, `worked_minutes ≈ 120`
- [ ] Yozuv kechagi sanada qoladi (bugungi kunga ko'chmasin)
- [ ] 2 kun oldingi ochiq yozuv **yopilmaydi** (oyna cheklovi)

### 2.2 — Unutilgan check-out uchun tuzatish yo'li yo'q

`worked_minutes` faqat "Ketdim" bosilganda hisoblanadi. Bosmagan kun 0 bo'lib qoladi
va `month_worked_hours` doimiy kam ko'rsatadi. Rahbar tahrirlay olmaydi — Dasturchi
faqat yozuvni **o'chira** oladi.

**Tuzatish:** Savol C javobiga qarab (avtomatik yopish / rahbar tahriri / ikkalasi).

**Qabul mezoni:** tanlangan variant ishlaydi va `test.py` da tekshiruv bor.

### 2.3 — Check-in poygasi → 500 xato

**Joy:** `api/services/attendance.py` — SELECT-then-INSERT, qulfsiz.

**Reproduktsiya:** ikkita parallel so'rov yuboring → ikkalasi ham `att=None` ko'radi,
ikkalasi INSERT qiladi → `uq_attendance_user_date` ikkinchisini rad etadi →
`IntegrityError` ushlanmagan → foydalanuvchiga **500**.

**Tuzatish:** `IntegrityError` ushlanib, tushunarli `CheckError` ("Siz bugun allaqachon
«Keldim» qilgansiz") ga aylantirilsin. Check-out'da constraint himoyasi yo'q — u yerda
ham parallel so'rov nazorati kerak.

**Qabul mezoni:**
- [ ] Parallel 2 ta check-in → biri 200, ikkinchisi **400** (500 emas)
- [ ] Bazada 1 ta yozuv

### 2.4 — Bekor qilingandan keyin ham check-in yuboriladi

**Joy:** `web/src/pages/CheckIn.tsx` + `web/src/components/FaceCapture.tsx`

**Reproduktsiya:** "Tahlil qilinmoqda..." paytida ✕ bosing → modal yopiladi, lekin
`capture()` async davom etadi; kamera to'xtaganda video oxirgi freymda muzlaydi, yuz
hali ham aniqlanadi → `onResult` chaqiriladi → closure ichidagi eski `showFace` guardni
o'tkazadi → **so'rov baribir ketadi**. Xodim "bekor qildim" deb o'ylaydi, davomat qayd
etilgan.

**Tuzatish:** `AbortController` yoki `cancelled` ref — modal yopilganda natija
e'tiborga olinmasin; `FaceCapture` unmount bo'lganda aniqlash sikli to'xtasin.

**Qabul mezoni:**
- [ ] Tahlil paytida bekor qilinsa **hech qanday so'rov ketmaydi**
- [ ] Kamera treklari to'xtaydi (resurs oqishi yo'q)

---

## 🟡 BOSQICH 3 — Mantiqiy xatolar

### 3.1 — Jadval o'zgartirilsa davomat qayta hisoblanmaydi
**Joy:** `api/routers/work_schedule.py` (weekly/override PUT) — recalc yo'q.
**Oqibat:** xodim 09:30 da keldi (`late=25`), rahbar startni 10:00 qildi → baza 25 da
qoladi, digest esa **joriy** jadvaldan hisoblab o'sha odamni "60 daq erta keldi" deb ham
ko'rsatadi — bir odam ayni vaqtda "kechikkan" ham, "erta kelgan" ham.
**Tuzatish:** jadval o'zgarganda o'sha sanadagi (**bugungi va kelajakdagi**) yozuvlarni
qayta hisoblash. **O'tgan kunlarga TEGMANG** (tarix). Muqobil: digest `early_in`ni ham
`Attendance`dan olsin (yagona manba).

### 3.2 — "Eng yaqin ofis" mantiqi noto'g'ri
**Joy:** `api/services/attendance.py` `_nearest_active_office` + `_validate_location`.
**Oqibat:** A ofis 100 m (radius 50), B ofis 120 m (radius 200) → xodim B ning qonuniy
radiusi ichida, lekin "eng yaqin" A bo'lgani uchun **rad etiladi**.
**Tuzatish:** "birorta faol ofis radiusi ichidami" tekshiruvi.

### 3.3 — Digest yuborilmasa ham "yuborildi" belgilanadi
**Joy:** `api/services/attendance_digest.py` `digest_tick`.
**Oqibat:** guruh sozlanmagan bo'lsa `sent=False` qaytadi, lekin `*_last_posted=today`
yoziladi → o'sha kun digesti butunlay yo'qoladi.
**Tuzatish:** faqat haqiqatan yuborilganda belgilash. "Dam olish kuni" holati alohida
(u qayta urinmasligi kerak — bu to'g'ri xatti-harakat).

### 3.4 — Dashboard aralash qamrov
**Joy:** `api/routers/attendance.py` `dashboard()` — `total_employees`,
`checked_in_today`, `late_today`, oylik jamlar **barcha** userlardan; `working_today`,
`not_checked_in` esa faqat `ATTENDANCE_TRACKED_ROLES` dan.
**Oqibat:** Boshliq check-in qilsa `checked_in_today > working_today`.
**Tuzatish:** hamma joyda `ATTENDANCE_TRACKED_ROLES`. Qo'shimcha savol: Boshliq umuman
check-in qila olsinmi? (`/me/check-in` da rol tekshiruvi yo'q.)

### 3.5 — N+1 so'rovlar
**Joy:** `attendance_digest.py` `collect_day` va `work_schedule.py` `all_week` —
har xodimga 2 tadan so'rov (override + weekly). Digest tick har daqiqa ishlaydi.
**Tuzatish:** `routers/attendance.py` `dashboard()` da **to'g'ri yechim bor** (override
va weekly bitta so'rovda olinib lug'atga solingan) — o'sha naqshni ko'chiring.

### 3.6 — GPS eskirgan bo'lishi mumkin
**Joy:** `web/src/pages/CheckIn.tsx` — joylashuv yuz tasdiqlashdan **oldin** olinadi;
model yuklanishi (~10 s) + muvaffaqiyatsiz urinishlar 2-3 daqiqa cho'zilishi mumkin.
**Tuzatish:** GPS ni yuborishdan **oldin** (yuz tasdiqlangandan keyin) olish yoki
eskirgan bo'lsa qayta olish.

### 3.7 — Xodim almashtirilganda eski jadval ko'rinadi
**Joy:** `web/src/pages/WorkSchedule.tsx` — javob kelguncha `week`da oldingi xodim
ma'lumoti turadi; tez "Saqlash" bosilsa **boshqa xodimning jadvali yozilib ketadi**.
**Tuzatish:** yuklanish paytida formani bloklash + saqlanmagan o'zgarish ogohlantirishi.

### 3.8 — Ofis koordinatasi bo'sh qolsa `0,0`
**Joy:** `web/src/pages/Offices.tsx` — `z.coerce.number()` bo'sh satrni 0 qiladi va
−90..90 oralig'idan o'tadi → ofis "Null Island"da yaratiladi, hech kim check-in qila
olmaydi, xato xabari esa chalg'ituvchi ("~6000 km uzoqdasiz").
**Tuzatish:** bo'sh qiymatni rad etuvchi validatsiya.

---

## 🟢 BOSQICH 4 — UX va barqarorlik

| # | Muammo | Joy |
|---|---|---|
| 4.1 | Rad sababi faqat qisqa toast — xodim o'qib ulgurmaydi, butun oqimni qaytadan boshlaydi | `CheckIn.tsx` |
| 4.2 | CDN (`justadudewhohacks.github.io`) ishlamasa "Qayta urinish" tugmasi yo'q; uchinchi tomon shaxsiy sahifasiga bog'liqlik | `FaceCapture.tsx`, `face.ts` |
| 4.3 | Bot backend xatosida **jim qoladi** (try/except yo'q, callback spinner osilib qoladi); 30 kunlik statistika Telegram 4096 belgi limitidan oshishi mumkin | `bot/handlers/attendance_stats.py` |
| 4.4 | GPS xatolari inglizcha ("User denied Geolocation") | `CheckIn.tsx`, `Offices.tsx` |
| 4.5 | `liveness: result.liveness ?? 1.0` — default **eng yuqori ishonch** bo'lishi teskari, `0` bo'lsin | `CheckIn.tsx` |
| 4.6 | `days=30` aslida **31 kun** oladi (`>=` + `timedelta(days=days)`) | `routers/attendance.py` |
| 4.7 | Override formasida `start < end` validatsiyasi yo'q (haftalikda bor) | `WorkSchedule.tsx` |
| 4.8 | Dashboard xatosi ko'rsatilmaydi; "Hozir ofisda" jonli ma'lumot bo'lsa-da avto-yangilanish yo'q | `Attendance.tsx` |
| 4.9 | Eskirgan izohlar: "faqat employee" deb yozilgan, aslida `ATTENDANCE_TRACKED_ROLES` | `attendance_digest.py`, `routers/attendance.py` |
| 4.10 | `fmtTime` ikki faylda nusxalangan (drift xavfi) | `CheckIn.tsx`, `Attendance.tsx` |
| 4.11 | Ro'yxatlarda `key={i}` (indeks); register tugmasi saqlash paytida disabled emas | `Attendance.tsx`, `FaceCapture.tsx` |

---

## 3. NIMA QILMASLIK KERAK (anti-maqsadlar)

- ❌ **Tarixni qayta yozmang.** Grace/hisob qoidasi o'zgarsa, mavjud `attendance`
  yozuvlarini qayta hisoblamang — faqat yangi yozuvlarga qo'llansin. (3.1 dagi recalc
  faqat **bugungi va kelajakdagi** kunlar uchun.)
- ❌ **Katta refactor qilmang.** Har bug uchun minimal, maqsadli o'zgarish. Butun
  servisni qayta yozish — alohida vazifa.
- ❌ **Yangi kutubxona qo'shmang** (Savol A da 1-variant tanlanmasa).
- ❌ **Lokal muhitdan guruhga xabar yubormang** — pastdagi ehtiyot choralariga qarang.
- ❌ **Verifix papkasiga tegmang** (`verifix/`) — u arxiv, ishlatilmaydi.

---

## 4. EHTIYOT CHORALARI (majburiy)

1. **Zaxira.** Har bosqichdan oldin: `cp app.db app.db.bak_<sana>_<bosqich>`.
2. **Guruhga tasodifiy xabar.** Lokal `.env` **haqiqiy Telegram guruhiga** ulangan.
   Digest bilan ishlaganda **faqat `dry_run=true`**. Lokal bazada digest hozir
   **o'chirilgan** (`attendance_digest_config.morning_enabled=0, evening_enabled=0`) —
   shundayligicha qoldiring. (Ilgari sinov paytida guruhga test xabar ketib qolgan.)
3. **Bot lokal polling ishlamaydi** — productionda faol webhook bor, himoya bloklaydi.
   Bot o'zgarishlari faqat deploy'dan keyin ko'rinadi (bu normal, xato emas).
4. **Migratsiya** kerak bo'lsa: `down_revision` ni joriy head (`a1b2c3d4e5f6`) ga ulang,
   `upgrade` **va** `downgrade` ikkalasini yozing, qo'llashdan oldin zaxira oling.
5. **Test ma'lumoti** `T-` prefiksi bilan yaratilsin, ish oxirida **to'liq** o'chirilsin.
6. **AuditLog tozalashda** faqat aniq `id` yoki tor vaqt oynasi bo'yicha filtrlang —
   ilgari keng filtr haqiqiy tarixiy yozuvlarni o'chirib yuborgan (qaytarib bo'lmagan).

---

## 5. SINOV TALABLARI

Har bosqichdan keyin **hammasi**:

```bash
# 1. Regressiya (26/26 o'tishi shart)
.venv/Scripts/python.exe test.py

# 2. Frontend
cd web && npx tsc --noEmit

# 3. Xizmatlarni qayta ishga tushirish va jonli tekshirish
schtasks /run /tn "HodimlarTizimi_StartAll"
```

**Har tuzatilgan bug uchun `test.py` ga yangi tekshiruv qo'shing.** Mavjud naqsh:

```python
# test.py ichida, run_tests() funksiyasida:
def check(name: str, cond: bool, extra: str = "") -> None: ...   # allaqachon bor

# Namuna (1.3 grace uchun):
try:
    # 09:06 ga to'g'ri keladigan check-in yasang (T- xodim + jadval bilan)
    ...
    row = conn.execute("select late_minutes from attendance where user_id=? and date=?",
                       (uid, today)).fetchone()
    check("grace bo'sag'a: 09:06 -> late=6 (1 emas)", row[0] == 6, f"bazada={row[0]}")
except Exception:
    check("grace tekshiruvi", False, traceback.format_exc(limit=1).strip())
```

Qoidalar:
- Har tekshiruv **try/except** bilan o'ralsin (bittasi yiqilsa qolganlari ishlasin).
- Sinov ma'lumoti `T-` prefiksi bilan, `finally` blokida tozalansin.
- Test **jonli ma'lumotga tegmasin**.

---

## 6. KUTILGAN NATIJA

Har bosqich uchun:
1. **Alohida commit** — o'zbekcha xabar, «nima o'zgardi va NEGA» tushuntirilgan
   (mavjud commit tarixidagi uslubga qarang).
2. **Yangilangan `test.py`** — tuzatilgan har bug uchun tekshiruv.
3. **Qisqa hisobot:** qaysi buglar tuzatildi, qaysilari qoldi va **nega**
   (masalan: "2.2 — Savol C javobi kutilmoqda").

Yakuniy hisobotda quyidagilar bo'lsin:
- Tuzatilgan buglar ro'yxati (band raqami bilan)
- `test.py` natijasi (nechta OK / FAIL)
- Qolgan ma'lum muammolar va sabab
- Deploy uchun eslatma (migratsiya kerakmi, frontend build kerakmi)
