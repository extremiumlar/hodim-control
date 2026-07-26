# Oylik ish haqi + kechikish jarimasi + qo'shimcha ish tizimi — loyiha rejasi

> Holat: **REJA** (kod yozilmagan). Manba: egasi talabi (2026-07-27) + mavjud
> tizim tahlili. Ijro qilinganda har bosqich alohida commit bo'ladi.

---

## 0. Mavjud poydevor (nima allaqachon bor)

Bu tizim noldan qurilmaydi — quyidagilar tayyor va qayta ishlatiladi:

| Nima | Qayerda |
|---|---|
| Kunlik davomat yozuvi: `late_minutes`, `early_leave_minutes`, `worked_minutes`, `status` | `db/models.py:628` (`Attendance`) |
| Kechikishni ish jadvalidan hisoblash (grace = bo'sag'a, yuqori chegara bilan) | `api/services/attendance.py:199` |
| Ish jadvali (haftalik andoza + sana override) | `WorkScheduleWeekly` / `WorkScheduleOverride` |
| Kelmaganlarni avtomatik `absent` deb yozish | `api/services/attendance_digest.py:259` |
| Sababli kunlar (tasdiqlash oqimi bilan) | `ExcusedDay` + `api/routers/excused_days.py` |
| Oylik bonus modeli + upsert + scheduler jobi | `Bonus`, `api/routers/bonuses.py`, `scheduler/jobs.py:117` |
| Kechikish statistikasi (kunma-kun, xodim kesimida) | `api/routers/attendance.py:533` (`_late_stats_data`) |
| Audit log, Excel eksport, PeriodPicker, DataTable | `AuditLog`, `api/services/export.py`, `web/src/components/` |

Ya'ni **jarima uchun kerakli xom ma'lumot allaqachon yig'ilyapti**. Qurilishi
kerak bo'lgan narsa — *pul qatlami*: stavka, qoida, hisob-kitob, tasdiqlash,
ko'rsatish.

---

## 1. Tizimning ideallashtirilgan ko'rinishi

Egasi aytgan 4 ta talab + men qo'shgan takomillashtirishlar (⭐ bilan belgilangan).

### 1.1 Kechikish limiti va jarima
- Har xodimga **oylik bepul kechikish limiti** beriladi (kun soni bo'yicha,
  masalan "oyiga 3 marta kechiksa jarima yo'q").
- ⭐ Limit **daqiqada** ham bo'lishi mumkin (masalan "oyiga jami 60 daqiqa").
  Ikkalasi ham sozlanadi; ikkalasi yoqilgan bo'lsa — qaysi biri birinchi
  tugasa, jarima o'shandan boshlanadi.
- Limit tugagach jarima rejimi (`fine_mode`):
  - `per_day` — kechikkan **har bir kun** uchun qat'iy summa *(egasi so'ragan asosiy rejim)*
  - ⭐ `per_minute` — har kechikkan daqiqa uchun summa
  - ⭐ `tiered` — pog'onali: 1–15 daq → X, 16–60 daq → Y, 60+ daq → Z
  - ⭐ `percent_of_daily` — o'sha kunlik ish haqining foizi (oyligi katta odamga
    jarima ham sezilarli bo'lsin)
- ⭐ **Oylik jarima shifti (cap)**: bir oyda jarima oylikning N% idan oshmaydi.
  Himoya to'siq — hisobdagi xato yoki 20 kun kechikish oylikni yeb yubormaydi.
- ⭐ **Jarima qayerdan yechiladi** (`fine_applies_to`): `bonus_first` (avval
  bonus/KPI dan, yetmasa qolgani oylikdan) yoki `net_salary` (to'g'ridan-to'g'ri).
  Sukut bo'yicha `bonus_first` — bu huquqiy jihatdan xavfsizroq (7.4-bandga qarang).
- ⭐ **Sababli (approved `ExcusedDay`) kun jarimaga kirmaydi** va limitni yemaydi.
- ⭐ Kelmagan kun (`absent`) uchun alohida qoida: qat'iy summa yoki kunlik
  ish haqini ushlab qolish (`absent_deduct_daily`).
- ⭐ Erta ketish uchun ixtiyoriy qoida (default: o'chiq).
- ⭐ Qoida **3 darajada**: global → lavozim (`Position`) → xodim. Amaldagisi:
  xodim > lavozim > global. HR bir marta global qo'yadi, istisnolarni nuqtaviy beradi.

### 1.2 Oylik ish haqi
- Har xodimga web paneldan **oylik stavka** kiritiladi.
- ⭐ Stavka **versiyalanadi** (`effective_from` bilan, `Norm` modelidagi naqsh):
  oylik oshirilsa o'tgan oylar hisobi buzilmaydi.
- ⭐ Hisob asosi (`pay_basis`): `monthly` (qat'iy oylik — sukut), `daily`
  (kunbay), `hourly` (soatbay). Kunbay/soatbay uchun ishlangan kun/daqiqa
  `Attendance` dan olinadi.
- ⭐ Oy o'rtasida ishga kirgan/ketgan xodim uchun **prorata** (rejadagi ish
  kunlariga nisbatan).

### 1.3 Qo'shimcha ish (overtime)
- Faqat **HR belgilagan xodimlarga** yoqiladi (`overtime_enabled`).
- Hisoblash rejimi (`overtime_mode`) — HR tanlaydi:
  - `derived` — xodimning **o'z oyligidan kelib chiqib**: soatlik stavka =
    oylik ÷ o'sha oydagi rejadagi ish soatlari, × koeffitsient (1.0 / 1.5 / 2.0)
  - `fixed_rate` — HR **o'zi summa belgilaydi** (so'm/soat)
- ⭐ Manbasi: check-out ish oynasi tugaganidan **keyin** bo'lsa, farq
  avtomatik "qo'shimcha ish" nomzodi bo'ladi; HR/rahbar **tasdiqlaydi**
  (`pending → approved`). Tasdiqsiz pul hisoblanmaydi — aks holda odam
  bekorga o'tirib pul olaveradi.
- ⭐ HR qo'lda ham kirita oladi (masalan dam olish kunidagi chiqish).
- ⭐ Himoyalar: `min_minutes` (masalan 15 daqiqadan kami hisoblanmaydi),
  kunlik va oylik yuqori chegara.

### 1.4 Oy oxirida avtomatik ish haqi varaqasi (payslip)
Formula:

```
JAMI = asosiy_oylik (prorata)
     + qo'shimcha_ish
     + bonus (mavjud Bonus modelidan)
     + qo'lda qo'shimchalar (mukofot)
     − kechikish_jarimasi
     − kelmagan kun ushlanmasi
     − qo'lda ushlanmalar (avans, zarar)
```

- ⭐ Har bir qator alohida saqlanadi (`PayslipItem`): "nega bu summa" degan
  savolga bir bosishda javob bo'ladi — nizolarning 90% shu yerda tugaydi.
- ⭐ Payslip **holati** bor: `draft → calculated → approved → paid`. Faqat
  `approved` bo'lgach xodim ko'radi va qayta hisoblash bloklanadi (qulf).
- ⭐ Hisob paytidagi **qoida va stavka snapshot** qilib saqlanadi (`breakdown`
  JSON) — keyin qoida o'zgarsa ham eski varaqa o'zgarmaydi.

### 1.5 ⭐ Shaffoflik (nizoni oldini olish)
- Bot xodimga **oldindan ogohlantiradi**: "Bu oy 2 marta kechikdingiz, limit 3.
  Keyingisidan jarima boshlanadi."
- Payslip tasdiqlangach botga tushadi: qisqacha + "Tafsilot" tugmasi.
- ⭐ Xodim payslip ostidan **e'tiroz** bildira oladi → HRga so'rov (mavjud
  `ExcusedDay` tasdiqlash naqshi bilan bir xil).

### 1.6 ⭐ Dasturchi rejimi (super-admin)
`dasturchi` roliga **cheklovsiz** boshqaruv: har qanday normani o'zgartirish,
har qanday yozuvni butunlay o'chirish, qulflarni ochish, boshqa rollarning
matritsa cheklovlaridan chetga chiqish. Batafsil — **11-bo'lim**.

---

## 2. Ma'lumot modeli (yangi jadvallar)

`db/models.py` ga qo'shiladi, bitta alembic migratsiyasi bilan.

```
SalaryRate                 # oylik stavka tarixi
  user_id, amount(14,2), pay_basis(monthly|daily|hourly),
  effective_from(date), changed_by, note, created_at
  → amaldagisi = effective_from <= sana bo'yicha oxirgisi

OvertimeProfile            # kimga qo'shimcha ish yoqilgan
  user_id(uniq), enabled, mode(derived|fixed_rate),
  fixed_rate_per_hour(12,2), multiplier(3,2)=1.0,
  norm_hours_source(schedule|fixed), fixed_norm_hours_per_month,
  min_minutes=15, daily_cap_minutes, monthly_cap_minutes,
  updated_by, updated_at

FinePolicy                 # jarima qoidasi (3 darajali)
  scope(global|position|user), scope_id(nullable),
  grace_minutes(nullable → global settings),
  free_late_days_per_month, free_late_minutes_per_month,
  fine_mode(per_day|per_minute|tiered|percent_of_daily),
  fine_per_day(12,2), fine_per_minute(12,2), tiers(JSON),
  percent_of_daily(5,2),
  absent_mode(none|fixed|deduct_daily), absent_fine(12,2),
  early_leave_enabled, early_leave_per_minute(12,2),
  monthly_cap_percent(5,2), monthly_cap_amount(12,2),
  fine_applies_to(bonus_first|net_salary),
  is_active, updated_by, updated_at
  UNIQUE(scope, scope_id)

OvertimeEntry              # qo'shimcha ish yozuvi
  user_id, date, minutes, source(auto_attendance|manual),
  status(pending|approved|rejected), note,
  decided_by, decided_at, created_at
  UNIQUE(user_id, date)

PayrollPeriod              # oy holati (qulf)
  period("YYYY-MM", uniq), status(draft|calculated|approved|paid),
  calculated_at, approved_by, approved_at, locked, note

Payslip                    # bir xodim, bir oy
  user_id, period, UNIQUE(user_id, period)
  base_amount, pay_basis, rate_snapshot(12,2),
  scheduled_days, worked_days, absent_days, excused_days,
  scheduled_minutes, worked_minutes,
  late_days, late_minutes, fined_late_days, fined_late_minutes,
  fine_amount, absent_deduction,
  overtime_minutes, overtime_amount, overtime_rate_snapshot,
  bonus_amount, adjustments_plus, adjustments_minus,
  gross(14,2), net(14,2), currency("UZS"),
  status(draft|calculated|approved|paid),
  breakdown(JSON: qo'llanilgan policy + kunma-kun ro'yxat),
  calculated_at, approved_by, approved_at

PayslipItem                # varaqaning har bir qatori
  payslip_id, kind(base|overtime|bonus|fine_late|fine_absent|
                   adjustment_plus|adjustment_minus),
  label, quantity(10,2), rate(12,2), amount(14,2), meta(JSON),
  sort_order

PayrollAdjustment          # qo'lda kiritilgan qo'shimcha/ushlanma
  user_id, period, kind(plus|minus), amount(14,2),
  reason, created_by, created_at
```

---

## 3. Hisoblash yadrosi — `api/services/payroll.py`

Yangi servis. **Toza funksiyalar** (DB'siz test qilinadigan) + bitta orkestrator.

```python
resolve_policy(db, user)                  -> FinePolicy   # user > position > global
resolve_rate(db, user, on_date)           -> SalaryRate
month_schedule(db, user, period)          -> (kunlar, rejadagi_daqiqalar)
collect_attendance(db, user, period)      -> kunma-kun ro'yxat (excused belgisi bilan)
compute_late_fine(days, policy, daily_pay)-> (fined_days, fine_amount, satrlar)
compute_overtime(db, user, period, prof)  -> (daqiqa, summa, satrlar)
compute_base(rate, sched, worked, policy) -> (base_amount, satrlar)
build_payslip(db, user, period)           -> Payslip + PayslipItem[]
run_payroll(db, period, user_ids=None)    -> idempotent upsert (Bonus naqshi)
```

Muhim qoidalar (kodda izoh bilan mustahkamlanadi):
1. Jarima **faqat** `status='late'` va `is_weekend=False` va sababli emas
   kunlar bo'yicha.
2. Limit **xronologik** yeyiladi (oy boshidan) — qaysi kun bepul, qaysi kun
   jarimali ekani aniq ko'rsatiladi.
3. Barcha summalar `Decimal`, oxirida sozlanadigan yaxlitlash (default 100 so'm).
4. `run_payroll` **idempotent**: qayta chaqirilsa bir xil natija, dublikat yo'q.
5. `PayrollPeriod.locked=True` bo'lsa — qayta hisoblash rad etiladi (409).

---

## 4. API (yangi router `api/routers/payroll.py`)

```
# Sozlamalar (faqat HR/boss/dasturchi)
GET    /payroll/policies                     # 3 daraja ro'yxati
PUT    /payroll/policies                     # scope+scope_id bo'yicha upsert
DELETE /payroll/policies/{id}
GET    /payroll/rates?user_id=               # stavka tarixi
POST   /payroll/rates                        # yangi stavka (effective_from)
GET    /payroll/overtime-profiles
PUT    /payroll/overtime-profiles/{user_id}

# Qo'shimcha ish
GET    /payroll/overtime?period=&status=
POST   /payroll/overtime                     # qo'lda kiritish
POST   /payroll/overtime/{id}/decide         # approve/reject

# Hisob-kitob
POST   /payroll/{period}/preflight           # ⭐ tayyorlik tekshiruvi (6-bo'lim)
POST   /payroll/{period}/calculate           # hammasi yoki user_ids
GET    /payroll/{period}                     # jadval (ro'yxat)
GET    /payroll/{period}/user/{user_id}      # to'liq tafsilot + satrlar
POST   /payroll/{period}/approve             # qulflaydi + botga xabar
POST   /payroll/{period}/reopen              # qulfni ochish (audit bilan)
GET    /payroll/{period}/export              # Excel (export.py orqali)
POST   /payroll/adjustments                  # qo'lda qo'shimcha/ushlanma
DELETE /payroll/adjustments/{id}

# Bot (X-Bot-Secret)
GET    /payroll/my/{telegram_id}             # oxirgi TASDIQLANGAN payslip
GET    /payroll/my/{telegram_id}/late-status # bu oy: kechikish / limit
POST   /payroll/{period}/calculate-cron      # scheduler chaqiruvi
```

Ruxsat: yangi `PAYROLL_ROLES = (hr, boss, dasturchi)`. **ROP pul summalarini
ko'rmaydi** — u faqat o'z jamoasining kechikish statistikasini ko'radi (mavjud
`/attendance/late-stats`). Bu ataylab: maosh maxfiy ma'lumot.

---

## 5. Interfeys

### 5.1 Web (`web/src/pages/`)
| Sahifa | Mazmun |
|---|---|
| `Payroll.tsx` (`/payroll`) | Davr tanlash → jadval: xodim, oylik, ishlangan kun/soat, kechikish (kun/daq), jarima, qo'shimcha, bonus, **JAMI**. Tugmalar: "Qayta hisoblash", "Tasdiqlash", "Excel". Qatorni bosish → tafsilot. |
| `PayrollSettings.tsx` (`/payroll/settings`) | 3 ta tab: **Jarima qoidasi** (global/lavozim/xodim), **Oylik stavkalar** (inline tahrir + tarix), **Qo'shimcha ish** (kimga yoqilgan + rejim). |
| `Overtime.tsx` (`/overtime`) | Tasdiq navbati: kun, xodim, daqiqa, manba, [Tasdiqlash] [Rad etish]. |
| `EmployeeProfile.tsx` | Yangi "Oylik" tab — oxirgi 6 oy varaqasi. |
| `CheckIn.tsx` | Xodimga: "Bu oy 2/3 kechikish ishlatildi" indikatori. |

Tafsilot oynasi (eng muhim ekran): yuqorida yig'indi, pastda **kunma-kun
jadval** — sana, kelgan vaqt, kechikish daqiqasi, "bepul limit" yoki "jarima
X so'm" belgisi, sababli bo'lsa izoh. Har bir raqamning kelib chiqishi ko'rinadi.

`App.tsx` ga 3 ta route + `Layout.tsx` nav guruhiga "Ish haqi" bo'limi
(faqat `PAYROLL_ROLES` ga ko'rinadi), `lib/api/endpoints.ts` + `lib/queries.ts`
ga mos hooklar.

### 5.2 Bot (`bot/handlers/payroll.py`)
- Xodim: **«💵 Mening oyligim»** — oxirgi tasdiqlangan varaqa (asosiy, jarima
  sababi bilan, qo'shimcha, jami) + «Kechikishlarim» tugmasi.
- Xodim: avtomatik ogohlantirish — limitdan 1 kun qolganda va limit
  tugaganda (birinchi jarimali kechikishda darhol xabar).
- HR/boss: oy hisoblangach «Payroll tayyor: N xodim, jami X. Tasdiqlaysizmi?»
- `Position.menu_flags` ga `payroll` bayrog'i — tugma kimga ko'rinishini
  boshqaradi (mavjud naqsh).

---

## 6. ⭐ Bosqich 0 — payrolldan OLDIN yopilishi shart bo'lgan teshiklar

Pul hisoblanadigan bo'lgach, davomatdagi har bir xato = real nizо. Shuning
uchun avval:

| # | Muammo | Yechim |
|---|---|---|
| 0.1 | HR davomatni **tuzata olmaydi** (faqat `DELETE` bor). Face ID/GPS ishlamay xodim check-in qilolmasa — nohaq jarima. | `PATCH /attendance/{id}` — check-in/out vaqtini, statusni, izohni o'zgartirish; majburiy sabab + `AuditLog`. |
| 0.2 | Check-out qilinmagan kun `worked_minutes=0` bo'lib qoladi → soatbay to'lov va qo'shimcha ish buziladi. | Kunlik yopish jobi: yarim tunda ochiq kunlarni ish oynasi oxiri bilan yopadi va `note` qo'yadi ("check-out yo'q — avtomatik yopildi"), keyin HR tuzatadi. |
| 0.3 | Ish jadvali belgilanmagan xodimga default (Du–Ju) qo'llanadi — payroll uchun xavfli. | `preflight` tekshiruvi: jadvalsiz xodimlar, stavkasiz xodimlar, check-out'siz kunlar, tasdiqlanmagan overtime, kutilayotgan `ExcusedDay` lar ro'yxati. Hisoblash **shu ro'yxat bo'sh bo'lmasa ogohlantirish bilan** davom etadi. |
| 0.4 | `bonuses/calculate-monthly` oyning **oxirgi kuni** ishlaydi — o'sha kunning o'zi hisobga tushmaydi. | Payroll jobi keyingi oyning **1-kuni ertalab** ishlaydi va `period` = o'tgan oy. Bonus jobini ham shunga moslashtirish tavsiya etiladi. |

---

## 7. Bosqichma-bosqich ijro rejasi

Har bosqich = alohida commit, oldingisidan mustaqil ishlaydi.

### Bosqich 0 — poydevor tuzatishlari ✅ BAJARILDI (2026-07-27)
**Fayllar:** `api/routers/attendance.py`, `api/services/attendance.py`,
`api/services/attendance_digest.py`, `api/schemas.py`, `test.py`,
`web/src/pages/Attendance.tsx`, `web/src/lib/api/{types,endpoints}.ts`,
`web/src/lib/queries.ts`
**Ish:** 6-bo'limdagi 0.1, 0.3, 0.4 (0.2 — check-out'siz kunni avtomatik
yopish — bu ishdan OLDIN allaqachon tayyor ekan: `attendance_digest.py`
`auto_close_unclosed_checkouts`).

- **0.1** — `PUT /attendance/manual`: HR/Boshliq/Dasturchi qo'lda check-in/out
  vaqtini tuzatadi (mahalliy "HH:MM"), server `recompute_fields`/
  `recompute_attendance` orqali kechikish/ishlangan vaqtni check-in oqimi
  bilan AYNAN bir xil qoida bo'yicha qayta hisoblaydi. **ROP'da bu huquq
  YO'Q** (`ATTENDANCE_EDIT_ROLES` — hr/boss/dasturchi) — kechikish endi pul
  qarori, ROP uni bekor qila olmasligi kerak. Majburiy `reason` (min 5 belgi),
  `AuditLog(action="attendance_manual_edit")`. Web: `Attendance.tsx` da qalam
  ikonkasi + dialog.
- **0.3** — `GET /attendance/readiness`: 5 guruh (jadvalsiz, yopilmagan
  check-out, avtomatik yopilgan, hal qilinmagan sababli kun, yuzsiz xodim).
  Web: "Ma'lumot tayyorligi" kartasi.
- **0.4** — bonus jobi oyning oxirgi kunida ishlaydi muammosi: **kod
  tekshirilmadi, HR bilan tasdiqlanmagan** — Bosqich 6 (avtomatika) ga
  qoldirildi, chunki payroll jobining o'zi hali yo'q.

**Test:** `test.py` da 0.1/0.3 uchun T- testlar (sababsiz→422, ROP→403,
kechikish qayta hisoblanishi, dam olish kunida 0, kelajak kunga taqiq,
readiness guruhlari). Real xizmatlarga (`uvicorn` qayta ishga tushirilib)
qarshi ishga tushirildi: **97 OK / 98** (yagona FAIL — Windows konsolining
oldindan mavjud `charmap` kodlash xatosi, mantiqqa aloqasi yo'q). `tsc
--noEmit` toza. Brauzer orqali vizual tekshirish bu muhitda ishlamadi
(lokal 5173 portiga ulanib bo'lmadi) — TypeScript kompilyatsiyasi va
backend testlari orqali tekshirildi.

**Bajarilgan deb hisoblanadi:** HR sayt orqali kechikishni tuzata oladi va
o'zgarish auditda ko'rinadi; check-out'siz kun avtomatik yopiladi; oylik
hisobdan oldin "bo'sh joylar" ro'yxati ko'rinadi.

### Bosqich 1 — ma'lumot modeli
**Fayllar:** `db/models.py`, `db/alembic/versions/<yangi>_payroll.py`
**Ish:** 2-bo'limdagi 8 ta jadval + indekslar + global `FinePolicy` seed
(hammasi 0/o'chiq — mavjud tizim xatti-harakati o'zgarmaydi).
**DoD:** `alembic upgrade head` toza bazada ham, mavjud `app.db` da ham o'tadi;
`downgrade` ishlaydi.

### Bosqich 2 — hisoblash yadrosi (kodning yuragi)
**Fayllar:** `api/services/payroll.py`, `test.py`
**Ish:** 3-bo'limdagi funksiyalar. **Test birinchi**: T- xodimlar ustida
sun'iy davomat yaratib, qo'lda hisoblangan kutilgan summa bilan solishtirish.
Majburiy testlar: limit ichida jarima yo'q; limit tugagach har kun jarima;
sababli kun limitni yemaydi; dam olish kuni jarimasiz; cap ishlaydi;
`bonus_first` bonusni yeb, qolganini oylikka o'tkazadi; overtime `derived` va
`fixed_rate` bir xil kirishda to'g'ri; idempotentlik (2 marta hisoblash = bir xil).
**DoD:** barcha T- testlar yashil; yadro DB'siz ham sinaladigan.

### Bosqich 3 — API
**Fayllar:** `api/routers/payroll.py`, `api/schemas.py`, `api/main.py`,
`api/deps.py` (`PAYROLL_ROLES`), `api/services/export.py`
**DoD:** 4-bo'limdagi barcha endpointlar; ruxsat testlari (ROP → 403,
xodim → faqat o'ziniki); qulflangan davrga `calculate` → 409.

### Bosqich 3.5 — ⭐ Dasturchi rejimi (super-admin qatlami)
**Fayllar:** `api/deps.py`, `api/routers/admin_override.py` (yangi),
`api/routers/norms.py`, `api/routers/payroll.py`, `api/routers/attendance.py`,
`db/models.py` (soft-delete ustunlari), `test.py`
**Ish:** 11-bo'lim to'liq.
**DoD:** dasturchi istalgan normani o'zgartira/o'chira oladi; har bir override
majburiy sabab bilan `AuditLog` ga tushadi; boshqa rollar bu endpointlarga
403 oladi.

### Bosqich 4 — Web panel
**Fayllar:** `web/src/pages/Payroll.tsx`, `PayrollSettings.tsx`, `Overtime.tsx`,
`EmployeeProfile.tsx`, `App.tsx`, `Layout.tsx`, `lib/api/endpoints.ts`,
`lib/api/types.ts`, `lib/queries.ts`
**DoD:** HR nol koddan: stavka kiritadi → limit va jarima qo'yadi → hisoblaydi
→ tafsilotda har bir jarimaning sababini ko'radi → tasdiqlaydi → Excel oladi.

### Bosqich 5 — Bot
**Fayllar:** `bot/handlers/payroll.py`, `bot/keyboards.py`, `bot/main.py`,
`bot/api_client.py`, `BOT_BUYRUQLARI.md`
**DoD:** xodim o'z varaqasini ko'radi (faqat tasdiqlangan); limit
ogohlantirishlari keladi; HR tasdiq xabarini oladi.

### Bosqich 6 — avtomatika
**Fayllar:** `scheduler/jobs.py`, `scheduler/main.py`, `scheduler/config.py`,
`.env.example`
**Ish:** `monthly_payroll` jobi (keyingi oy 1-kuni, bonusdan keyin);
kechikish limiti ogohlantirish jobi (kunlik); overtime nomzodlarini avtomatik
yaratish (kunlik).
**DoD:** job muvaffaqiyatsiz bo'lsa log + rahbarlarga xabar (mavjud
`call_api(label=...)` naqshi).

### Bosqich 7 — hisobot, maxfiylik, hujjat
**Fayllar:** `api/services/export.py`, `api/services/monthly_digest.py`,
`README.md`, `BOT_BUYRUQLARI.md`
**Ish:** Excel payslip (xodim uchun bitta varaq), oylik digestga "jami ish haqi
fondi" satri (faqat boss), barcha pul o'zgarishlari uchun `AuditLog`.

---

## 8. Nozik joylar (kodda izoh bilan mustahkamlanadi)

1. **Sababli kun** — faqat `approved`. `pending` sababli kun jarimani
   *to'xtatib turadi* (hisobda "kutilmoqda" deb ko'rsatiladi), rad etilsa jarima tiklanadi.
2. **Grace o'zgarishi** o'tmishga qo'llanmaydi — payroll saqlangan
   `late_minutes` ni oladi (`api/services/attendance.py:204` dagi izoh bilan mos).
3. **Vaqt mintaqasi**: hamma sana chegarasi `today_local()` (Asia/Tashkent),
   DB da naive-UTC. Yangi kodda `local_range_utc_naive` ishlatiladi.
4. ⭐ **Huquqiy eslatma**: O'zbekiston mehnat qonunchiligida ish haqidan
   "jarima" sifatida ushlab qolish cheklangan. Shuning uchun default
   `fine_applies_to = bonus_first` — jarima avval mukofot/bonusdan yechiladi.
   Buni yakuniy tanlash HR/yuristning qarori; tizim ikkala rejimni ham
   qo'llab-quvvatlaydi va tanlovni auditga yozadi.
5. **Yaxlitlash** — bitta joyda (`payroll.round_money`), default 100 so'mgacha.
6. **Maxfiylik** — summalar faqat `PAYROLL_ROLES` ga; botda faqat o'ziga;
   guruh digestiga xodim summasi **hech qachon** chiqmaydi.
7. **Qayta hisoblash** — `approved` davr uchun faqat `reopen` dan keyin,
   sabab bilan, auditga yozilib.

---

## 9. HR/egasidan kerakli qarorlar (kod yozishdan oldin)

| # | Savol | Taklif (default) |
|---|---|---|
| 1 | Limit **kun** bo'yicha, **daqiqa** bo'yicha yoki ikkalasi? | Kun bo'yicha (masalan 3) |
| 2 | Jarima rejimi? | `per_day` — qat'iy summa |
| 3 | Jarima qayerdan yechiladi? | Avval bonusdan, qolgani oylikdan |
| 4 | Oylik jarima chegarasi? | Oylikning 20% i |
| 5 | Sababsiz kelmagan kun? | O'sha kunlik ish haqi ushlanadi |
| 6 | Qo'shimcha ish koeffitsienti (`derived` rejim)? | 1.5× |
| 7 | Qo'shimcha ish norma soati manbai? | Ish jadvali (avtomatik) |
| 8 | ROP oylik summalarni ko'radimi? | Yo'q |
| 9 | Avans (oy o'rtasi to'lovi) bormi? | Bor — `PayrollAdjustment(minus)` orqali |
| 10 | Oyning qaysi kuni yopiladi? | Keyingi oyning 1-kuni, 06:00 |

---

## 10. Taxminiy hajm

| Bosqich | Hajm |
|---|---|
| 0 — poydevor tuzatishlari | kichik |
| 1 — model + migratsiya | kichik |
| 2 — hisoblash yadrosi + testlar | **katta (eng muhim)** |
| 3 — API | o'rta |
| 3.5 — Dasturchi rejimi | o'rta |
| 4 — Web panel | **katta** |
| 5 — Bot | o'rta |
| 6 — avtomatika | kichik |
| 7 — hisobot/hujjat | kichik |

Tavsiya: 0 → 1 → 2 → 3 ni ketma-ket bajarib, **4-bosqichdan oldin** HR bilan
bitta real oyni "quruq" hisoblab ko'rish (`preflight` + `calculate`, tasdiqsiz)
— raqamlar to'g'riligini interfeys qurilishidan oldin isbotlash uchun.

---

## 11. ⭐ Dasturchi rejimi — cheklovsiz boshqaruv qatlami

### 11.1 Hozirgi holat (nima bor, nima yo'q)

`dasturchi` roli allaqachon ko'p joyda imtiyozli, lekin **to'liq huquqi yo'q**:

| Bor | Yo'q (qo'shiladi) |
|---|---|
| Barcha xodimlarga norma qo'ya oladi ([norms.py:52](api/routers/norms.py:52)) | **Normani o'chirish/qaytarish** — `Norm` faqat qo'shiladi, hech qachon o'chmaydi |
| Davomat yozuvini o'chira oladi ([attendance.py:700](api/routers/attendance.py:700)) | Davomat yozuvini **tuzatish** (0.1-band bilan birga keladi) |
| Anketa, guruh, AI sozlamalarini to'liq boshqaradi | Lavozim **metrika cheklovi** — `_validate_metric` dasturchini ham to'xtatadi ([norms.py:103](api/routers/norms.py:103)) |
| Barcha rahbar endpointlariga kirish | **Xodim bo'lmaganlarga** (hr/rop/boss) norma qo'yish — `can_manage_norms` `target.role != employee` da `False` qaytaradi |
| | Vazifa, sababli kun, kunlik natija, video, ish jadvali yozuvlarini **majburan o'chirish/tahrirlash** |
| | Payroll: qulflangan davrni ochish, tasdiqlangan varaqani o'zgartirish/o'chirish |

Ya'ni bugun dasturchi "hamma narsani ko'radi va qo'yadi", lekin
**"hamma narsani orqaga qaytaradi"** emas. Talab shuni yopadi.

### 11.2 Tamoyillar

1. **Bitta yagona darvoza** — `api/deps.py` ga:
   ```python
   def require_dasturchi()          # Depends — faqat Role.dasturchi
   def is_superadmin(actor) -> bool # matritsa tekshiruvlarida qisqa yo'l
   ```
   Har bir `can_manage_*` funksiyasi eng boshida `is_superadmin(actor)` ni
   tekshiradi va `True` qaytaradi. Cheklov mantiqi tarqoq bo'lmaydi.

2. **Har bir override — majburiy sabab.** `override_reason: str` (min 5 belgi)
   bo'lmasa `422`. Sabab `AuditLog.after` ga tushadi.

3. **Tasodifan bosilmasin.** Xavfli amallar `?force=true` yoki
   `X-Override: yes` talab qiladi; web'da esa **«Dasturchi rejimi» tumblerи**
   yoqilmaguncha qizil tugmalar umuman ko'rinmaydi.

4. **Yumshoq o'chirish — sukut bo'yicha.** Pul va davomat yozuvlari
   (`Payslip`, `SalaryRate`, `Attendance`, `OvertimeEntry`, `Norm`) uchun
   `deleted_at` + `deleted_by` + `deleted_reason` ustunlari. Barcha o'qish
   so'rovlari `deleted_at IS NULL` bilan filtrlanadi. **Qattiq o'chirish**
   (`DELETE ... hard=true`) faqat dasturchiga va faqat alohida tasdiq bilan.
   Sabab: "butunlay o'chirish" kerak bo'lgan holatlarning 95% i aslida
   "ko'rinmasin" degani — qaytarib bo'lmaydigan o'chirish keyin nizoda isbot
   qoldirmaydi.

5. **Cheklovsizlik ≠ izsizlik.** Dasturchi hamma narsani qila oladi, lekin
   **har bir amal auditda qoladi** va Boshliq uni ko'ra oladi. Bu ikkovini
   himoya qiladi: dasturchini "sen o'zgartirding" ayblovidan, egasini esa
   sezilmay qolgan o'zgarishdan.

### 11.3 Yangi endpointlar — `api/routers/admin_override.py`

Barchasi `Depends(require_dasturchi)`, barchasi `override_reason` talab qiladi,
barchasi `AuditLog(action="override_*")` yozadi.

```
# Normalar (asosiy talab)
PUT    /admin/norms/{user_id}/{metric}     # HAR QANDAY qiymat, metrika cheklovisiz,
                                           # HAR QANDAY rolga (hr/rop/boss ham)
DELETE /admin/norms/{norm_id}              # bitta tarix yozuvini o'chirish
DELETE /admin/norms/{user_id}/{metric}     # metrikani BUTUNLAY tozalash
POST   /admin/norms/{user_id}/revert       # oldingi qiymatga qaytarish

# Universal yozuv boshqaruvi (bitta naqsh, ko'p jadval)
GET    /admin/records/{entity}             # ro'yxat (o'chirilganlar bilan)
PATCH  /admin/records/{entity}/{id}        # istalgan maydonni majburan tahrirlash
DELETE /admin/records/{entity}/{id}?hard=  # yumshoq (default) yoki qattiq
POST   /admin/records/{entity}/{id}/restore

  entity ∈ norm | attendance | excused_day | task | daily_result |
           mobilograf_video | work_schedule | overtime | salary_rate |
           payslip | payroll_adjustment | fine_policy | bonus | lead_event

# Payroll qulflari
POST   /admin/payroll/{period}/unlock      # tasdiqlangan davrni ochish
POST   /admin/payroll/{period}/force-recalculate
PATCH  /admin/payroll/{period}/user/{uid}  # tasdiqlangan varaqa summasini qo'lda tuzatish
DELETE /admin/payroll/{period}             # butun oy hisobini bekor qilish

# Tizim darajasi
POST   /admin/attendance/recalculate       # oraliq bo'yicha late_minutes'ni qayta hisoblash
                                           # (grace o'zgargandan keyin kerak bo'ladi)
POST   /admin/users/{id}/force-role        # rolni matritsasiz o'zgartirish
GET    /admin/audit/overrides              # faqat override_* amallar tarixi
```

`PATCH /admin/records/...` ni **oq ro'yxat** bilan yozish kerak: har bir
`entity` uchun ruxsat etilgan maydonlar lug'ati (`ALLOWED_FIELDS`). Aks holda
`id` yoki `user_id` ni tasodifan o'zgartirib bazaning bog'lanishini buzib
qo'yish mumkin — bu "kuch" emas, xato.

### 11.4 Mavjud kodga tegishli o'zgarishlar

| Fayl | O'zgarish |
|---|---|
| [norms.py:44](api/routers/norms.py:44) `can_manage_norms` | boshiga `if is_superadmin(actor): return True` — `target.role != employee` tekshiruvidan **oldin** |
| [norms.py:103](api/routers/norms.py:103) `_validate_metric` | `actor` argumenti qo'shiladi; dasturchi bo'lsa cheklov o'tkazib yuboriladi |
| [tasks.py:51](api/routers/tasks.py:51) matritsasi | xuddi shu qisqa yo'l |
| [excused_days.py:103](api/routers/excused_days.py:103) | dasturchi tasdiqlangan sababli kunni ham qayta hal qila oladi |
| `api/deps.py` | `require_dasturchi`, `is_superadmin` |
| `db/models.py` | 11.2/4-banddagi soft-delete ustunlari + migratsiya |

### 11.5 Interfeys

**Web** — `web/src/pages/AdminOverride.tsx` (`/admin`, faqat dasturchi):
- Yuqorida qizil banner: «⚠️ Dasturchi rejimi — bu yerdagi amallar cheklovsiz».
- Tumbler: **o'chiq holatda faqat ko'rish**, yoqilganda tahrir/o'chirish tugmalari.
- Jadval tanlash → yozuvlar ro'yxati (o'chirilganlari kulrang) → qator ustida
  [Tahrirlash] [O'chirish] [Tiklash].
- Har bir amalda **sabab so'raydigan dialog** (mavjud `ConfirmDialog` kengaytiriladi).
- Alohida tab: «Normalar» — xodim × metrika matritsasi, istalgan katakni
  bevosita tahrirlash yoki tozalash.
- Alohida tab: «Override tarixi» — kim, qachon, nimani, nima sababdan.

Boshqa sahifalarda (Norms, Attendance, Payroll) dasturchiga qo'shimcha qator
menyusi chiqadi: «O'chirish», «Majburan tahrirlash», «Qulfni ochish».

**Bot** — dasturchi uchun buyruqlar (`bot/handlers/admin_override.py`):
```
/norm_set <xodim> <metrika> <qiymat>   — cheklovsiz
/norm_del <xodim> <metrika>
/att_fix  <xodim> <sana> <kelgan_vaqt> — davomatni tuzatish
/unlock   <YYYY-MM>                    — payroll qulfini ochish
/undo     <id>                         — oxirgi o'chirilganni tiklash
```
Har biri sababni so'raydi (FSM, mavjud `fsm_storage` naqshi).

### 11.6 Xavfsizlik to'siqlari (kuchni yo'qotmasdan)

- Dasturchi **o'z rolini** o'zgartira oladi, lekin bu amal Boshliqqa darhol
  botga xabar bo'lib ketadi (`role_changed` + `override_*`).
- `DELETE /admin/payroll/{period}` va `hard=true` o'chirishlar — ikki bosqichli
  tasdiq (matn yozib tasdiqlash: davr nomini qo'lda terish).
- **Avtomatik zaxira**: `hard=true` o'chirishdan oldin yozuv JSON holida
  `AuditLog.before` ga to'liq ko'chiriladi — bazadan o'chsa ham auditda qoladi.
- `GET /admin/audit/overrides` Boshliqqa ham ochiq (dasturchi uni o'chira olmaydi
  — `AuditLog` `entity` oq ro'yxatiga kirmaydi).

### 11.7 Testlar (`test.py`)

- T-dasturchi metrikadan tashqari normani qo'ya oladi; T-HR qo'ya olmaydi (403).
- T-dasturchi ROP roliga norma qo'ya oladi.
- Normani o'chirish → `team_norms` da yo'qoladi; `restore` → qaytadi.
- Har bir override `AuditLog` da `override_*` bilan paydo bo'ladi va
  `override_reason` saqlanadi.
- `override_reason` siz so'rov → 422; boshqa rol → 403.
- `hard=true` o'chirishdan keyin `AuditLog.before` da to'liq yozuv nusxasi bor.
