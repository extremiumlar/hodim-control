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

### 1.1 Kechikish limiti va jarima — QAROR QILINDI (2026-07-27, 9-bo'lim javoblari)
- Har xodimga **oylik bepul kechikish limiti DAQIQADA** beriladi (masalan
  "oyiga jami 60 daqiqa bepul"). Kun soni bo'yicha limit ISHLATILMAYDI —
  faqat daqiqa yig'indisi kuzatiladi (`FinePolicy.free_late_minutes_per_month`).
- Limit (daqiqa) tugagandan keyin — **shundan keyingi HAR BIR kechikkan kun**
  uchun (kechikish necha daqiqa bo'lishidan qat'i nazar) qat'iy summa
  jarimalanadi. Summani **HR web saytdan kiritadi** (`fine_mode='per_day'`,
  `FinePolicy.fine_per_day`). Ya'ni ikki bosqichli qoida: limitgacha —
  jarimasiz; limitdan keyingi HAR bir kechikkan kun — bitta qat'iy summa
  (kechikish 6 daqiqa ham, 90 daqiqa ham bo'lsin — jarima bir xil).
  Limit qaysi kunda "tugaganini" aniqlash — 3-bo'limdagi
  "Limit xronologik yeyiladi" qoidasi bilan bir xil: oy boshidan kunma-kun
  yig'iladi, chegaradan **o'tkazgan** kunning o'zi hali bepul, undan keyingi
  har bir kechikkan kun jarimali.
- ⭐ `per_minute`/`tiered`/`percent_of_daily` rejimlari **kod darajasida
  qoldiriladi** (kengaytirish uchun `FinePolicy.fine_mode` enum'ida), lekin
  HR uchun default va asosiy ishlatiladigan rejim — yuqoridagi `per_day`.
- **Jarima qayerdan yechiladi** (`fine_applies_to`): **to'g'ridan-to'g'ri
  oylikdan** (`net_salary`) — QAROR. ⚠️ Huquqiy eslatma (8.4-bandga qarang):
  O'zbekiston mehnat qonunchiligida ish haqidan ushlab qolish cheklangan
  bo'lishi mumkin; bu qaror HR/yurist tomonidan tekshirilishi tavsiya
  etiladi. Tizim ikkala rejimni ham (`bonus_first`/`net_salary`) qo'llab-
  quvvatlaydi — HR istalgan vaqt `net_salary`dan `bonus_first`ga o'tkaza oladi.
- **Oylik jarima shifti (cap) — MAJBURIY**. Qiymatni (foiz yoki qat'iy summa)
  **HR web saytdan kiritadi** (`FinePolicy.monthly_cap_percent` yoki
  `monthly_cap_amount`) — tizimda qattiq kodlangan default (masalan 20%) YO'Q,
  HR har doim o'zi belgilashi shart (validatsiya: policy saqlanmasdan oldin
  ikkalasidan kamida bittasi to'ldirilgan bo'lishi kerak).
- **Sababli (approved `ExcusedDay`) kun jarimaga kirmaydi** va limit
  daqiqalarini yemaydi.
- **Kelmagan kun (`absent`)** — kunlik ish haqidan ULUSH EMAS, **HR web
  saytdan kiritgan QAT'IY SUMMA** (`FinePolicy.absent_fine`,
  `absent_mode='fixed'`). Kechikish jarimasidan alohida, mustaqil summa.
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

### 1.3 Qo'shimcha ish (overtime) — QAROR QILINDI
- Faqat **HR belgilagan xodimlarga** yoqiladi (`overtime_enabled`).
- Hisoblash rejimi (`overtime_mode`) — HR tanlaydi:
  - `derived` — xodimning **o'z oyligidan kelib chiqib**: soatlik stavka =
    oylik ÷ o'sha oydagi rejadagi ish soatlari (norma soati **ish
    jadvalidan avtomatik** — `WorkScheduleWeekly`/`Override`dan hisoblangan
    reja soatlar, QAROR). Koeffitsient (`OvertimeProfile.multiplier`) uchun
    **tizimda default YO'Q** — HR har xodim yoki lavozim uchun o'zi
    belgilaydi (1.0/1.5/2.0 yoki boshqa qiymat, majburiy maydon).
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
  fixed_rate_per_hour(12,2),
  # multiplier'da TIZIM DEFAULTI YO'Q (9-bo'lim, savol 6, QAROR) — HR har
  # xodim/lavozim uchun MAJBURIY kiritadi (`derived` rejimda NULL bo'lsa
  # saqlanmaydi, 422).
  multiplier(3,2),
  norm_hours_source(schedule|fixed)="schedule",  # QAROR: ish jadvalidan avtomatik
  fixed_norm_hours_per_month,
  min_minutes=15, daily_cap_minutes, monthly_cap_minutes,
  updated_by, updated_at

FinePolicy                 # jarima qoidasi (3 darajali)
  scope(global|position|user), scope_id(nullable),
  grace_minutes(nullable → global settings),
  # Limit FAQAT daqiqada (9-bo'lim, savol 1, QAROR) — free_late_days_per_month
  # KENGAYTIRISH uchun saqlanadi (kod tayyor bo'ladi), lekin HR uchun
  # ishlatiladigan yagona maydon free_late_minutes_per_month.
  free_late_days_per_month,  # ⭐ kelajakda, hozir ishlatilmaydi
  free_late_minutes_per_month,  # ← QAROR: asosiy maydon
  fine_mode(per_day|per_minute|tiered|percent_of_daily)="per_day",  # QAROR
  fine_per_day(12,2),  # ← QAROR: limitdan keyingi HAR kechikkan kunga qat'iy summa, HR kiritadi
  fine_per_minute(12,2), tiers(JSON), percent_of_daily(5,2),  # ⭐ kelajakda
  absent_mode(none|fixed|deduct_daily)="fixed",  # QAROR
  absent_fine(12,2),  # ← QAROR: HR kiritgan qat'iy summa (kelmagan kun)
  early_leave_enabled, early_leave_per_minute(12,2),
  # Cap MAJBURIY (9-bo'lim, savol 4, QAROR) — saqlashda ikkalasidan
  # kamida bittasi to'ldirilgan bo'lishi shart, qattiq default YO'Q.
  monthly_cap_percent(5,2), monthly_cap_amount(12,2),
  fine_applies_to(bonus_first|net_salary)="net_salary",  # QAROR (8.4-band, huquqiy eslatma)
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

Ruxsat — QAROR (9-bo'lim, savol 8): `PAYROLL_ROLES = (hr, rop, boss, dasturchi)`.
**ROP KO'RADI, lekin FAQAT O'Z JAMOASI uchun** — HR/Boss/Dasturchi hammani
ko'radi. Qamrov mavjud `norms.py::can_manage_norms` bilan bir xil naqsh
(`target.manager_id == actor.id` yoki lavozim `managed_by_roles`da "rop" bor):
- `GET /payroll/{period}` — ROP so'rasa, natija avtomatik uning jamoasiga
  filtrlanadi (boshqa xodimlar ro'yxatda umuman ko'rinmaydi, 403 emas —
  bo'sh/qisman ro'yxat).
- `GET /payroll/{period}/user/{user_id}` — ROP faqat o'z jamoasidagi
  `user_id` uchun 200 oladi, boshqasiga 403.
- Sozlamalar (`/payroll/policies`, `/payroll/rates`, `/payroll/overtime-profiles`,
  `/approve`, `/reopen`, `adjustments`) — ROP'da YO'Q, faqat HR/Boss/Dasturchi
  (stavka/qoida belgilash va tasdiqlash kadrlar qarori bo'lib qoladi).
- `PAYROLL_VIEW_ROLES = (hr, rop, boss, dasturchi)` (qamrov bilan) vs
  `PAYROLL_MANAGE_ROLES = (hr, boss, dasturchi)` (sozlash/tasdiqlash) — ikki
  alohida ro'yxat.

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
(`PAYROLL_VIEW_ROLES` ga ko'rinadi — ROP ham kiradi, lekin `PayrollSettings.tsx`
faqat `PAYROLL_MANAGE_ROLES`ga), `lib/api/endpoints.ts` + `lib/queries.ts`
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

### Bosqich 1 — ma'lumot modeli ✅ BAJARILDI (2026-07-27)
**Fayllar:** `db/models.py` (10 ta yangi enum + 8 ta jadval), `db/alembic/versions/88b50e2fbcb1_payroll_tables.py`
**Ish:** 2-bo'limdagi 8 ta jadval + indekslar. **Global `FinePolicy` seed
QILINMADI** (rejadagi dastlabki fikrdan farqli, ongli qaror): cap va
limit maydonlari MAJBURIY (9-bo'lim), bo'sh/taxminiy qiymatlar bilan qator
yaratish HRni "sozlangan" deb chalg'itardi. Buning o'rniga Bosqich 2dagi
`resolve_policy` qoidasi: **hech qanday `FinePolicy` topilmasa — jarima
UMUMAN QO'LLANMAYDI** (hisoblanadi, lekin 0). HR web orqali birinchi
`global` qoidani o'zi yaratmaguncha tizim "hammasi o'chiq" holatda qoladi —
xuddi talab qilingandek.
**DoD:** `alembic upgrade head` mavjud jonli `app.db`da sinaldi (yangidan
oldin zaxira olindi: `app.db.bak_2026-07-27_bosqich1_migration`); `downgrade
-1` barcha 8 jadvalni toza olib tashladi, qayta `upgrade head` tikladi;
real xizmatlarga qarshi `test.py` — **100 OK / 101** (o'sha bitta oldindan
mavjud FAIL, mantiqqa aloqasi yo'q).

### Bosqich 2 — hisoblash yadrosi (kodning yuragi) ✅ BAJARILDI (2026-07-27)
**Fayllar:** `api/services/payroll.py` (yangi, ~560 qator), `test.py`
(`test_payroll_engine`, 35 ta tekshiruv)

**Ish:** 3-bo'limdagi barcha funksiyalar yozildi: `resolve_policy` (3 daraja,
faqat faol qator ishtirok etadi, hech narsa topilmasa `None`), `resolve_rate`
+ `_first_rate` (tarixiy stavka), `month_schedule` (bitta so'rovda batch —
N+1 emas), `collect_attendance` (reja + `Attendance` + `ExcusedDay` — ikkala
manbadan `excused` aniqlanadi, chunki jonli check-in oqimi hali har doim
`status='excused'` yozmaydi), `compute_late_fine`/`compute_absent_fine`/
`apply_fine_cap`/`compute_base`/`compute_overtime`, orkestrator
`build_payslip` + `run_payroll` (idempotent upsert, `PayrollLocked`).

**Sinovdan o'tgan (barchasi T- xodimlar bilan, izolyatsiyalangan "2020-01"
davrida — jonli iyul 2026 ma'lumotiga tegmaydi):**
- Limit xronologik yeyiladi: chegaradan o'tkazgan kunning o'zi bepul (2 kun,
  jami 35 daq, limit 30), keyingi kun (10 daq) — jarimali.
- Sababli kun (`ExcusedDay`, yozuvsiz) to'g'ri aniqlanadi va limitni yemaydi.
- Kelmagan kun uchun qat'iy summa (Attendance yozuvsiz kun — defensiv
  "absent" filiali).
- Asosiy oylik (monthly, to'liq oy — prorata=1.0 holat).
- To'liq oqim: `run_payroll` → `Payslip` + 3 ta `PayslipItem` (base, fine_late,
  fine_absent) — summalar mos.
- **Idempotentlik**: 2 marta chaqirilganda bir xil `Payslip.id`, dublikat
  `PayslipItem` YO'Q, `net` o'zgarmaydi.
- **Qulf**: `locked=True` → `PayrollLocked` ko'tariladi.
- **Cap**: past cap qo'yilganda late+absent jarimasi PROPORSIONAL qisqaradi
  (ikkalasi ham 0 ga tushib qolmaydi).
- **Overtime**: `derived` (norma soati jadvaldan, × multiplier) va
  `fixed_rate` ikkalasi ham qo'lda hisoblangan summa bilan mos.
- **Avans/adjustment** (`minus`) qayta hisoblashda hisobga olinadi.
- **`resolve_policy` qamrovi**: xodim-qoida bor bo'lsa o'sha; yo'q va
  global bor bo'lsa globalga tushadi; umuman yo'q bo'lsa `None` — va
  `None`da jarima 0 (xavfsiz sukut, ataylab tekshirildi).
- Dam olish kuni jarimasiz — alohida test shart emas: `collect_attendance`
  tuzilishi bo'yicha `is_working=False` kunlar UNCONDITIONAL `status='weekend'`
  oladi (`Attendance.status`dan qat'i nazar), shuning uchun `late_days`
  ro'yxatiga umuman kirmaydi.

**⭐ Ma'lum cheklov (ataylab, ko'zi ochiq holda qoldirilgan):**
`fine_applies_to` (`bonus_first` vs `net_salary`) yakuniy `net` summasiga
TA'SIR QILMAYDI — matematik jihatdan bonusdan yechish yoki to'g'ridan-to'g'ri
oylikdan yechish bir xil natija beradi (`bonus - jarima` ayirmasi qaysi
"chelak"dan olinishidan qat'i nazar bir xil). Farq faqat QAYSI `PayslipItem`
kamayishida ko'rinadi (huquqiy/hisobot nuqtai nazaridan muhim bo'lishi
mumkin, 8.4-band). Hozircha `items` faqat `net_salary` ko'rinishida yig'iladi
(HR tanlagan QAROR default — 9-bo'lim); `bonus_first` ham to'g'ri `net`
beradi, lekin "avval bonusdan yechildi" item-darajasidagi ko'rinishi hali
qurilmagan — HR shu rejimni tanlasa Bosqich 3/4da qo'shiladi.

**DoD:** barcha T- testlar yashil (35/35); yadro DB'siz qismlari
(`compute_late_fine`, `compute_absent_fine`, `apply_fine_cap`, `compute_base`,
`round_money`) sof funksiyalar — DB'siz ham sinaladi; real xizmatlarga
qarshi to'liq `test.py`: **150 OK / 151** (yagona FAIL — oldindan mavjud
Windows konsol kodlash muammosi, mantiqqa aloqasi yo'q).

### Bosqich 3 — API ✅ BAJARILDI (2026-07-27)
**Fayllar:** `api/routers/payroll.py` (yangi), `api/schemas.py` (+~20 sxema),
`api/main.py` (router ro'yxatga olindi), `test.py` (`test_payroll_api`, 32
tekshiruv)

**Ish:** 4-bo'limdagi deyarli barcha endpointlar yozildi — sozlamalar
(`policies`, `rates`, `overtime-profiles`), qo'shimcha ish (`overtime` +
`decide`), hisob-kitob (`preflight`, `calculate`, `{period}` ro'yxat,
`{period}/user/{id}` tafsilot, `approve`, `periods`), qo'lda tuzatish
(`adjustments`), bot (`my`, `my/late-status`, `calculate-cron`).

**Ruxsat — `PAYROLL_VIEW_ROLES` (hr/rop/boss/dasturchi) vs
`PAYROLL_MANAGE_ROLES` (hr/boss/dasturchi)**, aynan 9-bo'lim savol 8
QARORIGA muvofiq: ROP payslip'larni ko'radi (`can_view_payroll` — `norms.py::
can_manage_norms` bilan bir xil qamrov naqshi: bevosita `manager_id` yoki
lavozimi "ROP boshqaradi"), lekin sozlash/tasdiqlash/hisoblashga huquqi YO'Q.

**Ataylab QILINMAGAN (rejaga muvofiq, keyingi bosqichlarga qoldirilgan):**
- `POST /payroll/{period}/reopen` — Bosqich 3.5 (Dasturchi rejimi,
  `admin_override.py`) ga tegishli, bu routerda YO'Q.
- `GET /payroll/{period}/export` (Excel) — Bosqich 7 (hisobot) ga qoldirildi.
- `preflight` reja qoralamasida POST deb yozilgan edi — GET qilib
  amalga oshirildi (ma'lumot o'zgartirmaydi, `/attendance/readiness` bilan
  bir xil qoida).

**Nozik texnik band:** `GET /payroll/periods` (literal) — bu route
`GET /payroll/{period}` catch-all'idan OLDIN ro'yxatdan o'tkazilishi SHART
edi (FastAPI'da bir xil segment sonli ikki route orasida tartib hal
qiluvchi) — kodda izoh bilan belgilangan.

**Test:** 32 ta HTTP-darajasidagi tekshiruv (`httpx`, real ishlayotgan API'ga
qarshi) — ruxsat matritsasi (xodim/ROP → sozlamalarga 403), validatsiya
(cap'siz policy → 422, multiplier'siz derived profil → 422, dublikat stavka
→ 400), to'liq oqim (hisoblash → ro'yxat → tafsilot → tasdiqlash → qulf →
qayta hisoblash 409), ROP qamrovi (o'z jamoasini ko'radi, begonaga 403),
bot endpointlari (tasdiqlanmagan payslip ko'rinmaydi, joriy oy live
late-status). Real xizmatlarga qarshi to'liq `test.py`: **186 OK / 187**
(yagona FAIL — oldindan mavjud Windows konsol kodlash muammosi).

**Ishlash jarayonida topilgan va tuzatilgan 2 ta xato:** `PayslipDetailOut`
sxemasida `base_amount` maydoni butunlay tushib qolgan edi (javobda doim
`null`); HTTP test sozlashida butun oy uchun Du-Ju jadval berilib, faqat
1 kunlik `Attendance` yozilgani sabab qolgan ~19 kun "kelmagan" deb
hisoblanib kutilmagan jarima chiqargan edi — bu aslida DVIZHOK to'g'ri
ishlagani (`collect_attendance`ning ataylab qilingan defensiv qoidasi),
test sozlashi Bosqich 2'dagi izolyatsiya naqshiga (faqat kerakli kunlarga
`WorkScheduleOverride`) moslashtirildi.

### Bosqich 3.5 — ⭐ Dasturchi rejimi (super-admin qatlami) ✅ BACKEND BAJARILDI (2026-07-27)
**Fayllar:** `api/deps.py` (`is_superadmin`, `require_dasturchi`),
`api/routers/admin_override.py` (yangi, ~450 qator), `api/routers/norms.py`,
`api/routers/tasks.py`, `api/routers/excused_days.py`, `api/routers/stats.py`,
`api/services/payroll.py`, `api/schemas.py` (+4 sxema), `api/main.py`,
`db/models.py` (`Norm`/`SalaryRate`ga soft-delete ustunlari),
`db/alembic/versions/26061eade58d_soft_delete_norm_salary_rate.py`, `test.py`
(`test_admin_override`, 33 tekshiruv)

**Ish — 11-bo'lim deyarli to'liq:**
- `is_superadmin`/`require_dasturchi` — yagona darvoza (11.2-band #1).
- Normalar (11.3-band, "asosiy talab"): `PUT/DELETE /admin/norms/{user_id}/
  {metric}`, `POST .../revert` — metrika/lavozim/rol cheklovisiz.
  `can_manage_norms`/`_validate_metric` (norms.py) va `_can_assign`/
  `_can_manage_existing_task` (tasks.py) endi `is_superadmin` orqali qisqa
  yo'l oladi — dasturchi HR/ROP/Boss'ga ham norma qo'ya oladi.
- `excused_days.py`: dasturchi tasdiqlangan/rad etilgan so'rovni
  `override_reason` bilan qayta hal qila oladi (oddiy HR/Boss — yo'q).
- Universal yozuv boshqaruvi: `GET/PATCH/DELETE/POST-restore
  /admin/records/{entity}/{id}` — 10 ta entity (norm, attendance,
  excused_day, task, daily_result, mobilograf_video, overtime, salary_rate,
  payroll_adjustment, fine_policy, bonus), har biri uchun `PATCH` oq
  ro'yxati bilan himoyalangan.
- Payroll qulflari: `unlock`, `force-recalculate`, `PATCH .../user/{uid}`
  (qo'lda summa tuzatish), `DELETE /admin/payroll/{period}` (butun oyni
  bekor qilish).
- Tizim darajasi: `POST /admin/attendance/recalculate` (sana oralig'i bo'yicha
  qayta hisoblash), `POST /admin/users/{id}/force-role`, `GET /admin/audit/
  overrides`.

**Yumshoq o'chirish (11.2-band #4)** — QARORDAN TORROQ qamrov: rejada 5 ta
jadval (`Payslip`, `SalaryRate`, `Attendance`, `OvertimeEntry`, `Norm`)
taklif qilingan edi, lekin ONGLI RAVISHDA faqat **`Norm` va `SalaryRate`**ga
qo'llandi — bular haqiqiy append-only tarixiy jadvallar ("xato yozuvni
tarixdan chiqarish" asosiy stsenariy). Qolganlari uchun mavjud mexanizmlar
yetarli: `Attendance` allaqachon Bosqich 0'dan qattiq o'chirishga ega
(semantikasini o'zgartirish xavfli bo'lardi); `OvertimeEntry`da `status`
maydoni bor (rad etish = bekor qilish); `Payslip` esa `run_payroll` orqali
QAYTA HISOBLANADI (upsert), "o'chirish" tabiiy ravishda butun davr darajasida
(`DELETE /admin/payroll/{period}`), bitta yozuv emas.

**Ishlash jarayonida topilgan va tuzatilgan muammolar:**
1. SQLite `batch_alter_table` FK ustunli yangi qatorga NOM talab qiladi —
   migratsiyada `sa.ForeignKey(..., name=...)` bilan tuzatildi.
2. `_row_to_dict()` xom `date`/`datetime`/`Decimal` qiymatlarni
   `AuditLog.before/after` (JSON ustun)ga yozganda SQLAlchemy oddiy
   `json.dumps` bilan 500 berardi — `_json_safe()` bilan oldindan ISO
   satr/floatga o'girildi.
3. **Test infratuzilmasi zaifligi** (mening kodimga aloqasi yo'q, lekin
   ochilgan): `AuditLog.actor_id` (Dasturchi override amallarida) tozalash
   bloklaridan tushib qolgan edi — faqat `target_user_id` tozalanardi. SQLite
   ROWID o'chirilgan id'larni qayta berishi bilan birga, bu keyingi test
   ishga tushirishda FK xatosi bilan yashirin xato zanjiriga olib kelardi.
   `test_payroll_engine`, `test_payroll_api`, `test_admin_override`ning
   barcha tozalash bloklariga `actor_id` ham qo'shildi.

**⭐ Ataylab QILINMAGAN (Bosqich 4/5ga qoldirilgan, rejadagi 11.5-band):**
- `web/src/pages/AdminOverride.tsx` — "Dasturchi rejimi" sahifasi (banner,
  tumbler, yozuvlar jadvali, tarix tab). Bosqich 4 (Web panel) qismida.
- `bot/handlers/admin_override.py` — `/norm_set`, `/att_fix`, `/unlock`,
  `/undo` buyruqlari. Bosqich 5 (Bot) qismida.
- Boshqa sahifalarga (Norms, Attendance, Payroll) "Dasturchi" qo'shimcha
  menyusi — Bosqich 4 bilan birga.

**DoD:** dasturchi istalgan normani (hatto HR/ROP/Boss'ga, hatto lavozimga
mos kelmagan metrikada) o'zgartira/o'chira/tiklay oladi; har bir override
majburiy sabab (`override_reason`, min 5 belgi, yo'q bo'lsa 422) bilan
`AuditLog(action="override_*")` ga tushadi; boshqa rollar (HR/Boss/ROP/xodim)
BARCHA `/admin/*` endpointlariga 403 oladi. 33 ta HTTP test + real
xizmatlarga qarshi to'liq `test.py`: **217 OK / 218** (yagona FAIL —
oldindan mavjud Windows konsol kodlash muammosi), ikki marta ketma-ket
ishga tushirilib barqarorlik tasdiqlandi.

### Bosqich 4 — Web panel ✅ BAJARILDI (2026-07-27)
**Fayllar:** `web/src/pages/Payroll.tsx`, `PayrollSettings.tsx`, `Overtime.tsx`
(yangi), `EmployeeProfile.tsx`, `CheckIn.tsx`, `App.tsx`, `Layout.tsx`,
`components/StatusBadge.tsx`, `lib/api/endpoints.ts`, `lib/api/types.ts`,
`lib/queries.ts`, `api/routers/payroll.py` (`GET /payroll/me/late-status` —
JWT versiyasi CheckIn uchun qo'shildi, avvalgisi faqat bot-secret edi)

**Ish:**
- `Payroll.tsx` (`/payroll`, PAYROLL_VIEW_ROLES — ROP ham kiradi): oy
  tanlagich, tayyorlik ogohlantirishi (`PreflightSection`, faqat MANAGE),
  jami statistikalar, payslip jadvali, qatorni bosib tafsilot dialogi
  (qatorlar + kunma-kun statistika), «Hisoblash»/«Tasdiqlash» tugmalari
  (faqat MANAGE, ROP ko'rmaydi).
- `PayrollSettings.tsx` (`/payroll/settings`, faqat MANAGE): 3 tab — Jarima
  qoidasi (global/lavozim/xodim qamrov, cap validatsiyasi), Oylik stavkalar
  (xodim tanlash + tarix + yangi stavka), Qo'shimcha ish (profil ro'yxati +
  yoqish/tahrirlash dialogi).
- `Overtime.tsx` (`/overtime`, faqat MANAGE): holat filtri, tasdiqlash
  navbati, qo'lda kiritish dialogi.
- `EmployeeProfile.tsx`: "Oylik (ish haqi)" bo'limi — davrlar ro'yxati,
  har biri bosilganda O'SHA davr tafsiloti so'raladi (Bonus tarixi bilan
  bir xil "kengaytiriladigan qator" naqshi — bitta xodim uchun "barcha
  davrlar" backend endpointi yo'q, shuning uchun N so'rov o'rniga lazy-fetch).
- `CheckIn.tsx`: `LateStatusCard` — joriy oy kechikish limiti holati (1.5-band,
  Shaffoflik). Qoida sozlanmagan bo'lsa (`free_limit_minutes=null`) HECH
  NARSA ko'rsatilmaydi.
- ROP kirish cheklovi ikki darajada: `Layout.tsx`da `onlyPayrollManager`
  nav filtri (Overtime/Settings ko'rinmaydi) + `App.tsx`da
  `PayrollManageRoute` (to'g'ridan-to'g'ri URL kiritsa ham `/payroll`ga
  qaytaradi).

**⭐ Ataylab QILINMAGAN:** Excel yuklab olish tugmasi — Bosqich 3'da
`/export` ATAYLAB Bosqich 7ga (hisobot) qoldirilgan edi, DoD'dagi "Excel
oladi" shu sababli hozircha yo'q (izchillik uchun reja matni ham
moslashtirildi).

**Tekshiruv — real xizmatlarga qarshi brauzerda (HTTPS+self-signed sert
avtomatlashtirilgan brauzerda ishlamagani uchun `VITE_NO_SSL=1` bilan
vaqtinchalik alohida portda ishga tushirilib, keyin to'xtatildi):**
`tsc --noEmit` toza; HR (`hr`) sifatida `/payroll` — real preflight
ma'lumoti (stavkasiz/jadvalsiz/yuzsiz xodimlar) to'g'ri ko'rsatildi;
`/payroll/settings` — «Yangi qoida» dialogi barcha maydonlar bilan to'liq
render bo'ldi; `/overtime` — bo'sh holat to'g'ri; `/employees/{id}` — "Oylik"
bo'limi to'g'ri; xodim sifatida `/check-in` — jarima qoidasi hali
sozlanmagani uchun `LateStatusCard` to'g'ri KO'RINMADI; ROP sifatida
`/payroll` — faqat ko'rish (Hisoblash/Tasdiqlash yo'q), nav'da
Overtime/Settings yo'q, to'g'ridan-to'g'ri `/payroll/settings`ga kirish
`/payroll`ga qaytardi. Hech qanday real ma'lumot yaratilmadi/o'zgartirilmadi
(faqat o'qish so'rovlari) — jonli kompaniya ma'lumotlariga tegilmadi.

### Bosqich 5 — Bot ✅ BAJARILDI (2026-07-27)
**Fayllar:** `bot/handlers/payroll.py` (yangi), `bot/keyboards.py`,
`bot/setup.py` (routerlar shu yerda ro'yxatga olinadi, `bot/main.py` emas —
reja qoralamasidagi fayl ro'yxati bittasida noaniq edi), `bot/api_client.py`,
`api/schemas.py` (`POSITION_MENU_KEYS`ga `"payroll"`),
`web/src/pages/Positions.tsx` (yangi bayroqni HR sozlashi uchun)

**Ish:**
- `BTN_PAYROLL = "💵 Mening oyligim"` — Boshliqdan tashqari HAMMAGA
  (xodim + HR/ROP/Dasturchi ham, `PAYROLL_TRACKED_ROLES` bilan bir xil
  qamrov; oddiy `BTN_KPI` xodim-only naqshidan farqli, chunki rahbarlar ham
  payroll orqali maosh oladi).
- Xabar: oxirgi TASDIQLANGAN payslip (asosiy, overtime, bonus, jarima
  sababi bilan, jami) + shu xabar ostida inline **«🕐 Kechikishlarim»**
  tugmasi — bosilganda joriy (hali yakunlanmagan) oy uchun JONLI hisoblangan
  limit holati ko'rsatiladi (`GET /payroll/my/{tg_id}/late-status`).
- `Position.menu_flags.payroll` — tugma HR tomonidan pozitsiya darajasida
  yashirilishi mumkin (mavjud tasks/norm/kpi/excused naqshi bilan bir xil).
- HR/Boss "Payroll tayyor"/xodimga "tasdiqlandi" xabarlari — **YANGI KOD
  TALAB QILMADI**: Bosqich 3'da `api/routers/payroll.py`ning `calculate`/
  `approve` endpointlari ichida ALLAQACHON `send_message` chaqirilgan edi
  (DoD'dagi "HR tasdiq xabarini oladi" shu orqali avvaldan qondirilgan).

**⭐ Ataylab QILINMAGAN (Bosqich 6ga qoldirilgan):** proaktiv ogohlantirish
("limitdan 1 kun qolganda", "limit tugagan zahoti darhol xabar") — bular
PUSH (backend tomonidan o'zi boshlab yuboradigan) xabarlar, bot esa faqat
PULL (xodim so'raganda javob beradigan) qismni qamrab oladi. Reja bo'yicha
ham bu Bosqich 6ning "kechikish limiti ogohlantirish jobi (kunlik)" o'z
ichiga oladi — ikki marta qurmaslik uchun shu yerda YO'Q.

`BOT_BUYRUQLARI.md` YANGILANMADI — hujjat o'z ta'rifi bo'yicha faqat
slash-buyruqlarni ("/...") qamraydi, oddiy menyu tugmalari (mavjud
"💰 Oylik KPI'm" ham) u yerda yo'q — izchillik uchun yangi tugma ham
qo'shilmadi.

**DoD:** xodim (va HR/ROP/Dasturchi) o'z varaqasini ko'radi, faqat
tasdiqlangan bo'lsa; «Kechikishlarim» joriy oy holatini jonli ko'rsatadi;
HR "Payroll tayyor" va xodim "tasdiqlandi" xabarlarini oladi (Bosqich 3'dan
meros). Tekshirildi: `build_dispatcher()` 25 router bilan xatosiz
yig'ildi; `bot.api_client.my_payslip`/`my_payroll_late_status` real
API'ga qarshi to'g'ri javob qaytardi; `_payslip_text` formatlash sun'iy
ma'lumot bilan tasdiqlandi; `tsc` toza; real xizmatlarga qarshi to'liq
`test.py`: 208/209 OK.

### Bosqich 6 — avtomatika ✅ BAJARILDI (2026-07-27)
**Fayllar:** `api/services/payroll.py` (`previous_period`, `detect_overtime_candidates`,
`late_limit_event_for`, `_minute_of_day_local`), `api/routers/payroll.py`
(`POST /payroll/calculate-monthly`, `POST /payroll/late-warnings-tick`,
`POST /payroll/overtime/auto-detect` — barchasi bot-secret), `scheduler/jobs.py`,
`scheduler/main.py`, `scheduler/config.py`, `test.py` (`test_payroll_automation`,
21 tekshiruv). `.env.example` YANGILANMADI — yangi env o'zgaruvchisi qo'shilmadi
(barcha yangi sozlamalar `scheduler/config.py`da qattiq kodlangan
soat/daqiqa konstantalari, mavjud boshqa job'lar bilan bir xil naqsh).

**Ish:**
- `monthly_payroll` — keyingi oyning 1-kuni ertalab soat 06:00 (9-bo'lim,
  savol 10, QAROR; oylik bonus soat 23:30da va davomat yopilishi soat 22:00da
  allaqachon tugagan bo'ladi). Davr avtomatik "o'tgan oy" (`previous_period`) —
  scheduler o'zi sana hisoblamaydi, API'ning o'zi `today_local()`dan chiqarib
  oladi (`bonuses.py::calculate_monthly`ning "berilmasa joriy oy" naqshi bilan
  bir xil, faqat "o'tgan oy" — chunki bu job YANGI oyning 1-kunida ishlaydi).
  Muvaffaqiyatli hisoblansa HR/Boshliqqa xuddi qo'lda `calculate` bilan bir xil
  "Payroll tayyor" DM ketadi.
- Kechikish limiti ogohlantirishi (1.5-band) — kunlik, soat 07:30 (ish kuni
  boshlanishidan oldin). ⭐ **Muhim dizayn qarori**: alohida "allaqachon
  yuborilganmi" jadval/ustun QO'SHILMADI (ongli qaror — yangi migratsiya
  shart emas). Buning o'rniga `late_limit_event_for` HAR SAFAR
  `compute_late_fine`dan qaytadan hisoblab, FAQAT aniq berilgan sanaga
  ("kecha") tegishli voqeani aniqlaydi: (a) `near_limit` — bepul limitdan
  ≤15 daqiqa (`LATE_WARNING_BUFFER_MINUTES`) qolgan birinchi kun, (b)
  `limit_reached` — limitni birinchi marta OSHIRGAN kun. `compute_late_fine`
  qoidasi bo'yicha "chegaradan o'tkazgan kunning o'zi hali bepul" — ya'ni
  limitni TO'LDIRGAN kunning o'zi emas, undan KEYINGI kechikkan kun birinchi
  jarimali (shu injiqlik testda ikki marta xato natijaga olib keldi, pastda).
  Job kuniga bir marta ishlatilsa, bu hisoblash usuli tabiiy ravishda ikki
  marta ogohlantirmaydi — DB holatiga bog'liq emas.
- Qo'shimcha ish avtomatik aniqlash (1.3-band) — kunlik, soat 01:00 (kam
  trafik). `detect_overtime_candidates`: `OvertimeProfile.enabled=True`
  xodimlarning check-out vaqti rejadagi tugash vaqtidan (`min_minutes`dan
  ko'p) keyin bo'lsa — `OvertimeEntry(source='auto_attendance', status='pending')`
  yaratadi (model docstringida oldindan e'lon qilingan qiymat, Bosqich 1'dan
  buyon kutilgan). Tasdiqsiz pul hisoblanmaydi — HR/rahbar mavjud
  `Overtime.tsx` navbatida ko'rib tasdiqlaydi/rad etadi (Bosqich 4, yangi
  UI SHART EMAS). ⭐ **Ma'lum cheklov**: yarim tundan oshgan (tungi) smenalar
  hisobga olinmaydi (xavfsiz tomonga og'adi — nomzod o'tkazib yuboriladi,
  noto'g'ri katta summa YARATILMAYDI) — to'liq yechim kelajakka qoldirilgan.
- Ikkala kunlik job ham (`late-warnings-tick`, `overtime/auto-detect`) va
  `calculate-monthly` ixtiyoriy sana/davr parametri qabul qiladi (berilmasa
  mos ravishda "kecha"/"o'tgan oy") — bu HAM scheduler uchun, HAM qo'lda
  orqaga to'ldirish (backfill) uchun ishlatiladi, HAM AYNAN shu tufayli
  test.py xavfsiz: real "bugun/kecha" o'rniga uzoq o'tmishdagi izolyatsiyalangan
  sanalar bilan chaqirilib, REAL xodimlarga tasodifiy xabar/yozuv ketishining
  oldi olindi (2026-07-27dagi "test.py botdan xabar yuborяpti" muammosi bilan
  bir xil sinf xato — bu safar OLDINDAN hisobga olindi).
- `[LABEL FAILED]`/`[LABEL OK]` log-prefiks naqshi (`monthly_bonus` bilan bir
  xil) — DoD'dagi "job muvaffaqiyatsiz bo'lsa log + rahbarlarga xabar" shu
  orqali qondirildi; bu repoda alohida "job xatosi haqida Telegram xabari"
  tizimi hech qachon bo'lmagan — `call_api`ning o'zi xatoni log qiladi,
  distinktiv prefiks esa grep qilishni osonlashtiradi (mavjud naqsh, YANGI
  ixtiro emas).

**Test:** `test_payroll_automation` — izolyatsiyalangan davr "2020-03".
To'g'ridan-to'g'ri servis chaqiruvlari (`detect_overtime_candidates`
idempotentligi + ish oynasi ichidagi check-out filtri; `late_limit_event_for`
5 kunlik ssenariy: near_limit → (jimlik) → limit_reached → (jimlik,
allaqachon boshlangan) → kechikmagan; `previous_period` yil chegarasi) VA
HTTP darajasida (bot-secretsiz → 401; barcha 3 endpoint aniq
sana/davr bilan → 200, natija to'g'ri). Xizmatlar qayta ishga tushirilib
(`schtasks /run /tn "HodimlarTizimi_StartAll"` — foydalanuvchi roziligi
bilan, chunki real xodimlarga bir necha soniyalik uzilish beradi), yangi
route'lar jonli serverda tasdiqlandi. Natija: **232 OK / 233** (yagona FAIL —
oldindan mavjud "2.2 avtomatik yopish tekshiruvi", Windows konsol kodlash
xatosi, mantiqqa aloqasi yo'q).

**Bajarilgan deb hisoblanadi:** oylik ish haqi HR aralashuvisiz keyingi oy
1-kunida hisoblanadi (HR baribir tasdiqlashi kerak — pul tasdig'i qo'lda
qoladi, ongli qaror); xodim limitga yaqinlashganda va limit tugaganda botdan
avtomatik xabar oladi; overtime-yoqilgan xodimlarning kechki qolishlari
HR/rahbar ko'rib chiqishi uchun avtomatik navbatga tushadi.

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
   "jarima" sifatida ushlab qolish cheklangan. Egasi qarori (2026-07-27,
   9-bo'lim savol 3) bilan `fine_applies_to = net_salary` (to'g'ridan-to'g'ri
   oylikdan) tanlandi. Tizim `bonus_first` rejimini ham qo'llab-quvvatlaydi —
   HR istalgan vaqt o'zgartira oladi; tanlov `AuditLog`ga yoziladi. **Ijro
   qilishdan oldin HR/yurist bilan tasdiqlash tavsiya etiladi** — bu kod
   darajasidagi huquqiy maslahat emas.
5. **Yaxlitlash** — bitta joyda (`payroll.round_money`), default 100 so'mgacha.
6. **Maxfiylik** — summalar `PAYROLL_VIEW_ROLES`ga (HR/ROP/Boss/Dasturchi),
   ROP faqat o'z jamoasini ko'radi (yuqoridagi 4-bo'lim); botda faqat o'ziga;
   guruh digestiga xodim summasi **hech qachon** chiqmaydi.
7. **Qayta hisoblash** — `approved` davr uchun faqat `reopen` dan keyin,
   sabab bilan, auditga yozilib.

---

## 9. HR/egasidan kerakli qarorlar — QARORLAR QILINDI (2026-07-27)

Hammasi egasi bilan bevosita muhokama qilinib, javob berilgan. Kod bu
qarorlarga muvofiq yoziladi (yuqoridagi 1.1/1.3/4-bo'limlarga singdirildi).

| # | Savol | QAROR |
|---|---|---|
| 1 | Limit **kun** bo'yicha, **daqiqa** bo'yicha yoki ikkalasi? | **Daqiqa bo'yicha.** Limit tugagach, keyingi HAR bir kechikkan kun uchun HR web saytda belgilagan qat'iy summa jarima yoziladi (1+2-savol birlashtirilgan qaror). |
| 2 | Jarima rejimi? | `per_day` — limitdan keyingi har kechikkan kunga qat'iy summa (yuqoriga qarang). |
| 3 | Jarima qayerdan yechiladi? | **To'g'ridan-to'g'ri oylikdan** (`net_salary`). ⚠️ Huquqiy tekshiruv tavsiya etiladi (8.4-band). |
| 4 | Oylik jarima chegarasi? | **Majburiy**, lekin qiymati qattiq kodlanmaydi — **HR web saytdan kiritadi**. |
| 5 | Sababsiz kelmagan kun? | Kunlik ulush EMAS — **HR web saytdan kiritgan qat'iy summa** (`absent_fine`). |
| 6 | Qo'shimcha ish koeffitsienti (`derived` rejim)? | Tizimda default YO'Q — **HR har xodim/lavozim uchun o'zi belgilaydi** (majburiy maydon). |
| 7 | Qo'shimcha ish norma soati manbai? | Ish jadvalidan avtomatik (tasdiqlandi). |
| 8 | ROP oylik summalarni ko'radimi? | **Ha — lekin faqat o'z jamoasi uchun** (`can_manage_norms` bilan bir xil qamrov naqshi). Sozlash/tasdiqlash huquqi hamon YO'Q. |
| 9 | Avans (oy o'rtasi to'lovi) bormi? | Bor — HR qo'lda kiritadi, `PayrollAdjustment(minus)` orqali (tasdiqlandi). |
| 10 | Oyning qaysi kuni yopiladi? | Keyingi oyning 1-kuni ertalab (tasdiqlandi). |

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
